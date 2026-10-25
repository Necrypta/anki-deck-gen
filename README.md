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

Name the deck with `::` to create subdecks, e.g. `Physics::Electromagnetism`. Then click **Export .apkg** and open the file in Anki.

There's a ready-made example in [`examples/`](examples): `physics_sample.txt` is the source and `physics_sample.apkg` is the result.

## Installing

Download **`AnkiDeckGenerator-Setup-X.Y.Z.exe`** from the [Releases page](https://github.com/Necrypta/anki-deck-gen/releases) and run it. It installs for your user only (no admin prompt), adds a Start-menu shortcut, and upgrades over the previous version. Uninstall it from *Settings → Apps*. A portable `.exe` is attached to each release as well.

Windows SmartScreen will warn about the unsigned app: choose **More info → Run anyway**.

## Testing updates

Every change comes as a pull request, and every pull request gets its own test build:

1. Open the PR. A bot comment links **Download AnkiDeckGenerator.exe**, and updates the link after each new push.
2. Unzip it and run it. Nothing to install.
3. Test, then reply on the PR (or in chat) with "merge" or what to fix.

Test builds are clearly marked: a yellow **Test build · PR #N · sha** badge in the sidebar and a matching window title. They save to `%APPDATA%\AnkiDeckGenerator-test`, so they never touch the work saved by your installed copy, which uses `%APPDATA%\AnkiDeckGenerator`. Settings shows which folder a build is using.

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

To work on the UI in an ordinary browser, run `python -m ankigen.devserver` (the API on :5174) alongside `npm run dev` and open http://localhost:5173. Exports land in `./exports`.

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
