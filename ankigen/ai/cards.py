"""JSON schema for generated cards, and turning a model reply into card fields."""

from __future__ import annotations

import re

from ..latex import MacroDef
from .text import normalize_math, parse_json_lenient, strip_fences, strip_think, tidy_math

ANSWER_ALIASES = ("answer", "back", "a")
QUESTION_ALIASES = ("question", "front", "q", "text")


def card_schema(fields: list[str]) -> dict:
    """JSON Schema for ``{"cards": [{field: str, ...}]}`` (strict-mode friendly)."""
    item = {
        "type": "object",
        "properties": {f: {"type": "string"} for f in fields},
        "required": list(fields),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"cards": {"type": "array", "items": item}},
        "required": ["cards"],
        "additionalProperties": False,
    }


def parse_cards(
    reply: str, fields: list[str], macros: list[MacroDef] | None = None
) -> list[dict[str, str]]:
    """Map a model reply onto ``fields``. Raises ``ValueError`` if it isn't JSON.

    Keys match case-insensitively; ``question``/``answer`` style keys fill the
    first two fields. Cards with an empty first field are dropped.
    """
    words = {m.name.lstrip("\\") for m in macros or []}
    data = parse_json_lenient(reply, words)
    if isinstance(data, dict):
        items = data.get("cards")
        if items is None:
            items = next((v for v in data.values() if isinstance(v, list)), [data])
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("The reply wasn't a list of cards")  # noqa: TRY004 (callers catch ValueError)

    cards = []
    for item in items:
        if not isinstance(item, dict):
            continue
        lower = {str(k).strip().lower(): v for k, v in item.items()}
        card = {}
        for i, f in enumerate(fields):
            value = lower.get(f.lower())
            if value is None and i < 2:
                aliases = QUESTION_ALIASES if i == 0 else ANSWER_ALIASES
                value = next((lower[a] for a in aliases if a in lower), None)
            card[f] = tidy_math(normalize_math(_as_text(value))).strip()
        if card[fields[0]]:
            cards.append(card)
    return cards


def parse_block_cards(reply: str, fields: list[str]) -> list[dict[str, str]]:
    """Cards from the plain-text ``Field: value`` / ``---`` format (no escaping needed).

    Falls back to JSON when the model answered with JSON anyway.
    """
    from ..parsers import parse_text

    text = strip_fences(strip_think(reply)).strip()
    if text.startswith(("{", "[")):
        return parse_cards(text, fields)
    result = parse_text(text, "block", fields=fields)
    cards = []
    for c in result.cards:
        lower = {k.lower(): v for k, v in c.fields.items()}
        card = {f: tidy_math(normalize_math(lower.get(f.lower(), ""))).strip() for f in fields}
        if card[fields[0]]:
            cards.append(card)
    if not cards:
        raise ValueError("No cards found in the reply")
    return cards


_BACKSLASH_WORD = re.compile(r"\\+backslash\s*(?=[A-Za-z])|\\textbackslash\s*(?=[A-Za-z])")


def repair_card(card: dict[str, str], fields: list[str]) -> list[str]:
    r"""Fix two small-model habits in place; returns what was fixed.

    * ``\\backslash dagger`` (a model escaping a backslash in words) → ``\dagger``
    * an extra field that just repeats the answer is emptied
    """
    fixed = []
    for f in fields:
        new = _BACKSLASH_WORD.sub(lambda _: "\\", card[f])
        if new != card[f]:
            card[f] = new
            fixed.append("backslash")
    if len(fields) > 2:
        answer = _plain(card[fields[1]])
        for f in fields[2:]:
            extra = _plain(card[f])
            if extra and answer and (extra == answer or extra in answer):
                card[f] = ""
                fixed.append("duplicate_extra")
    return fixed


def _plain(text: str) -> str:
    return re.sub(r"[\s$.,;:]+", "", text).lower()


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(_as_text(v) for v in value)
    return str(value)


_MATHLIKE = re.compile(r"\\[A-Za-z]+|[_^]\{")


def bare_latex(text: str) -> bool:
    r"""True when LaTeX appears outside ``$…$`` (it would show as raw ``\frac``)."""
    outside = re.sub(r"\$\$.+?\$\$|\$(?:\\.|[^$\\])+\$", "", text, flags=re.DOTALL)
    return bool(_MATHLIKE.search(outside))
