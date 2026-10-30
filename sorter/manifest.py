"""Load a move manifest CSV into validated rows."""
import csv
from dataclasses import dataclass, field
from pathlib import Path

from .rules import REQUIRED_COLUMNS, split_path, validate_row


class ManifestError(ValueError):
    pass


@dataclass
class Row:
    n: int                       # 1-based row number, as shown to the user
    fields: dict
    problems: list = field(default_factory=list)
    selected: bool = True        # rows with problems start unselected; the user may opt in

    @property
    def source(self) -> str:
        return "/".join(split_path(self.fields["SourceFile"]))

    @property
    def dest_folder(self) -> str:
        return "/".join(split_path(self.fields["DestinationFolder"]))


def load_manifest(path) -> list[Row]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise ManifestError("Manifest is missing columns: " + ", ".join(missing))
        rows = []
        for record in reader:
            fields = {k.strip(): (v or "").strip() for k, v in record.items() if k}
            if not any(fields.values()):
                continue                      # blank line
            row = Row(n=len(rows) + 1, fields=fields)
            row.problems = validate_row(fields)
            row.selected = not row.problems
            rows.append(row)
        return rows
