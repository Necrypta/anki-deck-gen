r"""Convert the app's ``$``-style math into delimiters Anki's MathJax understands.

Users write ``$...$`` for inline math and ``$$...$$`` for display math, the same
as in most notes apps. Anki renders ``\(...\)`` and ``\[...\]``, so this module
rewrites the former into the latter. A literal dollar sign is written ``\$``.
Inline code spans (backticks) are left untouched.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MacroDef:
    r"""A user macro, e.g. ``\dv`` with 3 args whose first (``#1``) is optional.

    ``optional`` is the default for ``#1`` when it is optional, else ``None``,
    matching LaTeX's ``\newcommand{\name}[args][default]{body}``.
    """

    name: str
    body: str
    args: int = 0
    optional: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "args": self.args, "optional": self.optional, "body": self.body}


# Physics-flavoured defaults, roughly mirroring the LaTeX `physics` package.
# \dv and \pdv take an optional order: \dv[2]{y}{x} is the second derivative.
DEFAULT_MACROS: list[MacroDef] = [
    MacroDef(r"\vb", r"\mathbf{#1}", 1),
    MacroDef(r"\vu", r"\hat{\mathbf{#1}}", 1),
    MacroDef(r"\dv", r"\frac{d^{#1} #2}{d #3^{#1}}", 3, ""),
    MacroDef(r"\pdv", r"\frac{\partial^{#1} #2}{\partial #3^{#1}}", 3, ""),
    MacroDef(r"\abs", r"\left|#1\right|", 1),
    MacroDef(r"\norm", r"\left\lVert#1\right\rVert", 1),
    MacroDef(r"\ev", r"\left\langle#1\right\rangle", 1),
    MacroDef(r"\bra", r"\left\langle#1\right|", 1),
    MacroDef(r"\ket", r"\left|#1\right\rangle", 1),
    MacroDef(r"\braket", r"\left\langle#1\middle|#2\right\rangle", 2),
    MacroDef(r"\grad", r"\nabla"),
    MacroDef(r"\curl", r"\nabla\times"),
    MacroDef(r"\divg", r"\nabla\cdot"),
]

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
        html.escape(p, quote=False)
        if idx % 2 == 0
        else p.replace("<", r"\lt ").replace(">", r"\gt ")
        for idx, p in enumerate(parts)
    )


def _infer_args(body: str) -> int:
    return max((int(m) for m in _ARG_RE.findall(body)), default=0)


def normalize_macros(value: Any) -> list[MacroDef]:
    r"""Accept a list of MacroDef / ``{name, args, optional, body}`` dicts, or the
    legacy ``{"\\name": "body"}`` mapping (args inferred from ``#n``)."""
    if not value:
        return []
    if isinstance(value, Mapping):
        return [MacroDef(str(k), str(v), _infer_args(str(v))) for k, v in value.items()]
    out: list[MacroDef] = []
    for item in value if isinstance(value, Iterable) else []:
        if isinstance(item, MacroDef):
            out.append(item)
            continue
        body = str(item.get("body", ""))
        optional = item.get("optional")
        out.append(
            MacroDef(
                name=str(item["name"]),
                body=body,
                args=int(item.get("args") if item.get("args") is not None else _infer_args(body)),
                optional=None if optional is None else str(optional),
            )
        )
    return out


def macro_preamble(macros: Any) -> str:
    r"""Build a hidden MathJax block defining ``macros`` for a card template.

    MathJax 3 (used by Anki) supports the optional-argument form
    ``\newcommand{\dv}[3][]{...}`` natively.
    """
    defs = []
    for m in normalize_macros(macros):
        spec = f"[{m.args}]" if m.args else ""
        if m.args and m.optional is not None:
            spec += f"[{m.optional}]"
        defs.append(rf"\newcommand{{{m.name}}}{spec}{{{m.body}}}")
    if not defs:
        return ""
    return '<div style="display:none">\\(' + "".join(defs) + "\\)</div>\n"


# ---------------------------------------------------------------- expansion
# Mirrors expandMacros in frontend/src/lib/macros.ts. Decks opened from an
# .apkg keep their own card templates, which don't carry the macro preamble,
# so their exported fields get the macros written out instead.

_MAX_DEPTH = 32


class MacroError(ValueError):
    pass


def _is_letter(c: str | None) -> bool:
    return bool(c) and ("a" <= c <= "z" or "A" <= c <= "Z")


def _at(s: str, i: int) -> str | None:
    return s[i] if 0 <= i < len(s) else None


def _skip_spaces(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def _match_group(s: str, start: int, open_: str, close: str) -> int:
    depth = braces = 0
    i = start
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if open_ == "[":
            if c == "{":
                braces += 1
            elif c == "}":
                braces -= 1
            elif c == "]" and braces == 0:
                return i
        elif c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _strip_outer_braces(arg: str) -> str:
    if arg.startswith("{") and _match_group(arg, 0, "{", "}") == len(arg) - 1:
        return arg[1:-1]
    return arg


def _read_arg(s: str, i: int, name: str) -> tuple[str, int]:
    i = _skip_spaces(s, i)
    if i >= len(s):
        raise MacroError(f"{name} is missing an argument")
    c = s[i]
    if c == "{":
        end = _match_group(s, i, "{", "}")
        if end == -1:
            raise MacroError(f"Unclosed {{ in an argument of {name}")
        return s[i + 1 : end], end + 1
    if c == "}":
        raise MacroError(f"{name} is missing an argument")
    if c == "\\":
        j = i + 1
        if _is_letter(_at(s, j)):
            while _is_letter(_at(s, j)):
                j += 1
        else:
            j += 1
        return s[i:j], j
    return c, i + 1


def _expand(s: str, defs: dict[str, MacroDef], depth: int) -> str:
    if depth > _MAX_DEPTH:
        raise MacroError("Macros expand into each other forever (check for a loop)")
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i] != "\\":
            out.append(s[i])
            i += 1
            continue
        j = i + 1
        if not _is_letter(_at(s, j)):
            out.append(s[i : i + 2])
            i += 2
            continue
        while _is_letter(_at(s, j)):
            j += 1
        name = s[i:j]
        d = defs.get(name)
        if d is None:
            out.append(name)
            i = j
            continue
        args: list[str] = []
        k = j
        mandatory = d.args
        if d.optional is not None and d.args > 0:
            at = _skip_spaces(s, k)
            if _at(s, at) == "[":
                end = _match_group(s, at, "[", "]")
                if end == -1:
                    raise MacroError(f"Unclosed [ after {name}")
                args.append(_strip_outer_braces(s[at + 1 : end]))
                k = end + 1
            else:
                args.append(d.optional)
            mandatory -= 1
        for _ in range(mandatory):
            arg, k = _read_arg(s, k, name)
            args.append(arg)

        def sub(m: re.Match, args: list[str] = args, body: str = d.body) -> str:
            n = int(m.group(1))
            if n > len(args):
                return m.group(0)
            arg = args[n - 1]
            glue = _is_letter(_at(arg, 0)) and re.search(r"\\[A-Za-z]+$", body[: m.start()])
            return f" {arg}" if glue else arg

        result = _expand(re.sub(r"#([1-9])", sub, d.body), defs, depth + 1)
        if re.search(r"\\[A-Za-z]+$", result) and _is_letter(_at(s, k)):
            result += " "
        out.append(result)
        i = k
    return "".join(out)


def expand_macros(tex: str, macros: Any) -> str:
    defs = {m.name: m for m in normalize_macros(macros)}
    if not defs or "\\" not in tex:
        return tex
    return _expand(tex, defs, 0)


def expand_field_macros(text: str, macros: Any) -> str:
    """Write out macros inside the ``$…$`` / ``$$…$$`` math of a field.

    Math is found the same way :func:`to_anki` finds it. Math that fails to
    expand (say, a missing argument) is left as typed.
    """
    defs = normalize_macros(macros)
    if not defs or "$" not in text:
        return text
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
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
            delim = "$$" if text.startswith("$$", i) else "$"
            end = _find_closing(text, i + len(delim), delim)
            if end != -1:
                body = text[i + len(delim) : end]
                try:
                    body = expand_macros(body, defs)
                except MacroError:
                    pass
                out.append(delim + body + delim)
                i = end + len(delim)
                continue
        out.append(ch)
        i += 1
    return "".join(out)
