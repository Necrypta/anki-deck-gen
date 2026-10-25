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


def clean_markdown(text: str) -> str:
    return normalize_math(strip_fences(strip_think(text))).strip()


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
