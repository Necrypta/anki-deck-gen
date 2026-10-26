# Anki Deck Generator

A small, minimalist Windows desktop app for building Anki decks with first-class LaTeX, made with physics in mind. Write cards by hand or import a text file, preview every formula live, and export a `.apkg` that you double-click to open in Anki.

- **Several decks at once:** switch between them in the sidebar. Each one exports to its own `.apkg`.
- **Card editor:** Front, Back and Extra fields, or your own custom fields, with a live KaTeX preview for each field and a card preview.
- **Note types:** Basic, Basic + reversed, Cloze (`{{c1::…}}`), and Custom (any number of named fields).
- **Text import:** paste or drop a file in the [block format](FORMAT.md#block-format) or a [delimited](FORMAT.md#delimited-format) format (TSV/CSV/pipe). Errors are reported with line numbers.
- **LaTeX:** write `$…$` and `$$…$$`. Physics macros (`\vb`, `\dv[n]`, `\pdv[n]`, `\ket`, …) and `\ce{}` (mhchem) work, and you can define your own with up to 9 arguments and an optional first argument. The macros are embedded in the exported cards, so Anki renders exactly what you previewed.
- **Re-exporting is safe:** deck, note-type and note IDs are stable, so importing a regenerated deck updates existing notes instead of duplicating them.
- Autosaves your work, has light and dark themes, and is keyboard-friendly.

## Using it

| Shortcut | Action |
| --- | --- |
| `Ctrl+Enter` | New card |
| `Ctrl+M` | Wrap selection in `$…$` |
| `Ctrl+Shift+C` | Wrap selection in a cloze (`{{cN::…}}`) |
| `Alt+↑ / ↓` | Previous / next card |
| `Ctrl+S` | Export the current deck as `.apkg` |
| `Ctrl+Shift+N` | New deck |
| `Ctrl+F` | Find in the material on the Generate page (`Enter` / `Shift+Enter` next / previous, `Esc` closes) |

Name the deck with `::` to create subdecks, e.g. `Physics::Electromagnetism`. Then click **Export .apkg** and open the file in Anki.

### Generating cards with AI

Open **Generate**, then paste notes, open or drop a file (PDF, image, `.txt` or `.md`), or press Ctrl+V to paste a screenshot.

- **PDFs and images** are read first: choose the pages (thumbnails show what you picked) and click **Read pages**. A vision model turns each page into text with LaTeX, which appears in the box for you to check and trim. For PDFs with a text layer you can choose **Text layer** instead: instant, but equations usually come out garbled. Pages that were already read with the same model come back instantly.
- Then click **Generate cards**. Suggested cards appear on the right as they're written. Untick or edit any of them, then **Add to deck**. Cards use the current deck's note type and fields, and your LaTeX macros.
- **Duplicates:** the AI is told which related cards the deck already has, so it writes fewer repeats. Any suggestion that repeats a card in the deck, or one above it in the list, arrives unticked with a note such as *Already in the deck*. **Compare** shows the other card; **Keep both** or **Keep this one instead** settles it. The check ignores wording like "What is…" or "State…", markup and spacing, so reworded repeats are caught too.

Set up a model under **Settings → AI card generation**:

- **On this computer (recommended):** install [Ollama](https://ollama.com/download), then run `ollama pull qwen3:8b` (writes the cards) and `ollama pull qwen2.5vl:7b` (reads pages); about 5 GB each. The app finds it automatically, and LM Studio, llama.cpp and Jan work too. It's free, private and works offline.
- **Online:** paste a free [Gemini API key](https://aistudio.google.com/apikey). It gives the best cards, but the free tier can take a few minutes per request. The key is kept in Windows Credential Manager.

There's a ready-made example in [`examples/`](examples): `physics_sample.txt` is the source and `physics_sample.apkg` is the result.

## Installing

Download **`AnkiDeckGenerator-Setup-X.Y.Z.exe`** from the [Releases page](https://github.com/Necrypta/anki-deck-gen/releases) and run it. It installs for your user only (no admin prompt), adds a Start-menu shortcut, and upgrades over the previous version. Uninstall it from *Settings → Apps*. A portable `.exe` is attached to each release as well.

Windows SmartScreen will warn about the unsigned app: choose **More info → Run anyway**.

## Testing updates

Every change comes as a pull request, and every pull request gets its own test build:

1. Open the PR. A bot comment links **Download the test build**, and updates the link after each new push.
2. Unzip it and run it. Nothing to install.
3. Test, then reply on the PR (or in chat) with "merge" or what to fix.

Test builds are clearly marked: a yellow **Test build · PR #N · sha** badge in the sidebar and a matching window title. They save to `%APPDATA%\AnkiDeckGenerator-test`, so they never touch the work saved by your installed copy, which uses `%APPDATA%\AnkiDeckGenerator`. Settings shows which folder a build is using.

## Comparing local AI models (bake-off)

Before AI card generation lands in the app, `ai-bakeoff.exe` (in every test-build zip) tries the local models on your own laptop and your own textbook pages, so the app's suggested defaults come from real results.

1. **Install a local runtime.** Ollama is easiest: `winget install Ollama.Ollama` (or the installer from ollama.com). It runs in the background on `localhost:11434`. LM Studio, llama.cpp `llama-server` and Jan work too; the tool finds them on their default ports.
2. **Download some models.** Run `ai-bakeoff.exe` with nothing to list what's installed and the `ollama pull …` commands for the suggestions. A good first set for an 8 GB GPU:
   ```
   ollama pull qwen2.5vl:7b     # reads pages (vision)
   ollama pull qwen3-vl:8b      # reads pages (vision)
   ollama pull qwen3:8b         # writes cards
   ollama pull deepseek-r1:8b   # writes cards (reasoning, slower)
   ```
3. **Run it.** Double-click `ai-bakeoff.exe`, drag a PDF onto the window, and give it 1–3 equation-heavy pages. Or from a terminal:
   ```
   ai-bakeoff.exe chapter.pdf --pages 12-13
   ai-bakeoff.exe chapter.pdf --pages 12 --read qwen2.5vl:7b lmstudio/qwen/qwen2.5-vl-7b --cards qwen3:8b
   ```
   Add a free Gemini key (`--gemini-key …`, or when the tool asks) to include Gemini as a reference.
4. **Read the report.** It opens in your browser with each page image next to every model's transcription, rendered with KaTeX, plus the cards and timings. **On GPU** below 100% means the model didn't fit in VRAM and is spilling into system RAM, which is much slower. Paste the summary table (also saved as `summary.md`) into chat to pick defaults.

The models are never hard-coded: the app will list whatever your runtime has installed.

## Releasing

1. Move the **Unreleased** lines in [CHANGELOG.md](CHANGELOG.md) under a new `## [X.Y.Z]` heading.
2. Bump `version` in `pyproject.toml` and `__version__` in `ankigen/__init__.py`.
3. Merge, then tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.

The `release` workflow checks that the tag matches the version, builds the installer with Inno Setup (`installer/AnkiDeckGenerator.iss`), and publishes a GitHub Release with that changelog section as its notes. Pull requests that change the installer get a dry run that builds it without publishing.

## Development

### Running from source

Only needed if you want to change code yourself. `.\scripts\run_from_source.ps1 [branch]` does all of this in one go.

Requirements: Python 3.10+, Node 18+, and on Windows the WebView2 runtime (already installed on Windows 10/11).

```powershell
git clone https://github.com/Necrypta/anki-deck-gen
cd anki-deck-gen
python -m venv .venv; .\.venv\Scripts\activate
pip install -e ".[dev]"
npm --prefix frontend ci
npm --prefix frontend run build
python -m ankigen
```

### Hot reload

```powershell
npm --prefix frontend run dev      # Vite on :5173
python -m ankigen --dev            # desktop window pointed at Vite
```

To work on the UI in an ordinary browser, run `python -m ankigen.devserver` (the API on :5174) alongside `npm run dev` and open http://localhost:5173. Exports land in `./exports`. Set `ANKIGEN_FAKE_AI=1` for a pretend AI model that answers instantly, for working on the Generate page without a real model.

### Building the .exe locally

```powershell
.\scripts\build_windows.ps1        # -> dist\AnkiDeckGenerator.exe
```

### Command line

```bash
python -m ankigen.cli examples/physics_sample.txt -o physics.apkg
python -m ankigen.cli cards.tsv --fields Front,Back,Extra
```

### Tests

```bash
pytest                       # parsers, LaTeX conversion, .apkg contents
npm --prefix frontend run typecheck
```

## How it's built

```
ankigen/            Python backend
  app.py            pywebview window hosting the UI
  api.py            methods the UI calls (window.pywebview.api.*)
  deck.py           genanki note types and .apkg writer
  latex.py          $…$ → \(…\) conversion, macro preamble
  parsers/          block + delimited text formats
  providers/        extension point for OCR / AI card sources (planned)
  cli.py, devserver.py
frontend/           React + TypeScript + KaTeX (Vite)
```

The UI is a static React build that pywebview loads (on Windows it runs in Edge WebView2). It calls Python directly through pywebview's JS bridge, so there's no web server or open port in the packaged app. Python writes the `.apkg` with [genanki](https://github.com/kerrickstaley/genanki).

Planned features and ideas are in [ROADMAP.md](ROADMAP.md).
