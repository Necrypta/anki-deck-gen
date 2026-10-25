"""Write the build label into ankigen/_build.py (run by CI before PyInstaller).

    python scripts/stamp_build.py "PR #4 · a1b2c3d"
    python scripts/stamp_build.py v0.2.0 --check-version
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE).group(1)


def package_version() -> str:
    text = (ROOT / "ankigen" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("label")
    p.add_argument("--check-version", action="store_true",
                   help="fail unless label is v<version> matching pyproject and __init__")
    args = p.parse_args()

    if args.check_version:
        versions = {project_version(), package_version()}
        if len(versions) != 1 or args.label != f"v{versions.pop()}":
            print(f"Tag {args.label} doesn't match pyproject.toml ({project_version()}) / "
                  f"ankigen/__init__.py ({package_version()})", file=sys.stderr)
            return 1

    target = ROOT / "ankigen" / "_build.py"
    src = target.read_text(encoding="utf-8")
    src = re.sub(r'^BUILD = .*$', "BUILD = " + json.dumps(args.label, ensure_ascii=False), src, flags=re.MULTILINE)
    target.write_text(src, encoding="utf-8")
    print(f"Build label: {args.label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
