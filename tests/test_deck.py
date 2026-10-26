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
    out, _ = build_apkg(spec, tmp_path / "deck")
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
        name="Custom",
        note_type="custom",
        fields=["Term", "Formula", "Units"],
        cards=[Card({"Term": "Force", "Formula": "$F=ma$", "Units": "N"})],
    )
    notes = _notes(build_apkg(spec, tmp_path / "c.apkg")[0], tmp_path)
    assert notes[0][0].split("\x1f") == ["Force", r"\(F=ma\)", "N"]


def test_api_write_and_session(tmp_path):
    api = Api(data_dir=tmp_path)
    res = api.write_deck(
        {
            "name": "API",
            "note_type": "basic",
            "fields": ["Front", "Back", "Extra"],
            "cards": [{"fields": {"Front": "q", "Back": "a"}, "tags": []}],
        },
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


def test_guid_survives_front_edits(tmp_path):
    import genanki

    api = Api(data_dir=tmp_path)
    deck = {
        "name": "D",
        "noteType": "basic",
        "fields": ["Front", "Back", "Extra"],
        "cards": [
            {"id": "c1", "fields": {"Front": "Old front", "Back": "a"}, "tags": []},
        ],
    }
    # A card from an older version gets the GUID its last export had…
    api.save_session({"version": 2, "decks": [deck]})
    card = api.load_session()["session"]["decks"][0]["cards"][0]
    assert card["guid"] == genanki.guid_for("D", "basic", "Old front")
    # …and keeps it after its front changes.
    card["fields"]["Front"] = "New front"
    spec = {
        "name": "D",
        "note_type": "basic",
        "fields": ["Front", "Back", "Extra"],
        "cards": [card],
    }
    res = api.write_deck(spec, str(tmp_path / "d.apkg"))
    assert res["guids"] == {}
    with zipfile.ZipFile(res["path"]) as z:
        z.extract("collection.anki2", tmp_path / "x")
    con = sqlite3.connect(tmp_path / "x" / "collection.anki2")
    assert con.execute("select guid from notes").fetchone()[0] == genanki.guid_for(
        "D", "basic", "Old front"
    )
    con.close()
    # A new card's GUID is handed back so the app can keep it.
    new = {**spec, "cards": [{"id": "c2", "fields": {"Front": "Q", "Back": "A"}, "tags": []}]}
    assert api.write_deck(new, str(tmp_path / "e.apkg"))["guids"] == {
        "c2": genanki.guid_for("D", "basic", "Q")
    }
