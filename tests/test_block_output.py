from ankigen.ai.cards import parse_block_cards, repair_card
from ankigen.ai.catalog import FakeProvider
from ankigen.ai.generate import Progress, Request, generate_cards
from ankigen.ai.providers import ChatResult

FIELDS = ["Front", "Back", "Extra"]

REPLY = r"""Sure, here are the cards:

Front: What is $\langle \phi | A^\dagger | \psi \rangle$ in terms of $A$?
Back: $$\langle \phi|A^\dagger|\psi\rangle = \langle\psi|A|\phi\rangle^*$$
Extra: Note: this defines the adjoint.
---
Front: Hermitian conjugate of a product?
Back: $(AB)^\\backslash dagger = B^\dagger A^\dagger$
Extra: $(AB)^\dagger = B^\dagger A^\dagger$
---
Front: Matrix form?
Back: $$
A = \begin{pmatrix} a & b \\
Note: c & d \end{pmatrix}
$$
Extra:
"""


def test_block_reply_keeps_latex_untouched():
    cards = parse_block_cards(REPLY, FIELDS)
    assert len(cards) == 3
    assert (
        cards[0]["Front"] == r"What is $\langle \phi | A^\dagger | \psi \rangle$ in terms of $A$?"
    )
    assert cards[0]["Extra"] == "Note: this defines the adjoint."  # "Note:" isn't a field
    assert "Note: c & d" in cards[2]["Back"]  # a Name: line inside $$ stays in the math


def test_repairs_backslash_words_and_duplicate_extra():
    card = parse_block_cards(REPLY, FIELDS)[1]
    assert repair_card(card, FIELDS) == ["backslash", "duplicate_extra"]
    assert card["Back"] == r"$(AB)^\dagger = B^\dagger A^\dagger$" and card["Extra"] == ""


def test_json_reply_still_accepted():
    cards = parse_block_cards('{"cards": [{"Front": "Q", "Back": "A", "Extra": ""}]}', FIELDS)
    assert cards == [{"Front": "Q", "Back": "A", "Extra": ""}]


def test_cloze_and_custom_fields():
    cloze = parse_block_cards("Text: The energy is {{c1::$E=mc^2$}}.\nExtra:", ["Text", "Extra"])
    assert cloze == [{"Text": "The energy is {{c1::$E=mc^2$}}.", "Extra": ""}]
    custom = parse_block_cards(
        "Quantity: Force\nFormula: $F=ma$\nUnits: N", ["Quantity", "Formula", "Units"]
    )
    assert custom[0]["Units"] == "N"


class Recorder(FakeProvider):
    def __init__(self, kind, reply):
        super().__init__("fake://")
        self.kind = kind
        self.reply = reply
        self.kw = None

    def chat(self, model, prompt, **kw):
        self.kw = kw
        return ChatResult(self.reply, seconds=0)


def test_local_models_get_plain_text_and_gemini_gets_json():
    local = Recorder("ollama", REPLY)
    prog = Progress()
    generate_cards(
        local, "qwen3:8b", Request("Some material about operators.", FIELDS), progress=prog
    )
    assert local.kw["schema"] is None and "three dashes" in local.kw["system"]
    assert len(prog.cards) == 3 and prog.cards[1]["flags"]["repaired"] == [
        "backslash",
        "duplicate_extra",
    ]

    gemini = Recorder("gemini", '{"cards": [{"Front": "Q", "Back": "A", "Extra": ""}]}')
    generate_cards(gemini, "gemini-3.8-flash", Request("Material.", FIELDS), progress=Progress())
    assert gemini.kw["schema"] is not None and "JSON only" in gemini.kw["system"]


def test_fake_writer_answers_in_block_format():
    prog = Progress()
    generate_cards(
        FakeProvider("fake://"),
        "fake",
        Request("One idea.\n\nAnother idea.", FIELDS),
        progress=prog,
    )
    assert [c["fields"]["Back"] for c in prog.cards] == ["One idea.", "Another idea."]
