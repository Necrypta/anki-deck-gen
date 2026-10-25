"""Desktop window: a pywebview shell around the bundled React UI."""

from __future__ import annotations

import sys
from pathlib import Path

DEV_URL = "http://localhost:5173"


def frontend_index() -> Path:
    # PyInstaller unpacks bundled data into sys._MEIPASS.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for candidate in (base / "frontend" / "dist" / "index.html", base / "dist" / "index.html"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Frontend build not found. Run `npm run build` in frontend/, or start with --dev."
    )


def run(dev: bool = False, debug: bool = False) -> None:
    import webview

    from .api import Api

    api = Api()
    # A plain path (not file://) makes pywebview serve it over its local HTTP
    # server; WebView2 refuses ES-module scripts from file:// URLs.
    url = DEV_URL if dev else str(frontend_index())
    window = webview.create_window(
        "Anki Deck Generator",
        url,
        js_api=api,
        width=1200,
        height=800,
        min_size=(860, 560),
        background_color="#fafafa",
    )
    api._attach(window)
    webview.start(debug=debug or dev, http_server=not dev, private_mode=False)
