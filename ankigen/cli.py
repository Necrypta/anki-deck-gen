"""Headless conversion: text file in, .apkg out.

python -m ankigen.cli examples/physics_sample.txt -o physics.apkg
python -m ankigen.cli cards.tsv --format delimited --fields Front,Back
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .deck import build_apkg
from .latex import DEFAULT_MACROS
from .models import DEFAULT_FIELDS, DeckSpec
from .parsers import PARSERS, parse_text


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ankigen.cli", description=__doc__.splitlines()[0])
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path)
    p.add_argument("--format", choices=list(PARSERS), help="default: by file extension")
    p.add_argument("--separator", default="tab", help="delimited only: tab, pipe, semicolon, comma")
    p.add_argument("--fields", help="comma-separated field names")
    p.add_argument("--deck", help="deck name (overrides '# deck:')")
    args = p.parse_args(argv)

    fmt = args.format or ("delimited" if args.input.suffix.lower() in {".tsv", ".csv"} else "block")
    fields = [f.strip() for f in args.fields.split(",")] if args.fields else None
    options: dict = {"fields": fields}
    if fmt == "delimited":
        options["separator"] = "comma" if args.input.suffix.lower() == ".csv" else args.separator

    result = parse_text(args.input.read_text(encoding="utf-8-sig"), fmt, **options)
    for e in result.errors:
        print(f"{args.input}:{e.line}: {e.message}", file=sys.stderr)
    if not result.cards:
        print("No cards found.", file=sys.stderr)
        return 1

    note_type = result.note_type or "basic"
    spec = DeckSpec(
        name=args.deck or result.deck or args.input.stem,
        note_type=note_type,
        fields=result.fields or DEFAULT_FIELDS.get(note_type, ["Front", "Back"]),
        cards=result.cards,
        tags=result.tags,
        macros=DEFAULT_MACROS,
    )
    out = build_apkg(spec, args.output or args.input.with_suffix(".apkg"))
    print(f"Wrote {len(spec.cards)} cards to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
