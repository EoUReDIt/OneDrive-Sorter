"""Check and apply a manifest against a local folder (for example the OneDrive sync folder).

Safety rules, enforced here and nowhere else:
  * everything stays inside the chosen root (no '..', no absolute paths, no symlink escapes)
  * moves only: nothing is deleted, overwritten or renamed
  * every move is logged before the next one starts, so a crash can still be undone
"""
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .manifest import Row

READY = "ready"
ALREADY_THERE = "already there"
NOT_FOUND = "source not found"
CONFLICT = "name conflict"
UNSAFE = "unsafe path"
NOT_SELECTED = "not selected"
MOVED = "moved"
FAILED = "failed"


class EngineError(Exception):
    pass


@dataclass
class PlanItem:
    row: Row
    state: str
    detail: str = ""
    src: Path | None = None
    dst: Path | None = None


@dataclass
class Report:
    moved: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    log_path: Path | None = None


def open_root(root) -> Path:
    real = Path(os.path.realpath(root))
    if not real.is_dir():
        raise EngineError(f"Root is not a folder: {root}")
    return real


def _segments(path: str) -> list[str]:
    """Split a relative manifest path and reject anything that could leave the root."""
    segs = [s for s in path.split("/") if s]
    for s in segs:
        if s in (".", "..") or "\\" in s or ":" in s or any(ord(c) < 32 for c in s):
            raise ValueError(f'unsafe path segment "{s}"')
    return segs


safe_segments = _segments


def _inside(root: Path, p) -> bool:
    real = os.path.realpath(p)
    try:
        return os.path.commonpath([os.path.normcase(str(root)), os.path.normcase(real)]) == os.path.normcase(str(root))
    except ValueError:                        # different drives on Windows
        return False


def _nearest_existing(p: Path) -> Path:
    while not os.path.lexists(p):
        p = p.parent
    return p


def check(rows: list[Row], root) -> list[PlanItem]:
    """Read-only dry run: decide what would happen to each row."""
    root = open_root(root)
    items, planned = [], set()
    for row in rows:
        if not row.selected:
            items.append(PlanItem(row, NOT_SELECTED, "; ".join(row.problems) or "deselected"))
            continue
        try:
            src_segs, dest_segs = _segments(row.source), _segments(row.dest_folder)
        except ValueError as e:
            items.append(PlanItem(row, UNSAFE, str(e)))
            continue
        if not src_segs or not dest_segs:
            items.append(PlanItem(row, UNSAFE, "empty source or destination"))
            continue
        src = root.joinpath(*src_segs)
        dst_dir = root.joinpath(*dest_segs)
        dst = dst_dir / src.name
        if not _inside(root, src.parent) or not _inside(root, _nearest_existing(dst_dir)):
            items.append(PlanItem(row, UNSAFE, "path resolves outside the root", src, dst))
        elif not os.path.lexists(src):
            items.append(PlanItem(row, NOT_FOUND, "no item with that name/path", src, dst))
        elif os.path.normcase(os.path.realpath(src.parent)) == os.path.normcase(os.path.realpath(dst_dir)):
            items.append(PlanItem(row, ALREADY_THERE, "already in the destination", src, dst))
        elif _inside(src, dst_dir) and os.path.isdir(src) and not os.path.islink(src):
            items.append(PlanItem(row, UNSAFE, "destination is inside the item being moved", src, dst))
        elif os.path.lexists(dst) or os.path.normcase(str(dst)) in planned:
            items.append(PlanItem(row, CONFLICT, "destination already has an item with this name; will not overwrite", src, dst))
        else:
            planned.add(os.path.normcase(str(dst)))
            detail = "destination exists" if dst_dir.is_dir() else "destination folder will be created"
            items.append(PlanItem(row, READY, detail, src, dst))
    return items


def _log_dir(log_dir) -> Path:
    d = Path(log_dir) if log_dir else Path.home() / ".onedrive-sorter" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def execute(items: list[PlanItem], root, log_dir=None, delay: float = 0.25,
            sleep=time.sleep, on_event=None, before_each=None) -> Report:
    """Perform the READY items. Never overwrites; re-checks each move just before doing it.

    before_each is called before every move; it may block (pause) and returns False to stop.
    """
    root = open_root(root)
    report = Report(log_path=_log_dir(log_dir) / f"moves_{datetime.now():%Y%m%d_%H%M%S_%f}.jsonl")
    emit = on_event or (lambda *_: None)
    with open(report.log_path, "a", encoding="utf-8") as log:
        for it in items:
            if it.state != READY:
                continue
            if before_each is not None and before_each() is False:
                break
            try:
                if os.path.lexists(it.dst):
                    raise EngineError("destination appeared since the check; not overwriting")
                os.makedirs(it.dst.parent, exist_ok=True)
                if not _inside(root, it.dst.parent):
                    raise EngineError("destination resolves outside the root")
                os.rename(it.src, it.dst)
                it.state = MOVED
                log.write(json.dumps({"src": it.src.relative_to(root).as_posix(),
                                      "dst": it.dst.relative_to(root).as_posix(),
                                      "root": str(root), "at": datetime.now().isoformat()}) + "\n")
                log.flush()
                os.fsync(log.fileno())
                report.moved.append(it)
                emit(MOVED, it)
            except (OSError, EngineError) as e:
                it.state, it.detail = FAILED, str(e)
                report.failed.append(it)
                emit(FAILED, it)
            sleep(delay)
    return report


def undo(log_path, root, sleep=time.sleep, delay: float = 0.25, on_event=None) -> Report:
    """Reverse a move log, newest first. Skips anything that would overwrite or is missing."""
    root = open_root(root)
    report = Report(log_path=Path(log_path))
    emit = on_event or (lambda *_: None)
    with open(log_path, encoding="utf-8") as fh:
        entries = [json.loads(line) for line in fh if line.strip()]
    for e in reversed(entries):
        row = Row(n=0, fields={})
        it = PlanItem(row, READY, src=root.joinpath(*e["dst"].split("/")), dst=root.joinpath(*e["src"].split("/")))
        try:
            if not (_inside(root, it.src.parent) and _inside(root, _nearest_existing(it.dst.parent))):
                raise EngineError("path resolves outside the root")
            if not os.path.lexists(it.src):
                raise EngineError("moved item is no longer there")
            if os.path.lexists(it.dst):
                raise EngineError("original location is occupied; not overwriting")
            os.makedirs(it.dst.parent, exist_ok=True)
            os.rename(it.src, it.dst)
            it.state = MOVED
            report.moved.append(it)
            emit(MOVED, it)
        except (OSError, EngineError) as ex:
            it.state, it.detail = FAILED, str(ex)
            report.failed.append(it)
            emit(FAILED, it)
        sleep(delay)
    return report
