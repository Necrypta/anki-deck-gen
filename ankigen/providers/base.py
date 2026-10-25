"""Extension point for anything that turns non-text input into cards.

OCR and AI generation will implement :class:`CardSource`. The UI only needs a
list of :class:`~ankigen.models.Card` back, so new sources plug straight into
the same import preview the text parsers use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..models import Card


@dataclass
class SourceInput:
    text: str | None = None
    image_paths: list[str] = field(default_factory=list)
    note_type: str = "basic"
    fields: list[str] = field(default_factory=lambda: ["Front", "Back"])
    options: dict[str, Any] = field(default_factory=dict)


class CardSource(Protocol):
    name: str

    def available(self) -> bool:
        """Whether dependencies / API keys / local servers are present."""
        ...

    def generate(self, source: SourceInput) -> list[Card]:
        ...
