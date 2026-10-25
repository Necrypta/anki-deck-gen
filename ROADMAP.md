# Roadmap & feature ideas

## Planned: new card sources

Both plug into `ankigen/providers/` through the `CardSource` interface and feed the same Import preview the text parsers use.

- **OCR**
  - Text from screenshots, scans and photos: Tesseract (`pytesseract`) or PaddleOCR.
  - **Equations → LaTeX** with a math-OCR model (e.g. `pix2tex` / LaTeX-OCR), so a screenshot of a textbook formula becomes `$…$`.
  - Paste an image from the clipboard straight into a field.
- **AI generation**
  - Local: **Ollama** (`http://localhost:11434`), with no API key and fully offline.
  - Online: Anthropic / OpenAI-compatible APIs with a user-supplied key (stored in Windows Credential Manager, not plain text).
  - "Generate N cards from these notes / this PDF section", with structured JSON output mapped to the deck's fields and LaTeX in `$…$`.
  - Review step: accept, edit or discard each suggested card before it's added.

## Content

- Images and diagrams in cards (paste/drag, bundled as Anki media).
- PDF import with page-range selection (text layer, falling back to OCR).
- Markdown / Obsidian notes import (headings → cards, `==highlight==` → cloze).
- CSV/Excel import with a column mapper.
- Audio fields (e.g. pronunciation) for non-physics decks.

## Physics-specific

- **Constants & units palette**: insert ħ, ε₀, μ₀, k_B, N_A, e, mₑ with values and SI units.
- **Formula-sheet mode**: paste a list of `Name: equation` lines to get name→equation cards (optionally reversed).
- **Auto-cloze an equation**: one cloze per term or symbol of a formula.
- **Dimensional-analysis lint**: warn when the two sides of an equation have mismatched units.
- **Derivation cards**: step-by-step cards that reveal one line of a derivation at a time.
- **TikZ / plot support**: render small diagrams to SVG at export time.

## Quality

- Duplicate detection (exact and near-duplicate fronts).
- Card lint: very long answers, multiple facts per card, unmatched `$`, KaTeX errors. (Unclosed `$` and render errors are already flagged on export.)
- Spell check that skips math.
- Front/back preview in Anki's own night-mode styling.

## Workflow

- **Deck projects**: save and open several decks (`.adg` JSON files) instead of one autosaved session.
- Multiple decks and batch export.
- **AnkiConnect**: push cards straight into a running Anki without a file, and pull existing decks back in for editing.
- Templates and presets (e.g. "Definition", "Formula + units", "Concept → example").
- Tag manager with rename and merge.
- Undo/redo history across the whole deck.
- Customisable card CSS and fonts per deck.

## AI extras (once AI is wired up)

- Suggest tags for each card.
- Rewrite verbose cards into atomic ones.
- Fill the Extra field with a short "why it's true" explanation.
- Generate cloze variants or reversed questions.
- "Explain my mistake": on a selected card, generate a conceptual follow-up card.
