# Changelog

Each pull request adds a line under **Unreleased**. Releasing moves those lines under a new version heading, and that section becomes the GitHub Release notes.

## [Unreleased]

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
