"""Local backend: exposes the engine to the browser page over HTTP on this computer only.

Why each protection exists (a web server on localhost is reachable by every web page you open):
  * binds to a loopback address only, so other computers cannot connect
  * every /api/ call needs a random per-run token in an Authorization header; a custom header also
    forces browsers to send a preflight request, and we never answer one, so other sites are blocked
  * the Host header must be our own address (defeats DNS-rebinding) and any Origin must be our own
  * the folder being sorted is fixed when the server starts; the page cannot choose another one
  * no delete, no overwrite, no general file serving: only the engine's checked moves, and one page
"""
import hmac
import json
import re
import secrets
import threading
import traceback
from importlib import resources
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__, config, context, engine, proposals
from .manifest import ManifestError, parse_manifest
from .rules import REQUIRED_COLUMNS, RULES

MAX_BODY = 5 * 1024 * 1024
PAGE = resources.files(__package__).joinpath("web", "index.html")
LOG_NAME = re.compile(r"^moves_[0-9_]+\.jsonl$")
LOOPBACK = ("127.0.0.1", "localhost")


class HttpError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def item_json(it):
    return {"n": it.row.n, "state": it.state, "detail": it.detail,
            "source": it.row.source, "dest_folder": it.row.dest_folder}


def row_json(r):
    return {"n": r.n, "fields": r.fields, "problems": r.problems, "selected": r.selected,
            "source": r.source, "dest_folder": r.dest_folder}


class Job:
    """One execute run, worked on in a background thread and polled by the page."""

    def __init__(self, total):
        self.status, self.total, self.error = "running", total, ""
        self.moved = self.failed = 0
        self.events, self.log_name = [], ""
        self.resume = threading.Event()
        self.resume.set()
        self.stop = False

    def record(self, kind, it):
        if kind == engine.MOVED:
            self.moved += 1
        else:
            self.failed += 1
        self.events.append({"n": it.row.n, "state": kind, "detail": it.detail, "source": it.row.source})

    def before_each(self):
        self.resume.wait()
        return not self.stop

    def snapshot(self):
        return {"status": "paused" if self.status == "running" and not self.resume.is_set() else self.status,
                "total": self.total, "moved": self.moved, "failed": self.failed,
                "events": self.events[-500:], "log": self.log_name, "error": self.error}


class State:
    def __init__(self, root, log_dir, token, proposals_dir=None, config_path=None):
        self.config_path = config_path
        self.root = engine.open_root(root)
        self.proposals_dir = Path(proposals_dir) if proposals_dir else proposals.default_dir()
        self.log_dir = Path(log_dir) if log_dir else Path.home() / ".onedrive-sorter" / "logs"
        self.token = token
        self.rows, self.job = [], None
        self.lock = threading.Lock()

    def _busy(self):
        return self.job is not None and self.job.status == "running"

    def _select(self, numbers):
        wanted = set(numbers)
        for r in self.rows:
            r.selected = r.n in wanted

    def load(self, csv_text):
        with self.lock:
            self.rows = parse_manifest(csv_text)
            return [row_json(r) for r in self.rows]

    def context_state(self):
        return context.state(config.load(self.config_path), self.root)

    def set_context(self, data):
        enabled, location, path = data.get("enabled"), data.get("location", "builtin"), data.get("path", "")
        if not isinstance(enabled, bool) or location not in ("builtin", "custom") or not isinstance(path, str) or len(path) > 1024:
            raise HttpError(400, "enabled must be true/false, location 'builtin' or 'custom', path text")
        cfg = config.load(self.config_path)
        cfg["context"] = {"enabled": enabled, "location": location, "path": path.strip()}
        if enabled:
            _, problem = context.resolve(cfg)
            if problem:
                raise HttpError(400, problem)                    # nothing is saved if the choice is unusable
        with self.lock:
            config.save(cfg, self.config_path)
        return self.context_state()

    def load_proposal(self, name):
        try:
            text, meta = proposals.read(self.proposals_dir, name)
        except ValueError:
            raise HttpError(400, "invalid proposal name")
        except FileNotFoundError:
            raise HttpError(404, "no such proposal")
        return self.load(text), meta.get("note", "")

    def check(self, numbers):
        with self.lock:
            self._select(numbers)
            return [item_json(i) for i in engine.check(self.rows, self.root)]

    def start(self, numbers, delay):
        with self.lock:
            if self._busy():
                raise HttpError(409, "a run is already in progress")
            self._select(numbers)
            ready = [i for i in engine.check(self.rows, self.root) if i.state == engine.READY]
            job = self.job = Job(len(ready))

        def work():
            try:
                rep = engine.execute(ready, self.root, log_dir=self.log_dir, delay=delay,
                                     on_event=job.record, before_each=job.before_each)
                job.log_name = rep.log_path.name
                job.status = "stopped" if job.stop else "done"
            except Exception as e:                      # surfaced to the page, not swallowed
                job.status, job.error = "error", str(e)

        threading.Thread(target=work, daemon=True).start()
        return job.snapshot()

    def undo(self, log_name, delay):
        if not isinstance(log_name, str) or not LOG_NAME.match(log_name):
            raise HttpError(400, "invalid log name")
        path = self.log_dir / log_name
        if not path.is_file():
            raise HttpError(404, "no such log")
        with self.lock:
            if self._busy():
                raise HttpError(409, "a run is in progress")
            rep = engine.undo(path, self.root, delay=delay)
        return {"moved": len(rep.moved),
                "failed": [{"source": i.dst.name, "detail": i.detail} for i in rep.failed]}

    def logs(self):
        if not self.log_dir.is_dir():
            return []
        return sorted((p.name for p in self.log_dir.iterdir() if LOG_NAME.match(p.name)), reverse=True)


def _delay(value):
    try:
        return min(max(float(value), 0.0), 30.0)
    except (TypeError, ValueError):
        raise HttpError(400, "delay must be a number")


class Handler(BaseHTTPRequestHandler):
    server_version = "sorter"

    def log_message(self, fmt, *args):          # keep the console quiet; tokens never reach logs
        pass

    # ---- plumbing -------------------------------------------------------------------------
    def _send(self, status, body, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype != "application/octet-stream" else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj).encode())

    def _origins(self):
        port = self.server.server_address[1]
        return {f"http://127.0.0.1:{port}", f"http://localhost:{port}", f"http://[::1]:{port}"}

    def _check_host_and_origin(self):
        host = self.headers.get("Host", "")
        if host not in {o[len("http://"):] for o in self._origins()}:
            raise HttpError(403, "bad Host header")
        origin = self.headers.get("Origin")
        if origin is not None and origin not in self._origins():
            raise HttpError(403, "bad Origin")

    def _check_token(self):
        given = self.headers.get("Authorization", "")
        if not hmac.compare_digest(given.encode(), ("Bearer " + self.server.state.token).encode()):
            raise HttpError(401, "missing or wrong token")

    def _body(self):
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            raise HttpError(415, "send application/json")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise HttpError(411, "Content-Length required")
        if length < 0 or length > MAX_BODY:
            raise HttpError(413, "request too large")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HttpError(400, "invalid JSON")
        if not isinstance(data, dict):
            raise HttpError(400, "expected a JSON object")
        return data

    def _numbers(self, data):
        nums = data.get("selected", [])
        if not isinstance(nums, list) or not all(isinstance(n, int) and not isinstance(n, bool) for n in nums):
            raise HttpError(400, "selected must be a list of row numbers")
        return nums

    def _dispatch(self, method):
        try:
            self._check_host_and_origin()
            path = urlsplit(self.path).path
            if method == "GET" and path in ("/", "/index.html"):
                return self._send(200, PAGE.read_bytes(), "text/html")
            if not path.startswith("/api/"):
                raise HttpError(404, "not found")
            self._check_token()
            st = self.server.state
            if method == "GET":
                if path == "/api/info":
                    return self._json(200, {"mode": "local", "root": str(st.root), "version": __version__,
                                            "rules": RULES, "required_columns": REQUIRED_COLUMNS})
                if path == "/api/job":
                    return self._json(200, st.job.snapshot() if st.job else {"status": "idle"})
                if path == "/api/logs":
                    return self._json(200, {"logs": st.logs()})
                if path == "/api/context":
                    return self._json(200, st.context_state())
                if path == "/api/proposals":
                    return self._json(200, {"proposals": proposals.list_all(st.proposals_dir)})
                raise HttpError(404, "not found")
            data = self._body()
            if path == "/api/manifest":
                text = data.get("csv")
                if not isinstance(text, str):
                    raise HttpError(400, "csv must be text")
                return self._json(200, {"rows": st.load(text)})
            if path == "/api/context":
                return self._json(200, st.set_context(data))
            if path == "/api/proposal":
                rows, note = st.load_proposal(data.get("name"))
                return self._json(200, {"rows": rows, "note": note})
            if path == "/api/check":
                return self._json(200, {"items": st.check(self._numbers(data))})
            if path == "/api/execute":
                return self._json(200, st.start(self._numbers(data), _delay(data.get("delay", 0.25))))
            if path in ("/api/job/pause", "/api/job/resume", "/api/job/stop"):
                job = st.job
                if job is None or job.status != "running":
                    raise HttpError(409, "no run in progress")
                if path.endswith("pause"):
                    job.resume.clear()
                elif path.endswith("resume"):
                    job.resume.set()
                else:
                    job.stop = True
                    job.resume.set()
                return self._json(200, job.snapshot())
            if path == "/api/undo":
                return self._json(200, st.undo(data.get("log"), _delay(data.get("delay", 0.25))))
            raise HttpError(404, "not found")
        except HttpError as e:
            self._json(e.status, {"error": e.message})
        except (ManifestError, engine.EngineError) as e:
            self._json(400, {"error": str(e)})
        except Exception:
            traceback.print_exc()
            self._json(500, {"error": "internal error"})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    # Anything else (including CORS preflight OPTIONS) is refused outright.
    def _refuse(self):
        self._json(405, {"error": "method not allowed"})

    do_OPTIONS = do_PUT = do_DELETE = do_PATCH = do_HEAD = _refuse


def make_server(root, log_dir=None, host="127.0.0.1", port=0, token=None, proposals_dir=None, config_path=None):
    if host not in LOOPBACK:
        raise ValueError("the backend only listens on a loopback address")
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    httpd.state = State(root, log_dir, token or secrets.token_urlsafe(32), proposals_dir, config_path)
    return httpd


def serve(root, port=8765, log_dir=None, proposals_dir=None, config_path=None):
    httpd = make_server(root, log_dir, port=port, proposals_dir=proposals_dir, config_path=config_path)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/#token={httpd.state.token}"
    print(f"Sorting: {httpd.state.root}\nOpen this address in your browser (it contains this run's token):\n{url}\n"
          "Press Ctrl+C to stop.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
