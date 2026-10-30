"""Small user settings shared by the page's backend and the MCP server (separate processes).

The page writes them; the MCP server re-reads them on every call, so a change in the page takes effect
immediately, without restarting Claude Code.
"""
import json
import os
from pathlib import Path

DEFAULTS = {"context": {"enabled": False, "location": "builtin", "path": ""}}


def default_path() -> Path:
    return Path.home() / ".onedrive-sorter" / "config.json"


def load(path=None) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))                       # deep copy
    try:
        data = json.loads(Path(path or default_path()).read_text(encoding="utf-8"))
        ctx = data.get("context", {})
        if isinstance(ctx.get("enabled"), bool):
            cfg["context"]["enabled"] = ctx["enabled"]
        if ctx.get("location") in ("builtin", "custom"):
            cfg["context"]["location"] = ctx["location"]
        if isinstance(ctx.get("path"), str):
            cfg["context"]["path"] = ctx["path"][:1024]
    except (OSError, ValueError, AttributeError):
        pass                                                     # missing or damaged file: use defaults
    return cfg


def save(cfg: dict, path=None) -> None:
    target = Path(path or default_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.replace(tmp, target)                                      # never leave a half-written file
