"""Keep equations exact when a model writes cards.

Small models make copying mistakes when they retype LaTeX: a dropped term, a
first derivative instead of a second. So the material's equations are
labelled ``[E1]``, ``[E2]``… and the model puts a label on the card instead
of retyping; the label is swapped back for the exact source math afterwards.
Math the model still typed itself is compared with the material, and a near
miss is flagged with the source version to use instead.
"""

from __future__ import annotations

import difflib
import re

from .text import _MATH_SEG

MIN_LABEL_CHARS = 12  # shorter inline math ($x$, $K_n$) is easy to copy
MIN_CHECK_CHARS = 6
CLOSE_ENOUGH = 0.6

_LABEL = re.compile(r"\$\$?\s*(?:\[\[?|⟦)E(\d+)(?:\]\]?|⟧)\s*\$?\$?|(?:\[\[?|⟦)E(\d+)(?:\]\]?|⟧)")


def math_segments(text: str) -> list[str]:
    """Every ``$…$`` / ``$$…$$`` in ``text``, with its delimiters."""
    return [m.group(0) for m in _MATH_SEG.finditer(text)]


def label_equations(text: str, min_chars: int = MIN_LABEL_CHARS) -> tuple[str, dict[str, str]]:
    """Append ``[E1]``… after each display equation and each longer inline one."""
    table: dict[str, str] = {}
    out: list[str] = []
    last = 0
    for m in _MATH_SEG.finditer(text):
        seg = m.group(0)
        body = seg.strip("$").strip()
        out.append(text[last : m.end()])
        last = m.end()
        if seg.startswith("$$") or len(body) >= min_chars:
            label = f"E{len(table) + 1}"
            table[label] = for_card(seg)
            out.append(f" [{label}]")
    out.append(text[last:])
    return "".join(out), table


def for_card(seg: str) -> str:
    """Source math as it should appear on a card: no equation number or end punctuation."""
    display = seg.startswith("$$")
    body = re.sub(r"\\tag\*?\{[^}]*\}", "", seg.strip().strip("$"))
    body = re.sub(r"[\s.,;]+$", "", body.strip()).strip()
    return f"$${body}$$" if display else f"${body}$"


def substitute(text: str, table: dict[str, str]) -> tuple[str, list[str]]:
    """Replace labels with the source math; returns the text and unknown labels."""
    unknown: list[str] = []

    def swap(m: re.Match) -> str:
        label = f"E{m.group(1) or m.group(2)}"
        if label in table:
            return table[label]
        unknown.append(label)
        return m.group(0)

    return _LABEL.sub(swap, text), unknown


def normalize(math: str) -> str:
    """A spacing- and markup-insensitive form of a math segment, for comparing."""
    s = math.strip().strip("$")
    s = re.sub(r"\\tag\{[^}]*\}", "", s)
    s = re.sub(r"\\(left|right)\.|\\(left|right|big|Big|bigg|Bigg)(?![A-Za-z])", "", s)
    s = re.sub(r"\\[,;:! ]|\\q?quad(?![A-Za-z])", "", s)
    s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"\{(\\?[A-Za-z0-9])\}", r"\1", s)
    return s.rstrip(".,;")


_PIECES = re.compile(r",|;|&|\\\\|\\q?quad(?![A-Za-z])|\\Rightarrow|\\implies|\\Longrightarrow")


def check_math(text: str, sources: list[str]) -> list[dict[str, str]]:
    """Math in ``text`` that nearly, but not exactly, matches the material.

    Exact matches and parts of a source equation are fine. A near miss comes
    back as ``{"got": …, "source": …}`` with the closest source equation.
    """
    normed = [(normalize(s), s) for s in sources]
    pieces = {normalize(p) for s in sources for p in _PIECES.split(s.strip().strip("$"))}
    issues = []
    for seg in math_segments(text):
        n = normalize(seg)
        if len(n) < MIN_CHECK_CHARS or n in pieces or any(n == src for src, _ in normed):
            continue
        # An expression without "=" quoted from inside a longer equation is fine;
        # a relation must match a whole equation or one of its parts.
        if "=" not in n and any(n in src for src, _ in normed):
            continue
        best, best_ratio = None, 0.0
        for src, original in normed:
            ratio = difflib.SequenceMatcher(None, n, src).ratio()
            if ratio > best_ratio:
                best, best_ratio = original, ratio
        if best is not None and best_ratio >= CLOSE_ENOUGH:
            # Keep the card's delimiter style ($ or $$).
            body = for_card(best).strip("$")
            source = f"$${body}$$" if seg.startswith("$$") else f"${body}$"
            issues.append({"got": seg, "source": source})
    return issues
