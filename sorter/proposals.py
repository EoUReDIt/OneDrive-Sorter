"""Plans that Claude proposes (through the MCP server) and that the human applies (in the page).

The two programs are separate processes, so they share a plain folder of files: one CSV per
proposal plus a small JSON note beside it. Proposing writes a file; it never touches the sorted folder.
"""
import json
import re
from datetime import datetime
from pathlib import Path

NAME = re.compile(r"^proposal_[0-9_]+\.csv$")
MAX_CSV = 1_000_000
MAX_ROWS = 5000


def default_dir() -> Path:
    return Path.home() / ".onedrive-sorter" / "proposals"


def clean(text: str, limit: int) -> str:
    """Notes come from an AI and are untrusted: drop control characters and cap the length."""
    return "".join(c if ord(c) >= 32 and ord(c) != 127 else " " for c in str(text))[:limit].strip()


def save(csv_text: str, note: str, summary: dict, proposals_dir) -> str:
    d = Path(proposals_dir)
    d.mkdir(parents=True, exist_ok=True)
    name = f"proposal_{datetime.now():%Y%m%d_%H%M%S_%f}.csv"
    (d / name).write_text(csv_text, encoding="utf-8", newline="")
    meta = {"note": clean(note, 500), "created": datetime.now().isoformat(timespec="seconds"), "summary": summary}
    (d / name.replace(".csv", ".json")).write_text(json.dumps(meta), encoding="utf-8")
    return name


def _meta(d: Path, name: str) -> dict:
    try:
        return json.loads((d / name.replace(".csv", ".json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"note": "", "created": "", "summary": {}}


def list_all(proposals_dir) -> list[dict]:
    d = Path(proposals_dir)
    if not d.is_dir():
        return []
    names = sorted((p.name for p in d.iterdir() if NAME.match(p.name)), reverse=True)
    return [{"name": n, **_meta(d, n)} for n in names]


def read(proposals_dir, name) -> tuple[str, dict]:
    if not isinstance(name, str) or not NAME.match(name):
        raise ValueError("invalid proposal name")
    d = Path(proposals_dir)
    path = d / name
    if not path.is_file():
        raise FileNotFoundError("no such proposal")
    return path.read_text(encoding="utf-8"), _meta(d, name)
