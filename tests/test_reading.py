import base64
import time

import pytest
from test_ai import _text_pdf

from ankigen.ai import catalog
from ankigen.ai.catalog import FakeProvider
from ankigen.ai.generate import Progress
from ankigen.ai.http import AiError
from ankigen.ai.providers import ChatResult
from ankigen.ai.reading import Reader, ReadRequest, describe_source, joined, save_upload, thumbnails
from ankigen.api import Api


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "chapter.pdf"
    _text_pdf(
        path,
        [
            "Gauss law relates flux to charge " * 10,
            "x",
            "Ampere law relates field to current " * 10,
        ],
    )
    return path


@pytest.fixture
def png(tmp_path):
    from PIL import Image

    path = tmp_path / "shot.png"
    Image.new("RGB", (300, 120), "white").save(path)
    return path


def test_describe_source(pdf, png, tmp_path):
    info = describe_source(pdf)
    assert info["kind"] == "pdf" and info["pages"] == 3 and info["text_pages"] == [1, 3]
    assert describe_source(png)["kind"] == "image"
    md = tmp_path / "notes.md"
    md.write_text("# Hi\n\n$x$", "utf-8")
    assert describe_source(md)["text"] == "# Hi\n\n$x$"


def test_save_upload(tmp_path, png):
    data = "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()
    saved = save_upload(tmp_path / "up", "My screenshot.png", data)
    assert saved.read_bytes() == png.read_bytes() and saved.name.startswith("My_screenshot-")
    with pytest.raises(ValueError):
        save_upload(tmp_path / "up", "x.docx", "AAAA")


def test_thumbnails(pdf, png):
    thumbs = thumbnails(pdf, [1, 3])
    assert set(thumbs) == {1, 3} and thumbs[1].startswith("data:image/jpeg;base64,")
    assert set(thumbnails(png, [1])) == {1}


class Counting(FakeProvider):
    def __init__(self, kind="ollama"):
        super().__init__("fake://")
        self.kind = kind
        self.calls = []

    def chat(self, model, prompt, **kw):
        self.calls.append(kw)
        if kw.get("pdf") is not None:
            return super().chat(model, prompt, **kw)
        return ChatResult("\\subsection*{Gauss}\n\nFlux $\\Phi = Q/\\epsilon_0$", seconds=0)


def test_text_layer_mode_warns_about_scans(pdf, tmp_path):
    prog = Progress()
    Reader(tmp_path).run(None, "", ReadRequest(str(pdf), "1-3", "text"), progress=prog)
    assert "Gauss law relates" in prog.pages[1] and prog.done == 3
    assert prog.warnings and "Pages 2" in prog.warnings[0]


def test_ai_mode_reads_each_page_and_caches(pdf, tmp_path):
    p = Counting()
    prog = Progress()
    Reader(tmp_path / "cache").run(p, "qwen2.5vl:7b", ReadRequest(str(pdf), "1-2"), progress=prog)
    assert len(p.calls) == 2 and all(c["images"] for c in p.calls)
    assert prog.pages[1] == "### Gauss\n\nFlux $\\Phi = Q/\\epsilon_0$"
    again = Progress()
    Reader(tmp_path / "cache").run(p, "qwen2.5vl:7b", ReadRequest(str(pdf), "1-2"), progress=again)
    assert len(p.calls) == 2 and again.pages == prog.pages and "earlier" in again.message
    other = Progress()
    Reader(tmp_path / "cache").run(p, "other-model", ReadRequest(str(pdf), "2"), progress=other)
    assert len(p.calls) == 3  # the cache is per model


def test_gemini_reads_three_pages_per_request(tmp_path):
    path = tmp_path / "long.pdf"
    _text_pdf(path, [f"page {i} " * 50 for i in range(1, 6)])
    p = Counting("gemini")
    prog = Progress()
    Reader(None).run(p, "gemini-3.8-flash", ReadRequest(str(path), "1-5"), progress=prog)
    assert [c["pdf"][:5] for c in p.calls] == [b"%PDF-", b"%PDF-"]
    assert sorted(prog.pages) == [1, 2, 3, 4, 5] and "Fake page 4" in prog.pages[4]
    assert joined(prog.pages).count("## Fake page") == 5


def test_reader_errors(pdf, png, tmp_path):
    with pytest.raises(AiError, match="no text layer"):
        Reader(None).run(None, "", ReadRequest(str(png), "", "text"), progress=Progress())
    with pytest.raises(AiError, match="Choose a model"):
        Reader(None).run(None, "", ReadRequest(str(pdf), ""), progress=Progress())
    with pytest.raises(ValueError):
        Reader(None).run(Counting(), "m", ReadRequest(str(pdf), "9"), progress=Progress())


def test_api_read_with_fake_runtime(pdf, tmp_path):
    api = Api(data_dir=tmp_path)
    up = api.upload_source("chapter.pdf", base64.b64encode(pdf.read_bytes()).decode())
    assert up["ok"] and up["pages"] == 3 and up["name"] == "chapter.pdf"
    assert api.source_thumbnails(up["path"], [1])["thumbs"]["1"].startswith("data:image/jpeg")
    ref = {"backend": "fake", "url": "fake://", "model": "fake-writer"}
    job = api.start_read({"path": up["path"], "pages": "2-3", "model": ref})["job"]
    for _ in range(100):
        s = api.job_status(job)
        if s["state"] != "running":
            break
        time.sleep(0.02)
    assert s["state"] == "done", s
    assert list(s["pages"]) == ["2", "3"] and "E = mc^2" in s["pages"]["3"]
    assert (tmp_path / "cache" / "read").exists()
    assert catalog.provider_for(ref, "read").kind == "fake"
