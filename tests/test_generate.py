import time

import pytest

from ankigen.ai import catalog, secrets
from ankigen.ai.catalog import FakeProvider
from ankigen.ai.generate import Progress, Request, chunk_markdown, generate_cards
from ankigen.ai.http import AiError
from ankigen.ai.providers import ChatResult
from ankigen.api import Api


def test_chunk_markdown_keeps_display_math_and_headings():
    text = (
        "# A\n\n"
        + "one " * 30
        + "\n\n$$\nx\n\ny\n$$\n\n## B\n\n"
        + "word " * 50
        + "\n\n"
        + "more " * 50
    )
    chunks = chunk_markdown(text, 60)
    assert chunks[0].startswith("# A") and "$$\nx\n\ny\n$$" in chunks[0]
    assert chunks[1].startswith("## B")
    assert len(chunks) == 3
    assert chunk_markdown("  \n\n ", 100) == []


class Scripted(FakeProvider):
    def __init__(self, replies):
        super().__init__("fake://")
        self.replies = list(replies)
        self.prompts = []

    def chat(self, model, prompt, **kw):
        self.prompts.append(prompt)
        return ChatResult(self.replies.pop(0), seconds=0.0, truncated=False)


def test_generate_cards_chunks_tags_flags_and_avoids_repeats():
    p = Scripted(
        [
            '{"cards": [{"Front": "Q1", "Back": "p_n = \\\\frac{1}{2}"}]}',
            "not json",
        ]
    )
    req = Request(
        "# A\n\n" + "a " * 1000 + "\n\n# B\n\n" + "b " * 1000, ["Front", "Back"], source="Ch 8.pdf"
    )
    prog = Progress()
    generate_cards(p, "m", req, progress=prog)
    assert prog.total == 2 and prog.done == 2
    assert prog.cards == [
        {
            "fields": {"Front": "Q1", "Back": r"p_n = \frac{1}{2}"},
            "tags": ["source::Ch_8"],
            "flags": {"bare_latex": ["Back"], "mismatch": [], "unknown_labels": [], "repaired": []},
        }
    ]
    assert "- Q1" in p.prompts[1]  # second chunk is told what's already written
    assert prog.warnings and prog.warnings[0].startswith("Part 2")


def test_generate_needs_material():
    with pytest.raises(AiError):
        generate_cards(
            FakeProvider("fake://"), "m", Request(" ", ["Front", "Back"]), progress=Progress()
        )


def _wait(api, job, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        s = api.job_status(job)
        if s["state"] != "running":
            return s
        time.sleep(0.02)
    raise AssertionError("job didn't finish")


def test_api_generate_with_fake_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv(catalog.FAKE_ENV, "1")
    monkeypatch.setattr(catalog, "KNOWN_LOCAL", [("Ollama", "ollama", "http://127.0.0.1:9")])
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(secrets, "_keyring", lambda: None)
    api = Api(data_dir=tmp_path)

    status = api.ai_status()
    assert status["ok"]
    names = [r["name"] for r in status["runtimes"]]
    assert names[:2] == ["Fake", "Ollama"]
    assert status["runtimes"][1]["status"] is None
    assert status["gemini"]["has_key"] is False

    ref = {"backend": "fake", "url": "fake://", "model": "fake-writer"}
    started = api.start_generate(
        {"material": "First idea.\n\nSecond idea.", "fields": ["Front", "Back"], "model": ref}
    )
    assert started["ok"]
    done = _wait(api, started["job"])
    assert done["state"] == "done" and done["card_count"] == 2
    assert done["cards"][1]["fields"]["Back"] == "Second idea."
    assert api.job_status(started["job"], 1)["cards"] == done["cards"][1:]

    assert api.start_generate({"material": "", "model": ref})["ok"] is False
    no_key = api.start_generate({"material": "x", "model": {"backend": "gemini", "model": "g"}})
    assert "Gemini API key" in no_key["error"]
    assert api.job_status("nope")["ok"] is False


def test_cancel_job(monkeypatch, tmp_path):
    api = Api(data_dir=tmp_path)

    class Slow(FakeProvider):
        def chat(self, *a, **kw):
            time.sleep(0.2)
            return super().chat(*a, **kw)

    monkeypatch.setattr(catalog, "provider_for", lambda ref, stage="cards": Slow("fake://"))
    material = "\n\n".join(f"# H{i}\n\n" + "w " * 1000 for i in range(5))
    job = api.start_generate({"material": material, "model": {"backend": "fake", "model": "x"}})[
        "job"
    ]
    time.sleep(0.05)
    api.cancel_job(job)
    s = _wait(api, job)
    assert s["state"] == "cancelled" and s["done"] < s["total"]


def test_secrets_memory_fallback(monkeypatch):
    monkeypatch.setattr(secrets, "_keyring", lambda: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert secrets.set_key("abc") is False and secrets.get_key() == "abc"
    monkeypatch.setenv("GEMINI_API_KEY", "env")
    assert secrets.get_key() == "env"
    secrets.clear_key()
    monkeypatch.delenv("GEMINI_API_KEY")
    assert secrets.get_key() == ""


def test_suggest_prefers_bakeoff_winners():
    runtimes = [
        {
            "status": "ok",
            "backend": "ollama",
            "url": "u",
            "models": [
                {"id": "llama3.1:8b", "vision": False},
                {"id": "qwen3:8b", "vision": False},
                {"id": "qwen2.5vl:7b", "vision": True},
            ],
        },
    ]
    assert catalog.suggest(runtimes, "cards")["model"] == "qwen3:8b"
    assert catalog.suggest(runtimes, "read")["model"] == "qwen2.5vl:7b"
    assert catalog.suggest([], "cards") is None
