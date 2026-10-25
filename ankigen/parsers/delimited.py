"""Delimited format: one card per line, fields split by a separator."""

from __future__ import annotations

import csv
import io

from ..models import Card, ParseError, ParseResult

SEPARATORS = {"tab": "\t", "pipe": "|", "semicolon": ";", "comma": ","}


def parse(
    text: str,
    fields: list[str] | None = None,
    separator: str = "tab",
    **_: object,
) -> ParseResult:
    sep = SEPARATORS.get(separator, separator) or "\t"
    fields = list(fields or ["Front", "Back"])
    result = ParseResult(fields=fields)

    reader = csv.reader(io.StringIO(text.replace("\r\n", "\n")), delimiter=sep,
                        quotechar='"', skipinitialspace=sep != "\t")
    for idx, row in enumerate(reader, start=1):
        if not row or not any(c.strip() for c in row):
            continue
        if row[0].lstrip().startswith("#"):
            # Anki's own exports start with "#separator:tab" style headers.
            continue
        if len(row) > len(fields):
            result.errors.append(ParseError(
                idx, f"{len(row)} values but only {len(fields)} fields ({', '.join(fields)})"
            ))
            continue
        values = {f: (row[i].strip() if i < len(row) else "") for i, f in enumerate(fields)}
        # A literal "\n" in delimited text means a line break inside the field.
        values = {k: v.replace("\\n", "\n") for k, v in values.items()}
        result.cards.append(Card(fields=values))
    return result
