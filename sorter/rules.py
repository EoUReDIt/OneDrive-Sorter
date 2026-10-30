"""Rules v37 (CURRENT_RULES_v37_Consolidated.pdf) and per-row validation."""
import json
from importlib import resources

# The rules live in rules.json (next to this file) so they can be changed without touching code.
# "top_level" maps each top-level folder to its allowed second-level folders, or null when any
# subfolder is allowed. The browser page keeps a copy for cloud mode; a test fails if they differ.
_DATA = json.loads(resources.files(__package__).joinpath("rules.json").read_text(encoding="utf-8"))
RULES = _DATA["top_level"]
REQUIRED_COLUMNS = _DATA["columns"]


def split_path(path: str) -> list[str]:
    """Split a manifest path on '/', dropping empty segments."""
    return [s for s in path.split("/") if s]


def validate_row(row: dict) -> list[str]:
    """Return human-readable problems for one manifest row (empty list = passes)."""
    problems = []
    if row["MoveAction"].upper() != "MOVE":
        problems.append(f'MoveAction "{row["MoveAction"]}" is not MOVE')
    if row["Status"] != "Verified":
        problems.append(f'Status is "{row["Status"]}", not Verified')
    if not row["SourceFile"]:
        problems.append("SourceFile is empty")
    segs = split_path(row["DestinationFolder"])
    if not segs:
        problems.append("DestinationFolder is empty")
    elif segs[0] not in RULES:
        problems.append(f'"{segs[0]}" is not a top-level folder in the rules')
    elif RULES[segs[0]] and len(segs) > 1 and segs[1] not in RULES[segs[0]]:
        problems.append(f'"{segs[1]}" is not defined under {segs[0]} in the rules')
    if any(s in (".", "..") for s in segs):
        problems.append("DestinationFolder contains . or ..")
    if ".." in row["SourceFile"].split("/"):
        problems.append("SourceFile contains ..")
    return problems
