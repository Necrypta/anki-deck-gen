"""Open an Anki ``.apkg``, and write it back with edits, keeping its scheduling.

An ``.apkg`` is a zip holding an SQLite collection: ``notes`` have the field
content, ``cards`` the scheduling (interval, due date, ease, lapses…) and
``revlog`` the review history, alongside numbered media files. Two layouts
exist:

* **legacy**: ``collection.anki21`` (or ``.anki2``), schema 11, note types and
  decks as JSON in the ``col`` table, a JSON ``media`` map, plain media files;
* **modern** (Anki 2.1.50+'s default): ``collection.anki21b``, schema 18,
  zstd-compressed, note types and decks in their own tables, and a
  zstd-compressed protobuf ``media`` map and media files.

genanki can only write brand-new cards, so instead :func:`write_package`
copies the original file and patches its notes: edited notes are updated,
new ones added (as new cards), removed ones deleted. Everything else (note
types, templates, CSS, deck options, other cards' scheduling, review
history, media) is copied untouched, in the layout it came in.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import secrets
import shutil
import sqlite3
import tempfile
import time
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .latex import expand_field_macros, field_to_html

COLLECTIONS = ("collection.anki21b", "collection.anki21", "collection.anki2")
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
MAX_MEDIA_BYTES = 8_000_000  # per file, for previews


# ------------------------------------------------------------------ protobuf


def _varint(b: bytes, i: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = b[i]
        i += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            return result, i


def _proto(b: bytes) -> list[tuple[int, Any]]:
    """Fields of a protobuf message as ``(number, value)``; enough for Anki's configs."""
    out: list[tuple[int, Any]] = []
    i = 0
    while i < len(b):
        key, i = _varint(b, i)
        num, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(b, i)
        elif wire == 2:
            size, i = _varint(b, i)
            value, i = b[i : i + size], i + size
        elif wire == 5:
            value, i = b[i : i + 4], i + 4
        elif wire == 1:
            value, i = b[i : i + 8], i + 8
        else:
            raise ValueError(f"Unsupported protobuf wire type {wire}")
        out.append((num, value))
    return out


def _first(fields: list[tuple[int, Any]], num: int, default: Any = None) -> Any:
    return next((v for n, v in fields if n == num), default)


# ------------------------------------------------------------------ zstd


def _zstd():
    import zstandard

    return zstandard


def _decompress(data: bytes) -> bytes:
    if not data.startswith(ZSTD_MAGIC):
        return data
    with _zstd().ZstdDecompressor().stream_reader(data) as reader:
        return reader.read()


def _compress(data: bytes) -> bytes:
    return _zstd().ZstdCompressor().compress(data)


# ------------------------------------------------------------------ fields


def strip_html_media(text: str) -> str:
    """Anki's ``strip_html_preserving_media_filenames``: for ``sfld`` and ``csum``."""
    text = re.sub(r"<img[^>]*?src=[\"']?([^\"'> ]+)[^>]*>", r" \1 ", text, flags=re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<(style|script).*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<.*?>", "", text, flags=re.DOTALL)
    return html.unescape(text).replace("\xa0", " ").strip()


def field_checksum(first_field: str) -> int:
    return int(hashlib.sha1(strip_html_media(first_field).encode()).hexdigest()[:8], 16)


_TAG = re.compile(r"<[a-zA-Z/!][^>]*>")


def anki_to_app(value: str) -> str:
    r"""An Anki field as the app writes fields: ``$…$`` math and plain line breaks.

    Other HTML (``<b>``, ``<img>``…) is kept; the app previews a safe subset.
    """
    s = value.replace("\r\n", "\n")
    # A literal $ in Anki would read as math in the app.
    s = re.sub(r"(?<!\\)\$", r"\\$", s)

    def math(m: re.Match) -> str:
        body = html.unescape(m.group(2)).replace("\xa0", " ")
        return f"$${body}$$" if m.group(1) == "[" else f"${body}$"

    s = re.sub(r"\\([(\[])(.*?)\\[)\]]", math, s, flags=re.DOTALL)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    # Anki's editor wraps lines in <div>s: one line each.
    s = re.sub(r"</div>\s*<div>|<div>|</div>", "\n", s, flags=re.IGNORECASE)
    s = s.strip("\n")
    s = s.replace("&nbsp;", " ")
    if not _TAG.search(s):
        s = html.unescape(s)
    return s


def app_to_anki(text: str, macros: Any) -> str:
    return field_to_html(expand_field_macros(text, macros))


def content_hash(fields: list[str], tags: list[str]) -> str:
    """Identifies a note's content as the app saw it on import; unchanged notes aren't rewritten."""
    joined = "\x1f".join(fields) + "\x1e" + " ".join(sorted(tags))
    return hashlib.sha1(joined.encode()).hexdigest()[:16]


_CLOZE = re.compile(r"\{\{c(\d+)::")


def cloze_ords(fields: list[str]) -> list[int]:
    return sorted({int(n) - 1 for f in fields for n in _CLOZE.findall(f) if int(n) > 0})


def template_fields(qfmt: str) -> list[str]:
    """Field names a card template's front refers to (roughly, as Anki does)."""
    names = []
    for ref in re.findall(r"\{\{([^{}]+)\}\}", qfmt):
        ref = ref.strip()
        if ref[:1] in "#^/":
            continue
        name = ref.split(":")[-1].strip()
        if name and name != "FrontSide":
            names.append(name)
    return names


# ------------------------------------------------------------------ reading


@dataclass
class Notetype:
    id: int
    name: str
    cloze: bool
    fields: list[str]
    templates: list[str]  # front templates, by ord
    sort_idx: int = 0


@dataclass
class Note:
    id: int
    guid: str
    mid: int
    mod: int
    fields: list[str]
    tags: list[str]
    deck_id: int  # deck of its first card


@dataclass
class Package:
    collection: str  # name inside the zip
    modern: bool
    notetypes: dict[int, Notetype]
    decks: dict[int, str]  # id → name, "A::B"
    notes: list[Note]
    media: dict[str, str] = field(default_factory=dict)  # zip entry → file name


@contextmanager
def _open_db(data: bytes) -> Iterator[tuple[sqlite3.Connection, Path]]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "collection.db"
        path.write_bytes(data)
        db = sqlite3.connect(path)
        # Schema 18 indexes some names with Anki's case-insensitive collation.
        db.create_collation(
            "unicase", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower())
        )
        try:
            yield db, path
        finally:
            db.close()


def _collection_name(z: zipfile.ZipFile) -> str:
    names = set(z.namelist())
    for name in COLLECTIONS:
        if name in names:
            return name
    raise ValueError("This isn't an Anki package: there's no collection inside")


def _media_map(z: zipfile.ZipFile) -> dict[str, str]:
    if "media" not in z.namelist():
        return {}
    raw = z.read("media")
    if raw.startswith(ZSTD_MAGIC):
        entries = [_proto(v) for n, v in _proto(_decompress(raw)) if n == 1]
        return {str(i): _first(e, 1, b"").decode() for i, e in enumerate(entries)}
    data = json.loads(raw.decode() or "{}")
    return {str(k): str(v) for k, v in data.items()}


def _notetypes(db: sqlite3.Connection, modern: bool) -> dict[int, Notetype]:
    out: dict[int, Notetype] = {}
    if modern:
        for ntid, name, config in db.execute("select id, name, config from notetypes"):
            cfg = _proto(config)
            fields = [
                r[0]
                for r in db.execute("select name from fields where ntid=? order by ord", (ntid,))
            ]
            templates = [
                (_first(_proto(c), 1, b"") or b"").decode()
                for (c,) in db.execute(
                    "select config from templates where ntid=? order by ord", (ntid,)
                )
            ]
            out[ntid] = Notetype(
                ntid, name, _first(cfg, 1, 0) == 1, fields, templates, _first(cfg, 2, 0)
            )
        return out
    models = json.loads(db.execute("select models from col").fetchone()[0])
    for key, m in models.items():
        out[int(key)] = Notetype(
            int(key),
            m["name"],
            m.get("type") == 1,
            [f["name"] for f in sorted(m["flds"], key=lambda f: f["ord"])],
            [t["qfmt"] for t in sorted(m["tmpls"], key=lambda t: t["ord"])],
            int(m.get("sortf", 0)),
        )
    return out


def _decks(db: sqlite3.Connection, modern: bool) -> dict[int, str]:
    if modern:
        return {i: n.replace("\x1f", "::") for i, n in db.execute("select id, name from decks")}
    decks = json.loads(db.execute("select decks from col").fetchone()[0])
    return {int(k): v["name"] for k, v in decks.items()}


def read_package(path: str | Path) -> Package:
    with zipfile.ZipFile(path) as z:
        name = _collection_name(z)
        data = _decompress(z.read(name))
        media = _media_map(z)
    modern = name.endswith("anki21b")
    with _open_db(data) as (db, _):
        notetypes = _notetypes(db, modern)
        decks = _decks(db, modern)
        # SQLite takes bare columns from the min() row: each note's first card.
        first_deck = {
            nid: did
            for nid, did, _ in db.execute("select nid, did, min(ord) from cards group by nid")
        }
        notes = [
            Note(nid, guid, mid, mod, flds.split("\x1f"), tags.split(), first_deck.get(nid, 1))
            for nid, guid, mid, mod, flds, tags in db.execute(
                "select id, guid, mid, mod, flds, tags from notes order by id"
            )
        ]
    if (
        name == "collection.anki2"
        and len(notes) == 1
        and "update to the latest Anki" in notes[0].fields[0]
    ):
        raise ValueError(
            "This package needs a newer reader: re-export it from Anki with “Support older Anki versions” ticked"
        )
    return Package(name, modern, notetypes, decks, notes, media)


def extract_media(path: str | Path, folder: Path, media: dict[str, str]) -> list[str]:
    """Write the package's media into ``folder``; returns the file names."""
    folder.mkdir(parents=True, exist_ok=True)
    names = []
    with zipfile.ZipFile(path) as z:
        entries = set(z.namelist())
        for entry, name in media.items():
            safe = Path(name).name
            if entry not in entries or not safe or safe != name:
                continue
            (folder / safe).write_bytes(_decompress(z.read(entry)))
            names.append(safe)
    return names


# ------------------------------------------------------------------ app decks


def package_decks(pkg: Package, package_id: str) -> list[dict[str, Any]]:
    """One app deck per (Anki deck, note type) pair, ready for the frontend."""
    groups: dict[tuple[int, int], list[Note]] = {}
    for note in pkg.notes:
        if note.mid in pkg.notetypes:
            groups.setdefault((note.deck_id, note.mid), []).append(note)
    per_deck: dict[int, int] = {}
    for did, _ in groups:
        per_deck[did] = per_deck.get(did, 0) + 1
    out = []
    for (did, mid), notes in sorted(
        groups.items(), key=lambda g: (pkg.decks.get(g[0][0], ""), g[0][1])
    ):
        nt = pkg.notetypes[mid]
        name = pkg.decks.get(did, "Imported")
        if per_deck[did] > 1:
            name = f"{name} · {nt.name}"
        cards = []
        for note in notes:
            values = [anki_to_app(v) for v in note.fields]
            values += [""] * (len(nt.fields) - len(values))
            cards.append(
                {
                    "fields": dict(zip(nt.fields, values, strict=False)),
                    "tags": note.tags,
                    "guid": note.guid,
                    "noteId": str(note.id),
                    "original": content_hash(values[: len(nt.fields)], note.tags),
                }
            )
        out.append(
            {
                "name": name,
                "noteType": "cloze" if nt.cloze else "custom",
                "fields": nt.fields,
                "cards": cards,
                "source": {
                    "packageId": package_id,
                    "notetypeId": str(mid),
                    "notetypeName": nt.name,
                    "ankiDeckId": str(did),
                    "format": "modern" if pkg.modern else "legacy",
                },
            }
        )
    return out


# ------------------------------------------------------------------ writing


@dataclass
class Changes:
    updated: int = 0
    added: int = 0
    deleted: int = 0
    new_cards: int = 0

    def to_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


def _ids(db: sqlite3.Connection, table: str) -> Iterator[int]:
    """Fresh ids above every existing one (Anki uses epoch milliseconds)."""
    last = max(
        db.execute(f"select coalesce(max(id), 0) from {table}").fetchone()[0],
        int(time.time() * 1000),
    )
    while True:
        last += 1
        yield last


def _guid() -> str:
    return secrets.token_urlsafe(8)[:10]


def _cards_wanted(nt: Notetype, fields: list[str]) -> list[int]:
    if nt.cloze:
        return cloze_ords(fields) or [0]
    filled = {n for n, v in zip(nt.fields, fields, strict=False) if strip_html_media(v)}
    ords = [i for i, q in enumerate(nt.templates) if any(f in filled for f in template_fields(q))]
    return ords or [0]


def write_package(
    original: str | Path, out: str | Path, decks: list[dict[str, Any]], macros: Any = None
) -> Changes:
    """Write ``original`` to ``out`` with the notes of the app ``decks`` applied.

    Each deck is one (Anki deck, note type) group from :func:`package_decks`.
    Notes of groups that aren't passed are left alone.
    """
    pkg = read_package(original)
    by_id = {n.id: n for n in pkg.notes}
    changes = Changes()
    now = int(time.time())
    with zipfile.ZipFile(original) as z:
        data = _decompress(z.read(pkg.collection))
    with _open_db(data) as (db, db_path):
        note_ids, card_ids = _ids(db, "notes"), _ids(db, "cards")
        due = db.execute("select coalesce(max(due), 0) from cards where type = 0").fetchone()[0]
        for deck in decks:
            src = deck["source"]
            mid, did = int(src["notetypeId"]), int(src["ankiDeckId"])
            nt = pkg.notetypes.get(mid)
            if nt is None:
                raise ValueError(
                    f"The note type “{src.get('notetypeName', mid)}” isn't in the original package"
                )
            group = {n.id for n in pkg.notes if n.mid == mid and n.deck_id == did}
            kept: set[int] = set()
            for card in deck.get("cards", []):
                app_fields = [str(card.get("fields", {}).get(f, "")) for f in nt.fields]
                tags = sorted({"_".join(t.split()) for t in card.get("tags", []) if str(t).strip()})
                nid = int(card["noteId"]) if str(card.get("noteId", "")).isdigit() else None
                if nid is not None and nid in by_id:
                    kept.add(nid)
                    if card.get("original") == content_hash(app_fields, card.get("tags", [])):
                        continue  # untouched: keep it byte for byte
                    values = [app_to_anki(v, macros) for v in app_fields]
                    db.execute(
                        "update notes set flds=?, sfld=?, csum=?, tags=?, mod=?, usn=-1 where id=?",
                        (
                            "\x1f".join(values),
                            strip_html_media(
                                values[nt.sort_idx] if nt.sort_idx < len(values) else ""
                            ),
                            field_checksum(values[0]),
                            f" {' '.join(tags)} " if tags else "",
                            now,
                            nid,
                        ),
                    )
                    changes.updated += 1
                else:
                    if not any(v.strip() for v in app_fields):
                        continue
                    values = [app_to_anki(v, macros) for v in app_fields]
                    nid = next(note_ids)
                    db.execute(
                        "insert into notes (id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)"
                        " values (?, ?, ?, ?, -1, ?, ?, ?, ?, 0, '')",
                        (
                            nid,
                            str(card.get("guid") or _guid()),
                            mid,
                            now,
                            f" {' '.join(tags)} " if tags else "",
                            "\x1f".join(values),
                            strip_html_media(
                                values[nt.sort_idx] if nt.sort_idx < len(values) else ""
                            ),
                            field_checksum(values[0]),
                        ),
                    )
                    changes.added += 1
                have = {o for (o,) in db.execute("select ord from cards where nid=?", (nid,))}
                for ord_ in _cards_wanted(nt, values):
                    if ord_ in have:
                        continue
                    due += 1
                    db.execute(
                        "insert into cards (id, nid, did, ord, mod, usn, type, queue, due, ivl, factor,"
                        " reps, lapses, left, odue, odid, flags, data)"
                        " values (?, ?, ?, ?, ?, -1, 0, 0, ?, 0, 0, 0, 0, 0, 0, 0, 0, '')",
                        (next(card_ids), nid, did, ord_, now, due),
                    )
                    changes.new_cards += 1
            removed = sorted(group - kept)
            for nid in removed:
                db.execute("delete from cards where nid=?", (nid,))
                db.execute("delete from notes where id=?", (nid,))
            changes.deleted += len(removed)
        db.execute("update col set mod=?", (now * 1000,))
        db.commit()
        db.execute("vacuum")
        db.close()
        patched = db_path.read_bytes()

    out = Path(out)
    tmp = out.with_name(out.name + ".tmp")
    with (
        zipfile.ZipFile(original) as src_zip,
        zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for info in src_zip.infolist():
            if info.filename == pkg.collection:
                payload = _compress(patched) if pkg.modern else patched
                dst.writestr(
                    info.filename,
                    payload,
                    compress_type=zipfile.ZIP_STORED if pkg.modern else zipfile.ZIP_DEFLATED,
                )
            else:
                dst.writestr(info, src_zip.read(info.filename))
    tmp.replace(out)
    return changes


def copy_original(path: str | Path, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "original.apkg"
    if Path(path).resolve() != target.resolve():
        shutil.copyfile(path, target)
    return target


def package_id(path: str | Path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:12]
