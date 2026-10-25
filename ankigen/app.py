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


def _setup_logging() -> None:
    """Log to <data dir>/app.log so problems on the user's machine can be diagnosed."""
    import logging
    from logging.handlers import RotatingFileHandler

    from .api import app_data_dir

    try:
        handler = RotatingFileHandler(
            app_data_dir() / "app.log", maxBytes=200_000, backupCount=1, encoding="utf-8"
        )
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def run(dev: bool = False, debug: bool = False) -> None:
    import logging

    import webview

    from . import build_label, is_release, shortcuts
    from .api import Api

    _setup_logging()
    logging.getLogger(__name__).info(
        "Starting %s (webview %s)", build_label(), getattr(webview, "__version__", "?")
    )

    api = Api()
    title = "Anki Deck Generator"
    if not is_release():
        title += f" (test build: {build_label()})"
    # A plain path (not file://) makes pywebview serve it over its local HTTP
    # server; WebView2 refuses ES-module scripts from file:// URLs.
    url = DEV_URL if dev else str(frontend_index())
    window = webview.create_window(
        title,
        url,
        js_api=api,
        width=1200,
        height=800,
        min_size=(860, 560),
        background_color="#fafafa",
    )
    api._attach(window)
    window.events.shown += lambda: shortcuts.install(window)
    webview.start(debug=debug or dev, http_server=not dev, private_mode=False)
