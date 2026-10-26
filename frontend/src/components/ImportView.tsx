import { useEffect, useMemo, useRef, useState } from "react";
import { api, type OpenedPackage } from "../api";
import { cardsFromParse } from "../lib/deck";
import { importPlan, indexDeck } from "../lib/duplicates";
import { DEFAULT_FIELDS, type Card, type Deck, type MacroDef, type ParseResult } from "../types";
import { DuplicateBox } from "./DuplicateBox";
import { Icon } from "./Icon";
import { MathPreview } from "./MathPreview";
import { Segmented } from "./Segmented";

type Format = "block" | "delimited";
type Separator = "tab" | "pipe" | "semicolon" | "comma";

interface Props {
  deck: Deck;
  macros: MacroDef[];
  onAppend: (cards: Card[]) => void;
  onReplace: (deck: Deck) => void;
  /** Decks read from an .apkg, to add to the sidebar. */
  onOpenPackage: (decks: OpenedPackage["decks"], summary: string) => void;
  notify: (msg: string, kind?: "error" | "info") => void;
}

const SAMPLE = `# deck: Physics::Electromagnetism
# tags: maxwell

Front: Gauss's law (differential form)
Back: $$\\nabla\\cdot\\vb{E} = \\frac{\\rho}{\\varepsilon_0}$$
---
Front: Faraday's law
Back: $$\\curl\\vb{E} = -\\pdv{\\vb{B}}{t}$$
Extra: The minus sign is Lenz's law.
`;

export function ImportView({ deck, macros, onAppend, onReplace, onOpenPackage, notify }: Props) {
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [format, setFormat] = useState<Format>("block");
  const [separator, setSeparator] = useState<Separator>("tab");
  const [fieldList, setFieldList] = useState(deck.fields.join(", "));
  const [result, setResult] = useState<ParseResult | null>(null);
  const [dragging, setDragging] = useState(false);
  const [opening, setOpening] = useState(false);
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  /** Duplicates the user chose to add anyway, by row. */
  const [kept, setKept] = useState<ReadonlySet<number>>(new Set());
  const seq = useRef(0);

  useEffect(() => setKept(new Set()), [result]);

  useEffect(() => {
    if (!text.trim()) {
      setResult(null);
      return;
    }
    const id = ++seq.current;
    const fields = fieldList.split(",").map((f) => f.trim()).filter(Boolean);
    const t = setTimeout(async () => {
      const res = await api.parseText(text, format, format === "delimited" ? { separator, fields } : {});
      if (id !== seq.current) return;
      if (res.ok) setResult(res);
      else notify(res.error, "error");
    }, 200);
    return () => clearTimeout(t);
  }, [text, format, separator, fieldList, notify]);

  const openFile = async () => {
    const res = await api.openTextFile();
    if (!res.ok) return notify(res.error, "error");
    if (res.cancelled || res.text === undefined) return;
    loadText(res.text, res.name ?? null);
  };

  const loadText = (content: string, name: string | null) => {
    setText(content);
    setFileName(name);
    if (name && /\.(tsv|csv)$/i.test(name)) {
      setFormat("delimited");
      setSeparator(name.toLowerCase().endsWith(".csv") ? "comma" : "tab");
    }
  };

  const opened = (res: Awaited<ReturnType<typeof api.uploadApkg>>) => {
    setOpening(false);
    if (!res.ok) return notify(res.error, "error");
    if (!res.decks?.length) return notify("That .apkg has no notes", "error");
    const { name, notes, media } = res.package;
    const n = res.decks.length;
    onOpenPackage(
      res.decks,
      `Opened ${name}: ${notes} note${notes === 1 ? "" : "s"} in ${n} deck${n === 1 ? "" : "s"}` +
        (media ? `, ${media} media file${media === 1 ? "" : "s"}` : "") +
        ". Reviews and scheduling are kept when you export it.",
    );
  };

  const openApkg = async () => {
    setOpening(true);
    const res = await api.openApkg();
    if (res.ok && res.cancelled) return setOpening(false);
    opened(res as Awaited<ReturnType<typeof api.uploadApkg>>);
  };

  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && /\.apkg$/i.test(file.name)) {
      setOpening(true);
      const data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
      return opened(await api.uploadApkg(file.name, data));
    }
    if (file) loadText(await file.text(), file.name);
  };

  const parsedFields = result?.fields ?? deck.fields;
  const count = result?.cards.length ?? 0;
  const lostFields = parsedFields.filter((f) => !deck.fields.some((d) => d.toLowerCase() === f.toLowerCase()));

  // What "Replace deck" would make the deck look like.
  const replaced = useMemo(() => {
    if (!result) return null;
    const parsed = result.fields ?? deck.fields;
    const noteType = result.note_type ?? (sameFields(parsed, DEFAULT_FIELDS.basic) ? "basic" : "custom");
    // Pad e.g. "Front, Back" columns out to the full built-in field list.
    const fields =
      noteType !== "custom" && sameFields(parsed, DEFAULT_FIELDS[noteType]) ? [...DEFAULT_FIELDS[noteType]] : parsed;
    return { noteType, fields, cards: cardsFromParse({ ...result, tags: [] }, fields) };
  }, [result, deck.fields]);

  // Duplicates: against the deck when adding; only within the paste when replacing.
  const deckIndex = useMemo(() => indexDeck(deck.cards, deck.fields), [deck.cards, deck.fields]);
  const appended = useMemo(() => (result ? cardsFromParse(result, deck.fields) : []), [result, deck.fields]);
  const addPlan = useMemo(
    () => importPlan(appended, deckIndex, deck.fields, skipDuplicates, kept),
    [appended, deckIndex, deck.fields, skipDuplicates, kept],
  );
  const replacePlan = useMemo(
    () => (replaced ? importPlan(replaced.cards, null, replaced.fields, skipDuplicates, kept) : null),
    [replaced, skipDuplicates, kept],
  );
  const addCount = addPlan.include.filter(Boolean).length;
  const replaceCount = replacePlan?.include.filter(Boolean).length ?? 0;
  const duplicateCount = addPlan.matches.filter(Boolean).length;

  const append = () => {
    if (!result) return;
    onAppend(appended.filter((_, i) => addPlan.include[i]));
    const skipped = count - addCount;
    notify(`Added ${addCount} card${addCount === 1 ? "" : "s"}${skipped ? `, skipped ${skipped} duplicate${skipped === 1 ? "" : "s"}` : ""}`);
    setText("");
    setFileName(null);
  };

  const replace = () => {
    if (!result || !replaced || !replacePlan) return;
    onReplace({
      ...deck,
      name: result.deck ?? deck.name,
      noteType: replaced.noteType,
      fields: replaced.fields,
      tags: result.tags.length ? result.tags : deck.tags,
      cards: replaced.cards.filter((_, i) => replacePlan.include[i]),
    });
    notify(`Deck replaced with ${replaceCount} card${replaceCount === 1 ? "" : "s"}`);
    setText("");
    setFileName(null);
  };

  return (
    <div className="import">
      <section
        className={`import-source ${dragging ? "is-dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <div className="pane-head">
          <Segmented
            label="Format"
            value={format}
            onChange={setFormat}
            options={[
              { value: "block", label: "Block" },
              { value: "delimited", label: "Delimited" },
            ]}
          />
          <div className="toolbar-right">
            {fileName && (
              <span className="file-name muted small" title={fileName}>
                {fileName}
              </span>
            )}
            <button type="button" className="ghost-btn" onClick={openFile}>
              <Icon name="file" size={14} /> Open file
            </button>
            <button
              type="button"
              className="ghost-btn"
              onClick={openApkg}
              disabled={opening}
              title="Open an Anki deck (.apkg) to edit it here, keeping its reviews and media"
            >
              <Icon name="import" size={14} /> {opening ? "Opening…" : "Open .apkg"}
            </button>
          </div>
        </div>

        {format === "delimited" && (
          <div className="import-options">
            <label>
              <span>Separator</span>
              <select value={separator} onChange={(e) => setSeparator(e.target.value as Separator)}>
                <option value="tab">Tab</option>
                <option value="pipe">Pipe |</option>
                <option value="semicolon">Semicolon ;</option>
                <option value="comma">Comma ,</option>
              </select>
            </label>
            <label className="grow">
              <span>Columns</span>
              <input value={fieldList} onChange={(e) => setFieldList(e.target.value)} placeholder="Front, Back" />
            </label>
          </div>
        )}

        <textarea
          className="import-text"
          value={text}
          spellCheck={false}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            format === "block"
              ? "Paste text, or drop a .txt or .apkg file here.\n\nFront: question\nBack: answer with $math$\n---\nFront: …"
              : "One card per line, e.g.\nNewton's 2nd law\t$F = ma$"
          }
        />
        {!text && format === "block" && (
          <button type="button" className="link-btn" onClick={() => setText(SAMPLE)}>
            Load an example
          </button>
        )}
      </section>

      <section className="import-preview">
        <div className="pane-head">
          <div>
            <div className="pane-title">{result ? `${count} card${count === 1 ? "" : "s"}` : "Preview"}</div>
            {result?.deck && <div className="muted small">Deck: {result.deck}</div>}
            {duplicateCount > 0 && (
              <label className="small skip-dups">
                <input type="checkbox" checked={skipDuplicates} onChange={(e) => setSkipDuplicates(e.target.checked)} />
                <span className="dup-count">
                  Skip {duplicateCount} possible duplicate{duplicateCount === 1 ? "" : "s"}
                </span>
              </label>
            )}
          </div>
          <div className="toolbar-right">
            <button
              type="button"
              className="ghost-btn"
              disabled={!replaceCount || !!deck.source}
              onClick={replace}
              title={
                deck.source
                  ? "This deck came from an .apkg: add cards to it instead, so its notes and reviews stay"
                  : replaceCount < count
                    ? "Repeats within the pasted text are left out"
                    : undefined
              }
            >
              Replace deck
            </button>
            <button type="button" className="primary-btn" disabled={!addCount} onClick={append}>
              Add {addCount || ""} to deck
            </button>
          </div>
        </div>

        {result && result.errors.length > 0 && (
          <ul className="issues">
            {result.errors.map((e, i) => (
              <li key={i}>
                {e.line > 0 && <span className="issue-line">Line {e.line}</span>}
                {e.message}
              </li>
            ))}
          </ul>
        )}
        {result && count > 0 && lostFields.length > 0 && (
          <div className="notice">
            “Add to deck” drops fields the current deck doesn't have ({lostFields.join(", ")}). “Replace deck” keeps them.
          </div>
        )}

        {result && count > 0 ? (
          <div className="table-wrap">
            <table className="preview-table">
              <thead>
                <tr>
                  <th>#</th>
                  {parsedFields.map((f) => (
                    <th key={f}>{f}</th>
                  ))}
                  {duplicateCount > 0 && <th>Duplicate?</th>}
                </tr>
              </thead>
              <tbody>
                {result.cards.slice(0, 200).map((c, i) => {
                  const dup = addPlan.matches[i];
                  return (
                    <tr key={i} className={addPlan.include[i] ? "" : "is-off"}>
                      <td className="muted">{i + 1}</td>
                      {parsedFields.map((f) => (
                        <td key={f}>
                          <MathPreview text={c.fields[f] ?? ""} macros={macros} />
                        </td>
                      ))}
                      {duplicateCount > 0 && (
                        <td className="dup-cell">
                          {dup && (
                            <DuplicateBox
                              match={dup}
                              other={dup.where === "deck" ? deck.cards[dup.index] : appended[dup.index]}
                              fields={deck.fields}
                              macros={macros}
                              keepLabel={kept.has(i) ? "Skip it" : "Add anyway"}
                              onKeepBoth={
                                skipDuplicates
                                  ? () =>
                                      setKept((k) => {
                                        const next = new Set(k);
                                        if (next.has(i)) next.delete(i);
                                        else next.add(i);
                                        return next;
                                      })
                                  : undefined
                              }
                            />
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {count > 200 && <div className="muted small pad">Showing the first 200 of {count}.</div>}
          </div>
        ) : (
          <div className="empty-state muted">
            {text.trim() ? "No cards found yet." : "Parsed cards appear here as you type."}
            <div className="small">
              Format reference: <code>FORMAT.md</code>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function sameFields(a: string[], b: string[]) {
  return a.length <= b.length && a.every((f, i) => f.toLowerCase() === b[i].toLowerCase());
}
