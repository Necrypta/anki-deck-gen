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

from .deck import build_apkg
from .latex import DEFAULT_MACROS
from .models import DeckSpec
from .parsers import PARSERS, parse_text


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    path = Path(base) / "AnkiDeckGenerator"
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

    # pywebview tries to expose every public attribute, so keep these private.
    def _attach(self, window: Any) -> None:
        self._window = window

    @property
    def _session_file(self) -> Path:
        return (self._data_dir or app_data_dir()) / "session.json"

    @_safe
    def info(self) -> dict[str, Any]:
        from . import __version__
        return {"version": __version__, "formats": list(PARSERS), "default_macros": DEFAULT_MACROS}

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
