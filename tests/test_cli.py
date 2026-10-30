from pathlib import Path

from sorter.__main__ import main

FIXTURE = str(Path(__file__).parent / "fixtures" / "sample_manifest.csv")


def make_root(tmp_path):
    root = tmp_path / "od"
    root.mkdir()
    for name in ("Example Resume.pdf", "Employer Notes", "Clearance Form.pdf", "Course Deck.pptx"):
        (root / name).write_text("x")
    (root / "Interview Folder").mkdir()
    return root


def test_dry_run_changes_nothing(tmp_path, capsys):
    root = make_root(tmp_path)
    assert main(["run", FIXTURE, "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "Dry run" in out and "4 of 5 row(s) ready" in out
    assert (root / "Example Resume.pdf").exists()


def test_apply_then_undo_round_trip(tmp_path, capsys):
    root = make_root(tmp_path)
    logs = tmp_path / "logs"
    assert main(["run", FIXTURE, "--root", str(root), "--apply", "--delay", "0", "--log-dir", str(logs)]) == 0
    assert (root / "Career/Resume Workspace/Example Resume.pdf").exists()
    assert (root / "Career/Employers/Acme/Employer Notes").exists()
    assert (root / "Course Deck.pptx").exists()               # flagged row was held back
    log = next(logs.iterdir())
    assert main(["undo", str(log), "--root", str(root), "--delay", "0"]) == 0
    assert (root / "Example Resume.pdf").exists()


def test_include_flagged_moves_the_flagged_row(tmp_path):
    root = make_root(tmp_path)
    assert main(["run", FIXTURE, "--root", str(root), "--apply", "--include-flagged",
                 "--delay", "0", "--log-dir", str(tmp_path / "l")]) == 0
    assert (root / "Academic/ARIN 350/Final Presentation/Course Deck.pptx").exists()


def test_bad_root_exits_2(tmp_path, capsys):
    assert main(["check", FIXTURE, "--root", str(tmp_path / "nope")]) == 2


def test_empty_and_placeholder_roots_exit_2_with_a_clear_message(tmp_path, capsys):
    for bad, words in (("", "No folder given"), ("${ONEDRIVE_SORT_ROOT}", "environment variable")):
        assert main(["check", FIXTURE, "--root", bad]) == 2
        assert words in capsys.readouterr().err
