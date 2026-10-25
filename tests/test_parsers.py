import pytest

from ankigen.parsers import parse_text

BLOCK = """\
# deck: Physics::EM
# tags: maxwell em

Front: Gauss's law
Back: $$\\nabla\\cdot\\vb{E} = \\frac{\\rho}{\\varepsilon_0}$$
Extra: Divergence theorem.
---
front: Faraday's law
back: $$
\\nabla\\times\\vb{E} = -\\pdv{\\vb{B}}{t}
$$
Tags: induction
"""


def test_block_basic():
    r = parse_text(BLOCK)
    assert not r.errors
    assert r.deck == "Physics::EM"
    assert r.tags == ["maxwell", "em"]
    assert r.note_type == "basic"
    assert r.fields == ["Front", "Back", "Extra"]
    assert len(r.cards) == 2
    assert r.cards[0].fields["Extra"] == "Divergence theorem."
    assert r.cards[1].fields["Back"].startswith("$$\n")
    assert r.cards[1].tags == ["induction"]


def test_block_multiline_math_not_split_by_colon_lines():
    text = "Front: q\nBack: $$\na: b\n$$\n"
    r = parse_text(text)
    assert not r.errors
    assert r.cards[0].fields["Back"] == "$$\na: b\n$$"


def test_block_declared_fields_ignore_prose_colons():
    text = "# fields: Front, Back\nFront: q\nBack: answer\nNote: still the answer\n"
    r = parse_text(text)
    assert r.cards[0].fields["Back"] == "answer\nNote: still the answer"


def test_block_custom_type():
    text = "# type: custom\nTerm: Lorentz force\nFormula: $F = q(E + v \\times B)$\nUnits: N\n"
    r = parse_text(text)
    assert r.note_type == "custom"
    assert r.fields == ["Term", "Formula", "Units"]


def test_block_cloze_detected():
    r = parse_text("Text: {{c1::$F=ma$}} is Newton's second law\n")
    assert r.note_type == "cloze"
    assert r.fields == ["Text", "Extra"]


def test_block_errors_have_line_numbers():
    r = parse_text("# type: banana\nFront: a\nBack: b\n---\nstray text\n")
    lines = {e.line for e in r.errors}
    assert 1 in lines
    assert 5 in lines


def test_block_unknown_field_on_builtin_type_warns():
    r = parse_text("# type: basic\nFront: a\nBack: b\nHint: c\n")
    assert any("Hint" in e.message for e in r.errors)


def test_delimited_tab():
    r = parse_text("q1\ta1\nq2\ta2\\nmore\n", "delimited")
    assert [c.fields["Front"] for c in r.cards] == ["q1", "q2"]
    assert r.cards[1].fields["Back"] == "a2\nmore"


def test_delimited_pipe_and_extra_fields():
    r = parse_text(
        "#separator:pipe\nF | $F=ma$ | N\nE | $E=mc^2$\n", "delimited",
        separator="pipe", fields=["Front", "Back", "Extra"],
    )
    assert len(r.cards) == 2
    assert r.cards[0].fields["Extra"] == "N"
    assert r.cards[1].fields["Extra"] == ""


def test_delimited_too_many_values():
    r = parse_text("a\tb\tc\n", "delimited")
    assert r.errors and r.errors[0].line == 1


def test_unknown_format():
    with pytest.raises(ValueError):
        parse_text("x", "yaml")
