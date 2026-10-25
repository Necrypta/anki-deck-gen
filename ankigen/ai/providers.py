"""AI backends behind one interface.

* :class:`Ollama`: Ollama's native API (``localhost:11434``).
* :class:`OpenAICompatible`: any server speaking the OpenAI chat API. Covers
  local runtimes (LM Studio, llama.cpp ``llama-server``, Jan, vLLM, KoboldCpp)
  and hosted ones (OpenRouter, DeepSeek…).
* :class:`Gemini`: Google's Gemini API (free tier available).

Models are never hard-coded: each backend lists what is installed/available.
"""

from __future__ import annotations

import base64
import re
import threading
import time
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .http import AiError, request_json
from .text import strip_think


@dataclass(frozen=True)
class ModelInfo:
    id: str
    vision: bool | None = None  # None: the backend can't tell
    thinking: bool = False
    detail: str = ""  # e.g. "8.2B · Q4_K_M · 5.2 GB"


@dataclass
class ChatResult:
    text: str
    seconds: float  # prompt + generation time, excluding model load where known
    load_seconds: float = 0.0
    output_tokens: int | None = None
    input_tokens: int | None = None
    truncated: bool = False  # hit the output-token limit
    thinking_tokens: int | None = None

    @property
    def tokens_per_second(self) -> float | None:
        if not self.output_tokens or self.seconds <= 0:
            return None
        return self.output_tokens / self.seconds


@dataclass
class Provider:
    """Base class. ``name`` is shown to the user, ``kind`` picks the API."""

    base_url: str
    name: str = ""
    timeout: float = 600
    kind: str = field(default="", init=False)
    on_retry: Callable[[int, float], None] | None = field(default=None, repr=False, compare=False)

    def ping(self) -> str:
        """Short status such as ``"Ollama 0.12.3"``; raises :class:`AiError`."""
        raise NotImplementedError

    def list_models(self) -> list[ModelInfo]:
        raise NotImplementedError

    def chat(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        images: list[bytes] | tuple[bytes, ...] = (),
        pdf: bytes | None = None,
        schema: dict | None = None,
        temperature: float = 0.2,
        cancel: threading.Event | None = None,
    ) -> ChatResult:
        raise NotImplementedError


def image_mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


_VISION_NAME = re.compile(
    r"vl\b|vl[-_:.]|vision|llava|minicpm-?v|pixtral|gemma-?3|internvl|moondream|ocr|"
    r"qwen2\.5-?omni|smolvlm|granite.*vision|llama-?4|mistral-small-3",
    re.IGNORECASE,
)


def guess_vision(model_id: str) -> bool | None:
    """Best guess from the model name, for backends that don't say."""
    return True if _VISION_NAME.search(model_id) else None


def _gb(size: int | None) -> str:
    return f"{size / 1e9:.1f} GB" if size else ""


# --------------------------------------------------------------------- Ollama


@dataclass
class Ollama(Provider):
    base_url: str = "http://localhost:11434"
    name: str = "Ollama"
    num_ctx: int = 8192
    max_tokens: int = 4096  # stops runaway thinking or repetition loops

    def __post_init__(self) -> None:
        self.kind = "ollama"
        self.base_url = self.base_url.rstrip("/")
        self._caps: dict[str, list[str]] = {}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def ping(self) -> str:
        v = request_json(self._url("/api/version"), timeout=3, retries=0)
        return f"{self.name} {v.get('version', '')}".strip()

    def capabilities(self, model: str) -> list[str]:
        if model not in self._caps:
            try:
                info = request_json(self._url("/api/show"), {"model": model}, timeout=10, retries=0)
                self._caps[model] = list(info.get("capabilities") or [])
            except AiError:
                self._caps[model] = []
        return self._caps[model]

    def list_models(self) -> list[ModelInfo]:
        tags = request_json(self._url("/api/tags"), timeout=10, retries=0).get("models") or []
        names = [m.get("name") or m.get("model") for m in tags]
        with ThreadPoolExecutor(max_workers=8) as pool:
            caps = dict(zip(names, pool.map(self.capabilities, names)))
        models = []
        for m, name in zip(tags, names):
            c = caps[name]
            if "embedding" in c and "completion" not in c:
                continue
            d = m.get("details") or {}
            detail = " · ".join(
                x
                for x in (d.get("parameter_size"), d.get("quantization_level"), _gb(m.get("size")))
                if x
            )
            vision = ("vision" in c) if c else guess_vision(name)
            models.append(ModelInfo(name, vision, "thinking" in c, detail))
        return sorted(models, key=lambda m: m.id)

    def chat(
        self,
        model,
        prompt,
        *,
        system=None,
        images=(),
        pdf=None,
        schema=None,
        temperature=0.2,
        cancel=None,
    ) -> ChatResult:
        if pdf is not None:
            raise AiError("Ollama can't read PDFs directly; send page images instead")
        messages = [{"role": "system", "content": system}] if system else []
        user: dict = {"role": "user", "content": prompt}
        if images:
            user["images"] = [b64(i) for i in images]
        messages.append(user)
        body: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
                "num_predict": self.max_tokens,
            },
            "keep_alive": "10m",
        }
        if schema is not None:
            body["format"] = schema
        if "thinking" in self.capabilities(model):
            body["think"] = False  # cards don't need it, and it's 3-5x slower
        start = time.monotonic()
        r = request_json(
            self._url("/api/chat"),
            body,
            timeout=self.timeout,
            cancel=cancel,
            on_retry=self.on_retry,
        )
        wall = time.monotonic() - start
        ns = 1e9
        gen = (r.get("prompt_eval_duration", 0) + r.get("eval_duration", 0)) / ns
        msg = r.get("message") or {}
        return _checked(
            ChatResult(
                text=strip_think(msg.get("content", "")),
                seconds=gen or wall,
                load_seconds=r.get("load_duration", 0) / ns,
                output_tokens=r.get("eval_count"),
                input_tokens=r.get("prompt_eval_count"),
                truncated=r.get("done_reason") == "length",
            ),
            raw=msg.get("content", "") + msg.get("thinking", ""),
        )


def _checked(result: ChatResult, raw: str) -> ChatResult:
    """Turn "thought until the limit, then said nothing" into a clear error."""
    if not result.text.strip() and raw.strip():
        tokens = f" all {result.output_tokens} tokens" if result.output_tokens else ""
        raise AiError(
            f"The model spent{tokens} thinking and gave no answer. "
            "Try a non-thinking (instruct) version of it."
        )
    return result


# ---------------------------------------------------------- OpenAI-compatible


@dataclass
class OpenAICompatible(Provider):
    base_url: str = "http://localhost:1234"
    name: str = "OpenAI-compatible"
    api_key: str | None = None
    vision_models: set[str] = field(default_factory=set)  # user says "this one reads images"
    max_tokens: int = 4096

    def __post_init__(self) -> None:
        self.kind = "openai"
        url = self.base_url.rstrip("/")
        self.base_url = url if url.endswith("/v1") else f"{url}/v1"
        self._json_mode: dict[str, str] = {}  # model -> "schema" | "object" | "none"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def ping(self) -> str:
        self._models(timeout=3)  # fail fast when nothing is listening
        n = len(self.list_models())
        return f"{self.name} · {n} model{'s' * (n != 1)}"

    def _models(self, timeout: float = 10) -> list[dict]:
        r = request_json(
            f"{self.base_url}/models", headers=self._headers(), timeout=timeout, retries=0
        )
        data = r.get("data")
        if not isinstance(data, list):
            raise AiError(f"{self.base_url} doesn't look like an OpenAI-compatible server")
        return data

    def list_models(self) -> list[ModelInfo]:
        models = []
        for m in self._models():
            mid = str(m.get("id", ""))
            if not mid or "embed" in mid.lower():
                continue
            vision = True if mid in self.vision_models else guess_vision(mid)
            models.append(ModelInfo(mid, vision))
        return sorted(models, key=lambda m: m.id)

    def chat(
        self,
        model,
        prompt,
        *,
        system=None,
        images=(),
        pdf=None,
        schema=None,
        temperature=0.2,
        cancel=None,
    ) -> ChatResult:
        if pdf is not None:
            raise AiError(f"{self.name} can't read PDFs directly; send page images instead")
        content: str | list = prompt
        if images:
            content = [{"type": "text", "text": prompt}] + [
                {"type": "image_url", "image_url": {"url": f"data:{image_mime(i)};base64,{b64(i)}"}}
                for i in images
            ]
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": content})
        body: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
            "max_tokens": self.max_tokens,
        }

        modes = ["schema", "object", "none"] if schema is not None else ["none"]
        if model in self._json_mode:
            modes = modes[modes.index(self._json_mode[model]) :]
        start = time.monotonic()
        for i, mode in enumerate(modes):
            if mode == "schema":
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "cards", "strict": True, "schema": schema},
                }
            elif mode == "object":
                body["response_format"] = {"type": "json_object"}
            else:
                body.pop("response_format", None)
            try:
                r = request_json(
                    f"{self.base_url}/chat/completions",
                    body,
                    headers=self._headers(),
                    timeout=self.timeout,
                    cancel=cancel,
                    on_retry=self.on_retry,
                )
            except AiError as e:
                # Servers without structured output reject response_format with 400/422.
                if e.status in (400, 422) and i < len(modes) - 1:
                    continue
                raise
            self._json_mode[model] = mode
            break
        wall = time.monotonic() - start
        choices = r.get("choices") or [{}]
        msg = choices[0].get("message") or {}
        usage = r.get("usage") or {}
        content = msg.get("content") or ""
        return _checked(
            ChatResult(
                text=strip_think(content),
                seconds=wall,
                output_tokens=usage.get("completion_tokens"),
                input_tokens=usage.get("prompt_tokens"),
                truncated=choices[0].get("finish_reason") == "length",
            ),
            raw=content + (msg.get("reasoning_content") or msg.get("reasoning") or ""),
        )


# --------------------------------------------------------------------- Gemini

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
_GEMINI_SKIP = re.compile(
    r"embedding|imagen|veo|tts|image-generation|-image|live|native-audio|aqa", re.IGNORECASE
)


def gemini_schema(schema: dict) -> dict:
    """JSON Schema → Gemini's OpenAPI subset (upper-case types, no additionalProperties)."""
    out: dict = {}
    for k, v in schema.items():
        if k == "additionalProperties":
            continue
        if k == "type":
            out[k] = str(v).upper()
        elif k == "properties":
            out[k] = {name: gemini_schema(s) for name, s in v.items()}
            out["propertyOrdering"] = list(v)
        elif k == "items":
            out[k] = gemini_schema(v)
        else:
            out[k] = v
    return out


def gemini_version(model: str) -> float | None:
    m = re.match(r"gemini-(\d+(?:\.\d+)?)", model)
    return float(m.group(1)) if m else None


def gemini_thinking(model: str) -> dict | None:
    """Keep thinking short: reading a page or writing cards doesn't need it,
    and Gemini 3's default made a page take minutes in the bake-off."""
    v = gemini_version(model)
    if v is None:
        return None
    if v >= 3:
        return {"thinkingLevel": "low"}
    if "flash" in model:
        return {"thinkingBudget": 0}  # 2.x Flash can switch it off; Pro can't
    return None


@dataclass
class Gemini(Provider):
    base_url: str = GEMINI_URL
    name: str = "Gemini"
    api_key: str = ""

    def __post_init__(self) -> None:
        self.kind = "gemini"
        self.base_url = self.base_url.rstrip("/")
        self._no_thinking_config: set[str] = set()

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise AiError("No Gemini API key set")
        return {"x-goog-api-key": self.api_key}

    def ping(self) -> str:
        n = len(self.list_models())
        return f"{self.name} · {n} models"

    def list_models(self) -> list[ModelInfo]:
        models, token = [], ""
        while True:
            q = urllib.parse.urlencode(
                {"pageSize": 1000, **({"pageToken": token} if token else {})}
            )
            r = request_json(
                f"{self.base_url}/models?{q}", headers=self._headers(), timeout=15, retries=1
            )
            for m in r.get("models") or []:
                mid = str(m.get("name", "")).removeprefix("models/")
                methods = m.get("supportedGenerationMethods") or []
                if (
                    "generateContent" in methods
                    and "gemini" in mid
                    and not _GEMINI_SKIP.search(mid)
                ):
                    models.append(
                        ModelInfo(mid, True, bool(m.get("thinking")), m.get("displayName", ""))
                    )
            token = r.get("nextPageToken") or ""
            if not token:
                return sorted(models, key=lambda m: m.id)

    def chat(
        self,
        model,
        prompt,
        *,
        system=None,
        images=(),
        pdf=None,
        schema=None,
        temperature=0.2,
        cancel=None,
    ) -> ChatResult:
        parts: list[dict] = [{"text": prompt}]
        if pdf is not None:
            parts.append({"inline_data": {"mime_type": "application/pdf", "data": b64(pdf)}})
        parts += [{"inline_data": {"mime_type": image_mime(i), "data": b64(i)}} for i in images]
        body: dict = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": temperature},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if schema is not None:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = gemini_schema(schema)
        model = model.removeprefix("models/")
        thinking = gemini_thinking(model)
        if thinking is not None and model not in self._no_thinking_config:
            body["generationConfig"]["thinkingConfig"] = thinking
        start = time.monotonic()
        url = f"{self.base_url}/models/{model}:generateContent"
        kw = {"headers": self._headers(), "timeout": self.timeout, "cancel": cancel}
        try:
            r = request_json(url, body, on_retry=self.on_retry, **kw)
        except AiError as e:
            # A model that rejects our thinking setting: try once with its default.
            if (
                e.status != 400
                or "think" not in str(e).lower()
                or "thinkingConfig" not in body["generationConfig"]
            ):
                raise
            self._no_thinking_config.add(model)
            del body["generationConfig"]["thinkingConfig"]
            r = request_json(url, body, on_retry=self.on_retry, **kw)
        wall = time.monotonic() - start
        block = (r.get("promptFeedback") or {}).get("blockReason")
        candidates = r.get("candidates") or []
        if block or not candidates:
            raise AiError(f"Gemini returned nothing ({block or 'no candidates'})")
        cand = candidates[0]
        texts = [
            p.get("text", "")
            for p in (cand.get("content") or {}).get("parts") or []
            if not p.get("thought")
        ]
        if not any(texts) and cand.get("finishReason") not in (None, "STOP"):
            raise AiError(f"Gemini stopped early: {cand.get('finishReason')}")
        usage = r.get("usageMetadata") or {}
        return ChatResult(
            text="".join(texts).strip(),
            seconds=wall,
            output_tokens=usage.get("candidatesTokenCount"),
            input_tokens=usage.get("promptTokenCount"),
            thinking_tokens=usage.get("thoughtsTokenCount"),
        )


def newest_gemini(ids: list[str], family: str = "flash") -> str | None:
    """The newest stable model of a family, e.g. ``gemini-3.8-flash``.

    Google retires older models for new keys, so never pin a version.
    """

    def version(mid: str) -> tuple[float, int]:
        m = re.match(rf"gemini-(\d+(?:\.\d+)?)-{family}(-latest)?$", mid)
        return (float(m.group(1)), 0) if m else (-1.0, 0)

    stable = [i for i in ids if version(i)[0] >= 0]
    if stable:
        return max(stable, key=version)
    loose = [i for i in ids if family in i and "lite" not in i]
    return loose[-1] if loose else (ids[-1] if ids else None)


# ------------------------------------------------------------------ discovery

# Default ports of the common local runtimes. OpenAI-compatible ones are
# probed on /v1/models; Ollama on /api/version.
KNOWN_LOCAL: list[tuple[str, str, str]] = [
    ("Ollama", "ollama", "http://localhost:11434"),
    ("LM Studio", "openai", "http://localhost:1234"),
    ("llama.cpp", "openai", "http://localhost:8080"),
    ("Jan", "openai", "http://localhost:1337"),
    ("KoboldCpp", "openai", "http://localhost:5001"),
]


def make_provider(kind: str, base_url: str, name: str = "", **kw) -> Provider:
    if kind == "ollama":
        return Ollama(base_url, name or "Ollama", **kw)
    if kind == "openai":
        return OpenAICompatible(base_url, name or "OpenAI-compatible", **kw)
    if kind == "gemini":
        return Gemini(base_url or GEMINI_URL, name or "Gemini", **kw)
    raise ValueError(f"Unknown AI backend: {kind}")


@dataclass
class Detected:
    provider: Provider
    status: str | None  # None: not running
    error: str = ""


def detect_local(candidates: list[tuple[str, str, str]] | None = None) -> list[Detected]:
    """Probe local runtimes in parallel (about a second in total)."""
    providers = [make_provider(kind, url, name) for name, kind, url in candidates or KNOWN_LOCAL]

    def probe(p: Provider) -> Detected:
        try:
            return Detected(p, p.ping())
        except AiError as e:
            return Detected(p, None, str(e))

    with ThreadPoolExecutor(max_workers=len(providers) or 1) as pool:
        return list(pool.map(probe, providers))
