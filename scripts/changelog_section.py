"""Print one version's section of CHANGELOG.md (used as GitHub Release notes).

python scripts/changelog_section.py 0.2.0 [-o notes.md]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def section(version: str, text: str) -> str:
    pattern = rf"^## \[?v?{re.escape(version)}\]?[^\n]*\n(.*?)(?=^## |\Z)"
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip()
    # Dry runs build before the version has its own section.
    m = re.search(r"^## \[?Unreleased\]?[^\n]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return (m.group(1).strip() if m else "") or "No notes."


if __name__ == "__main__":
    notes = section(sys.argv[1], CHANGELOG.read_text(encoding="utf-8"))
    if len(sys.argv) > 3 and sys.argv[2] == "-o":
        Path(sys.argv[3]).write_text(notes + "\n", encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(notes)
