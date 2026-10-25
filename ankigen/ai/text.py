"""Clean up model output: thinking blocks, code fences, math delimiters and
JSON that small local models get slightly wrong."""

from __future__ import annotations

import json
import re

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"^\s*```[\w-]*\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


def strip_think(text: str) -> str:
    """Drop ``<think>…</think>`` reasoning that DeepSeek-R1 / Qwen3 emit."""
    text = _THINK.sub("", text)
    # A reply cut off mid-thought, or a template that ate the opening tag.
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


def strip_fences(text: str) -> str:
    m = _FENCE.match(text)
    return m.group(1) if m else text


def normalize_math(text: str) -> str:
    r"""Convert ``\(…\)`` / ``\[…\]`` to the app's ``$…$`` / ``$$…$$``."""
    text = re.sub(r"\\\[(.+?)\\\]", lambda m: f"$${m.group(1)}$$", text, flags=re.DOTALL)
    return re.sub(r"\\\((.+?)\\\)", lambda m: f"${m.group(1).strip()}$", text, flags=re.DOTALL)


_SPECIAL = re.compile(r"<\|[^<>|]{0,40}\|>|<nl>|<\|?(?:im_end|im_start|endoftext)\|?>")


def strip_special_tokens(text: str) -> str:
    """Remove leaked template tokens such as ``<|im_end|>`` or ``<|md_start|>``."""
    return _SPECIAL.sub("", text)


def collapse_repeats(text: str, limit: int = 2) -> tuple[str, bool]:
    """Cut a repetition loop: keep a line repeated back-to-back at most ``limit`` times.

    Returns the text and whether anything was cut.
    """
    out: list[str] = []
    run = 0
    looped = False
    for line in text.split("\n"):
        if not line.strip() or line.strip() in ("$$", "---", "```"):
            out.append(line)
            continue
        same = line.strip() == _last_nonblank(out)
        run = run + 1 if same else 0
        if run >= limit:
            looped = True
            continue
        if same:
            # drop the blank lines between repeats too
            while out and not out[-1].strip():
                out.pop()
        out.append(line)
    return "\n".join(out), looped


def _last_nonblank(lines: list[str]) -> str:
    return next((x.strip() for x in reversed(lines) if x.strip()), "")


_MATH_SEG = re.compile(r"\$\$.+?\$\$|(?<!\\)\$(?:\\.|[^$\\\n])+\$", re.DOTALL)
_SECTION = re.compile(r"^[ \t]*\\(sub)?(sub)?section\*?\{(.+?)\}[ \t]*$", re.MULTILINE)
_ENV = re.compile(
    r"\\begin\{(aligned|align\*?|equation\*?|gather\*?|gathered|multline\*?|eqnarray\*?)\}"
    r".*?\\end\{\1\}",
    re.DOTALL,
)


def _outside_math(text: str, fix) -> str:
    """Apply ``fix`` only to the parts of ``text`` that aren't already math."""
    out, last = [], 0
    for m in _MATH_SEG.finditer(text):
        out += [fix(text[last : m.start()]), m.group(0)]
        last = m.end()
    out.append(fix(text[last:]))
    return "".join(out)


def latex_to_markdown(text: str) -> str:
    r"""Fix LaTeX that vision models leave in Markdown: ``\subsection*{X}`` becomes
    a heading, and a bare ``\begin{aligned}…`` block gets the ``$$`` it needs."""

    def fix(part: str) -> str:
        part = _SECTION.sub(
            lambda m: "#" * (2 + bool(m.group(1)) + bool(m.group(2))) + " " + m.group(3), part
        )
        return _ENV.sub(lambda m: f"\n$$\n{m.group(0).strip()}\n$$\n", part)

    return _outside_math(text, fix)


def tidy_math(text: str) -> str:
    r"""Trim padding inside inline math (``$ x $`` → ``$x$``) and drop ``\text{ }`` spacers."""

    def trim(m: re.Match) -> str:
        seg = m.group(0)
        if seg.startswith("$$"):
            return seg
        inner = re.sub(r"\\text\{\s*\}", " ", seg[1:-1]).strip()
        return f"${re.sub(r'  +', ' ', inner)}$" if inner else seg

    return _MATH_SEG.sub(trim, text)


def clean_markdown(text: str) -> str:
    text = collapse_repeats(strip_special_tokens(strip_fences(strip_think(text))))[0]
    text = latex_to_markdown(normalize_math(text))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# LaTeX commands whose first letter is also a JSON escape (\b \f \n \r \t \u).
# Models often write "\frac" inside JSON strings, which parses as a form feed
# followed by "rac"; these get their backslash doubled before parsing.
# fmt: off
LATEX_WORDS = {
    "bar", "beta", "begin", "bf", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr",
    "binom", "bm", "bmod", "boldsymbol", "bot", "box", "boxed", "bra", "braket", "bullet",
    "backslash", "because", "bigcup", "bigcap", "bigoplus", "bigotimes", "frac", "flat", "forall",
    "frown", "footnotesize", "nabla", "ne", "neq", "neg", "newline", "ni", "nleq", "ngeq",
    "nless", "ngtr", "nolimits", "noindent", "norm", "normalsize", "not", "nu", "nparallel",
    "nsubseteq", "rangle", "rceil", "rfloor", "right", "rightarrow", "rightharpoonup", "rho",
    "rm", "rvert", "rVert", "rbrace", "rbrack", "tag", "tan", "tanh", "tau", "text", "textbf",
    "textit", "textrm", "textsf", "texttt", "tfrac", "theta", "therefore", "tilde", "times", "to",
    "top", "triangle", "triangleq", "tt", "textstyle", "underbrace", "underline", "uparrow",
    "updownarrow", "upsilon",
}
# fmt: on


def repair_latex_escapes(raw: str, extra_words: set[str] | None = None) -> str:
    r"""Double backslashes inside JSON strings that are really LaTeX.

    ``\frac`` → ``\\frac``, ``\nabla`` → ``\\nabla``, and invalid escapes such as
    ``\alpha`` (invalid in JSON) too. Real escapes like ``\n`` before ordinary
    words, ``\"`` and ``\\`` are left alone.
    """
    words = LATEX_WORDS | (extra_words or set())
    out: list[str] = []
    in_str = False
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == '"':
            in_str = not in_str
            out.append(c)
            i += 1
        elif c == "\\" and in_str and i + 1 < len(raw):
            nxt = raw[i + 1]
            word = re.match(r"[A-Za-z]+", raw[i + 1 :])
            if nxt in '"\\/':
                out.append(raw[i : i + 2])
            elif nxt == "u" and re.match(r"u[0-9a-fA-F]{4}", raw[i + 1 : i + 6]):
                out.append(raw[i : i + 6])
                i += 4
            elif nxt in "bfnrt" and not (word and word.group(0) in words):
                out.append(raw[i : i + 2])
            else:
                out.append("\\\\" + nxt)
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_json_lenient(text: str, extra_words: set[str] | None = None) -> object:
    """Parse the first JSON value in a reply, repairing common model mistakes.

    Handles thinking blocks, code fences, chatter around the JSON, LaTeX
    backslashes, and output truncated mid-list (keeps the complete items).
    Raises ``ValueError`` when nothing usable is found.
    """
    text = strip_fences(strip_think(text))
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("No JSON found in the reply")
    body = repair_latex_escapes(text[min(starts) :], extra_words)
    try:
        return json.JSONDecoder().raw_decode(body)[0]
    except json.JSONDecodeError:
        pass
    fixed = _close_truncated(body)
    if fixed is not None:
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
    raise ValueError("The reply wasn't valid JSON")


def _close_truncated(body: str) -> str | None:
    """Cut after the last complete object inside a list and close the brackets."""
    stack: list[str] = []
    in_str = esc = False
    best: tuple[int, list[str]] | None = None
    for i, c in enumerate(body):
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in "{[":
            stack.append(c)
        elif c in "}]":
            if not stack:
                break
            opened = stack.pop()
            if opened == "{" and stack and stack[-1] == "[":
                best = (i, stack.copy())
            if not stack:
                return None  # complete value: truncation isn't the problem
    if best is None:
        return None
    end, open_stack = best
    closers = "".join("]" if s == "[" else "}" for s in reversed(open_stack))
    return body[: end + 1] + closers


def split_page_marks(text: str, pages: list[int]) -> dict[int, str]:
    """Split a whole-document transcription on ``<!-- page N -->`` markers.

    Text before the first marker, or everything when there are no markers,
    goes to the first page.
    """
    out = {n: "" for n in pages}
    parts = re.split(r"<!--\s*page\s+(\d+)\s*-->", text)
    out[pages[0]] = parts[0].strip()
    for num, body in zip(parts[1::2], parts[2::2]):
        n = int(num)
        key = n if n in out else pages[0]
        out[key] = (out[key] + "\n\n" + body.strip()).strip()
    return out
