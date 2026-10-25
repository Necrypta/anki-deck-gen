"""Plain data types shared by the parsers, deck builder and API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .latex import MacroDef, normalize_macros

NOTE_TYPES = ("basic", "reversed", "cloze", "custom")

DEFAULT_FIELDS: dict[str, list[str]] = {
    "basic": ["Front", "Back", "Extra"],
    "reversed": ["Front", "Back", "Extra"],
    "cloze": ["Text", "Extra"],
}


@dataclass
class Card:
    fields: dict[str, str]
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"fields": dict(self.fields), "tags": list(self.tags)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Card:
        return cls(
            fields={str(k): str(v) for k, v in data.get("fields", {}).items()},
            tags=[str(t) for t in data.get("tags", [])],
        )


@dataclass
class DeckSpec:
    name: str
    note_type: str = "basic"
    fields: list[str] = field(default_factory=lambda: list(DEFAULT_FIELDS["basic"]))
    cards: list[Card] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    macros: list[MacroDef] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.note_type not in NOTE_TYPES:
            raise ValueError(f"Unknown note type: {self.note_type!r}")
        self.macros = normalize_macros(self.macros)
        if not self.fields:
            raise ValueError("A note type needs at least one field")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeckSpec:
        note_type = data.get("note_type", "basic")
        return cls(
            name=str(data.get("name") or "Untitled"),
            note_type=note_type,
            fields=list(data.get("fields") or DEFAULT_FIELDS.get(note_type, ["Front", "Back"])),
            cards=[Card.from_dict(c) for c in data.get("cards", [])],
            tags=[str(t) for t in data.get("tags", [])],
            macros=normalize_macros(data.get("macros")),
        )


@dataclass
class ParseError:
    line: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"line": self.line, "message": self.message}


@dataclass
class ParseResult:
    cards: list[Card] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)
    deck: str | None = None
    note_type: str | None = None
    fields: list[str] | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cards": [c.to_dict() for c in self.cards],
            "errors": [e.to_dict() for e in self.errors],
            "deck": self.deck,
            "note_type": self.note_type,
            "fields": self.fields,
            "tags": list(self.tags),
        }
