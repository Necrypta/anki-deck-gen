"""What the AI settings page shows: which runtimes are running, their models,
and turning the user's choice (a model reference) back into a provider."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import secrets
from .http import AiError
from .providers import (
    GEMINI_URL,
    KNOWN_LOCAL,
    ChatResult,
    ModelInfo,
    Provider,
    detect_local,
    make_provider,
    newest_gemini,
)

# Bake-off winners on an 8 GB GPU; only used to pre-select models that are installed.
SUGGESTED = {"read": ["qwen2.5vl:7b"], "cards": ["qwen3:8b", "qwen2.5vl:7b"]}
NUM_CTX = {"read": 6144, "cards": 8192}
GEMINI_TIMEOUT = 900  # the free tier can take several minutes per request

FAKE_ENV = "ANKIGEN_FAKE_AI"  # devserver/tests: a pretend local runtime


def _model_dict(m: ModelInfo) -> dict[str, Any]:
    return {"id": m.id, "vision": m.vision, "thinking": m.thinking, "detail": m.detail}


def local_status(extra_urls: list[str] | None = None) -> list[dict[str, Any]]:
    """Every known local runtime (running or not) plus the user's own URLs."""
    candidates = list(KNOWN_LOCAL)
    for url in extra_urls or []:
        url = url.strip().rstrip("/")
        if url and all(url != c[2] for c in candidates):
            candidates.append(("Custom", "openai", url))
    runtimes = []
    if os.environ.get(FAKE_ENV):
        runtimes.append(_fake_status())
    found = detect_local(candidates)

    def describe(d) -> dict[str, Any]:
        entry = {
            "name": d.provider.name,
            "backend": d.provider.kind,
            "url": _plain_url(d.provider),
            "status": d.status,
            "error": d.error,
            "models": [],
        }
        if d.status:
            try:
                entry["models"] = [_model_dict(m) for m in d.provider.list_models()]
            except AiError as e:
                entry["error"] = str(e)
        return entry

    with ThreadPoolExecutor(max_workers=len(found) or 1) as pool:
        runtimes += list(pool.map(describe, found))
    return runtimes


def _plain_url(p: Provider) -> str:
    url = p.base_url
    return url[:-3] if p.kind == "openai" and url.endswith("/v1") else url


def gemini_status() -> dict[str, Any]:
    key = secrets.get_key("gemini")
    if not key:
        return {"has_key": False, "models": [], "error": ""}
    try:
        models = make_provider("gemini", GEMINI_URL, api_key=key).list_models()
    except AiError as e:
        return {"has_key": True, "models": [], "error": str(e)}
    ids = [m.id for m in models]
    return {
        "has_key": True,
        "models": [_model_dict(m) for m in models],
        "default": newest_gemini(ids),
        "fast": newest_gemini(ids, "flash-lite"),
        "error": "",
    }


def suggest(runtimes: list[dict[str, Any]], stage: str) -> dict[str, str] | None:
    """A sensible default model reference for ``stage`` among what's installed."""
    pool = [
        (r, m)
        for r in runtimes
        if r["status"]
        for m in r["models"]
        if stage != "read" or m["vision"]
    ]
    for want in SUGGESTED[stage]:
        for r, m in pool:
            if m["id"] == want or m["id"].split(":latest")[0] == want:
                return {"backend": r["backend"], "url": r["url"], "model": m["id"]}
    return None


def provider_for(ref: dict[str, Any], stage: str = "cards") -> Provider:
    """Build the provider a model reference points to."""
    backend = ref.get("backend")
    if backend == "fake":
        return FakeProvider("fake://", "Fake")
    if backend == "gemini":
        key = secrets.get_key("gemini")
        if not key:
            raise AiError("Add a Gemini API key in Settings → AI first")
        return make_provider(
            "gemini", ref.get("url") or GEMINI_URL, api_key=key, timeout=GEMINI_TIMEOUT
        )
    if backend == "ollama":
        return make_provider("ollama", ref.get("url") or KNOWN_LOCAL[0][2], num_ctx=NUM_CTX[stage])
    if backend == "openai":
        return make_provider("openai", ref["url"])
    raise AiError("Choose an AI model in Settings → AI first")


# ----------------------------------------------------------------- fake runtime


def _fake_status() -> dict[str, Any]:
    return {
        "name": "Fake",
        "backend": "fake",
        "url": "fake://",
        "status": "Fake AI (testing)",
        "error": "",
        "models": [{"id": "fake-writer", "vision": True, "thinking": False, "detail": "for tests"}],
    }


class FakeProvider(Provider):
    """Answers instantly with one card per paragraph; for the devserver and UI tests."""

    def __post_init__(self) -> None:
        self.kind = "fake"

    def ping(self) -> str:
        return "Fake AI"

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("fake-writer", True)]

    def chat(
        self, model, prompt, *, system=None, images=(), pdf=None, schema=None, **_
    ) -> ChatResult:
        import json
        import re

        material = prompt.split("<<<", 1)[-1].rsplit(">>>", 1)[0]
        fields = list(
            (schema or {})
            .get("properties", {})
            .get("cards", {})
            .get("items", {})
            .get("properties", {})
        )
        fields = fields or ["Front", "Back"]
        cards = []
        for para in [p.strip() for p in material.split("\n\n") if p.strip()][:20]:
            words = re.sub(r"\s+", " ", para)
            card = {f: "" for f in fields}
            card[fields[0]] = f"What does this say: {words[:60]}?"
            if len(fields) > 1:
                card[fields[1]] = words[:200]
            cards.append(card)
        return ChatResult(json.dumps({"cards": cards}), seconds=0.01)
