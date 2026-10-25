# Changelog

Each pull request adds a line under **Unreleased**. Releasing moves those lines under a new version heading, and that section becomes the GitHub Release notes.

## [Unreleased]

- **AI bake-off tool** (`ai-bakeoff.exe` in test builds): compares local models (Ollama, LM Studio, llama.cpp, Jan) and optionally Gemini on your own PDF pages, and writes a report with transcriptions, cards, speed and GPU fit. Groundwork for AI card generation.
- Bake-off fixes from the first real run: generation is capped so thinking models can't run for minutes, thinking-only replies give a clear error, leaked tokens and repetition loops are cleaned up and flagged, cards with math outside `$…$` are flagged, and Gemini uses the newest Flash model instead of a retired one.
- Second round: Gemini thinks less and reads all selected PDF pages in one request; rate-limit waits are shown and counted; card prompts ask for short answers that don't repeat the question; stray LaTeX headings and unwrapped `aligned` blocks in transcriptions are fixed; reading defaults to a context size that fits an 8 GB GPU.

## [0.2.0] - 2026-10-25

- **Multiple decks:** work on several decks at once. They're listed in the sidebar with **New deck** (`Ctrl+Shift+N`), duplicate and delete (with undo). Each deck keeps its own cards, note type and tags. Your existing deck carries over automatically.
- **Custom note type has its own field designer:** rename, reorder, add and remove fields for the whole deck, with presets like *Quantity · Formula · Units*. Batch input is now one click away via **Import batch…** in the editor.
- **Switching note types never discards content.** Fields are kept in order and only relabelled, and anything a smaller type can't show is kept and comes back. Each deck remembers its Custom layout. Layout presets stay available on the Custom tab and keep your content.
- **New LaTeX macro editor:** a row per macro with name, number of arguments (up to 9), an optional first argument with a default, and a live example. Changes only apply when you click **Save macros**, and invalid definitions are flagged.
- `\dv` and `\pdv` now take an optional order: `\dv[2]{y}{x}` gives d²y/dx². Saved macros still matching the old defaults are upgraded automatically.
- Every pull request gets a downloadable test build, linked in a PR comment.
- Test builds show a "Test build" badge and their label (e.g. `PR #4 · a1b2c3d`) in the sidebar, window title and Settings.
- Test and dev builds save to `%APPDATA%\AnkiDeckGenerator-test`, separate from the installed release.
- Tagged versions publish a Windows installer (per-user, Start-menu shortcut, uninstaller, in-place upgrades) and a portable `.exe` on GitHub Releases.

## [0.1.0]

- First version: card editor (Basic, Reversed, Cloze, Custom), live KaTeX preview with physics macros, block and delimited text import, `.apkg` export, autosave, light/dark theme, CLI.
