"""Small JSON-over-HTTP helper shared by the AI backends (stdlib only)."""

from __future__ import annotations

import json
import random
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

RETRY_STATUS = {429, 500, 502, 503, 504}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}

# Local runtimes must never go through a system proxy.
_direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_default = urllib.request.build_opener()


class AiError(Exception):
    """A backend call failed. ``status`` is the HTTP status when there was one."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class Cancelled(AiError):
    pass


def is_local(url: str) -> bool:
    return (urllib.parse.urlsplit(url).hostname or "") in LOCAL_HOSTS


def request_json(
    url: str,
    body: dict | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 600,
    retries: int = 3,
    cancel: threading.Event | None = None,
    on_retry: Callable[[int, float], None] | None = None,
) -> dict:
    """GET (no body) or POST JSON and return the decoded reply.

    Retries 429/5xx with backoff (honouring ``Retry-After``). Connection errors
    are raised straight away so probing for a local runtime stays fast.
    ``on_retry(status, seconds)`` is told before each wait, so callers can
    show "rate limited, waiting 20 s" instead of looking stuck.
    """
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", "Accept": "application/json", **(headers or {})}
    opener = _direct if is_local(url) else _default
    host = urllib.parse.urlsplit(url).netloc
    for attempt in range(retries + 1):
        if cancel is not None and cancel.is_set():
            raise Cancelled("Cancelled")
        req = urllib.request.Request(url, data=data, headers=hdrs)
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
            return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            raw_err = _read_error(e)
            detail = _error_detail(e, raw_err)
            if e.code in RETRY_STATUS and attempt < retries:
                delay = _retry_delay(e, attempt, raw_err)
                if on_retry is not None:
                    on_retry(e.code, delay)
                _sleep(delay, cancel)
                continue
            raise AiError(f"HTTP {e.code} from {host}: {detail}", e.code) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            reason = getattr(e, "reason", None) or e
            raise AiError(f"Couldn't reach {host}: {reason}") from None
        except json.JSONDecodeError:
            raise AiError(f"{host} didn't reply with JSON") from None
    raise AiError(f"{host}: too many retries")  # pragma: no cover


def _read_error(e: urllib.error.HTTPError) -> str:
    try:
        return e.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _error_detail(e: urllib.error.HTTPError, raw: str) -> str:
    if not raw:
        return str(e.reason or "")
    try:
        err = json.loads(raw).get("error", raw)
    except (json.JSONDecodeError, AttributeError):
        return raw.strip()[:300] or str(e.reason)
    if isinstance(err, dict):
        err = err.get("message") or json.dumps(err)
    return str(err)[:300]


def _retry_delay(e: urllib.error.HTTPError, attempt: int, raw: str = "") -> float:
    """Backoff, or what the server asked for: ``Retry-After``, or Gemini's
    ``"retryDelay": "23s"`` in the error body."""
    wanted = 2.0 * 2**attempt + random.uniform(0, 1)
    try:
        wanted = max(wanted, float(e.headers.get("Retry-After") or 0))
    except (TypeError, ValueError):
        pass
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', raw)
    if m:
        wanted = max(wanted, float(m.group(1)) + 1)
    return min(60.0, wanted)


def _sleep(seconds: float, cancel: threading.Event | None) -> None:
    if cancel is None:
        time.sleep(seconds)
    elif cancel.wait(seconds):
        raise Cancelled("Cancelled")
