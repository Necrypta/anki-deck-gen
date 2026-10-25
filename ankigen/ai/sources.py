"""Load study material: PDF pages (text layer + rendered image), images and text files."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
TEXT_EXT = {".txt", ".md", ".markdown", ".tex"}

# A page with fewer visible characters than this is treated as a scan.
MIN_TEXT_CHARS = 200


@dataclass
class Page:
    number: int  # 1-based
    text: str = ""  # PDF text layer ("" for scans and images)
    image: bytes | None = None  # PNG

    @property
    def has_text_layer(self) -> bool:
        return len(re.sub(r"\s", "", self.text)) >= MIN_TEXT_CHARS


def parse_page_range(spec: str | None, count: int) -> list[int]:
    """``"1-3, 7"`` → ``[1, 2, 3, 7]``; empty means every page. Raises ``ValueError``."""
    if not spec or not spec.strip():
        return list(range(1, count + 1))
    pages: list[int] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d*))?", part)
        if not m:
            raise ValueError(f"Bad page range: {part!r}")
        a = int(m.group(1))
        b = a if m.group(2) is None else int(m.group(2) or count)
        if a < 1 or b > count or a > b:
            raise ValueError(f"Pages {part} are outside 1-{count}")
        pages += [p for p in range(a, b + 1) if p not in pages]
    return pages


def _png(img, max_side: int) -> bytes:
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def pdf_page_count(path: str | Path) -> int:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        return len(pdf)
    finally:
        pdf.close()


def load_pdf(
    path: str | Path,
    pages: list[int] | None = None,
    *,
    dpi: int = 150,
    max_side: int = 1800,
    render: bool = True,
) -> list[Page]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        out = []
        for n in pages or range(1, len(pdf) + 1):
            page = pdf[n - 1]
            textpage = page.get_textpage()
            text = textpage.get_text_range().replace("\r\n", "\n")
            textpage.close()
            image = _png(page.render(scale=dpi / 72).to_pil(), max_side) if render else None
            page.close()
            out.append(Page(n, text, image))
        return out
    finally:
        pdf.close()


def pdf_subset(path: str | Path, pages: list[int]) -> bytes:
    """A new PDF holding only ``pages``, for backends that read PDFs directly."""
    import pypdfium2 as pdfium

    src = pdfium.PdfDocument(str(path))
    dst = pdfium.PdfDocument.new()
    try:
        dst.import_pages(src, [p - 1 for p in pages])
        buf = io.BytesIO()
        dst.save(buf)
        return buf.getvalue()
    finally:
        dst.close()
        src.close()


def load_image(path: str | Path, *, max_side: int = 1800) -> Page:
    from PIL import Image

    with Image.open(path) as img:
        return Page(1, "", _png(img, max_side))


def source_kind(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    if ext in PDF_EXT:
        return "pdf"
    if ext in IMAGE_EXT:
        return "image"
    if ext in TEXT_EXT:
        return "text"
    raise ValueError(f"Unsupported file type: {ext or Path(path).name}")
