# Roadmap & feature ideas

## Planned: AI card generation (in progress)

The shared backend is in `ankigen/ai/`. It's runtime- and model-agnostic: Ollama, any OpenAI-compatible server (LM Studio, llama.cpp, Jan, vLLM, or hosted services such as OpenRouter and DeepSeek), and Gemini.

- **Step 0 (done):** `scripts/ai_bakeoff.py` compares models on real pages to choose suggested defaults.
- **Text and Markdown → cards (done in 0.3):**
  - a Generate page: source → editable Markdown → options → review and add;
  - Settings → AI, with detected runtimes, model pickers and a Gemini key stored in Windows Credential Manager.
- **PDFs and images:**
  - page-range picker;
  - text layer or visual reading for scans and equations;
  - paste a screenshot.
- **Polish:** flag duplicates against the deck, estimate time and quota, regenerate a single card.

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
