"""Run from OUTSIDE the repository, inside a fresh environment that has the built wheel installed
(CI does this). Proves the installed package finds its rules, its page and its commands.
Usage: python package_smoke.py path/to/sample_manifest.csv"""
import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from importlib import resources
from pathlib import Path

manifest = sys.argv[1]
bindir = Path(sys.executable).parent                      # the environment's own scripts folder
exe = shutil.which("onedrive-sorter", path=str(bindir)) or shutil.which("onedrive-sorter")
assert exe, "the onedrive-sorter command is not installed"

assert json.loads(resources.files("sorter").joinpath("rules.json").read_text())["top_level"]["Career"]
assert b"OneDrive Sorter" in resources.files("sorter").joinpath("web", "index.html").read_bytes()
from sorter import context
assert {"README.md", "TESTING.md", "USAGE_FOR_AI.md"} <= {f["name"] for f in context.list_files(context.builtin_dir())}, \
    "the installed package is missing its bundled guides"
import sorter
assert "site-packages" in sorter.__file__ or "dist-packages" in sorter.__file__, sorter.__file__

root = Path(tempfile.mkdtemp()) / "OneDrive"
root.mkdir()
for n in ("Example Resume.pdf", "Employer Notes", "Clearance Form.pdf", "Course Deck.pptx"):
    (root / n).write_text("x")
(root / "Interview Folder").mkdir()

out = subprocess.run([exe, "check", manifest, "--root", str(root)], capture_output=True, text=True)
assert out.returncode == 0 and "4 of 5 row(s) ready" in out.stdout, out.stdout + out.stderr

server = subprocess.Popen([exe, "serve", "--root", str(root), "--port", "0"], stdout=subprocess.PIPE, text=True)
try:
    url = None
    for line in server.stdout:
        m = re.search(r"http://127\.0\.0\.1:\d+/#token=(\S+)", line)
        if m:
            url, token = m.group(0), m.group(1)
            break
    assert url, "serve did not print an address"
    base = url.split("#")[0]
    assert b"OneDrive Sorter" in urllib.request.urlopen(base).read()
    req = urllib.request.Request(base + "api/info", headers={"Authorization": "Bearer " + token})
    assert json.loads(urllib.request.urlopen(req).read())["root"] == str(root.resolve())
finally:
    server.terminate()

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def tools():
    async with stdio_client(StdioServerParameters(command=exe, args=["mcp", "--root", str(root)])) as s:
        async with ClientSession(s[0], s[1]) as session:
            await session.initialize()
            return {t.name for t in (await session.list_tools()).tools}

assert asyncio.run(asyncio.wait_for(tools(), 60)) == {"get_rules", "list_folder", "validate_manifest", "propose_plan", "list_context_files", "read_context_file"}
print("package smoke: OK")
