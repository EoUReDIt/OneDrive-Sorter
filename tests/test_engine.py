import json
import os
from pathlib import Path

import pytest

from sorter import engine
from sorter.manifest import Row
from sorter.rules import validate_row


def mkrow(src, dest, n=1):
    f = dict(SourceFile=src, DestinationFolder=dest, Status="Verified", MoveAction="MOVE")
    r = Row(n=n, fields=f)
    r.problems = validate_row(f)
    r.selected = not r.problems
    return r


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "OneDrive"
    root.mkdir()
    (root / "resume.pdf").write_text("r")
    (root / "Interviews Stuff").mkdir()
    (root / "Interviews Stuff" / "note.txt").write_text("n")
    return root


def states(items):
    return [i.state for i in items]


def run(items, root, tmp_path):
    return engine.execute(items, root, log_dir=tmp_path / "logs", delay=0, sleep=lambda s: None)


def test_check_is_read_only_and_creates_nothing(tree):
    items = engine.check([mkrow("resume.pdf", "Career/Resume Workspace")], tree)
    assert states(items) == [engine.READY]
    assert "will be created" in items[0].detail
    assert not (tree / "Career").exists()


def test_execute_moves_creates_folders_and_logs(tree, tmp_path):
    items = engine.check([mkrow("resume.pdf", "Career/Resume Workspace"),
                          mkrow("Interviews Stuff", "Career/Interviews", 2)], tree)
    rep = run(items, tree, tmp_path)
    assert len(rep.moved) == 2 and not rep.failed
    assert (tree / "Career/Resume Workspace/resume.pdf").read_text() == "r"
    assert (tree / "Career/Interviews/Interviews Stuff/note.txt").exists()
    assert not (tree / "resume.pdf").exists()
    lines = [json.loads(l) for l in rep.log_path.read_text().splitlines()]
    assert [l["src"] for l in lines] == ["resume.pdf", "Interviews Stuff"]


def test_missing_source_and_already_there(tree):
    (tree / "Career").mkdir()
    (tree / "Career" / "x.pdf").write_text("x")
    items = engine.check([mkrow("nope.pdf", "Career/Interviews"), mkrow("Career/x.pdf", "Career")], tree)
    assert states(items) == [engine.NOT_FOUND, engine.ALREADY_THERE]


def test_never_overwrites_existing_destination(tree, tmp_path):
    (tree / "Career/Resume Workspace").mkdir(parents=True)
    (tree / "Career/Resume Workspace/resume.pdf").write_text("OLD")
    items = engine.check([mkrow("resume.pdf", "Career/Resume Workspace")], tree)
    assert states(items) == [engine.CONFLICT]
    run(items, tree, tmp_path)
    assert (tree / "Career/Resume Workspace/resume.pdf").read_text() == "OLD"
    assert (tree / "resume.pdf").exists()


def test_two_rows_same_destination_second_conflicts(tree):
    (tree / "sub").mkdir()
    (tree / "sub" / "resume.pdf").write_text("other")
    items = engine.check([mkrow("resume.pdf", "Career/Resume Workspace"),
                          mkrow("sub/resume.pdf", "Career/Resume Workspace", 2)], tree)
    assert states(items) == [engine.READY, engine.CONFLICT]


def test_destination_changed_after_check_is_not_overwritten(tree, tmp_path):
    items = engine.check([mkrow("resume.pdf", "Career/Resume Workspace")], tree)
    (tree / "Career/Resume Workspace").mkdir(parents=True)
    (tree / "Career/Resume Workspace/resume.pdf").write_text("RACE")
    rep = run(items, tree, tmp_path)
    assert len(rep.failed) == 1
    assert (tree / "Career/Resume Workspace/resume.pdf").read_text() == "RACE"


@pytest.mark.parametrize("src,dest", [
    ("../outside.txt", "Career/Interviews"),
    ("resume.pdf", "Career/../../escape"),
    ("resume.pdf", "Career\\..\\x"),
    ("C:/Windows/x", "Career/Interviews"),
])
def test_path_escapes_are_rejected(tree, src, dest):
    r = mkrow(src, dest)
    r.selected = True                      # even if the user forces the row on
    assert states(engine.check([r], tree)) == [engine.UNSAFE]


def test_symlink_escape_is_rejected(tree, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        os.symlink(outside, tree / "Career", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert states(engine.check([mkrow("resume.pdf", "Career/Resume Workspace")], tree)) == [engine.UNSAFE]
    assert list(outside.iterdir()) == []


def test_cannot_move_folder_into_itself(tree):
    r = mkrow("Interviews Stuff", "Unsorted/inner")
    (tree / "Unsorted").mkdir()
    (tree / "Unsorted" / "inner").mkdir()
    assert states(engine.check([r], tree)) == [engine.READY]
    bad = mkrow("Unsorted", "Unsorted/inner", 2)
    assert states(engine.check([bad], tree)) == [engine.UNSAFE]


def test_flagged_rows_are_not_selected_until_forced(tree):
    r = mkrow("resume.pdf", "Academic/ARIN 350/Final")
    assert states(engine.check([r], tree)) == [engine.NOT_SELECTED]
    r.selected = True
    assert states(engine.check([r], tree)) == [engine.READY]


def test_undo_restores_everything_in_reverse(tree, tmp_path):
    items = engine.check([mkrow("resume.pdf", "Career/Resume Workspace"),
                          mkrow("Interviews Stuff", "Career/Interviews", 2)], tree)
    rep = run(items, tree, tmp_path)
    back = engine.undo(rep.log_path, tree, delay=0, sleep=lambda s: None)
    assert len(back.moved) == 2 and not back.failed
    assert (tree / "resume.pdf").read_text() == "r"
    assert (tree / "Interviews Stuff/note.txt").exists()


def test_undo_does_not_overwrite_occupied_original(tree, tmp_path):
    items = engine.check([mkrow("resume.pdf", "Career/Resume Workspace")], tree)
    rep = run(items, tree, tmp_path)
    (tree / "resume.pdf").write_text("NEW")
    back = engine.undo(rep.log_path, tree, delay=0, sleep=lambda s: None)
    assert len(back.failed) == 1
    assert (tree / "resume.pdf").read_text() == "NEW"
    assert (tree / "Career/Resume Workspace/resume.pdf").exists()


def test_execute_only_touches_ready_items(tree, tmp_path):
    items = engine.check([mkrow("nope.pdf", "Career/Interviews")], tree)
    rep = run(items, tree, tmp_path)
    assert not rep.moved and not rep.failed


def test_open_root_rejects_missing_folder(tmp_path):
    with pytest.raises(engine.EngineError):
        engine.open_root(tmp_path / "missing")
