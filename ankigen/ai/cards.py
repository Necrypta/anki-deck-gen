"""JSON schema for generated cards, and turning a model reply into card fields."""

from __future__ import annotations

import re

from ..latex import MacroDef
from .text import normalize_math, parse_json_lenient

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
            card[f] = normalize_math(_as_text(value)).strip()
        if card[fields[0]]:
            cards.append(card)
    return cards


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
