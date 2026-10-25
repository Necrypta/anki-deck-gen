r"""Convert the app's ``$``-style math into delimiters Anki's MathJax understands.

Users write ``$...$`` for inline math and ``$$...$$`` for display math, the same
as in most notes apps. Anki renders ``\(...\)`` and ``\[...\]``, so this module
rewrites the former into the latter. A literal dollar sign is written ``\$``.
Inline code spans (backticks) are left untouched.
"""

from __future__ import annotations

import html
import re

# Physics-flavoured defaults, roughly mirroring the LaTeX `physics` package.
DEFAULT_MACROS: dict[str, str] = {
    r"\vb": r"\mathbf{#1}",
    r"\vu": r"\hat{\mathbf{#1}}",
    r"\dv": r"\frac{d#1}{d#2}",
    r"\pdv": r"\frac{\partial #1}{\partial #2}",
    r"\abs": r"\left|#1\right|",
    r"\norm": r"\left\lVert#1\right\rVert",
    r"\ev": r"\left\langle#1\right\rangle",
    r"\bra": r"\left\langle#1\right|",
    r"\ket": r"\left|#1\right\rangle",
    r"\braket": r"\left\langle#1\middle|#2\right\rangle",
    r"\grad": r"\nabla",
    r"\curl": r"\nabla\times",
    r"\divg": r"\nabla\cdot",
}

_ARG_RE = re.compile(r"#(\d)")


def to_anki(text: str) -> str:
    r"""Rewrite ``$$..$$`` to ``\[..\]`` and ``$..$`` to ``\(..\)``.

    Unterminated math is left as-is so nothing gets lost.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            if text[i + 1] == "$":
                out.append("$")
                i += 2
                continue
            out.append(text[i : i + 2])
            i += 2
            continue
        if ch == "`":
            end = text.find("`", i + 1)
            if end != -1:
                out.append(text[i : end + 1])
                i = end + 1
                continue
        if ch == "$":
            display = text.startswith("$$", i)
            delim = "$$" if display else "$"
            end = _find_closing(text, i + len(delim), delim)
            if end != -1:
                body = text[i + len(delim) : end]
                if display:
                    out.append(r"\[" + body + r"\]")
                else:
                    out.append(r"\(" + body + r"\)")
                i = end + len(delim)
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _find_closing(text: str, start: int, delim: str) -> int:
    i = start
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text.startswith(delim, i):
            # Avoid treating the first `$` of a `$$` as an inline close.
            if delim == "$" and text.startswith("$$", i):
                return -1 if i == start else i
            return i if i > start else -1
        i += 1
    return -1


def field_to_html(text: str) -> str:
    """Prepare a raw field for Anki: convert math and keep line breaks.

    Text outside math is HTML-escaped unless it already looks like HTML, so
    users can still paste ``<b>`` or ``<img>`` tags deliberately.
    """
    converted = to_anki(text)
    if not re.search(r"<[a-zA-Z/][^>]*>", converted):
        converted = _escape_outside_math(converted)
    return converted.replace("\r\n", "\n").replace("\n", "<br>")


def _escape_outside_math(text: str) -> str:
    parts = re.split(r"(\\\(.*?\\\)|\\\[.*?\\\])", text, flags=re.DOTALL)
    return "".join(
        html.escape(p, quote=False) if idx % 2 == 0 else p.replace("<", r"\lt ").replace(">", r"\gt ")
        for idx, p in enumerate(parts)
    )


def macro_preamble(macros: dict[str, str]) -> str:
    r"""Build a hidden MathJax block defining ``macros`` for a card template."""
    if not macros:
        return ""
    defs = []
    for name, body in macros.items():
        nargs = max((int(m) for m in _ARG_RE.findall(body)), default=0)
        arg = f"[{nargs}]" if nargs else ""
        defs.append(rf"\newcommand{{{name}}}{arg}{{{body}}}")
    return '<div style="display:none">\\(' + "".join(defs) + "\\)</div>\n"
