"""HTTP bridge for developing the UI in a normal browser.

    python -m ankigen.devserver      # then: cd frontend && npm run dev

Exposes the same :class:`~ankigen.api.Api` methods as the desktop window at
``POST /api/<method>`` with a JSON array of arguments. Native dialogs don't
exist here, so ``export_deck`` writes into ``./exports`` and ``open_text_file``
is unavailable (paste or drag a file into the Import view instead).
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import Api
from .models import DeckSpec

EXPORT_DIR = Path.cwd() / "exports"


class DevApi(Api):
    def export_deck(self, deck):  # type: ignore[override]
        spec = DeckSpec.from_dict(deck)
        name = re.sub(r'[<>:"/\\|?*]+', "_", spec.name.split("::")[-1]).strip() or "deck"
        return self.write_deck(deck, str(EXPORT_DIR / f"{name}.apkg"))

    def open_text_file(self):  # type: ignore[override]
        return {"ok": False, "error": "No file dialog in browser mode: drop the file instead"}

    def open_source_file(self):  # type: ignore[override]
        return {"ok": False, "error": "No file dialog in browser mode: drop the file instead"}

    def reveal(self, path):  # type: ignore[override]
        return {"ok": True}


def serve(port: int = 5174) -> None:
    api = DevApi(data_dir=Path.cwd() / ".devdata")
    (Path.cwd() / ".devdata").mkdir(exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            method = self.path.removeprefix("/api/").strip("/")
            fn = getattr(api, method, None) if not method.startswith("_") else None
            if fn is None:
                self._send(404, {"ok": False, "error": f"No such method: {method}"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            args = json.loads(self.rfile.read(length) or b"[]")
            self._send(200, fn(*args))

        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_: object) -> None:
            pass

    print(f"ankigen dev API on http://127.0.0.1:{port}/api/")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    serve()
