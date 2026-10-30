"""Copy the canonical page (sorter/web/index.html) to the repository root, where GitHub Pages serves it."""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
shutil.copyfile(root / "sorter" / "web" / "index.html", root / "index.html")
print("index.html updated from sorter/web/index.html")
