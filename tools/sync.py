"""Refresh the copies that must stay identical to their sources:

  sorter/web/index.html      -> index.html               (GitHub Pages serves the root copy)
  README.md, docs/TESTING.md,
  docs/USAGE_FOR_AI.md       -> sorter/context/          (bundled guides AI tools can read)

Run after editing any of the sources. tests/test_rules.py fails if a copy is stale.
"""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
PAIRS = [
    (root / "sorter" / "web" / "index.html", root / "index.html"),
    (root / "README.md", root / "sorter" / "context" / "README.md"),
    (root / "docs" / "TESTING.md", root / "sorter" / "context" / "TESTING.md"),
    (root / "docs" / "USAGE_FOR_AI.md", root / "sorter" / "context" / "USAGE_FOR_AI.md"),
]
for src, dst in PAIRS:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"{dst.relative_to(root)} <- {src.relative_to(root)}")
