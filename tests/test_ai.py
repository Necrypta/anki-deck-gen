import importlib.util
import io
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from ankigen.ai import AiError, Gemini, Ollama, OpenAICompatible, detect_local
from ankigen.ai import http as aihttp
from ankigen.ai.cards import bare_latex, card_schema, parse_cards
from ankigen.ai.prompts import card_messages, macro_signature, read_messages, target_count
from ankigen.ai.providers import gemini_schema, guess_vision, newest_gemini
from ankigen.ai.sources import load_image, load_pdf, parse_page_range, pdf_subset, source_kind
from ankigen.ai.text import (
    clean_markdown,
    collapse_repeats,
    normalize_math,
    parse_json_lenient,
    repair_latex_escapes,
    strip_think,
)
from ankigen.latex import DEFAULT_MACROS, MacroDef

ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------ text fixes


def test_strip_think():
    assert strip_think("<think>hmm\nok</think>\n\nAnswer") == "Answer"
    assert strip_think("half a thought</think>Answer") == "Answer"
    assert strip_think("plain") == "plain"


def test_normalize_math():
    assert normalize_math(r"a \(x^2\) b \[E=mc^2\]") == "a $x^2$ b $$E=mc^2$$"


def test_repair_latex_escapes():
    raw = r'{"a": "\frac{1}{2} \nabla \theta \beta \rho \alpha \left( \uparrow", "b": "line\nThe end \"q\" \\ é"}'
    data = json.loads(repair_latex_escapes(raw))
    assert data["a"] == r"\frac{1}{2} \nabla \theta \beta \rho \alpha \left( \uparrow"
    assert data["b"] == 'line\nThe end "q" \\ é'


def test_repair_keeps_correct_escapes_and_user_macros():
    raw = r'{"a": "\\frac{a}{b} \norm{v} \vb{F}"}'
    assert (
        json.loads(repair_latex_escapes(raw, {"norm", "vb"}))["a"] == r"\frac{a}{b} \norm{v} \vb{F}"
    )


def test_parse_json_lenient_variants():
    assert parse_json_lenient('```json\n{"cards": []}\n```') == {"cards": []}
    assert parse_json_lenient('Sure! Here you go: {"x": 1} Hope it helps') == {"x": 1}
    assert parse_json_lenient('<think>{"no": 1}</think>[1, 2]') == [1, 2]
    truncated = (
        '{"cards": [{"Front": "A", "Back": "1"}, {"Front": "B", "Back": "2"}, {"Front": "C", "Ba'
    )
    assert parse_json_lenient(truncated) == {
        "cards": [{"Front": "A", "Back": "1"}, {"Front": "B", "Back": "2"}]
    }
    with pytest.raises(ValueError):
        parse_json_lenient("no json here")
    with pytest.raises(ValueError):
        parse_json_lenient('{"cards": [{"Front": "A"')


# ----------------------------------------------------------------- cards/prompts


def test_card_schema_and_parse():
    schema = card_schema(["Quantity", "Formula", "Units"])
    assert schema["properties"]["cards"]["items"]["required"] == ["Quantity", "Formula", "Units"]
    reply = '{"cards": [{"quantity": "Force", "Formula": "\\(F=ma\\)"}, {"Quantity": "", "Formula": "x"}]}'
    assert parse_cards(reply, ["Quantity", "Formula", "Units"]) == [
        {"Quantity": "Force", "Formula": "$F=ma$", "Units": ""}
    ]


def test_parse_cards_aliases_and_bare_list():
    reply = '[{"question": "What is \\hbar?", "answer": ["h over", "2 pi"]}]'
    assert parse_cards(reply, ["Front", "Back"]) == [
        {"Front": r"What is \hbar?", "Back": "h over\n2 pi"}
    ]


def test_parse_cards_unescaped_latex_from_small_model():
    reply = (
        '{"cards": [{"Front": "Write \\nabla \\cdot E", "Back": "$\\frac{\\rho}{\\epsilon_0}$"}]}'
    )
    reply = reply.replace("\\\\", "\\")  # what a sloppy model actually sends
    card = parse_cards(reply, ["Front", "Back"], DEFAULT_MACROS)[0]
    assert card == {"Front": r"Write \nabla \cdot E", "Back": r"$\frac{\rho}{\epsilon_0}$"}


def test_prompts():
    dv = next(m for m in DEFAULT_MACROS if m.name == r"\dv")
    assert macro_signature(dv) == r"\dv[a]{b}{c}"
    assert macro_signature(MacroDef(r"\vb", r"\mathbf{#1}", 1)) == r"\vb{a}"
    system, user = card_messages("word " * 330, ["Text", "Extra"], note_type="cloze", macros=[dv])
    assert "{{c1::" in system and r"\dv[a]{b}{c}" in system and '"Text": "..."' in system
    assert "about 3 cards" in user and "<<<" in user
    assert target_count("x " * 10_000, "thorough") == 40
    assert read_messages("deepseek-ocr:3b")[0] is None
    assert "LaTeX" in read_messages("qwen2.5vl:7b")[0]


def test_gemini_schema_and_vision_guess():
    g = gemini_schema(card_schema(["Front", "Back"]))
    item = g["properties"]["cards"]["items"]
    assert g["type"] == "OBJECT" and item["type"] == "OBJECT" and "additionalProperties" not in item
    assert item["propertyOrdering"] == ["Front", "Back"]
    assert guess_vision("qwen/qwen2.5-vl-7b") and guess_vision("gemma-3-4b-it")
    assert guess_vision("qwen3-8b") is None


# ----------------------------------------------------------------------- sources


def _text_pdf(path: Path, pages: list[str]) -> None:
    """Write a minimal PDF with one line of Helvetica text per page."""
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        None,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids = []
    for text in pages:
        stream = f"BT /F1 9 Tf 20 700 Td ({text}) Tj ET".encode()
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode()}\nendstream")
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {len(objs)} 0 R >>"
        )
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{o}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(out.getvalue())


def test_page_ranges():
    assert parse_page_range("", 3) == [1, 2, 3]
    assert parse_page_range("1-2, 5, 2", 6) == [1, 2, 5]
    assert parse_page_range("4-", 6) == [4, 5, 6]
    for bad in ("0", "3-1", "9", "a"):
        with pytest.raises(ValueError):
            parse_page_range(bad, 6)


def test_load_pdf_text_layer_and_render(tmp_path):
    pdf = tmp_path / "t.pdf"
    _text_pdf(pdf, ["Newton second law F equals m a " * 12, "x"])
    pages = load_pdf(pdf, [1, 2], dpi=50)
    assert "Newton second law" in pages[0].text and pages[0].has_text_layer
    assert not pages[1].has_text_layer
    assert pages[0].image[:4] == b"\x89PNG"
    assert pdf_subset(pdf, [2])[:5] == b"%PDF-"
    assert len(load_pdf(tmp_path / "t.pdf", render=False)) == 2


def test_load_image_and_kinds(tmp_path):
    from PIL import Image

    Image.new("RGB", (4000, 1000), "white").save(tmp_path / "a.jpg")
    page = load_image(tmp_path / "a.jpg", max_side=1000)
    with Image.open(io.BytesIO(page.image)) as img:
        assert img.size == (1000, 250)
    assert [source_kind(n) for n in ("a.PDF", "b.png", "c.md")] == ["pdf", "image", "text"]
    with pytest.raises(ValueError):
        source_kind("x.docx")


# ------------------------------------------------------------- backends (stubbed)


class Stub:
    """A local HTTP server that imitates Ollama, OpenAI-compatible and Gemini APIs."""

    def __init__(self):
        self.requests: list[tuple[str, dict, dict]] = []
        self.fail_429 = 0
        self.reject_schema = False
        self.only_thinking = False
        self.reply = '{"cards": [{"Front": "Q", "Back": "A"}]}'
        stub = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                stub.requests.append((self.path, {}, dict(self.headers)))
                self._route(None)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stub.requests.append((self.path, body, dict(self.headers)))
                self._route(body)

            def _route(self, body):
                p = self.path
                if p == "/api/version":
                    return self._send({"version": "0.12.0"})
                if p == "/api/tags":
                    return self._send(
                        {
                            "models": [
                                {
                                    "name": "qwen2.5vl:7b",
                                    "size": 6e9,
                                    "details": {
                                        "parameter_size": "8.3B",
                                        "quantization_level": "Q4_K_M",
                                    },
                                },
                                {"name": "qwen3:8b", "size": 5.2e9, "details": {}},
                                {"name": "nomic-embed-text:latest", "size": 3e8, "details": {}},
                            ]
                        }
                    )
                if p == "/api/show":
                    caps = {
                        "qwen2.5vl:7b": ["completion", "vision"],
                        "qwen3:8b": ["completion", "thinking"],
                        "nomic-embed-text:latest": ["embedding"],
                    }
                    return self._send({"capabilities": caps.get(body["model"], [])})
                if p == "/api/chat" and stub.only_thinking:
                    return self._send(
                        {
                            "message": {"content": "", "thinking": "hmm " * 50},
                            "eval_count": 4096,
                            "done_reason": "length",
                        }
                    )
                if p == "/api/chat":
                    return self._send(
                        {
                            "message": {"content": "<think>x</think>" + stub.reply},
                            "eval_count": 50,
                            "eval_duration": 2e9,
                            "prompt_eval_duration": 5e8,
                            "load_duration": 3e9,
                        }
                    )
                if p == "/api/ps":
                    return self._send(
                        {"models": [{"name": "qwen3:8b", "size": 100, "size_vram": 80}]}
                    )
                if p == "/v1/models":
                    return self._send(
                        {
                            "data": [
                                {"id": "qwen/qwen2.5-vl-7b"},
                                {"id": "text-embedding-x"},
                                {"id": "local-model"},
                            ]
                        }
                    )
                if p == "/v1/chat/completions":
                    if (
                        stub.reject_schema
                        and body.get("response_format", {}).get("type") == "json_schema"
                    ):
                        return self._send(
                            {"error": {"message": "response_format not supported"}}, 400
                        )
                    return self._send(
                        {
                            "choices": [{"message": {"content": stub.reply}}],
                            "usage": {"completion_tokens": 20, "prompt_tokens": 9},
                        }
                    )
                if p.startswith("/v1beta/models?"):
                    return self._send(
                        {
                            "models": [
                                {
                                    "name": "models/gemini-2.5-flash",
                                    "supportedGenerationMethods": ["generateContent"],
                                },
                                {
                                    "name": "models/text-embedding-004",
                                    "supportedGenerationMethods": ["embedContent"],
                                },
                                {
                                    "name": "models/gemini-2.5-flash-preview-tts",
                                    "supportedGenerationMethods": ["generateContent"],
                                },
                            ]
                        }
                    )
                if p.endswith(":generateContent"):
                    if stub.fail_429:
                        stub.fail_429 -= 1
                        return self._send(
                            {"error": {"message": "quota"}}, 429, {"Retry-After": "0"}
                        )
                    return self._send(
                        {
                            "candidates": [
                                {
                                    "content": {
                                        "parts": [
                                            {"text": "plan", "thought": True},
                                            {"text": stub.reply},
                                        ]
                                    },
                                    "finishReason": "STOP",
                                }
                            ],
                            "usageMetadata": {"candidatesTokenCount": 12},
                        }
                    )
                self._send({"error": "not found"}, 404)

            def _send(self, obj, status=200, headers=None):
                data = json.dumps(obj).encode()
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(aihttp, "_retry_delay", lambda e, attempt: 0)
    s = Stub()
    yield s
    s.server.shutdown()


def test_ollama(stub):
    o = Ollama(stub.url)
    assert o.ping() == "Ollama 0.12.0"
    models = o.list_models()
    assert [m.id for m in models] == ["qwen2.5vl:7b", "qwen3:8b"]
    assert models[0].vision and models[0].detail == "8.3B · Q4_K_M · 6.0 GB"
    assert models[1].thinking and not models[1].vision

    r = o.chat(
        "qwen3:8b", "hi", system="sys", images=[b"\x89PNG\r\n\x1a\nxx"], schema={"type": "object"}
    )
    assert (
        r.text == stub.reply
        and r.load_seconds == 3
        and r.seconds == 2.5
        and r.tokens_per_second == 20
    )
    body = stub.requests[-1][1]
    assert (
        body["think"] is False and body["format"] == {"type": "object"} and body["stream"] is False
    )
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1]["images"] == ["iVBORw0KGgp4eA=="]
    with pytest.raises(AiError):
        o.chat("qwen3:8b", "hi", pdf=b"%PDF")


def test_openai_compatible_falls_back_without_schema(stub):
    o = OpenAICompatible(stub.url, "LM Studio")
    assert o.base_url.endswith("/v1") and o.ping() == "LM Studio · 2 models"
    assert [(m.id, m.vision) for m in o.list_models()] == [
        ("local-model", None),
        ("qwen/qwen2.5-vl-7b", True),
    ]
    stub.reject_schema = True
    r = o.chat(
        "local-model", "hi", images=[b"\xff\xd8\xffjpg"], schema=card_schema(["Front", "Back"])
    )
    assert r.text == stub.reply and r.output_tokens == 20
    sent = [
        b.get("response_format", {}).get("type")
        for p, b, _ in stub.requests
        if p.endswith("/completions")
    ]
    assert sent == ["json_schema", "json_object"]
    content = stub.requests[-1][1]["messages"][0]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    o.chat("local-model", "again", schema={"type": "object"})  # remembers the mode that worked
    assert stub.requests[-1][1]["response_format"]["type"] == "json_object"


def test_gemini(stub):
    g = Gemini(f"{stub.url}/v1beta", api_key="KEY")
    assert [m.id for m in g.list_models()] == ["gemini-2.5-flash"]
    stub.fail_429 = 2
    r = g.chat(
        "gemini-2.5-flash",
        "read",
        system="sys",
        pdf=b"%PDF-1.4",
        schema=card_schema(["Front", "Back"]),
    )
    assert r.text == stub.reply and r.output_tokens == 12
    path, body, headers = stub.requests[-1]
    headers = {k.lower(): v for k, v in headers.items()}
    assert path == "/v1beta/models/gemini-2.5-flash:generateContent"
    assert headers["x-goog-api-key"] == "KEY" and "KEY" not in path
    assert body["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "application/pdf"
    assert body["generationConfig"]["responseSchema"]["type"] == "OBJECT"
    with pytest.raises(AiError, match="No Gemini API key"):
        Gemini(f"{stub.url}/v1beta").list_models()


def test_errors_and_detection(stub):
    with pytest.raises(AiError, match="HTTP 404"):
        aihttp.request_json(f"{stub.url}/nope", retries=0)
    found = detect_local(
        [("Ollama", "ollama", stub.url), ("LM Studio", "openai", "http://127.0.0.1:9")]
    )
    assert found[0].status == "Ollama 0.12.0"
    assert found[1].status is None and "Couldn't reach" in found[1].error


def test_cancel_stops_retries(stub):
    stub.fail_429 = 5
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(aihttp.Cancelled):
        Gemini(f"{stub.url}/v1beta", api_key="K").chat("gemini-2.5-flash", "x", cancel=cancel)


# ------------------------------------------------------------------- bake-off


def _bakeoff():
    spec = importlib.util.spec_from_file_location("ai_bakeoff", ROOT / "scripts" / "ai_bakeoff.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ai_bakeoff"] = mod  # dataclasses look their module up
    spec.loader.exec_module(mod)
    return mod


def test_bakeoff_end_to_end(stub, tmp_path, capsys):
    pdf = tmp_path / "chapter.pdf"
    _text_pdf(pdf, ["Gauss law " * 30, "Ampere law " * 30, "extra"])
    stub.reply = '{"cards": [{"Front": "State Gauss\'s law", "Back": "$\\\\oint E \\\\cdot dA = Q/\\\\epsilon_0$"}]}'
    out = tmp_path / "report"
    code = _bakeoff().main(
        [
            str(pdf),
            "--pages",
            "1-2",
            "--ollama",
            stub.url,
            "--out",
            str(out),
            "--no-open",
            "--dpi",
            "40",
        ]
    )
    assert code == 0
    results = json.loads((out / "results.json").read_text("utf-8"))
    assert [r["model"] for r in results["read"]] == ["qwen2.5vl:7b"]
    assert sorted(c["model"] for c in results["cards"]) == ["qwen2.5vl:7b", "qwen3:8b"]
    assert all(
        c["json_ok"] and c["cards"][0]["Front"] == "State Gauss's law" for c in results["cards"]
    )
    assert results["card_input"]["from"] == "transcription by qwen2.5vl:7b"
    gpu = {c["model"]: c["gpu"] for c in results["cards"]}
    assert gpu["qwen3:8b"] == 0.8
    report = (out / "report.html").read_text("utf-8")
    assert "__DATA__" not in report
    assert '"images": {"1"' in report
    assert "| cards | qwen3:8b |" in (out / "summary.md").read_text("utf-8")
    assert "ollama pull deepseek-r1:8b" in capsys.readouterr().out


def test_bakeoff_list(stub, capsys):
    assert _bakeoff().main(["--list", "--ollama", stub.url]) == 0
    out = capsys.readouterr().out
    assert "Suggested for an 8 GB GPU" in out and "[x] qwen3:8b" in out


# ------------------------------------------------------- fixes from the bake-off


def test_clean_markdown_strips_tokens_and_loops():
    raw = "<|im_end|>\n<|md_start|>Intro.<nl>\n" + "<|md_start|>same line\n<|md_end|>\n" * 6 + "End"
    assert clean_markdown(raw) == "Intro.\nsame line\nsame line\n\nEnd"
    text, looped = collapse_repeats("$$\nx\n$$\n$$\ny\n$$")
    assert not looped and text.count("$$") == 4


def test_bare_latex():
    assert bare_latex(r"p_n(x) = \frac{1}{K_n}")
    assert not bare_latex(r"$K_n = \frac{1}{2}$ and $$a^{2}$$")
    assert not bare_latex("Plain answer with x_n")


def test_newest_gemini():
    ids = [
        "gemini-2.5-flash",
        "gemini-3.8-flash",
        "gemini-3.8-flash-lite",
        "gemini-3.8-pro",
        "gemini-10.0-flash-preview-x",
    ]
    assert newest_gemini(ids) == "gemini-3.8-flash"
    assert newest_gemini(["gemini-pro-latest"]) == "gemini-pro-latest"
    assert newest_gemini([]) is None


def test_thinking_only_reply_is_a_clear_error(stub):
    stub.only_thinking = True
    with pytest.raises(AiError, match="spent all 4096 tokens thinking"):
        Ollama(stub.url).chat("qwen3:8b", "hi")
    assert stub.requests[-1][1]["options"]["num_predict"] == 4096


def test_openai_sends_token_limit(stub):
    OpenAICompatible(stub.url).chat("local-model", "hi")
    assert stub.requests[-1][1]["max_tokens"] == 4096
