import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import {
  bareLatex,
  describeRef,
  effectiveReader,
  effectiveWriter,
  formatElapsed,
  isLocal,
  toDeckCards,
} from "../lib/ai";
import { findDuplicates, indexDeck, plainText } from "../lib/duplicates";
import { hasMathProblem } from "../lib/math";
import type {
  AiSettings,
  AiStatus,
  Card,
  Deck,
  Density,
  Focus,
  GeneratedCard,
  JobStatus,
  MacroDef,
  ReadMode,
  SourceFile,
} from "../types";
import { DuplicateBox } from "./DuplicateBox";
import { FieldInput } from "./FieldInput";
import { FindTextarea } from "./FindTextarea";
import { Icon } from "./Icon";
import { MathPreview } from "./MathPreview";
import { ModelSelect } from "./ModelSelect";
import { Segmented } from "./Segmented";
import { SourceCard } from "./SourceCard";

export interface ReviewCard extends GeneratedCard {
  key: string;
  selected: boolean;
  /** The user chose to keep it although it looks like a duplicate. */
  dupDismissed?: boolean;
}

/** Kept by App per deck, so leaving the page doesn't lose work or a running job. */
export interface GenerateState {
  material: string;
  source: string;
  jobId: string | null;
  job: Omit<JobStatus, "cards"> | null;
  cards: ReviewCard[];
  /** A PDF or image to read into the material first. */
  file: SourceFile | null;
  pageSpec: string;
  readMode: ReadMode;
  readJobId: string | null;
  readJob: Omit<JobStatus, "cards"> | null;
}

export const emptyGenerateState = (): GenerateState => ({
  material: "",
  source: "",
  jobId: null,
  job: null,
  cards: [],
  file: null,
  pageSpec: "",
  readMode: "ai",
  readJobId: null,
  readJob: null,
});

const startingJob = (id: string): Omit<JobStatus, "cards"> => ({
  id,
  state: "running",
  error: "",
  done: 0,
  total: 0,
  message: "Starting…",
  elapsed: 0,
  card_count: 0,
  warnings: [],
  pages: {},
});

const TEXT_FILE = /\.(txt|md|markdown|tex)$/i;
const READABLE_FILE = /\.(pdf|png|jpe?g|webp|bmp|gif|tiff?)$/i;

interface Props {
  deck: Deck;
  macros: MacroDef[];
  ai: AiSettings;
  status: AiStatus | null;
  state: GenerateState;
  onState: (update: (s: GenerateState) => GenerateState) => void;
  onAiChange: (ai: AiSettings) => void;
  onAdd: (cards: Card[]) => void;
  onOpenSettings: () => void;
  notify: (msg: string, kind?: "error" | "info") => void;
}

const POLL_MS = 800;
const EXISTING_LIMIT = 3000; // deck fronts sent to the writer so it can avoid repeats

export function GenerateView({ deck, macros, ai, status, state, onState, onAiChange, onAdd, onOpenSettings, notify }: Props) {
  const [preview, setPreview] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [findSignal, setFindSignal] = useState(0);
  const [stepSignal, setStepSignal] = useState({ n: 0, back: false });

  const openFind = () => {
    setPreview(false);
    setFindSignal((n) => n + 1);
  };

  // Ctrl+F searches the material, F3 / Shift+F3 jump between matches. In the
  // desktop app WebView2 swallows these keys, so ankigen/shortcuts.py catches
  // them natively and sends an "ankigen:find" event instead; in a browser the
  // keydown arrives as usual.
  useEffect(() => {
    const find = (step: boolean, back: boolean) => {
      if (step) setStepSignal((s) => ({ n: s.n + 1, back }));
      else openFind();
    };
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "f") {
        e.preventDefault();
        find(false, false);
      } else if (e.key === "F3") {
        e.preventDefault();
        find(true, e.shiftKey);
      }
    };
    const onNative = (e: Event) => {
      const d = (e as CustomEvent<{ shift?: boolean; step?: boolean }>).detail ?? {};
      find(!!d.step, !!d.shift);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("ankigen:find", onNative);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("ankigen:find", onNative);
    };
  }, []);
  const writer = effectiveWriter(ai, status);
  const reader = effectiveReader(ai, status);
  const running = state.job?.state === "running";
  const reading = state.readJob?.state === "running";
  const cardCount = useRef(state.cards.length);
  cardCount.current = state.cards.length;
  const [hideDuplicates, setHideDuplicates] = useState(false);

  const deckIndex = useMemo(() => indexDeck(deck.cards, deck.fields), [deck.cards, deck.fields]);
  const deckIndexRef = useRef(deckIndex);
  deckIndexRef.current = deckIndex;
  const fieldsRef = useRef(deck.fields);
  fieldsRef.current = deck.fields;
  const dupes = useMemo(() => findDuplicates(state.cards, deckIndex, deck.fields), [state.cards, deckIndex, deck.fields]);

  // Poll the running job; new cards are appended as they arrive.
  useEffect(() => {
    if (!state.jobId || !running) return;
    const jobId = state.jobId;
    let stop = false;
    const tick = async () => {
      const res = await api.jobStatus(jobId, cardCount.current);
      if (stop) return;
      if (!res.ok) {
        onState((s) => ({ ...s, job: s.job && { ...s.job, state: "error", error: res.error } }));
        return;
      }
      const { cards, ...job } = res;
      onState((s) => {
        if (s.jobId !== jobId) return s;
        const all = [...s.cards, ...cards.map((c, i) => ({ ...c, key: `${jobId}-${s.cards.length + i}`, selected: true }))];
        // Cards that look like duplicates arrive unticked; after that, the user's ticks stick.
        const found = cards.length ? findDuplicates(all, deckIndexRef.current, fieldsRef.current) : [];
        return { ...s, job, cards: all.map((c, i) => (i >= s.cards.length && found[i] ? { ...c, selected: false } : c)) };
      });
      if (job.state === "error") notify(job.error, "error");
      if (job.state === "running") timer = window.setTimeout(tick, POLL_MS);
    };
    let timer = window.setTimeout(tick, 200);
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [state.jobId, running, onState, notify]);

  // Poll the reading job; when it finishes, its pages become the material.
  useEffect(() => {
    if (!state.readJobId || !reading) return;
    const jobId = state.readJobId;
    let stop = false;
    const tick = async () => {
      const res = await api.jobStatus(jobId, 0);
      if (stop) return;
      if (!res.ok) {
        onState((s) => ({ ...s, readJob: s.readJob && { ...s.readJob, state: "error", error: res.error } }));
        return notify(res.error, "error");
      }
      const { cards: _cards, ...job } = res;
      const text = Object.entries(job.pages)
        .sort(([a], [b]) => Number(a) - Number(b))
        .map(([, t]) => t.trim())
        .filter(Boolean)
        .join("\n\n");
      onState((s) => (s.readJobId !== jobId ? s : { ...s, readJob: job, material: job.state === "running" ? s.material : text || s.material }));
      if (job.state === "error") notify(job.error, "error");
      else if (job.state === "done") {
        const n = Object.keys(job.pages).length;
        notify(`Read ${n} page${n === 1 ? "" : "s"}. Check the text, then generate cards.`);
      }
      if (job.state === "running") timer = window.setTimeout(tick, POLL_MS);
    };
    let timer = window.setTimeout(tick, 200);
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [state.readJobId, reading, onState, notify]);

  const setMaterial = (material: string, source = state.source) => onState((s) => ({ ...s, material, source }));

  const takeSource = (res: Awaited<ReturnType<typeof api.uploadSource>>) => {
    if (!res.ok) return notify(res.error, "error");
    if (res.kind === "text") {
      onState((s) => ({ ...s, file: null, material: res.text, source: res.name }));
    } else {
      const firstPages = res.kind === "pdf" && res.pages > 5 ? "1-5" : "";
      onState((s) => ({ ...s, file: res, source: res.name, pageSpec: firstPages, readJob: null, readJobId: null }));
    }
  };

  const openFile = async () => {
    const res = await api.openSourceFile();
    if (res.ok && res.cancelled) return;
    takeSource(res as Awaited<ReturnType<typeof api.uploadSource>>);
  };

  const uploadFile = async (file: File) => {
    if (TEXT_FILE.test(file.name)) return setMaterial(await file.text(), file.name);
    if (!READABLE_FILE.test(file.name)) return notify("Drop a PDF, an image, or a .txt / .md file", "error");
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result));
      r.onerror = () => reject(r.error);
      r.readAsDataURL(file);
    });
    takeSource(await api.uploadSource(file.name, dataUrl));
  };

  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) await uploadFile(file);
  };

  // Ctrl+V a screenshot anywhere on the left pane.
  const onPaste = async (e: React.ClipboardEvent) => {
    const image = [...e.clipboardData.files].find((f) => f.type.startsWith("image/"));
    if (!image) return;
    e.preventDefault();
    const ext = image.type.split("/")[1] || "png";
    await uploadFile(new File([image], `Pasted screenshot.${ext}`, { type: image.type }));
  };

  const read = async () => {
    if (!state.file) return;
    const res = await api.startRead({
      path: state.file.path,
      pages: state.file.kind === "pdf" ? state.pageSpec : "",
      mode: state.readMode,
      model: state.readMode === "ai" ? reader : null,
    });
    if (!res.ok) return notify(res.error, "error");
    onState((s) => ({ ...s, readJobId: res.job, readJob: startingJob(res.job) }));
  };

  const generate = async () => {
    if (!writer) return notify("Choose a model in Settings → AI first", "error");
    const res = await api.startGenerate({
      material: state.material,
      fields: deck.fields,
      note_type: deck.noteType,
      macros,
      density: ai.density,
      focus: ai.focus,
      source: ai.tagSource ? state.source : "",
      use_macros: ai.useMacros,
      existing: deck.cards
        .map((c) => plainText(c.fields[deck.fields[0]] ?? "").replace(/\s+/g, " ").trim().slice(0, 120))
        .filter(Boolean)
        .slice(-EXISTING_LIMIT),
      model: writer,
    });
    if (!res.ok) return notify(res.error, "error");
    onState((s) => ({ ...s, jobId: res.job, job: startingJob(res.job) }));
  };

  const cancel = async () => {
    if (state.jobId) await api.cancelJob(state.jobId);
  };

  const updateCard = (key: string, update: (c: ReviewCard) => ReviewCard) =>
    onState((s) => ({ ...s, cards: s.cards.map((c) => (c.key === key ? update(c) : c)) }));

  const selected = state.cards.filter((c) => c.selected);
  const flagged = (i: number) => !!dupes[i] && !state.cards[i].dupDismissed;
  const flaggedCount = state.cards.filter((_, i) => flagged(i)).length;
  const allSelected = state.cards.length > 0 && selected.length === state.cards.length;

  const add = () => {
    if (!selected.length) return;
    onAdd(toDeckCards(selected, deck.fields));
    notify(`Added ${selected.length} card${selected.length === 1 ? "" : "s"} to “${deck.name}”`);
    onState((s) => ({ ...s, cards: s.cards.filter((c) => !c.selected) }));
  };

  const words = state.material.trim() ? state.material.trim().split(/\s+/).length : 0;
  const noModels = status !== null && !writer;

  return (
    <div className="import generate">
      <section
        className={`import-source ${dragging ? "is-dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onPaste={onPaste}
      >
        <div className="pane-head">
          <Segmented
            label="View"
            value={preview ? "preview" : "edit"}
            onChange={(v) => setPreview(v === "preview")}
            options={[
              { value: "edit", label: "Edit" },
              { value: "preview", label: "Preview" },
            ]}
          />
          <div className="toolbar-right">
            {state.source && !state.file && (
              <span className="file-name muted small" title={state.source}>
                {state.source}
              </span>
            )}
            <button type="button" className="icon-btn" title="Find in text (Ctrl+F)" aria-label="Find in text" onClick={openFind}>
              <Icon name="search" size={15} />
            </button>
            <button type="button" className="ghost-btn" onClick={openFile}>
              <Icon name="file" size={14} /> Open file
            </button>
          </div>
        </div>

        {state.file && (
          <SourceCard
            file={state.file}
            pageSpec={state.pageSpec}
            mode={state.readMode}
            job={state.readJob}
            reader={reader}
            status={status}
            onPageSpec={(pageSpec) => onState((s) => ({ ...s, pageSpec }))}
            onMode={(readMode) => onState((s) => ({ ...s, readMode }))}
            onReader={(r) => onAiChange({ ...ai, reader: r })}
            onRead={read}
            onStop={() => state.readJobId && api.cancelJob(state.readJobId)}
            onRemove={() => onState((s) => ({ ...s, file: null, readJob: null, readJobId: null }))}
          />
        )}
        {state.readJob && state.readJob.state !== "running" && state.readJob.warnings.length > 0 && (
          <div className="source-warn small">{state.readJob.warnings.join(" ")}</div>
        )}

        {preview ? (
          <div className="material-preview">
            <MathPreview text={state.material} macros={macros} placeholder="Nothing to preview yet." showErrors />
          </div>
        ) : (
          <FindTextarea
            value={state.material}
            onChange={(v) => setMaterial(v)}
            findSignal={findSignal}
            stepSignal={stepSignal}
            placeholder={
              state.file
                ? "Click Read pages above; the text appears here for you to check and trim."
                : "Paste notes, or drop a PDF, an image or a .txt / .md file here. Ctrl+V pastes a screenshot.\n\n" +
                  "Math in $…$ and $$…$$ works best. Delete anything you don't want cards for, like exercises."
            }
          />
        )}

        <div className="generate-options">
          <label className="grow">
            <span>Writes cards with</span>
            <ModelSelect
              status={status}
              value={writer}
              label="Model that writes the cards"
              onChange={(writer) => onAiChange({ ...ai, writer })}
            />
          </label>
          {/* A div, not a label: a label forwards :hover to its first button. */}
          <div className="option">
            <span>How many</span>
            <Segmented<Density>
              label="How many cards"
              value={ai.density}
              onChange={(density) => onAiChange({ ...ai, density })}
              options={[
                { value: "few", label: "Few" },
                { value: "normal", label: "Normal" },
                { value: "thorough", label: "Thorough" },
              ]}
            />
          </div>
          <label>
            <span>Focus</span>
            <select value={ai.focus} onChange={(e) => onAiChange({ ...ai, focus: e.target.value as Focus })}>
              <option value="balanced">Balanced</option>
              <option value="equations">Equations & laws</option>
              <option value="definitions">Definitions</option>
              <option value="concepts">Concepts & why</option>
            </select>
          </label>
        </div>
        <div className="generate-actions">
          <span className="muted small">
            {words ? `${words.toLocaleString()} words · ` : ""}
            {deck.fields.join(" · ")} cards for “{deck.name}”
          </span>
          {running ? (
            <button type="button" className="ghost-btn" onClick={cancel}>
              Stop
            </button>
          ) : (
            <button type="button" className="primary-btn" onClick={generate} disabled={!words || !writer || reading}>
              <Icon name="sparkle" /> Generate cards
            </button>
          )}
        </div>
      </section>

      <section className="import-preview">
        <div className="pane-head">
          <div>
            <div className="pane-title">{state.cards.length ? `${state.cards.length} suggested cards` : "Review"}</div>
            <div className="muted small">
              {writer ? `Cards written by ${describeRef(writer)}` : "No model chosen"}
            </div>
            {flaggedCount > 0 && (
              <div className="small">
                <span className="dup-count">
                  {flaggedCount} possible duplicate{flaggedCount === 1 ? "" : "s"}
                </span>{" "}
                <button type="button" className="link-btn" onClick={() => setHideDuplicates(!hideDuplicates)}>
                  {hideDuplicates ? "Show them" : "Hide them"}
                </button>
              </div>
            )}
          </div>
          <div className="toolbar-right">
            {state.cards.length > 0 && (
              <>
                <button
                  type="button"
                  className="ghost-btn"
                  onClick={() => onState((s) => ({ ...s, cards: s.cards.map((c) => ({ ...c, selected: !allSelected })) }))}
                >
                  {allSelected ? "Select none" : "Select all"}
                </button>
                <button
                  type="button"
                  className="ghost-btn"
                  disabled={running}
                  onClick={() => onState((s) => ({ ...s, cards: [] }))}
                >
                  Clear
                </button>
              </>
            )}
            <button type="button" className="primary-btn" disabled={!selected.length} onClick={add}>
              Add {selected.length || ""} to deck
            </button>
          </div>
        </div>

        {state.job && (state.job.state === "running" || state.job.warnings.length > 0 || state.job.state === "error") && (
          <JobBar job={state.job} local={isLocal(writer)} />
        )}

        {noModels ? (
          <div className="empty-state muted">
            <p>No AI model is set up yet.</p>
            <p className="small">Install Ollama with a model on this computer, or add a free Gemini key.</p>
            <button type="button" className="primary-btn" onClick={onOpenSettings}>
              Set up AI
            </button>
          </div>
        ) : state.cards.length === 0 ? (
          <div className="empty-state muted">
            {running ? "Cards appear here as they're written." : "Suggested cards appear here for you to check before they go in the deck."}
          </div>
        ) : (
          <ul className="review-list">
            {state.cards.map((c, i) => {
              const dup = flagged(i) ? dupes[i] : null;
              if (dup && hideDuplicates) return null;
              const problems = deck.fields.filter((f) => hasMathProblem(c.fields[f] ?? "", macros));
              const bare = deck.fields.filter((f) => bareLatex(c.fields[f] ?? ""));
              const isEditing = editing === c.key;
              return (
                <li key={c.key} className={`review-card ${c.selected ? "" : "is-off"}`}>
                  <input
                    type="checkbox"
                    checked={c.selected}
                    aria-label={`Keep card ${i + 1}`}
                    onChange={(e) => updateCard(c.key, (x) => ({ ...x, selected: e.target.checked }))}
                  />
                  <div className="review-body">
                    {isEditing
                      ? deck.fields.map((f) => (
                          <FieldInput
                            key={f}
                            name={f}
                            value={c.fields[f] ?? ""}
                            macros={macros}
                            cloze={deck.noteType === "cloze"}
                            onChange={(v) => updateCard(c.key, (x) => ({ ...x, fields: { ...x.fields, [f]: v } }))}
                          />
                        ))
                      : deck.fields.map((f, fi) =>
                          c.fields[f]?.trim() ? (
                            <div key={f} className={fi === 0 ? "review-front" : "review-back"}>
                              {fi > 1 && <span className="review-label">{f}</span>}
                              <MathPreview text={c.fields[f]} macros={macros} />
                            </div>
                          ) : null,
                        )}
                    {(problems.length > 0 || bare.length > 0 || (c.flags.unknown_labels?.length ?? 0) > 0) && (
                      <div className="review-flags">
                        {problems.length > 0 && <span className="flag">LaTeX error in {problems.join(", ")}</span>}
                        {bare.length > 0 && <span className="flag">Math outside $…$ in {bare.join(", ")}</span>}
                        {(c.flags.unknown_labels?.length ?? 0) > 0 && (
                          <span className="flag">Unknown equation {c.flags.unknown_labels!.join(", ")}</span>
                        )}
                      </div>
                    )}
                    {(c.flags.mismatch ?? [])
                      .filter((m) => (c.fields[m.field] ?? "").includes(m.got))
                      .map((m, mi) => (
                        <div key={mi} className="mismatch">
                          <div className="mismatch-head">
                            <span className="flag">Equation differs from the material ({m.field})</span>
                            <button
                              type="button"
                              className="link-btn"
                              onClick={() =>
                                updateCard(c.key, (x) => ({
                                  ...x,
                                  fields: { ...x.fields, [m.field]: (x.fields[m.field] ?? "").replace(m.got, m.source) },
                                }))
                              }
                            >
                              Use the material's version
                            </button>
                          </div>
                          <div className="mismatch-source">
                            <span className="review-label">Material</span>
                            <MathPreview text={m.source} macros={macros} />
                          </div>
                        </div>
                      ))}
                    {dup && (
                      <DuplicateBox
                        match={dup}
                        other={dup.where === "deck" ? deck.cards[dup.index] : state.cards[dup.index]}
                        fields={deck.fields}
                        macros={macros}
                        onKeepBoth={() => updateCard(c.key, (x) => ({ ...x, selected: true, dupDismissed: true }))}
                        onKeepThis={
                          dup.where === "batch"
                            ? () => {
                                const otherKey = state.cards[dup.index].key;
                                onState((s) => ({
                                  ...s,
                                  cards: s.cards.map((x) =>
                                    x.key === c.key ? { ...x, selected: true, dupDismissed: true } :x.key === otherKey ? { ...x, selected: false } : x,
                                  ),
                                }));
                              }
                            : undefined
                        }
                      />
                    )}
                  </div>
                  <button
                    type="button"
                    className="icon-btn xs"
                    title={isEditing ? "Done" : "Edit"}
                    onClick={() => setEditing(isEditing ? null : c.key)}
                  >
                    <Icon name={isEditing ? "check" : "edit"} size={14} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function JobBar({ job, local }: { job: Omit<JobStatus, "cards">; local: boolean }) {
  const running = job.state === "running";
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
  return (
    <div className={`job-bar ${job.state === "error" ? "is-error" : ""}`}>
      {running && (
        <>
          <div className="job-line">
            <span>{job.message || "Working…"}</span>
            <span className="muted">{formatElapsed(job.elapsed)}</span>
          </div>
          <div className="progress" aria-hidden="true">
            <div className={`progress-fill ${job.total ? "" : "is-indeterminate"}`} style={{ width: job.total ? `${Math.max(pct, 4)}%` : undefined }} />
          </div>
          {!local && job.elapsed > 20 && (
            <div className="muted small">Gemini's free tier can take a few minutes per request.</div>
          )}
        </>
      )}
      {job.state === "error" && <div>{job.error}</div>}
      {job.warnings.map((w, i) => (
        <div key={i} className="small">
          {w}
        </div>
      ))}
    </div>
  );
}
