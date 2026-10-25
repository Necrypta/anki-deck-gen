"""Read PDF pages and images into Markdown + LaTeX with a vision model.

Results are cached per file, page and model in the data folder, so reading
the same pages again (say, after changing the card options) is instant.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from .generate import Progress
from .http import AiError
from .prompts import READ_SYSTEM, read_messages, read_pdf_user
from .providers import Provider
from .sources import (
    IMAGE_EXT,
    PDF_EXT,
    TEXT_EXT,
    Page,
    load_image,
    load_pdf,
    parse_page_range,
    pdf_page_count,
    pdf_subset,
    source_kind,
)
from .text import clean_markdown, split_page_marks

GEMINI_PAGES_PER_REQUEST = 3  # one request for 3 pages took ~6 min on the free tier
THUMB_WIDTH = 150
MAX_UPLOAD = 60 * 1024 * 1024


def file_hash(path: str | Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def describe_source(path: str | Path) -> dict:
    """What the Generate page needs to show for a file the user picked."""
    path = Path(path)
    kind = source_kind(path)
    info: dict = {"kind": kind, "path": str(path), "name": path.name}
    if kind == "text":
        info["text"] = path.read_text(encoding="utf-8-sig", errors="replace")
    elif kind == "pdf":
        pages = load_pdf(path, render=False)
        info["pages"] = len(pages)
        info["text_pages"] = [p.number for p in pages if p.has_text_layer]
    else:
        info["pages"] = 1
        info["text_pages"] = []
    return info


def save_upload(folder: Path, name: str, data_b64: str) -> Path:
    """Store a dropped or pasted file (the browser can't hand over a path)."""
    data = base64.b64decode(data_b64.split(",", 1)[-1])
    if len(data) > MAX_UPLOAD:
        raise ValueError("That file is larger than 60 MB")
    ext = Path(name).suffix.lower()
    if ext not in PDF_EXT | IMAGE_EXT | TEXT_EXT:
        raise ValueError(f"Unsupported file type: {ext or name}")
    folder.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "_", Path(name).stem)[:60] or "file"
    target = folder / f"{stem}-{hashlib.sha1(data).hexdigest()[:8]}{ext}"
    target.write_bytes(data)
    return target


def thumbnails(path: str | Path, pages: list[int], width: int = THUMB_WIDTH) -> dict[int, str]:
    """Small JPEG data URLs for the page strip."""
    from PIL import Image

    path = Path(path)
    out: dict[int, str] = {}
    if source_kind(path) == "image":
        imgs = {1: Image.open(path)}
    else:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        try:
            imgs = {}
            for n in pages:
                page = pdf[n - 1]
                scale = width / page.get_width()
                imgs[n] = page.render(scale=scale * 2).to_pil()
                page.close()
        finally:
            pdf.close()
    for n, img in imgs.items():
        img = img.convert("RGB")
        img.thumbnail((width * 2, width * 4))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70)
        out[n] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return out


@dataclass
class ReadRequest:
    path: str
    pages: str = ""  # page range, e.g. "12-15"; empty = all
    mode: str = "ai"  # "ai": read pages with the model; "text": PDF text layer only


class Reader:
    def __init__(self, cache_dir: Path | None) -> None:
        self.cache_dir = cache_dir

    def _cache(self, key: str, n: int, model: str) -> Path | None:
        if self.cache_dir is None:
            return None
        safe = re.sub(r"[^\w.-]+", "_", model)
        return self.cache_dir / f"{key}-{safe}-p{n}.md"

    def run(
        self,
        provider: Provider | None,
        model: str,
        req: ReadRequest,
        *,
        progress: Progress,
        cancel: threading.Event | None = None,
    ) -> None:
        path = Path(req.path)
        kind = source_kind(path)
        if kind == "text":
            raise AiError("Text files don't need reading")
        numbers = [1] if kind == "image" else parse_page_range(req.pages, pdf_page_count(path))
        progress.total = len(numbers)

        if req.mode == "text":
            if kind == "image":
                raise AiError("An image has no text layer; read it with a model instead")
            for page in load_pdf(path, numbers, render=False):
                progress.pages[page.number] = _plain_text(page.text)
                progress.done += 1
            empty = [n for n, t in progress.pages.items() if len(t.strip()) < 20]
            if empty:
                progress.warnings.append(
                    f"Pages {_ranges(empty)} have no text layer (probably scans); read them with a model."
                )
            progress.message = f"{len(numbers)} pages"
            return

        if provider is None:
            raise AiError("Choose a model for reading pages in Settings → AI")
        key = file_hash(path)
        todo = []
        for n in numbers:
            cached = self._cache(key, n, model)
            if cached is not None and cached.exists():
                progress.pages[n] = cached.read_text("utf-8")
                progress.done += 1
            else:
                todo.append(n)
        if not todo:
            progress.message = f"{len(numbers)} pages (from earlier)"
            return

        whole_pdf = provider.kind == "gemini" and kind == "pdf"
        step = GEMINI_PAGES_PER_REQUEST if whole_pdf else 1
        for i in range(0, len(todo), step):
            if cancel is not None and cancel.is_set():
                return
            group = todo[i : i + step]
            label = f"page {group[0]}" if len(group) == 1 else f"pages {group[0]}–{group[-1]}"
            progress.message = f"Reading {label} ({progress.done + 1} of {progress.total})"
            if whole_pdf:
                result = provider.chat(
                    model,
                    read_pdf_user(group),
                    system=READ_SYSTEM,
                    pdf=pdf_subset(path, group),
                    temperature=0.0,
                    cancel=cancel,
                )
                texts = split_page_marks(result.text, group)
            else:
                page = load_image(path) if kind == "image" else load_pdf(path, group)[0]
                system, user = read_messages(model)
                result = provider.chat(
                    model, user, system=system, images=[page.image], temperature=0.0, cancel=cancel
                )
                texts = {group[0]: result.text}
            if result.truncated:
                progress.warnings.append(f"{label.capitalize()}: the reply was cut off")
            for n, text in texts.items():
                md = clean_markdown(text)
                progress.pages[n] = md
                cached = self._cache(key, n, model)
                if cached is not None and md:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_text(md, "utf-8")
            progress.done += len(group)
        progress.message = f"{len(numbers)} pages"


def _plain_text(text: str) -> str:
    """Tidy a PDF text layer: re-join hyphenated line breaks and wrapped lines."""
    text = text.replace("￾", "").replace("­", "")
    text = re.sub(r"-\n(?=[a-z])", "", text)
    paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    return "\n\n".join(p for p in paras if p)


def _ranges(nums: list[int]) -> str:
    nums = sorted(nums)
    out, start, prev = [], nums[0], nums[0]
    for n in nums[1:] + [None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        out.append(str(start) if start == prev else f"{start}–{prev}")
        if n is not None:
            start = prev = n
    return ", ".join(out)


def joined(pages: dict[int, str]) -> str:
    return "\n\n".join(t.strip() for _, t in sorted(pages.items()) if t.strip())


__all__ = [
    "Page",
    "ReadRequest",
    "Reader",
    "describe_source",
    "joined",
    "save_upload",
    "thumbnails",
]
