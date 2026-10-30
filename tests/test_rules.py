import json
import re
from pathlib import Path

import pytest

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
    """The page keeps a copy of the rules for cloud mode (it has no backend to ask); fail loudly if it drifts."""
    html = (Path(__file__).parent.parent / "sorter" / "web" / "index.html").read_text(encoding="utf-8")
    js_rules = json.loads(re.search(r"const RULES = (\{.*?\n\});", html, re.S).group(1))
    assert js_rules == RULES
    js_cols = json.loads(re.search(r"const REQUIRED_COLUMNS = (\[.*?\]);", html, re.S).group(1))
    assert js_cols == REQUIRED_COLUMNS


def test_root_page_matches_the_packaged_page():
    """GitHub Pages serves the root index.html; the package serves sorter/web/index.html."""
    root = Path(__file__).parent.parent
    assert (root / "index.html").read_bytes() == (root / "sorter" / "web" / "index.html").read_bytes(), \
        "run: python tools/sync.py"


@pytest.mark.parametrize("src,copy", [("README.md", "README.md"), ("docs/TESTING.md", "TESTING.md"),
                                      ("docs/USAGE_FOR_AI.md", "USAGE_FOR_AI.md")])
def test_bundled_guides_match_their_sources(src, copy):
    """AI tools read the copies in sorter/context/; they must equal the documents people read."""
    root = Path(__file__).parent.parent
    assert (root / src).read_bytes() == (root / "sorter" / "context" / copy).read_bytes(), "run: python tools/sync.py"


def test_the_ai_guide_names_every_top_level_folder_and_every_tool():
    """Keep the guide honest: it must mention each rule folder and each real MCP tool."""
    root = Path(__file__).parent.parent
    guide = (root / "docs" / "USAGE_FOR_AI.md").read_text(encoding="utf-8")
    assert all(name in guide for name in RULES)
    for tool in ("get_rules", "list_folder", "validate_manifest", "propose_plan", "list_context_files", "read_context_file"):
        assert tool in guide
    for names in RULES.values():
        for second in names or []:
            assert second in guide, second
