"""The whole chain, no mocks: Claude (MCP client) looks around and proposes; the human (HTTP API, as the
page does) loads the proposal, checks, executes and undoes. Only the human steps change the folder."""
import asyncio
import http.client
import json
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters          # noqa: E402
from mcp.client.stdio import stdio_client                      # noqa: E402

from sorter.server import make_server                          # noqa: E402

REPO = Path(__file__).resolve().parent.parent
HEADER = "SourceFile,DestinationFolder,Category,SubCategory,Confidence,Status,MoveAction,Notes\n"


def tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def api(httpd, method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": "Bearer tok", **({"Content-Type": "application/json"} if data else {})}
    c.request(method, path, data, headers)
    r = c.getresponse()
    return r.status, json.loads(r.read())


def claude_session(root, proposals_dir):
    """What Claude does: look at the folder, draft a manifest from what it saw, validate, propose."""
    async def main():
        params = StdioServerParameters(command=sys.executable, cwd=str(REPO),
                                       args=["-m", "sorter", "mcp", "--root", str(root), "--proposals-dir", str(proposals_dir)])
        async with stdio_client(params) as streams:
            async with ClientSession(streams[0], streams[1]) as s:
                await s.initialize()
                call = lambda n, a=None: s.call_tool(n, a or {})
                listing = json.loads((await call("list_folder")).content[0].text)
                dest = {"Resume": "Career/Resume Workspace", "Clearance": "Career/Security Clearance", "Notes": "Career/Employers/Acme"}
                rows = [f"{e['name']},{d},,,100,Verified,MOVE,"
                        for e in listing["entries"] for k, d in dest.items() if k in e["name"]]
                csv_text = HEADER + "\n".join(rows) + "\n"
                check = json.loads((await call("validate_manifest", {"csv_text": csv_text})).content[0].text)
                assert set(check["summary"]) == {"ready"}, check
                return json.loads((await call("propose_plan", {"csv_text": csv_text, "note": "end to end"})).content[0].text)
    return asyncio.run(asyncio.wait_for(main(), 60))


def test_propose_review_apply_and_undo(tmp_path):
    root = tmp_path / "OneDrive"
    root.mkdir()
    for n in ("Example Resume.pdf", "Clearance Form.pdf", "Employer Notes", "holiday.jpg"):
        (root / n).write_text("x")
    original = tree(root)
    pdir = tmp_path / "proposals"

    proposal = claude_session(root, pdir)
    assert proposal["nothing_moved"] is True
    assert tree(root) == original                                   # Claude changed nothing

    httpd = make_server(root, tmp_path / "logs", token="tok", proposals_dir=pdir)
    threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.02), daemon=True).start()
    try:
        _, listed = api(httpd, "GET", "/api/proposals")
        assert [p["name"] for p in listed["proposals"]] == [proposal["proposal"]]
        _, loaded = api(httpd, "POST", "/api/proposal", {"name": proposal["proposal"]})
        assert loaded["note"] == "end to end" and len(loaded["rows"]) == 3
        assert tree(root) == original                               # loading changed nothing

        picked = [r["n"] for r in loaded["rows"]]
        _, checked = api(httpd, "POST", "/api/check", {"selected": picked})
        assert [i["state"] for i in checked["items"]] == ["ready"] * 3
        assert tree(root) == original                               # checking changed nothing

        api(httpd, "POST", "/api/execute", {"selected": picked, "delay": 0})
        for _ in range(200):
            _, job = api(httpd, "GET", "/api/job")
            if job["status"] != "running":
                break
            time.sleep(0.05)
        assert job["status"] == "done" and job["moved"] == 3
        assert (root / "Career/Resume Workspace/Example Resume.pdf").exists() and (root / "holiday.jpg").exists()

        _, undone = api(httpd, "POST", "/api/undo", {"log": job["log"], "delay": 0})
        assert undone["moved"] == 3 and undone["failed"] == []
        assert [p for p in tree(root) if "." in Path(p).name or p == "Employer Notes"] == \
               [p for p in original]                                # every file is back where it started
    finally:
        httpd.shutdown()
        httpd.server_close()
