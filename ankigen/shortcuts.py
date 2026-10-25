"""Shortcuts the embedded browser swallows before the page can see them.

pywebview turns off WebView2's browser accelerator keys outside debug mode
(``AreBrowserAcceleratorKeysEnabled = False``), so Ctrl+F and F3 never reach
the page as key events. On Windows we catch them on the WinForms ``WebView2``
control instead and pass them on as an ``ankigen:find`` DOM event.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from typing import Any

log = logging.getLogger(__name__)

FIND_EVENT = "ankigen:find"


def find_script(shift: bool = False, step: bool = False) -> str:
    detail = json.dumps({"shift": shift, "step": step})
    return f"window.dispatchEvent(new CustomEvent({json.dumps(FIND_EVENT)}, {{detail: {detail}}}))"


def handle_key(window: Any, ctrl: bool, shift: bool, key: str) -> bool:
    """Forward Ctrl+F / F3 to the page; returns True when the key was used."""
    if ctrl and not shift and key == "F":
        script = find_script()
    elif key == "F3":
        script = find_script(shift=shift, step=True)
    else:
        return False
    # evaluate_js waits for the page; calling it on the UI thread would deadlock.
    threading.Thread(target=window.evaluate_js, args=(script,), daemon=True).start()
    return True


def install(window: Any) -> bool:
    """Hook the native WebView2 control (Windows only). Never raises."""
    if sys.platform != "win32":
        return False
    try:
        webview_control = window.native.browser.webview
    except AttributeError:
        log.warning("Find shortcut: no native WebView2 control found")
        return False

    seen = [0]

    def on_key(_sender: Any, e: Any) -> None:
        try:
            code = e.KeyCode
            name = code.ToString() if hasattr(code, "ToString") else str(code)
            if seen[0] < 30:  # enough to see in app.log whether Ctrl+F arrives at all
                seen[0] += 1
                log.info("KeyDown %s ctrl=%s shift=%s", name, e.Control, e.Shift)
            if handle_key(window, bool(e.Control), bool(e.Shift), name.split(".")[-1]):
                e.Handled = True
        except Exception:
            log.exception("Find shortcut failed")

    try:
        webview_control.KeyDown += on_key
        log.info("Find shortcut: listening on %s", type(webview_control).__name__)
        return True
    except Exception:
        log.exception("Find shortcut: couldn't listen for keys")
        return False
