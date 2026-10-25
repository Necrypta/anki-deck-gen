"""Block format: ``Field: value`` lines, cards separated by ``---``.

See FORMAT.md for the full description.
"""

from __future__ import annotations

import re

from ..models import DEFAULT_FIELDS, NOTE_TYPES, Card, ParseError, ParseResult

_FIELD_RE = re.compile(r"^([A-Za-z][\w ]{0,31}):\s?(.*)$")
_DIRECTIVE_RE = re.compile(r"^#\s*(\w+)\s*:\s*(.*)$")
_SEPARATOR_RE = re.compile(r"^-{3,}\s*$")


def parse(text: str, fields: list[str] | None = None, **_: object) -> ParseResult:
    result = ParseResult()
    lines = text.replace("\r\n", "\n").split("\n")

    current: dict[str, list[str]] = {}
    current_tags: list[str] = []
    current_field: str | None = None
    start_line = 1
    in_header = True

    def flush(end_line: int) -> None:
        nonlocal current, current_tags, current_field
        if current:
            values = {k: "\n".join(v).strip() for k, v in current.items()}
            if any(values.values()):
                result.cards.append(Card(fields=values, tags=current_tags))
            else:
                result.errors.append(ParseError(start_line, "Card has no content"))
        current, current_tags, current_field = {}, [], None

    for idx, raw in enumerate(lines, start=1):
        line = raw.rstrip()

        if in_header:
            m = _DIRECTIVE_RE.match(line)
            if m:
                _apply_directive(result, m.group(1).lower(), m.group(2).strip(), idx)
                continue
            if not line.strip():
                continue
            in_header = False

        if _SEPARATOR_RE.match(line):
            flush(idx)
            start_line = idx + 1
            continue

        m = _FIELD_RE.match(line)
        if m and _starts_field(m.group(1).strip(), fields or result.fields) and not (
            current_field and _inside_math(current.get(current_field, []))
        ):
            name = m.group(1).strip()
            if not current:
                start_line = idx
            if name.lower() == "tags":
                current_tags = m.group(2).split()
                current_field = None
                continue
            key = _canonical(name, fields or result.fields)
            if key in current:
                result.errors.append(ParseError(idx, f"Field '{name}' appears twice in one card"))
            current[key] = [m.group(2)]
            current_field = key
            continue

        if current_field is not None:
            current[current_field].append(line)
        elif line.strip():
            result.errors.append(
                ParseError(idx, "Text outside a field. Start the line with e.g. 'Front:'")
            )

    flush(len(lines))
    _validate(result, fields)
    return result


def _apply_directive(result: ParseResult, key: str, value: str, line: int) -> None:
    if key == "deck":
        result.deck = value
    elif key == "type":
        value = value.lower()
        if value not in NOTE_TYPES:
            result.errors.append(ParseError(line, f"Unknown type '{value}'. Use: {', '.join(NOTE_TYPES)}"))
        else:
            result.note_type = value
    elif key == "tags":
        result.tags = value.split()
    elif key == "fields":
        result.fields = [f.strip() for f in value.split(",") if f.strip()]
    else:
        result.errors.append(ParseError(line, f"Unknown directive '# {key}:'"))


def _starts_field(name: str, declared: list[str] | None) -> bool:
    """With declared fields, only those names (and Tags) open a new field.

    Without them any ``Name:`` line does, which is convenient but means prose
    like ``Note: ...`` inside an answer would split it. Declaring ``# fields:``
    avoids that.
    """
    if not declared:
        return True
    lower = name.lower()
    return lower == "tags" or any(f.lower() == lower for f in declared)


def _canonical(name: str, known: list[str] | None) -> str:
    for f in known or []:
        if f.lower() == name.lower():
            return f
    for defaults in DEFAULT_FIELDS.values():
        for f in defaults:
            if f.lower() == name.lower():
                return f
    return name


def _inside_math(lines: list[str]) -> bool:
    """True if the field so far has an unclosed ``$$`` block."""
    text = "\n".join(lines).replace(r"\$", "")
    return text.count("$$") % 2 == 1


def _validate(result: ParseResult, fields: list[str] | None) -> None:
    explicit = result.fields is not None or bool(fields)
    if result.fields is None:
        seen: list[str] = list(fields or [])
        for card in result.cards:
            for f in card.fields:
                if f not in seen:
                    seen.append(f)
        result.fields = seen or None

    if result.note_type is None and result.fields:
        lower = {f.lower() for f in result.fields}
        result.note_type = "custom"
        for name in ("basic", "cloze"):
            if lower <= {d.lower() for d in DEFAULT_FIELDS[name]}:
                result.note_type = name
                break

    # Built-in types use their standard field list unless fields were declared.
    if result.note_type in DEFAULT_FIELDS and not explicit:
        standard = DEFAULT_FIELDS[result.note_type]
        unknown = [f for f in result.fields or [] if f not in standard]
        if unknown:
            result.errors.append(ParseError(
                0, f"Fields {', '.join(unknown)} aren't part of the '{result.note_type}' type "
                   "and will be ignored. Use '# type: custom' to keep them.",
            ))
        result.fields = list(standard)
