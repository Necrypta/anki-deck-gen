"""Anki Deck Generator: build .apkg decks with LaTeX from text."""

__version__ = "0.2.0"


def build_label() -> str:
    from ._build import BUILD

    return BUILD


def is_release() -> bool:
    """True only for tagged release builds (label like ``v0.2.0``)."""
    return build_label() == f"v{__version__}"
