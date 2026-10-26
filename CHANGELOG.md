# Changelog

Each pull request adds a line under **Unreleased**. Releasing moves those lines under a new version heading, and that section becomes the GitHub Release notes.

## [Unreleased]

- **Open and edit Anki decks (.apkg):** **Import → Open .apkg** opens a deck exported from Anki, with its images, and exporting saves it back with every card's reviews, intervals and due dates kept, plus its note types, styling and media. Edited notes update in place when you import the file into Anki again.
- **Edited cards no longer duplicate in Anki:** exporting a deck again after changing a card's front used to add it to Anki as a new card (with no reviews). Each card now keeps the same identity across exports.
- Field previews now show basic formatting such as **bold** and line breaks, the way Anki does.

- **Duplicate warnings on Import:** pasted or opened cards that repeat a card in the deck, or one earlier in the text, are marked in the preview with **Compare**, and skipped when you add them (untick **Skip duplicates**, or click **Add anyway** on a card, to keep them).

## [0.4.0] - 2026-10-26

- **Safer saving:** each time the app starts, it backs up your decks to `backups\` in the data folder (the last 10 are kept). A save file that can't be read is now kept aside instead of being replaced by an empty deck. You'll also get a warning if your decks were last saved by a newer version. **Settings → Open data folder** shows where everything is, and the README explains how to restore a backup.
- **Duplicate cards:** on the Generate page, a suggested card that repeats one already in the deck, or one suggested above it, arrives unticked and marked *Already in the deck* or *Very similar to card 4 above*. It also catches reworded versions, such as "What is the Pauli exclusion principle?" and "State the Pauli exclusion principle." **Compare** shows the two cards side by side, and **Keep both** or **Keep this one instead** settles it. The AI is also told which related cards the deck already has, so it writes fewer repeats to begin with.

## [0.3.0] - 2026-10-25

- **Generate cards with AI:** a new **Generate** page turns your study material into suggested cards for the current deck. You review, edit and untick them, then add them. Cards use the deck's note type and fields, with options for how many cards and what to focus on, and can be tagged with their source file.
- **PDFs, images and screenshots:** open or drop a PDF, an image, or a `.txt` / `.md` file, or paste a screenshot with Ctrl+V. Pick the PDF pages (with thumbnails), then **Read pages**: a vision model turns them into editable text with LaTeX that you can check and trim before cards are written. PDFs with a text layer can use it instead, with no AI. Pages already read with the same model come back instantly.
- **Local or online AI, your choice of model:** works with Ollama, LM Studio, llama.cpp and Jan on your own computer (free, private, offline), or with Google Gemini using a free API key kept in Windows Credential Manager. Suggested on an 8 GB GPU: qwen2.5vl:7b reads pages and qwen3:8b writes cards. Set it up under **Settings → AI card generation**.
- **Equations stay exact:** the AI refers to the material's equations by label instead of retyping them, so the exact LaTeX goes on the card. An equation it did retype that nearly matches the material (a dropped term, a first derivative instead of a second) is flagged in review with a one-click **Use the material's version**. Cards with LaTeX errors or math outside `$…$` are flagged too.
- **Cleaner output from local models:** they write cards as plain text rather than JSON, which avoids garbled backslashes; leftover `\backslash` words are repaired and an Extra field that repeats the answer is cleared. The AI only uses your LaTeX macros if you turn on **Let AI use my LaTeX macros**.
- **Find in the material:** Ctrl+F (or the magnifier button) opens a small find bar that highlights every match, with next/previous (Enter / Shift+Enter, F3), a match count and match case.
- **Diagnostics:** the app writes `app.log` in its data folder (**Show log file** in Settings), Settings shows the screen's build, and a banner appears if the window ever shows a mismatched version.
- **AI bake-off tool** (`ai-bakeoff.exe`, in test builds): compares models on your own PDF pages and writes a report with transcriptions, cards, speed and GPU fit.

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
