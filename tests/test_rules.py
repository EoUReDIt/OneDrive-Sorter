import json
import re
from pathlib import Path

from sorter.rules import REQUIRED_COLUMNS, RULES, validate_row


def row(**kw):
    base = dict(SourceFile="a.pdf", DestinationFolder="Career/Interviews", Status="Verified", MoveAction="MOVE")
    base.update(kw)
    return base


def test_valid_row_passes():
    assert validate_row(row()) == []


def test_rule_defined_second_level_passes_for_academic():
    assert validate_row(row(DestinationFolder="Academic/University Coursework/ARIN 350/Final")) == []


def test_unknown_top_level_flagged():
    assert any("top-level" in p for p in validate_row(row(DestinationFolder="Stuff/Here")))


def test_unknown_second_level_flagged():
    assert any("ARIN 350" in p for p in validate_row(row(DestinationFolder="Academic/ARIN 350/Final")))


def test_top_level_without_defined_children_allows_any_subfolder():
    assert validate_row(row(DestinationFolder="Unsorted/anything/at/all")) == []


def test_status_and_action_flagged():
    assert validate_row(row(Status="Probable"))
    assert validate_row(row(MoveAction="DELETE"))


def test_dotdot_flagged_in_source_and_destination():
    assert validate_row(row(DestinationFolder="Career/../x"))
    assert validate_row(row(SourceFile="../x.pdf"))


def test_empty_fields_flagged():
    assert validate_row(row(SourceFile=""))
    assert validate_row(row(DestinationFolder=""))


def test_browser_copy_of_rules_matches_python():
    """index.html duplicates the rules until the final refactor; fail loudly if they drift."""
    html = (Path(__file__).parent.parent / "index.html").read_text(encoding="utf-8")
    js_rules = json.loads(re.search(r"const RULES = (\{.*?\n\});", html, re.S).group(1))
    assert js_rules == RULES
    js_cols = json.loads(re.search(r"const REQUIRED_COLUMNS = (\[.*?\]);", html, re.S).group(1))
    assert js_cols == REQUIRED_COLUMNS
