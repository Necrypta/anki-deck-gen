"""API keys live in the OS credential store (Windows Credential Manager via
``keyring``), never in the session file. ``GEMINI_API_KEY`` overrides it,
which is handy in development."""

from __future__ import annotations

import contextlib
import os
import sys

SERVICE = "AnkiDeckGenerator"
_memory: dict[str, str] = {}  # when no credential store is available (e.g. headless Linux)


def _keyring():
    try:
        import keyring
        from keyring.backends import fail

        if sys.platform == "win32":
            # A frozen exe has no entry-point metadata, so name the backend directly.
            from keyring.backends.Windows import WinVaultKeyring

            if not isinstance(keyring.get_keyring(), WinVaultKeyring):
                keyring.set_keyring(WinVaultKeyring())
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring
    except Exception:  # noqa: BLE001 - any import/backend problem means "not available"
        return None


def get_key(name: str = "gemini") -> str:
    env = os.environ.get(f"{name.upper()}_API_KEY")
    if env:
        return env
    kr = _keyring()
    if kr is not None:
        with contextlib.suppress(Exception):
            return kr.get_password(SERVICE, name) or ""
    return _memory.get(name, "")


def set_key(key: str, name: str = "gemini") -> bool:
    """Store the key; returns False when it's only kept for this session."""
    kr = _keyring()
    if kr is not None:
        with contextlib.suppress(Exception):
            kr.set_password(SERVICE, name, key)
            return True
    _memory[name] = key
    return False


def clear_key(name: str = "gemini") -> None:
    _memory.pop(name, None)
    kr = _keyring()
    if kr is not None:
        with contextlib.suppress(Exception):  # nothing stored
            kr.delete_password(SERVICE, name)
