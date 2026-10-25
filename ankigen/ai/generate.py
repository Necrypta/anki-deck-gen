"""Turn study material (Markdown + LaTeX) into cards, chunk by chunk."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from ..latex import MacroDef
from .cards import bare_latex, card_schema, parse_cards
from .http import AiError
from .prompts import card_messages
from .providers import Provider

# Words per chunk. Small local models write better cards from shorter input;
# Gemini handles a lot at once but each request is slow, so fewer is better.
CHUNK_WORDS = {"local": 900, "gemini": 3000}
AVOID_LIMIT = 40  # earlier fronts passed to later chunks to avoid repeats


def chunk_markdown(text: str, max_words: int) -> list[str]:
    """Split on headings, then pack paragraphs into chunks of about ``max_words``.

    A ``$$ … $$`` block is never split, and a heading stays with what follows it.
    """
    blocks = _blocks(text)
    chunks: list[list[str]] = []
    words = 0
    only_headings = True  # a chunk is never just a heading
    for block in blocks:
        n = len(block.split())
        heading = block.lstrip().startswith("#")
        full = words + n > max_words or (heading and words > max_words // 3)
        if chunks and full and not only_headings:
            chunks.append([])
            words, only_headings = 0, True
        if not chunks:
            chunks.append([])
        chunks[-1].append(block)
        words += n
        only_headings = only_headings and heading
    return ["\n\n".join(c).strip() for c in chunks if "".join(c).strip()]


def _blocks(text: str) -> list[str]:
    """Paragraphs separated by blank lines, keeping display math in one piece."""
    out: list[str] = []
    cur: list[str] = []
    in_math = False
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.count("$$") % 2:
            in_math = not in_math
        if not line.strip() and not in_math:
            if cur:
                out.append("\n".join(cur))
                cur = []
            continue
        cur.append(line)
    if cur:
        out.append("\n".join(cur))
    return out


@dataclass
class Request:
    material: str
    fields: list[str]
    note_type: str = "basic"
    macros: list[MacroDef] = field(default_factory=list)
    density: str = "normal"
    focus: str = "balanced"
    source: str = ""  # file name, for the source:: tag

    def source_tag(self) -> str | None:
        name = re.sub(r"\.[A-Za-z0-9]+$", "", self.source).strip()
        name = re.sub(r"[^\w.-]+", "_", name).strip("_")
        return f"source::{name}" if name else None


@dataclass
class Progress:
    done: int = 0
    total: int = 0
    message: str = ""
    cards: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pages: dict[int, str] = field(default_factory=dict)  # reading jobs: page → Markdown


def generate_cards(
    provider: Provider,
    model: str,
    req: Request,
    *,
    progress: Progress,
    cancel: threading.Event | None = None,
    on_update: Callable[[], None] | None = None,
) -> None:
    """Fill ``progress.cards`` chunk by chunk; raises :class:`AiError` on failure."""
    size = CHUNK_WORDS["gemini" if provider.kind == "gemini" else "local"]
    chunks = chunk_markdown(req.material, size)
    if not chunks:
        raise AiError("There's no material to make cards from")
    progress.total = len(chunks)
    schema = card_schema(req.fields)
    tag = req.source_tag()
    fronts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        if cancel is not None and cancel.is_set():
            return
        progress.message = f"Writing cards for part {i} of {len(chunks)}"
        if on_update:
            on_update()
        system, user = card_messages(
            chunk,
            req.fields,
            note_type=req.note_type,
            macros=req.macros,
            density=req.density,
            focus=req.focus,
            avoid=fronts[-AVOID_LIMIT:],
        )
        result = provider.chat(model, user, system=system, schema=schema, cancel=cancel)
        try:
            cards = parse_cards(result.text, req.fields, req.macros)
        except ValueError as e:
            progress.warnings.append(f"Part {i}: {e}")
            cards = []
        if result.truncated:
            progress.warnings.append(
                f"Part {i}: the reply was cut off, so some cards may be missing"
            )
        for c in cards:
            flags = [f for f in req.fields if bare_latex(c[f])]
            progress.cards.append(
                {"fields": c, "tags": [tag] if tag else [], "flags": {"bare_latex": flags}}
            )
            fronts.append(c[req.fields[0]][:120])
        progress.done = i
        if on_update:
            on_update()
    progress.message = f"{len(progress.cards)} cards"
