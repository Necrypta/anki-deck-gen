from ankigen.ai.catalog import FakeProvider
from ankigen.ai.equations import check_math, label_equations, math_segments, substitute
from ankigen.ai.generate import Progress, Request, generate_cards
from ankigen.ai.prompts import card_messages
from ankigen.ai.providers import ChatResult
from ankigen.latex import DEFAULT_MACROS

MATERIAL = r"""## Hermite polynomials

They obey $$H_{n+1}(x) = 2xH_n(x) - 2nH_{n-1}(x). \tag{8.14}$$
and $$\frac{d^2H_n}{dx^2} - 2x\frac{dH_n}{dx} + 2nH_n = 0.$$
They are standardized with $K_n = (-1)^n$, and $k_n^{(n)} = 2^n$ is the leading coefficient."""


def test_labels_and_substitution():
    labelled, table = label_equations(MATERIAL)
    assert "$$ [E1]" in labelled and "$$ [E2]" in labelled
    assert "$K_n = (-1)^n$ [E3]" in labelled  # 12+ characters
    assert table["E1"] == "$$H_{n+1}(x) = 2xH_n(x) - 2nH_{n-1}(x)$$"  # no tag, no full stop
    text, unknown = substitute("Recurrence: [E1]; also $[E3]$, [[E2]] and [E9]", table)
    assert text == (
        "Recurrence: $$H_{n+1}(x) = 2xH_n(x) - 2nH_{n-1}(x)$$; also $K_n = (-1)^n$, "
        "$$\\frac{d^2H_n}{dx^2} - 2x\\frac{dH_n}{dx} + 2nH_n = 0$$ and [E9]"
    )
    assert unknown == ["E9"]


def test_check_math_flags_near_misses_only():
    sources = math_segments(MATERIAL)
    assert check_math(r"$H_{n+1}(x)=2x H_n(x)-2nH_{n-1}(x)$", sources) == []  # spacing only
    assert check_math(r"$\left. K_n = (-1)^n \right.$ and $2xH_n(x)$ and $x$", sources) == []
    dropped = check_math(r"$H_{n+1}(x) = 2xH_n(x)$", sources)
    assert dropped == [
        {"got": r"$H_{n+1}(x) = 2xH_n(x)$", "source": r"$H_{n+1}(x) = 2xH_n(x) - 2nH_{n-1}(x)$"}
    ]
    order = check_math(r"$$\frac{dH_n}{dx} - 2x\frac{dH_n}{dx} + 2nH_n = 0$$", sources)
    assert order[0]["source"].startswith(r"$$\frac{d^2H_n}{dx^2}")
    assert check_math(r"$E = mc^2 + \frac{p^2}{2m}$", sources) == []  # unrelated: not flagged


def test_prompt_mentions_labels_and_macros_only_when_asked():
    system, _ = card_messages("x", ["Front", "Back"], labelled=True)
    assert "[E3]" in system and r"\dv" not in system
    assert "Copy mathematics exactly" in system
    with_macros, _ = card_messages("x", ["Front", "Back"], macros=DEFAULT_MACROS)
    assert r"\dv[a]{b}{c}" in with_macros and "[E3]" not in with_macros


class Writer(FakeProvider):
    def __init__(self, reply):
        super().__init__("fake://")
        self.reply = reply
        self.calls = []

    def chat(self, model, prompt, **kw):
        self.calls.append((prompt, kw))
        return ChatResult(self.reply, seconds=0)


def test_generate_swaps_labels_and_flags_retyped_mistakes():
    reply = (
        '{"cards": ['
        '{"Front": "Hermite recurrence?", "Back": "[E1]"},'
        '{"Front": "Hermite ODE?", "Back": "$$\\\\frac{dH_n}{dx} - 2x\\\\frac{dH_n}{dx} + 2nH_n = 0$$"},'
        '{"Front": "Bad label?", "Back": "[E7]"}]}'
    )
    w = Writer(reply)
    prog = Progress()
    generate_cards(
        w, "qwen3:8b", Request(MATERIAL, ["Front", "Back"], macros=DEFAULT_MACROS), progress=prog
    )
    prompt, kw = w.calls[0]
    assert kw["temperature"] == 0.0 and "[E1]" in prompt and r"\dv[a]" not in kw["system"]
    first, second, third = prog.cards
    assert first["fields"]["Back"] == "$$H_{n+1}(x) = 2xH_n(x) - 2nH_{n-1}(x)$$"
    assert first["flags"]["mismatch"] == []
    assert second["flags"]["mismatch"][0]["field"] == "Back"
    assert second["flags"]["mismatch"][0]["source"].startswith(r"$$\frac{d^2H_n}{dx^2}")
    assert third["flags"]["unknown_labels"] == ["E7"]


def test_use_macros_option_offers_them():
    w = Writer('{"cards": []}')
    generate_cards(
        w,
        "m",
        Request(MATERIAL, ["Front", "Back"], macros=DEFAULT_MACROS, use_macros=True),
        progress=Progress(),
    )
    assert r"\dv[a]{b}{c}" in w.calls[0][1]["system"]
