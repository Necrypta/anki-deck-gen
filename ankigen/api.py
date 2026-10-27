"""Methods exposed to the frontend as ``window.pywebview.api.*``.

Every method returns plain JSON-serialisable data. Errors come back as
``{"ok": False, "error": "..."}`` instead of raising, so the UI can show them.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from . import anki_package
from .ai import catalog, secrets
from .ai.generate import Request, generate_cards
from .ai.jobs import Jobs
from .ai.reading import Reader, ReadRequest, describe_source, save_upload, thumbnails
from .deck import build_apkg, card_guid
from .latex import DEFAULT_MACROS, normalize_macros
from .models import NOTE_TYPES, Card, DeckSpec
from .parsers import PARSERS, parse_text


def app_data_dir() -> Path:
    """Where the autosaved session lives.

    Test and dev builds use a separate folder so trying out a PR build can
    never overwrite the work saved by the installed release.
    """
    from . import is_release

    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    path = Path(base) / ("AnkiDeckGenerator" if is_release() else "AnkiDeckGenerator-test")
    path.mkdir(parents=True, exist_ok=True)
    return path


KEEP_BACKUPS = 10


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def _give_guids(session: dict[str, Any]) -> None:
    """Store each card's export GUID, as earlier versions derived it from the front.

    From then on the GUID stays put when the front is edited.
    """
    for deck in session.get("decks") or []:
        if not isinstance(deck, dict) or not isinstance(deck.get("cards"), list):
            continue
        fields = deck.get("fields") or ["Front"]
        spec = DeckSpec(
            name=str(deck.get("name") or "").strip() or "Untitled",
            note_type=deck.get("noteType") if deck.get("noteType") in NOTE_TYPES else "basic",
            fields=list(fields),
        )
        for card in deck["cards"]:
            if (
                isinstance(card, dict)
                and not card.get("guid")
                and isinstance(card.get("fields"), dict)
            ):
                card["guid"] = card_guid(spec, Card.from_dict(card))


def _safe(fn: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return {"ok": True, **(fn(*args, **kwargs) or {})}
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI as a toast
            return {"ok": False, "error": str(exc)}

    return wrapper


def _dialog(kind: str) -> object:
    """pywebview 5 renamed OPEN_DIALOG/SAVE_DIALOG to FileDialog.OPEN/SAVE."""
    import webview

    fd = getattr(webview, "FileDialog", None)
    return getattr(fd, kind) if fd is not None else getattr(webview, f"{kind}_DIALOG")


class Api:
    def __init__(self, data_dir: Path | None = None) -> None:
        self._window: Any = None
        self._data_dir = data_dir
        self._jobs = Jobs()

    # pywebview tries to expose every public attribute, so keep these private.
    def _attach(self, window: Any) -> None:
        self._window = window

    @property
    def _dir(self) -> Path:
        return self._data_dir or app_data_dir()

    @property
    def _session_file(self) -> Path:
        return self._dir / "session.json"

    @_safe
    def info(self) -> dict[str, Any]:
        from . import __version__, build_label, is_release

        return {
            "version": __version__,
            "build": build_label(),
            "release": is_release(),
            "data_dir": str(self._data_dir or app_data_dir()),
            "formats": list(PARSERS),
            "default_macros": [m.to_dict() for m in DEFAULT_MACROS],
        }

    @_safe
    def parse_text(
        self, text: str, fmt: str = "block", options: dict | None = None
    ) -> dict[str, Any]:
        return parse_text(text, fmt, **(options or {})).to_dict()

    @_safe
    def open_text_file(self) -> dict[str, Any]:
        result = self._window.create_file_dialog(
            _dialog("OPEN"), file_types=("Text files (*.txt;*.tsv;*.csv;*.md)", "All files (*.*)")
        )
        if not result:
            return {"cancelled": True}
        path = Path(result[0])
        return {"path": str(path), "name": path.name, "text": path.read_text(encoding="utf-8-sig")}

    @_safe
    def export_deck(self, deck: dict[str, Any]) -> dict[str, Any]:
        """Ask where to save, then write the ``.apkg``."""
        spec = DeckSpec.from_dict(deck)
        if not spec.cards:
            raise ValueError("The deck has no cards yet")
        default = re.sub(r'[<>:"/\\|?*]+', "_", spec.name.split("::")[-1]).strip() or "deck"
        target = self._window.create_file_dialog(
            _dialog("SAVE"), save_filename=f"{default}.apkg", file_types=("Anki deck (*.apkg)",)
        )
        if not target:
            return {"cancelled": True}
        target = target[0] if isinstance(target, (list, tuple)) else target
        return self._write(spec, target)

    @_safe
    def write_deck(self, deck: dict[str, Any], path: str) -> dict[str, Any]:
        """Write without a dialog (used by tests and scripts)."""
        return self._write(DeckSpec.from_dict(deck), path)

    # ------------------------------------------------------------ .apkg files

    def _package_dir(self, package_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}", package_id or ""):
            raise ValueError("Unknown package")
        return self._dir / "packages" / package_id

    @_safe
    def open_apkg(self) -> dict[str, Any]:
        result = self._window.create_file_dialog(
            _dialog("OPEN"), file_types=("Anki package (*.apkg)", "All files (*.*)")
        )
        if not result:
            return {"cancelled": True}
        return self._import_apkg(Path(result[0]))

    @_safe
    def import_apkg(self, path: str) -> dict[str, Any]:
        return self._import_apkg(Path(path))

    @_safe
    def upload_apkg(self, name: str, data_b64: str) -> dict[str, Any]:
        """A dropped .apkg: the page can't pass a path, so it sends the bytes."""
        data = base64.b64decode(data_b64.split(",", 1)[-1])
        folder = self._dir / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f"upload-{hashlib.sha1(data).hexdigest()[:8]}.apkg"
        tmp.write_bytes(data)
        try:
            return self._import_apkg(tmp, name)
        finally:
            tmp.unlink(missing_ok=True)

    def _import_apkg(self, path: Path, name: str | None = None) -> dict[str, Any]:
        pkg = anki_package.read_package(path)
        pid = anki_package.package_id(path)
        folder = self._package_dir(pid)
        anki_package.copy_original(path, folder)
        media = anki_package.extract_media(path, folder / "media", pkg.media)
        name = name or path.name
        (folder / "info.json").write_text(json.dumps({"name": name}), encoding="utf-8")
        decks = anki_package.package_decks(pkg, pid)
        return {
            "decks": decks,
            "package": {
                "id": pid,
                "name": name,
                "notes": sum(len(d["cards"]) for d in decks),
                "media": len(media),
                "format": "modern" if pkg.modern else "legacy",
            },
        }

    @_safe
    def media_data(self, package_id: str, names: list[str]) -> dict[str, Any]:
        """Images of an opened package as data URLs, for previews."""
        folder = self._package_dir(package_id) / "media"
        out = {}
        for name in names[:50]:
            f = folder / Path(name).name
            mime = mimetypes.guess_type(f.name)[0] or ""
            if (
                mime.startswith("image/")
                and f.is_file()
                and f.stat().st_size <= anki_package.MAX_MEDIA_BYTES
            ):
                out[name] = f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()
        return {"media": out}

    @_safe
    def export_package(
        self, package_id: str, decks: list[dict[str, Any]], macros: Any = None
    ) -> dict[str, Any]:
        """Save an opened .apkg with the app's edits; scheduling and media are kept."""
        folder = self._package_dir(package_id)
        original = folder / "original.apkg"
        if not original.exists():
            raise ValueError("The original .apkg for this deck is gone; open it again to export")
        info = (
            json.loads((folder / "info.json").read_text("utf-8"))
            if (folder / "info.json").exists()
            else {}
        )
        target = self._window.create_file_dialog(
            _dialog("SAVE"),
            save_filename=info.get("name", "deck.apkg"),
            file_types=("Anki deck (*.apkg)",),
        )
        if not target:
            return {"cancelled": True}
        target = target[0] if isinstance(target, (list, tuple)) else target
        return self._write_package(original, target, decks, macros)

    @_safe
    def write_package(
        self, package_id: str, decks: list[dict[str, Any]], path: str, macros: Any = None
    ) -> dict[str, Any]:
        """Write without a dialog (used by tests and scripts)."""
        return self._write_package(
            self._package_dir(package_id) / "original.apkg", path, decks, macros
        )

    def _write_package(
        self, original: Path, path: str, decks: list[dict[str, Any]], macros: Any
    ) -> dict[str, Any]:
        out = Path(path)
        if out.suffix.lower() != ".apkg":
            out = out.with_suffix(".apkg")
        out.parent.mkdir(parents=True, exist_ok=True)
        changes = anki_package.write_package(original, out, decks, normalize_macros(macros))
        return {
            "path": str(out),
            "count": sum(len(d.get("cards", [])) for d in decks),
            "changes": changes.to_dict(),
        }

    def _write(self, spec: DeckSpec, path: str) -> dict[str, Any]:
        out, guids = build_apkg(spec, path)
        return {"path": str(out), "count": len(spec.cards), "guids": guids}

    @_safe
    def reveal(self, path: str) -> dict[str, Any]:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", str(Path(path).parent)])
        return {}

    @_safe
    def load_session(self) -> dict[str, Any]:
        """The saved session, after backing it up.

        A file that can't be read is moved aside rather than left for the next
        autosave to overwrite with an empty deck.
        """
        from . import __version__

        f = self._session_file
        if not f.exists():
            return {"session": None}
        try:
            session = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(session, dict):
                raise TypeError("not a session")
        except (OSError, ValueError, TypeError):
            kept = f.with_name(f"session-unreadable-{_stamp()}.json")
            f.replace(kept)
            return {
                "session": None,
                "notice": f"Your saved decks couldn't be read, so a new session was started. "
                f"The old file was kept as {kept.name} in the data folder.",
            }
        self._backup_session()
        _give_guids(session)
        saved_by = session.pop("savedBy", None)
        notice = None
        if isinstance(saved_by, str) and _version_key(saved_by) > _version_key(__version__):
            notice = (
                f"Your decks were last saved by a newer version ({saved_by}). "
                f"A backup was kept in the data folder's backups folder."
            )
        return {"session": session, "notice": notice}

    @_safe
    def save_session(self, session: dict[str, Any]) -> dict[str, Any]:
        from . import __version__

        f = self._session_file
        tmp = f.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({**session, "savedBy": __version__}, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(f)
        return {}

    def _backup_session(self) -> None:
        """Copy session.json into backups/, keeping the newest few distinct copies."""
        data = self._session_file.read_bytes()
        folder = self._dir / "backups"
        folder.mkdir(exist_ok=True)
        existing = sorted(folder.glob("session-*.json"))
        if existing and existing[-1].read_bytes() == data:
            return
        (folder / f"session-{_stamp()}.json").write_bytes(data)
        for old in sorted(folder.glob("session-*.json"))[:-KEEP_BACKUPS]:
            old.unlink(missing_ok=True)

    # ------------------------------------------------------------------ AI

    @_safe
    def ai_status(self, extra_urls: list[str] | None = None) -> dict[str, Any]:
        """Local runtimes (running or not, with models), Gemini, and suggestions."""
        runtimes = catalog.local_status(extra_urls)
        return {
            "runtimes": runtimes,
            "gemini": catalog.gemini_status(),
            "suggested": {
                "read": catalog.suggest(runtimes, "read"),
                "cards": catalog.suggest(runtimes, "cards"),
            },
        }

    @_safe
    def set_api_key(self, key: str) -> dict[str, Any]:
        """Check the key against Gemini, then store it in the credential store."""
        key = (key or "").strip()
        if not key:
            raise ValueError("Paste a key first")
        from .ai.providers import GEMINI_URL, make_provider

        make_provider("gemini", GEMINI_URL, api_key=key).list_models()  # raises if it's wrong
        stored = secrets.set_key(key)
        return {"stored": stored, "gemini": catalog.gemini_status()}

    @_safe
    def clear_api_key(self) -> dict[str, Any]:
        secrets.clear_key()
        return {}

    @_safe
    def start_generate(self, request: dict[str, Any]) -> dict[str, Any]:
        """Start writing cards in the background; poll with ``job_status``."""
        ref = request.get("model") or {}
        provider = catalog.provider_for(ref, "cards")
        req = Request(
            material=request.get("material", ""),
            fields=list(request.get("fields") or ["Front", "Back"]),
            note_type=request.get("note_type", "basic"),
            macros=normalize_macros(request.get("macros")),
            density=request.get("density", "normal"),
            focus=request.get("focus", "balanced"),
            source=request.get("source", ""),
            use_macros=bool(request.get("use_macros")),
            existing=[str(f)[:120] for f in (request.get("existing") or [])][-3000:],
        )
        if not req.material.strip():
            raise ValueError("Add some material first")
        job = self._jobs.start(
            lambda job: generate_cards(
                provider, ref.get("model", ""), req, progress=job.progress, cancel=job.cancel
            )
        )
        return {"job": job.id}

    @_safe
    def open_source_file(self) -> dict[str, Any]:
        """Pick a PDF, image, or text/Markdown file for the Generate page."""
        result = self._window.create_file_dialog(
            _dialog("OPEN"),
            file_types=(
                "Study material (*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.txt;*.md)",
                "All files (*.*)",
            ),
        )
        if not result:
            return {"cancelled": True}
        return describe_source(result[0])

    @_safe
    def upload_source(self, name: str, data_b64: str) -> dict[str, Any]:
        """A dropped or pasted file: the page can't pass a path, so it sends the bytes."""
        info = describe_source(save_upload(self._dir / "uploads", name, data_b64))
        return {**info, "name": name}  # show the name the user knows, not the stored one

    @_safe
    def source_thumbnails(self, path: str, pages: list[int]) -> dict[str, Any]:
        return {"thumbs": {str(n): url for n, url in thumbnails(path, pages[:40]).items()}}

    @_safe
    def start_read(self, request: dict[str, Any]) -> dict[str, Any]:
        """Read PDF pages or an image into Markdown in the background."""
        req = ReadRequest(
            path=request["path"], pages=request.get("pages", ""), mode=request.get("mode", "ai")
        )
        ref = request.get("model") or {}
        provider = catalog.provider_for(ref, "read") if req.mode == "ai" else None
        reader = Reader(self._dir / "cache" / "read")
        job = self._jobs.start(
            lambda job: reader.run(
                provider, ref.get("model", ""), req, progress=job.progress, cancel=job.cancel
            )
        )
        return {"job": job.id}

    @_safe
    def job_status(self, job_id: str, since: int = 0) -> dict[str, Any]:
        return self._jobs.get(job_id).snapshot(since)

    @_safe
    def cancel_job(self, job_id: str) -> dict[str, Any]:
        self._jobs.get(job_id).cancel.set()
        return {}
