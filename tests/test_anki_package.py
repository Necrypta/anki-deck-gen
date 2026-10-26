import copy
import sqlite3
import zipfile
from pathlib import Path

import pytest

from ankigen import anki_package as ap
from ankigen.api import Api
from ankigen.latex import DEFAULT_MACROS, expand_field_macros, expand_macros

FIXTURES = Path(__file__).parent / "fixtures"
BOTH = ["physics-modern.apkg", "physics-legacy.apkg"]


def _db(path, tmp_path):
    """The collection inside an .apkg, opened for checking."""
    with zipfile.ZipFile(path) as z:
        name = ap._collection_name(z)
        data = ap._decompress(z.read(name))
    f = tmp_path / f"check-{path.stem}.db"
    f.write_bytes(data)
    db = sqlite3.connect(f)
    db.create_collation("unicase", lambda a, b: (a > b) - (a < b))
    return db


def _deck(decks, name):
    return next(d for d in decks if d["name"] == name)


@pytest.mark.parametrize("fixture", BOTH)
def test_read_package(fixture):
    pkg = ap.read_package(FIXTURES / fixture)
    assert pkg.modern == fixture.startswith("physics-modern")
    assert pkg.media == {"0": "wave.png"}
    decks = ap.package_decks(pkg, "abc")
    assert [d["name"] for d in decks] == [
        "Physics · Basic",
        "Physics · Cloze",
        "Physics · Term",
        "Physics::Waves",
    ]
    basic = _deck(decks, "Physics · Basic")
    assert basic["noteType"] == "custom" and basic["fields"] == ["Front", "Back"]
    assert basic["cards"][0]["fields"] == {"Front": "Mass–energy equivalence", "Back": "$E = mc^2$"}
    assert basic["cards"][1]["fields"]["Back"] == "A measure of disorder\n(in J/K)"
    assert basic["cards"][0]["tags"] == ["relativity"] and basic["cards"][0]["guid"]
    assert _deck(decks, "Physics · Cloze")["noteType"] == "cloze"
    waves = _deck(decks, "Physics::Waves")["cards"]
    assert waves[0]["fields"]["Back"] == '<img src="wave.png">'
    assert waves[1]["fields"]["Back"].startswith("$$\\frac{\\partial^2 u}")
    assert _deck(decks, "Physics · Term")["source"]["notetypeName"] == "Term"


def test_field_conversion():
    assert ap.anki_to_app(r"costs $5, \(a &lt; b\)") == r"costs \$5, $a < b$"
    assert ap.anki_to_app("<div>one</div><div>two</div>") == "one\ntwo"
    assert ap.anki_to_app("a &amp; b") == "a & b"
    assert ap.anki_to_app("<b>a</b> &amp; b") == "<b>a</b> &amp; b"  # with HTML, entities stay
    assert (
        ap.app_to_anki(r"costs \$5 and $\vb{F}$", DEFAULT_MACROS) == r"costs $5 and \(\mathbf{F}\)"
    )
    assert ap.cloze_ords(["{{c1::a}} {{c3::b}}", "{{c1::c}}"]) == [0, 2]
    assert ap.template_fields(
        "{{#Formula}}{{Formula}}{{/Formula}} {{text:Term}} {{FrontSide}}"
    ) == [
        "Formula",
        "Term",
    ]
    assert ap.field_checksum("What is <b>entropy</b>?") == 2518912460  # Anki's own value


def test_expand_macros():
    assert expand_macros(r"\dv[2]{y}{x}", DEFAULT_MACROS) == r"\frac{d^{2} y}{d x^{2}}"
    assert (
        expand_field_macros(r"\$5 and $\vb F$ and $\vb$", DEFAULT_MACROS)
        == r"\$5 and $\mathbf{F}$ and $\vb$"
    )


@pytest.mark.parametrize("fixture", BOTH)
def test_unchanged_export_keeps_everything(fixture, tmp_path):
    src = FIXTURES / fixture
    out = tmp_path / "out.apkg"
    changes = ap.write_package(src, out, ap.package_decks(ap.read_package(src), "p"))
    assert changes.to_dict() == {"updated": 0, "added": 0, "deleted": 0, "new_cards": 0}
    a, b = _db(src, tmp_path), _db(out, tmp_path)
    for q in (
        "select * from notes order by id",
        "select * from cards order by id",
        "select * from revlog order by id",
    ):
        assert a.execute(q).fetchall() == b.execute(q).fetchall()
    with zipfile.ZipFile(src) as za, zipfile.ZipFile(out) as zb:
        assert za.namelist() == zb.namelist()
        assert za.read("media") == zb.read("media") and za.read("0") == zb.read("0")


@pytest.mark.parametrize("fixture", BOTH)
def test_edit_add_delete(fixture, tmp_path):
    src = FIXTURES / fixture
    decks = ap.package_decks(ap.read_package(src), "p")
    basic = _deck(decks, "Physics · Basic")
    basic["cards"][1]["fields"]["Back"] = r"A measure of $\vb{disorder}$"
    basic["cards"][1]["tags"] = ["thermo"]
    basic["cards"].append(
        {"fields": {"Front": "<b>New</b> card", "Back": "$x$"}, "tags": [], "guid": "g-new-0001"}
    )
    _deck(decks, "Physics · Cloze")["cards"][0]["fields"]["Text"] += " {{c3::extra}}"
    term = _deck(decks, "Physics · Term")
    gone = term["cards"].pop()["noteId"]
    term["cards"].append(
        {
            "fields": {"Term": "Work", "Definition": "Force times distance", "Formula": "$W = Fd$"},
            "tags": [],
        }
    )
    untouched = copy.deepcopy(_deck(decks, "Physics::Waves"))

    out = tmp_path / "out.apkg"
    changes = ap.write_package(src, out, decks, DEFAULT_MACROS)
    assert changes.to_dict() == {"updated": 2, "added": 2, "deleted": 1, "new_cards": 4}

    before, after = _db(src, tmp_path), _db(out, tmp_path)
    nid = int(basic["cards"][1]["noteId"])
    flds, sfld, csum, tags = after.execute(
        "select flds, sfld, csum, tags from notes where id=?", (nid,)
    ).fetchone()
    assert flds == "What is <b>entropy</b>?\x1fA measure of \\(\\mathbf{disorder}\\)"
    assert sfld == "What is entropy?" and csum == 2518912460 and tags == " thermo "
    # The edited note keeps its cards and their scheduling.
    q = "select id, ord, type, queue, due, ivl, factor, reps from cards where nid=?"
    assert after.execute(q, (nid,)).fetchall() == before.execute(q, (nid,)).fetchall()
    new = after.execute("select id, csum, sfld from notes where guid='g-new-0001'").fetchone()
    assert new[1] == ap.field_checksum("New card") and new[2] == "New card"
    assert after.execute(
        "select type, queue, did from cards where nid=?", (new[0],)
    ).fetchall() == [(0, 0, int(basic["source"]["ankiDeckId"]))]
    work = after.execute("select id from notes where flds like 'Work%'").fetchone()[0]
    assert sorted(o for (o,) in after.execute("select ord from cards where nid=?", (work,))) == [
        0,
        1,
    ]
    cloze = int(_deck(decks, "Physics · Cloze")["cards"][0]["noteId"])
    assert sorted(o for (o,) in after.execute("select ord from cards where nid=?", (cloze,))) == [
        0,
        1,
        2,
    ]
    assert after.execute("select count(*) from notes where id=?", (int(gone),)).fetchone()[0] == 0
    assert after.execute("select count(*) from cards where nid=?", (int(gone),)).fetchone()[0] == 0
    # Other notes, and the review history, are untouched.
    for card in untouched["cards"]:
        q = "select * from notes where id=?"
        assert (
            after.execute(q, (int(card["noteId"]),)).fetchall()
            == before.execute(q, (int(card["noteId"]),)).fetchall()
        )
    assert (
        after.execute("select * from revlog").fetchall()
        == before.execute("select * from revlog").fetchall()
    )
    # Same layout as the original.
    with zipfile.ZipFile(out) as z:
        name = ap._collection_name(z)
        assert name == ("collection.anki21b" if "modern" in fixture else "collection.anki21")
        assert z.read(name).startswith(ap.ZSTD_MAGIC) == ("modern" in fixture)
    assert ap.read_package(out).notes  # and it reads back


def test_rejects_non_packages(tmp_path):
    bad = tmp_path / "x.apkg"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(ValueError, match="isn't an Anki package"):
        ap.read_package(bad)


def test_api_round_trip(tmp_path):
    api = Api(data_dir=tmp_path)
    res = api.import_apkg(str(FIXTURES / "physics-modern.apkg"))
    assert res["ok"], res
    pkg = res["package"]
    assert pkg["notes"] == 7 and pkg["media"] == 1 and pkg["format"] == "modern"
    assert api.media_data(pkg["id"], ["wave.png", "nope.png"])["media"]["wave.png"].startswith(
        "data:image/png;base64,"
    )
    decks = res["decks"]
    decks[0]["cards"][0]["fields"]["Back"] = "$E = mc^{2}$"
    out = api.write_package(pkg["id"], decks, str(tmp_path / "edited"), [])
    assert out["ok"] and out["path"].endswith("edited.apkg") and out["changes"]["updated"] == 1
    assert api.media_data("../etc", [])["ok"] is False
