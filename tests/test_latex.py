import pytest

from ankigen.latex import field_to_html, macro_preamble, to_anki


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("$F=ma$", r"\(F=ma\)"),
        ("$$E=mc^2$$", r"\[E=mc^2\]"),
        ("a $x$ and $$y$$ b", r"a \(x\) and \[y\] b"),
        (r"costs \$5", "costs $5"),
        (r"$\$5$", r"\(\$5\)"),
        ("`$not math$`", "`$not math$`"),
        ("unclosed $x", "unclosed $x"),
        ("$$\n\\int_0^1 x\\,dx\n$$", "\\[\n\\int_0^1 x\\,dx\n\\]"),
        (r"$\frac{a}{b}$", r"\(\frac{a}{b}\)"),
        ("$$", "$$"),
    ],
)
def test_to_anki(src, expected):
    assert to_anki(src) == expected


def test_field_to_html_escapes_text_but_not_math():
    out = field_to_html("a < b\n$x < y$")
    assert out == r"a &lt; b<br>\(x \lt  y\)"


def test_field_to_html_keeps_user_html():
    assert field_to_html("<b>bold</b> $x$") == r"<b>bold</b> \(x\)"


def test_macro_preamble_counts_args():
    pre = macro_preamble({r"\vb": r"\mathbf{#1}", r"\hb": r"\hbar"})
    assert r"\newcommand{\vb}[1]{\mathbf{#1}}" in pre
    assert r"\newcommand{\hb}{\hbar}" in pre
    assert macro_preamble({}) == ""
