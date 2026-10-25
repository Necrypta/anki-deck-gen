"""AI card source (planned).

Intended backends, all behind the same :class:`~ankigen.providers.base.CardSource`
interface:
  * Local: Ollama over its HTTP API (``http://localhost:11434``).
  * Online: Anthropic / OpenAI-compatible APIs with a user-supplied key.

The prompt will ask for JSON matching the deck's fields and require LaTeX in
``$...$`` / ``$$...$$`` so output drops straight into the existing pipeline.
"""

from __future__ import annotations

from ..models import Card
from .base import SourceInput


class AiSource:
    name = "ai"

    def __init__(self, backend: str = "ollama", model: str | None = None) -> None:
        self.backend = backend
        self.model = model

    def available(self) -> bool:
        return False

    def generate(self, source: SourceInput) -> list[Card]:
        raise NotImplementedError("AI generation isn't implemented yet. See ROADMAP.md")
