import json

import pytest

from sorter import proposals


def test_save_list_read_round_trip(tmp_path):
    name = proposals.save("a,b\n1,2\n", "my note", {"ready": 1}, tmp_path)
    assert proposals.NAME.match(name)
    listed = proposals.list_all(tmp_path)
    assert [p["name"] for p in listed] == [name] and listed[0]["note"] == "my note"
    text, meta = proposals.read(tmp_path, name)
    assert text == "a,b\n1,2\n" and meta["summary"] == {"ready": 1}


def test_newest_first(tmp_path):
    a = proposals.save("x", "", {}, tmp_path)
    b = proposals.save("y", "", {}, tmp_path)
    assert [p["name"] for p in proposals.list_all(tmp_path)] == [b, a]


def test_notes_are_cleaned_and_capped(tmp_path):
    name = proposals.save("x", "line1\nline2\x00\x1b[31m" + "z" * 1000, {}, tmp_path)
    note = json.loads((tmp_path / name.replace(".csv", ".json")).read_text())["note"]
    assert "\n" not in note and "\x00" not in note and "\x1b" not in note and len(note) <= 500


@pytest.mark.parametrize("bad", ["../x.csv", "proposal_1.csv/../../x", "proposal_x.csv", "other.csv", "", None, 5])
def test_read_rejects_names_that_are_not_proposals(tmp_path, bad):
    with pytest.raises(ValueError):
        proposals.read(tmp_path, bad)


def test_read_missing_and_listing_a_missing_folder(tmp_path):
    with pytest.raises(FileNotFoundError):
        proposals.read(tmp_path, "proposal_20200101_000000_000000.csv")
    assert proposals.list_all(tmp_path / "nope") == []


def test_missing_sidecar_is_tolerated(tmp_path):
    name = proposals.save("x", "n", {}, tmp_path)
    (tmp_path / name.replace(".csv", ".json")).unlink()
    assert proposals.list_all(tmp_path)[0]["note"] == ""
