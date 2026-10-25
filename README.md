# Anki Deck Generator

A small, minimalist Windows desktop app for building Anki decks with first-class LaTeX, made with physics in mind. Write cards by hand or import a text file, preview every formula live, and export a `.apkg` that you double-click to open in Anki.

- **Card editor:** Front, Back and Extra fields, or your own custom fields, with a live KaTeX preview for each field and a card preview.
- **Note types:** Basic, Basic + reversed, Cloze (`{{c1::…}}`), and Custom (any number of named fields).
- **Text import:** paste or drop a file in the [block format](FORMAT.md#block-format) or a [delimited](FORMAT.md#delimited-format) format (TSV/CSV/pipe). Errors are reported with line numbers.
- **LaTeX:** write `$…$` and `$$…$$`. Physics macros (`\vb`, `\dv`, `\pdv`, `\ket`, …) and `\ce{}` (mhchem) work. The macros are embedded in the exported cards, so Anki renders exactly what you previewed.
- **Re-exporting is safe:** deck, note-type and note IDs are stable, so importing a regenerated deck updates existing notes instead of duplicating them.
- Autosaves your work, has light and dark themes, and is keyboard-friendly.

## Using it

| Shortcut | Action |
| --- | --- |
| `Ctrl+Enter` | New card |
| `Ctrl+M` | Wrap selection in `$…$` |
| `Ctrl+Shift+C` | Wrap selection in a cloze (`{{cN::…}}`) |
| `Alt+↑ / ↓` | Previous / next card |
| `Ctrl+S` | Export `.apkg` |

Name the deck with `::` to create subdecks, e.g. `Physics::Electromagnetism`. Then click **Export .apkg** and open the file in Anki.

There's a ready-made example in [`examples/`](examples): `physics_sample.txt` is the source and `physics_sample.apkg` is the result.

## Running from source

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

### Development (hot reload)

```powershell
npm --prefix frontend run dev      # Vite on :5173
python -m ankigen --dev            # desktop window pointed at Vite
```

To work on the UI in an ordinary browser, run `python -m ankigen.devserver` (the API on :5174) alongside `npm run dev` and open http://localhost:5173. Exports land in `./exports`.

### Building the .exe

```powershell
.\scripts\build_windows.ps1        # -> dist\AnkiDeckGenerator.exe
```

GitHub Actions does the same on every push to `main`. Download `AnkiDeckGenerator-windows` from the run's artifacts.

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
