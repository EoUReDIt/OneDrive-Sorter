from pathlib import Path

import pytest

from sorter.manifest import ManifestError, load_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_manifest.csv"


def test_fixture_loads_and_flags_one_row():
    rows = load_manifest(FIXTURE)
    assert len(rows) == 5
    assert [r.selected for r in rows] == [True, True, True, True, False]
    assert "ARIN 350" in rows[4].problems[0]
    assert rows[0].fields["Notes"] == "Quoted, with a comma"


def test_missing_columns_raise(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("SourceFile,DestinationFolder\na,b\n")
    with pytest.raises(ManifestError, match="missing columns"):
        load_manifest(p)


def test_bom_and_blank_lines(tmp_path):
    text = FIXTURE.read_text(encoding="utf-8")
    p = tmp_path / "m.csv"
    p.write_text("\ufeff" + text + "\n\n,,,,,,,\n", encoding="utf-8")
    assert len(load_manifest(p)) == 5


def test_paths_are_normalised(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("SourceFile,DestinationFolder,Category,SubCategory,Confidence,Status,MoveAction,Notes\n"
                 "/a//b.pdf,/Career//Interviews/,,,,Verified,MOVE,\n")
    r = load_manifest(p)[0]
    assert (r.source, r.dest_folder) == ("a/b.pdf", "Career/Interviews")
