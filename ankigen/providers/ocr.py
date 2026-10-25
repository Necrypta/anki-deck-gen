"""OCR card source (planned).

Intended approach:
  * Plain text: Tesseract via ``pytesseract`` or PaddleOCR.
  * Equations: a LaTeX-OCR model (e.g. ``pix2tex``) so screenshots of
    textbook formulas come back as ``$...$`` LaTeX.
  * The recognised text is then either split with a parser or handed to an
    AI source to turn into question/answer pairs.
"""

from __future__ import annotations

from ..models import Card
from .base import SourceInput


class OcrSource:
    name = "ocr"

    def available(self) -> bool:
        return False

    def generate(self, source: SourceInput) -> list[Card]:
        raise NotImplementedError("OCR import isn't implemented yet. See ROADMAP.md")
