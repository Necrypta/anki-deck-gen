import sqlite3
import zipfile

from ankigen.api import Api
from ankigen.deck import build_apkg, build_model
from ankigen.latex import DEFAULT_MACROS
from ankigen.models import Card, DeckSpec


def _notes(apkg, tmp_path):
    with zipfile.ZipFile(apkg) as z:
        z.extract("collection.anki2", tmp_path)
    con = sqlite3.connect(tmp_path / "collection.anki2")
    try:
        return con.execute("select flds, tags, mid from notes").fetchall()
    finally:
        con.close()


def test_build_basic_apkg(tmp_path):
    spec = DeckSpec(
        name="Physics::Mechanics",
        cards=[
            Card({"Front": "Newton II", "Back": "$F=ma$"}, tags=["newton"]),
            Card({"Front": "KE", "Back": r"$\frac12 mv^2$", "Extra": "scalar"}),
            Card({"Front": "", "Back": "skipped: empty front"}),
        ],
        tags=["mech"],
        macros=DEFAULT_MACROS,
    )
    out = build_apkg(spec, tmp_path / "deck")
    assert out.suffix == ".apkg" and out.exists()
    notes = _notes(out, tmp_path)
    assert len(notes) == 2
    flds = sorted(n[0] for n in notes)
    assert r"KE\x1f\(\frac12 mv^2\)\x1fscalar".replace(r"\x1f", "\x1f") in flds
    assert any("mech" in n[1] and "newton" in n[1] for n in notes)
    assert {n[2] for n in notes} == {build_model(spec).model_id}


def test_stable_ids_across_builds():
    a = DeckSpec(name="X", cards=[Card({"Front": "a", "Back": "b"})])
    b = DeckSpec(name="X", cards=[Card({"Front": "c", "Back": "d"})])
    assert build_model(a).model_id == build_model(b).model_id


def test_reversed_and_cloze_models():
    rev = build_model(DeckSpec(name="R", note_type="reversed"))
    assert len(rev.templates) == 2
    cloze = build_model(DeckSpec(name="C", note_type="cloze", fields=["Text", "Extra"]))
    assert "cloze:Text" in cloze.templates[0]["qfmt"]


def test_custom_fields(tmp_path):
    spec = DeckSpec(
        name="Custom", note_type="custom", fields=["Term", "Formula", "Units"],
        cards=[Card({"Term": "Force", "Formula": "$F=ma$", "Units": "N"})],
    )
    notes = _notes(build_apkg(spec, tmp_path / "c.apkg"), tmp_path)
    assert notes[0][0].split("\x1f") == ["Force", r"\(F=ma\)", "N"]


def test_api_write_and_session(tmp_path):
    api = Api(data_dir=tmp_path)
    res = api.write_deck(
        {"name": "API", "note_type": "basic", "fields": ["Front", "Back", "Extra"],
         "cards": [{"fields": {"Front": "q", "Back": "a"}, "tags": []}]},
        str(tmp_path / "api.apkg"),
    )
    assert res["ok"] and res["count"] == 1
    assert api.save_session({"cards": [1]})["ok"]
    assert api.load_session()["session"] == {"cards": [1]}
    assert api.parse_text("Front: a\nBack: b", "block")["cards"][0]["fields"]["Front"] == "a"
    assert api.write_deck({"name": "bad", "note_type": "nope"}, "x")["ok"] is False


def test_cli_example(tmp_path):
    from pathlib import Path

    from ankigen.cli import main

    src = Path(__file__).parent.parent / "examples" / "physics_sample.txt"
    out = tmp_path / "sample.apkg"
    assert main([str(src), "-o", str(out)]) == 0
    notes = _notes(out, tmp_path)
    assert len(notes) == 8
    assert any("maxwell" in n[1] and "sample" in n[1] for n in notes)
