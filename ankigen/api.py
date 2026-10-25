"""Methods exposed to the frontend as ``window.pywebview.api.*``.

Every method returns plain JSON-serialisable data. Errors come back as
``{"ok": False, "error": "..."}`` instead of raising, so the UI can show them.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from .ai import catalog, secrets
from .ai.generate import Request, generate_cards
from .ai.jobs import Jobs
from .ai.reading import Reader, ReadRequest, describe_source, save_upload, thumbnails
from .deck import build_apkg
from .latex import DEFAULT_MACROS, normalize_macros
from .models import DeckSpec
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
    def parse_text(self, text: str, fmt: str = "block", options: dict | None = None) -> dict[str, Any]:
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

    def _write(self, spec: DeckSpec, path: str) -> dict[str, Any]:
        out = build_apkg(spec, path)
        return {"path": str(out), "count": len(spec.cards)}

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
        f = self._session_file
        if not f.exists():
            return {"session": None}
        return {"session": json.loads(f.read_text(encoding="utf-8"))}

    @_safe
    def save_session(self, session: dict[str, Any]) -> dict[str, Any]:
        f = self._session_file
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(session, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)
        return {}

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

