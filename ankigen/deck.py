"""Build ``.apkg`` files with genanki."""

from __future__ import annotations

import hashlib
from pathlib import Path

import genanki

from .latex import field_to_html, macro_preamble
from .models import DeckSpec

CARD_CSS = """\
.card {
  font-family: "Inter", -apple-system, "Segoe UI", system-ui, sans-serif;
  font-size: 20px;
  line-height: 1.5;
  text-align: center;
  color: #18181b;
  background: #ffffff;
  padding: 24px;
}
.nightMode .card, .card.nightMode { color: #e4e4e7; background: #18181b; }
hr#answer { border: none; border-top: 1px solid #e4e4e7; margin: 20px 0; }
.nightMode hr#answer { border-top-color: #3f3f46; }
.extra { margin-top: 16px; font-size: 16px; color: #71717a; }
.cloze { font-weight: 600; color: #4f46e5; }
.nightMode .cloze { color: #a5b4fc; }
"""


def stable_id(*parts: str) -> int:
    """Deterministic 31-bit-ish ID so re-exports update instead of duplicating."""
    digest = hashlib.sha1("\x1f".join(parts).encode()).digest()
    return (int.from_bytes(digest[:8], "big") % (1 << 30)) + (1 << 30)


def _extra_html(fields: list[str]) -> str:
    return "".join(f'{{{{#{f}}}}}<div class="extra">{{{{{f}}}}}</div>{{{{/{f}}}}}' for f in fields)


def build_model(spec: DeckSpec) -> genanki.Model:
    pre = macro_preamble(spec.macros)
    fields = spec.fields
    model_fields = [{"name": f} for f in fields]
    name = f"ADG {spec.note_type.title()} ({', '.join(fields)})"
    model_id = stable_id("model", name, pre)

    if spec.note_type == "cloze":
        text, rest = fields[0], fields[1:]
        templates = [
            {
                "name": "Cloze",
                "qfmt": pre + f"{{{{cloze:{text}}}}}",
                "afmt": pre + f"{{{{cloze:{text}}}}}" + _extra_html(rest),
            }
        ]
        return genanki.Model(
            model_id,
            name,
            fields=model_fields,
            templates=templates,
            css=CARD_CSS,
            model_type=genanki.Model.CLOZE,
        )

    if len(fields) < 2:
        raise ValueError("Basic and custom note types need at least two fields")

    front, back, rest = fields[0], fields[1], fields[2:]
    templates = [
        {
            "name": "Card 1",
            "qfmt": pre + f"{{{{{front}}}}}",
            "afmt": pre + f'{{{{FrontSide}}}}<hr id="answer">{{{{{back}}}}}' + _extra_html(rest),
        }
    ]
    if spec.note_type == "reversed":
        templates.append(
            {
                "name": "Card 2",
                "qfmt": pre + f"{{{{{back}}}}}",
                "afmt": pre
                + f'{{{{FrontSide}}}}<hr id="answer">{{{{{front}}}}}'
                + _extra_html(rest),
            }
        )
    return genanki.Model(model_id, name, fields=model_fields, templates=templates, css=CARD_CSS)


def _clean_tag(tag: str) -> str:
    return "_".join(tag.split())


def build_deck(spec: DeckSpec) -> genanki.Deck:
    model = build_model(spec)
    deck = genanki.Deck(stable_id("deck", spec.name), spec.name)
    for card in spec.cards:
        values = [field_to_html(card.fields.get(f, "")) for f in spec.fields]
        if not values[0].strip():
            continue
        tags = sorted({_clean_tag(t) for t in [*spec.tags, *card.tags] if t.strip()})
        guid = genanki.guid_for(spec.name, spec.note_type, card.fields.get(spec.fields[0], ""))
        deck.add_note(genanki.Note(model=model, fields=values, tags=tags, guid=guid))
    return deck


def build_apkg(spec: DeckSpec, path: str | Path) -> Path:
    path = Path(path)
    if path.suffix.lower() != ".apkg":
        path = path.with_suffix(".apkg")
    path.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(build_deck(spec)).write_to_file(str(path))
    return path
