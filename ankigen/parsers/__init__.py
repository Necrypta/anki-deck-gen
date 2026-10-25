"""Text parsers that turn a file's contents into cards."""

from __future__ import annotations

from collections.abc import Callable

from ..models import ParseResult
from . import block, delimited

Parser = Callable[..., ParseResult]

PARSERS: dict[str, Parser] = {
    "block": block.parse,
    "delimited": delimited.parse,
}


def parse_text(text: str, fmt: str = "block", **options: object) -> ParseResult:
    try:
        parser = PARSERS[fmt]
    except KeyError:
        raise ValueError(f"Unknown format {fmt!r}. Available: {', '.join(PARSERS)}") from None
    return parser(text, **options)
