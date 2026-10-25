"""Prompts for the two AI stages: reading a page into Markdown, then writing cards."""

from __future__ import annotations

import json

from ..latex import MacroDef

READ_SYSTEM = """\
You transcribe pages of physics and maths study material into clean Markdown.

Rules:
- Transcribe faithfully and in reading order. Do not summarise, explain, correct or add anything.
- Write ALL mathematics in LaTeX: inline as $...$, display equations as $$...$$ on their own \
lines. Never use \\( \\) or \\[ \\]. Keep equation numbers as \\tag{n} inside the display math.
- Keep headings (#, ##, ###), lists, bold and italics. Tables become Markdown tables.
- For a figure or diagram write one line: [Figure: caption or a short description].
- Leave out running headers, footers, page numbers and margin notes (short side labels such \
as "summary of properties").
- Copy symbols exactly: Greek letters as \\nu, \\mu, \\alpha… (never v for \\nu), primes, \\hbar.
- Output only the Markdown, with no commentary and no code fences."""

READ_USER = "Transcribe this page."
PAGE_MARK = "<!-- page {n} -->"


def read_pdf_user(pages: list[int]) -> str:
    """For backends that take the whole PDF at once (Gemini): one request, split after."""
    marks = ", ".join(PAGE_MARK.format(n=n) for n in pages)
    return (
        f"This PDF has {len(pages)} page(s). Transcribe every page in order. Start each page "
        f"with its marker on its own line ({marks}), using the original page numbers."
    )


# Dedicated OCR models (DeepSeek-OCR, olmOCR, Nanonets-OCR…) are trained on a
# fixed instruction and ignore long system prompts.
OCR_MODEL_HINTS = ("ocr",)
OCR_USER = "Convert the document to markdown."

DENSITY_WORDS = {"few": 220, "normal": 110, "thorough": 60}

FOCUS = {
    "balanced": "definitions, laws, key equations and the main concepts",
    "equations": "equations and laws: what each one states, its symbols, and when it applies",
    "definitions": "definitions of terms and quantities, with units where given",
    "concepts": "conceptual understanding: why things happen, cause and effect, comparisons",
}

CARD_SYSTEM = """\
You write Anki flashcards for a university physics student from the study material they give you.

Rules:
- Each card tests ONE atomic fact, definition, law, equation or idea.
- A card must make sense on its own, without seeing the material. Name the topic when the \
question would otherwise be ambiguous.
- Prefer precise questions ("What is…", "State…", "Write the equation for…", "Why does…"). \
Avoid yes/no questions and answers that list more than three items.
- Keep answers short and never restate the question: give just the fact, formula or reason. \
Put supporting detail in an extra field if there is one; never repeat the answer there, leave it \
empty instead.
- Use LaTeX for ALL mathematics: inline $...$, display $$...$$. Never use \\( \\) or \\[ \\]. \
Write $x$ not $ x $, and no \\text{{ }} spacers.
- Use only facts from the material. Do not invent values, names or results.
- Copy mathematics exactly as the material writes it: never drop terms, rename symbols, \
simplify, or change the order of a derivative.
{labels}{macros}
{note_type}
{reply_format}"""

JSON_FORMAT = """\
Reply with JSON only, in exactly this shape:
{shape}
Example of one good card (a different topic, for style only):
{example}"""

# Small local models garble LaTeX when they have to escape every backslash in
# JSON, so they write plain text that the app's block parser reads instead.
BLOCK_FORMAT = """\
Reply with the cards only, in exactly this plain-text format: each field on a line starting \
with its name and a colon, and a line with three dashes between cards. This is plain text, \
not JSON: write LaTeX normally with single backslashes (\\frac, \\dagger, \\langle).
{shape}
Example of one good card (a different topic, for style only):
{example}"""


LABEL_RULE = """\
- Equations in the material are labelled like [E1]. To put one on a card, write only its \
label, e.g. an answer of just [E3], or "The Hermite recurrence: [E3]". Do not retype a labelled equation.
"""


def is_ocr_model(model: str) -> bool:
    return any(h in model.lower() for h in OCR_MODEL_HINTS)


def read_messages(model: str) -> tuple[str | None, str]:
    """(system, user) for transcribing one page image."""
    if is_ocr_model(model):
        return None, OCR_USER
    return READ_SYSTEM, READ_USER


def macro_signature(m: MacroDef) -> str:
    letters = "abcdefghi"
    parts = [m.name]
    for i in range(m.args):
        arg = letters[i]
        parts.append(f"[{arg}]" if i == 0 and m.optional is not None else f"{{{arg}}}")
    return "".join(parts)


def macro_rules(macros: list[MacroDef]) -> str:
    if not macros:
        return ""
    lines = [f"  {macro_signature(m)} = {m.body}" for m in macros]
    return (
        "- These LaTeX macros are defined; use them where they fit "
        "(#1, #2… are the arguments, an argument in [ ] is optional):\n" + "\n".join(lines)
    )


def note_type_rules(note_type: str, fields: list[str]) -> str:
    if note_type == "cloze":
        return (
            f'- Cloze cards: put the whole statement in "{fields[0]}" and hide the key part '
            "with {{c1::…}} (use c2, c3… for further deletions in the same card). Never put "
            "a cloze deletion inside $…$; wrap the whole formula: {{c1::$E=mc^2$}}."
            + (f' "{fields[1]}" is optional context.' if len(fields) > 1 else "")
        )
    front, rest = fields[0], fields[1:]
    text = f'- "{front}" is the question side.'
    if rest:
        text += f' "{rest[0]}" is the answer.'
    if len(rest) > 1:
        others = ", ".join(f'"{f}"' for f in rest[1:])
        text += f" {others} may be left empty if the material has nothing for them."
    return text


def card_shape(fields: list[str]) -> str:
    inner = ", ".join(f'"{f}": "..."' for f in fields)
    return f'{{"cards": [{{{inner}}}, ...]}}'


def block_shape(fields: list[str]) -> str:
    card = "\n".join(f"{f}: ..." for f in fields)
    return f"{card}\n---\n{card}"


def example_card(fields: list[str], note_type: str = "basic", output: str = "json") -> str:
    if note_type == "cloze":
        values = [
            "The de Broglie wavelength of a particle with momentum $p$ is {{c1::$\\lambda = h/p$}}."
        ]
    else:
        values = [
            "What is the de Broglie wavelength of a particle with momentum $p$?",
            "$\\lambda = h/p$",
        ]
    card = {f: (values[i] if i < len(values) else "") for i, f in enumerate(fields)}
    if output == "block":
        return "\n".join(f"{f}: {v}".rstrip() for f, v in card.items())
    return json.dumps(card, ensure_ascii=False)


def target_count(material: str, density: str = "normal") -> int:
    words = len(material.split())
    return max(1, min(40, round(words / DENSITY_WORDS.get(density, 110))))


def card_messages(
    material: str,
    fields: list[str],
    *,
    note_type: str = "basic",
    macros: list[MacroDef] | None = None,
    density: str = "normal",
    focus: str = "balanced",
    avoid: list[str] | None = None,
    labelled: bool = False,
    output: str = "json",
) -> tuple[str, str]:
    """(system, user) for writing cards from a chunk of Markdown.

    ``labelled``: the material's equations carry ``[E1]``-style labels that the
    model should use instead of retyping. ``macros`` are only offered to the
    model when given (retyping math into macros is where small models slip).
    ``output``: ``"json"`` (for schema-constrained backends) or ``"block"``.
    """
    if output == "block":
        reply_format = BLOCK_FORMAT.format(
            shape=block_shape(fields), example=example_card(fields, note_type, "block")
        )
    else:
        reply_format = JSON_FORMAT.format(
            shape=card_shape(fields), example=example_card(fields, note_type)
        )
    system = CARD_SYSTEM.format(
        labels=LABEL_RULE if labelled else "",
        macros=macro_rules(macros or []),
        note_type=note_type_rules(note_type, fields),
        reply_format=reply_format,
    )
    user = [
        f"Write about {target_count(material, density)} cards. Focus on {FOCUS.get(focus, FOCUS['balanced'])}.",
    ]
    if avoid:
        user.append(
            "Cards already written (don't repeat these):\n" + "\n".join(f"- {a}" for a in avoid)
        )
    user.append(f"Material:\n<<<\n{material.strip()}\n>>>")
    return system, "\n\n".join(user)
