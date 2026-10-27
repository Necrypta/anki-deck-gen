"""Build the small .apkg files in tests/fixtures with real Anki.

Needs the official ``anki`` package (not an app dependency)::

    python -m venv .ankienv && .ankienv/bin/pip install anki
    .ankienv/bin/python scripts/make_apkg_fixtures.py

Writes ``physics-modern.apkg`` (the Anki 2.1.50+ default layout) and
``physics-legacy.apkg`` ("Support older Anki versions"), both with
scheduling, review history and media.
"""

from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path

from anki.collection import Collection, ExportAnkiPackageOptions
from anki.decks import DeckId

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
# A 1x1 PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def build(folder: Path) -> Collection:
    col = Collection(str(folder / "collection.anki2"))
    physics = col.decks.id("Physics")
    waves = col.decks.id("Physics::Waves")
    col.media.write_data("wave.png", PNG)

    basic = col.models.by_name("Basic")
    cloze = col.models.by_name("Cloze")

    # A custom note type with two templates, like many shared decks have.
    term = col.models.new("Term")
    for name in ("Term", "Definition", "Formula"):
        col.models.add_field(term, col.models.new_field(name))
    t1 = col.models.new_template("Recall")
    t1["qfmt"], t1["afmt"] = "{{Term}}", "{{FrontSide}}<hr id=answer>{{Definition}}"
    t2 = col.models.new_template("Formula")
    t2["qfmt"], t2["afmt"] = (
        "{{#Formula}}{{Formula}}{{/Formula}}",
        "{{FrontSide}}<hr id=answer>{{Term}}",
    )
    col.models.add_template(term, t1)
    col.models.add_template(term, t2)
    term["css"] = ".card { font-family: serif; }"
    col.models.add(term)
    term = col.models.by_name("Term")

    def add(model, deck, fields, tags=()):
        note = col.new_note(model)
        for k, v in fields.items():
            note[k] = v
        note.tags = list(tags)
        col.add_note(note, DeckId(deck))
        return note

    add(
        basic,
        physics,
        {"Front": "Mass–energy equivalence", "Back": r"\(E = mc^2\)"},
        ["relativity"],
    )
    add(
        basic,
        physics,
        {"Front": "What is <b>entropy</b>?", "Back": "A measure of disorder<br>(in J/K)"},
    )
    add(basic, waves, {"Front": "A sine wave", "Back": '<img src="wave.png">'}, ["waves"])
    add(
        basic,
        waves,
        {
            "Front": "Wave equation",
            "Back": r"\[\frac{\partial^2 u}{\partial t^2} = c^2 \nabla^2 u\]",
        },
    )
    add(
        cloze,
        physics,
        {
            "Text": "Newton's second law: {{c1::\\(F = ma\\)}} ({{c2::force}} equals mass times acceleration)",
            "Back Extra": "",
        },
    )
    add(
        term,
        physics,
        {"Term": "Momentum", "Definition": "Mass times velocity", "Formula": r"\(p = mv\)"},
    )
    add(
        term,
        physics,
        {"Term": "Inertia", "Definition": "Resistance to changes in motion", "Formula": ""},
    )

    # Study a few cards so there's scheduling and review history to keep.
    col.decks.select(physics)
    for ease in (3, 3, 4, 2):
        card = col.sched.getCard()
        if card is None:
            break
        card.start_timer()
        col.sched.answerCard(card, ease)
    return col


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        col = build(Path(tmp))
        for name, legacy in (("physics-modern.apkg", False), ("physics-legacy.apkg", True)):
            opts = ExportAnkiPackageOptions(
                with_scheduling=True, with_deck_configs=True, with_media=True, legacy=legacy
            )
            col.export_anki_package(out_path=str(OUT / name), options=opts, limit=None)
            print("wrote", OUT / name)
        col.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
