"""AI card generation: read study material into Markdown, then write cards.

Backends (Ollama, any OpenAI-compatible server, Gemini) live in
:mod:`ankigen.ai.providers`; nothing here depends on a specific model.
"""

from .http import AiError, Cancelled
from .providers import (
    KNOWN_LOCAL,
    ChatResult,
    Gemini,
    ModelInfo,
    Ollama,
    OpenAICompatible,
    Provider,
    detect_local,
    make_provider,
)

__all__ = [
    "KNOWN_LOCAL",
    "AiError",
    "Cancelled",
    "ChatResult",
    "Gemini",
    "ModelInfo",
    "Ollama",
    "OpenAICompatible",
    "Provider",
    "detect_local",
    "make_provider",
]
