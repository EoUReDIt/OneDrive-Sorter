import http.client
import json
import threading
import time
from pathlib import Path

import pytest

from sorter import proposals
from sorter.server import MAX_BODY, make_server

FIXTURE = Path(__file__).parent / "fixtures" / "sample_manifest.csv"


@pytest.fixture
def srv(tmp_path):
    root = tmp_path / "OneDrive"
    root.mkdir()
    for name in ("Example Resume.pdf", "Employer Notes", "Clearance Form.pdf", "Course Deck.pptx"):
        (root / name).write_text("x")
    (root / "Interview Folder").mkdir()
    httpd = make_server(root, tmp_path / "logs", token="t0k", proposals_dir=tmp_path / "props")
    threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.02), daemon=True).start()
    httpd.root, httpd.port, httpd.props = root, httpd.server_address[1], tmp_path / "props"
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def raw(srv, method, path, body=None, headers=None, host=None, token="t0k"):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    c.putrequest(method, path, skip_host=True)
    c.putheader("Host", host or f"127.0.0.1:{srv.port}")
    hdrs = dict(headers or {})
    if token is not None:
        hdrs.setdefault("Authorization", "Bearer " + token)
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
        hdrs["Content-Length"] = str(len(data))
    for k, v in hdrs.items():
        c.putheader(k, v)
    c.endheaders(data)
    r = c.getresponse()
    payload = r.read()
    c.close()
    try:
        return r.status, json.loads(payload), r
    except ValueError:
        return r.status, payload, r


def load_fixture(srv):
    return raw(srv, "POST", "/api/manifest", {"csv": FIXTURE.read_text()})


def wait_done(srv):
    for _ in range(200):
        s, job, _ = raw(srv, "GET", "/api/job")
        if job["status"] in ("done", "stopped", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


# ---- the page and the guard rails ------------------------------------------------------------

def test_binds_to_loopback_only(srv):
    assert srv.server_address[0] == "127.0.0.1"
    with pytest.raises(ValueError):
        make_server(srv.root, host="0.0.0.0")


def test_page_is_served_without_a_token_and_nothing_else_is(srv):
    s, body, r = raw(srv, "GET", "/", token=None)
    assert s == 200 and b"OneDrive Sorter" in body
    assert r.getheader("X-Frame-Options") == "DENY"
    for path in ("/README.md", "/../index.html", "/sorter/engine.py", "/etc/passwd"):
        assert raw(srv, "GET", path, token=None)[0] == 404


def test_api_needs_the_right_token(srv):
    assert raw(srv, "GET", "/api/info", token=None)[0] == 401
    assert raw(srv, "GET", "/api/info", token="wrong")[0] == 401
    assert raw(srv, "GET", "/api/info", headers={"Authorization": "t0k"}, token=None)[0] == 401
    assert raw(srv, "GET", "/api/info")[0] == 200


def test_wrong_host_header_is_rejected(srv):
    assert raw(srv, "GET", "/api/info", host="evil.example")[0] == 403
    assert raw(srv, "GET", "/", host="evil.example:80", token=None)[0] == 403


def test_foreign_origin_is_rejected_even_with_the_token(srv):
    assert raw(srv, "GET", "/api/info", headers={"Origin": "https://evil.example"})[0] == 403
    assert raw(srv, "GET", "/api/info", headers={"Origin": f"http://127.0.0.1:{srv.port}"})[0] == 200


def test_preflight_and_other_methods_are_refused_with_no_cors_headers(srv):
    for method in ("OPTIONS", "PUT", "DELETE", "PATCH"):
        s, _, r = raw(srv, method, "/api/execute", headers={"Origin": "https://evil.example",
                                                           "Access-Control-Request-Method": "POST"})
        assert s == 405
        assert r.getheader("Access-Control-Allow-Origin") is None


def test_no_cors_headers_on_normal_responses(srv):
    _, _, r = raw(srv, "GET", "/api/info")
    assert r.getheader("Access-Control-Allow-Origin") is None


def test_body_limits_and_content_type(srv):
    assert raw(srv, "POST", "/api/check", b"{}", headers={"Content-Type": "text/plain"})[0] == 415
    assert raw(srv, "POST", "/api/check", b"{not json")[0] == 400
    assert raw(srv, "POST", "/api/check", b"[1,2]")[0] == 400
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    c.putrequest("POST", "/api/manifest")
    for k, v in {"Authorization": "Bearer t0k", "Content-Type": "application/json",
                 "Content-Length": str(MAX_BODY + 1)}.items():
        c.putheader(k, v)
    c.endheaders()
    assert c.getresponse().status == 413


def test_info_exposes_rules_and_root(srv):
    s, info, _ = raw(srv, "GET", "/api/info")
    assert s == 200 and info["mode"] == "local" and info["root"] == str(srv.state.root)
    assert "Career" in info["rules"]


# ---- the workflow --------------------------------------------------------------------------

def test_load_check_execute_and_undo(srv):
    s, data, _ = load_fixture(srv)
    rows = data["rows"]
    assert s == 200 and len(rows) == 5 and [r["selected"] for r in rows] == [True] * 4 + [False]

    s, data, _ = raw(srv, "POST", "/api/check", {"selected": [1, 2, 3, 4]})
    states = [i["state"] for i in data["items"]]
    assert states == ["ready"] * 4 + ["not selected"]
    assert not (srv.root / "Career").exists()                  # check is read-only

    s, job, _ = raw(srv, "POST", "/api/execute", {"selected": [1, 2, 3, 4], "delay": 0})
    assert s == 200
    job = wait_done(srv)
    assert job["status"] == "done" and job["moved"] == 4 and job["failed"] == 0
    assert (srv.root / "Career/Resume Workspace/Example Resume.pdf").exists()
    assert (srv.root / "Course Deck.pptx").exists()             # unselected row untouched

    s, logs, _ = raw(srv, "GET", "/api/logs")
    assert logs["logs"] == [job["log"]]
    s, res, _ = raw(srv, "POST", "/api/undo", {"log": job["log"], "delay": 0})
    assert s == 200 and res["moved"] == 4 and res["failed"] == []
    assert (srv.root / "Example Resume.pdf").exists()


def test_flagged_row_runs_only_when_the_user_selects_it(srv):
    load_fixture(srv)
    raw(srv, "POST", "/api/execute", {"selected": [5], "delay": 0})
    job = wait_done(srv)
    assert job["moved"] == 1
    assert (srv.root / "Academic/ARIN 350/Final Presentation/Course Deck.pptx").exists()


def test_server_rechecks_instead_of_trusting_the_page(srv):
    load_fixture(srv)
    (srv.root / "Career/Resume Workspace").mkdir(parents=True)
    (srv.root / "Career/Resume Workspace/Example Resume.pdf").write_text("OLD")
    raw(srv, "POST", "/api/execute", {"selected": [1], "delay": 0})
    job = wait_done(srv)
    assert job["moved"] == 0 and job["total"] == 0
    assert (srv.root / "Career/Resume Workspace/Example Resume.pdf").read_text() == "OLD"


def test_pause_resume_and_stop(srv):
    load_fixture(srv)
    raw(srv, "POST", "/api/execute", {"selected": [1, 2, 3, 4], "delay": 0.3})
    assert raw(srv, "POST", "/api/job/pause", {})[2].status == 200
    time.sleep(0.8)
    s, job, _ = raw(srv, "GET", "/api/job")
    assert job["status"] == "paused" and job["moved"] < 4
    assert raw(srv, "POST", "/api/execute", {"selected": [1], "delay": 0})[0] == 409    # one run at a time
    raw(srv, "POST", "/api/job/stop", {})
    job = wait_done(srv)
    assert job["status"] == "stopped" and job["moved"] < 4


def test_pause_without_a_run_is_a_conflict(srv):
    assert raw(srv, "POST", "/api/job/pause", {})[0] == 409


def test_bad_inputs_get_clean_errors(srv):
    assert raw(srv, "POST", "/api/manifest", {"csv": 5})[0] == 400
    assert raw(srv, "POST", "/api/manifest", {"csv": "a,b\n1,2\n"})[0] == 400          # missing columns
    assert raw(srv, "POST", "/api/check", {"selected": ["x"]})[0] == 400
    assert raw(srv, "POST", "/api/check", {"selected": [True]})[0] == 400
    assert raw(srv, "POST", "/api/execute", {"selected": [], "delay": "fast"})[0] == 400
    assert raw(srv, "GET", "/api/nope")[0] == 404
    assert raw(srv, "POST", "/api/nope", {})[0] == 404


@pytest.mark.parametrize("name", ["../../etc/passwd", "moves_1.jsonl/../../x", "other.jsonl", "", 5, None])
def test_undo_rejects_log_names_that_are_not_ours(srv, name):
    assert raw(srv, "POST", "/api/undo", {"log": name})[0] in (400, 404)


def test_undo_unknown_but_well_formed_log_is_404(srv):
    assert raw(srv, "POST", "/api/undo", {"log": "moves_20200101_000000_000000.jsonl"})[0] == 404


def test_path_escape_in_manifest_is_unsafe_even_if_selected(srv):
    csv = ("SourceFile,DestinationFolder,Category,SubCategory,Confidence,Status,MoveAction,Notes\n"
           "../outside.txt,Career/Interviews,,,,Verified,MOVE,\n")
    raw(srv, "POST", "/api/manifest", {"csv": csv})
    s, data, _ = raw(srv, "POST", "/api/check", {"selected": [1]})
    assert data["items"][0]["state"] == "unsafe path"


# ---- proposals from Claude -------------------------------------------------------------------

def test_proposals_list_load_and_apply(srv):
    assert raw(srv, "GET", "/api/proposals")[1] == {"proposals": []}
    name = proposals.save(FIXTURE.read_text(), "first pass <b>x</b>", {"ready": 4}, srv.props)
    s, data, _ = raw(srv, "GET", "/api/proposals")
    assert [p["name"] for p in data["proposals"]] == [name] and data["proposals"][0]["note"] == "first pass <b>x</b>"

    s, data, _ = raw(srv, "POST", "/api/proposal", {"name": name})
    assert s == 200 and len(data["rows"]) == 5 and data["note"] == "first pass <b>x</b>"
    assert not (srv.root / "Career").exists()                       # loading a proposal moves nothing

    raw(srv, "POST", "/api/execute", {"selected": [1, 2, 3, 4], "delay": 0})
    assert wait_done(srv)["moved"] == 4


@pytest.mark.parametrize("name", ["../x.csv", "proposal_x.csv", "moves_1.jsonl", "", None, 5])
def test_proposal_names_are_validated(srv, name):
    assert raw(srv, "POST", "/api/proposal", {"name": name})[0] == 400


def test_unknown_proposal_is_404(srv):
    assert raw(srv, "POST", "/api/proposal", {"name": "proposal_20200101_000000_000000.csv"})[0] == 404


def test_proposal_endpoints_need_the_token(srv):
    assert raw(srv, "GET", "/api/proposals", token=None)[0] == 401
    assert raw(srv, "POST", "/api/proposal", {"name": "x"}, token=None)[0] == 401
