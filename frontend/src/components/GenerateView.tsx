import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { bareLatex, describeRef, effectiveWriter, formatElapsed, isLocal, toDeckCards } from "../lib/ai";
import { hasMathProblem } from "../lib/math";
import type { AiSettings, AiStatus, Card, Deck, Density, Focus, GeneratedCard, JobStatus, MacroDef } from "../types";
import { FieldInput } from "./FieldInput";
import { Icon } from "./Icon";
import { MathPreview } from "./MathPreview";
import { ModelSelect } from "./ModelSelect";
import { Segmented } from "./Segmented";

export interface ReviewCard extends GeneratedCard {
  key: string;
  selected: boolean;
}

/** Kept by App per deck, so leaving the page doesn't lose work or a running job. */
export interface GenerateState {
  material: string;
  source: string;
  jobId: string | null;
  job: Omit<JobStatus, "cards"> | null;
  cards: ReviewCard[];
}

export const emptyGenerateState = (): GenerateState => ({ material: "", source: "", jobId: null, job: null, cards: [] });

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

export function GenerateView({ deck, macros, ai, status, state, onState, onAiChange, onAdd, onOpenSettings, notify }: Props) {
  const [preview, setPreview] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const writer = effectiveWriter(ai, status);
  const running = state.job?.state === "running";
  const cardCount = useRef(state.cards.length);
  cardCount.current = state.cards.length;

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
      onState((s) =>
        s.jobId !== jobId
          ? s
          : {
              ...s,
              job,
              cards: [...s.cards, ...cards.map((c, i) => ({ ...c, key: `${jobId}-${s.cards.length + i}`, selected: true }))],
            },
      );
      if (job.state === "error") notify(job.error, "error");
      if (job.state === "running") timer = window.setTimeout(tick, POLL_MS);
    };
    let timer = window.setTimeout(tick, 200);
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [state.jobId, running, onState, notify]);

  const setMaterial = (material: string, source = state.source) => onState((s) => ({ ...s, material, source }));

  const openFile = async () => {
    const res = await api.openTextFile();
    if (!res.ok) return notify(res.error, "error");
    if (res.cancelled || res.text === undefined) return;
    setMaterial(res.text, res.name ?? "");
  };

  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (!/\.(txt|md|markdown|tex)$/i.test(file.name)) {
      return notify("For now, drop a .txt or .md file. PDFs and images come in the next update.", "error");
    }
    setMaterial(await file.text(), file.name);
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
      model: writer,
    });
    if (!res.ok) return notify(res.error, "error");
    onState((s) => ({
      ...s,
      jobId: res.job,
      job: { id: res.job, state: "running", error: "", done: 0, total: 0, message: "Starting…", elapsed: 0, card_count: 0, warnings: [] },
    }));
  };

  const cancel = async () => {
    if (state.jobId) await api.cancelJob(state.jobId);
  };

  const updateCard = (key: string, update: (c: ReviewCard) => ReviewCard) =>
    onState((s) => ({ ...s, cards: s.cards.map((c) => (c.key === key ? update(c) : c)) }));

  const selected = state.cards.filter((c) => c.selected);
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
            {state.source && <span className="muted small">{state.source}</span>}
            <button type="button" className="ghost-btn" onClick={openFile}>
              <Icon name="file" size={14} /> Open file
            </button>
          </div>
        </div>

        {preview ? (
          <div className="material-preview">
            <MathPreview text={state.material} macros={macros} placeholder="Nothing to preview yet." showErrors />
          </div>
        ) : (
          <textarea
            className="import-text"
            value={state.material}
            spellCheck={false}
            onChange={(e) => setMaterial(e.target.value)}
            placeholder={
              "Paste notes or a textbook section, or drop a .txt / .md file here.\n\n" +
              "Math in $…$ and $$…$$ works best. Delete anything you don't want cards for, like exercises."
            }
          />
        )}

        <div className="generate-options">
          <label className="grow">
            <span>Model</span>
            <ModelSelect status={status} value={writer} onChange={(writer) => onAiChange({ ...ai, writer })} />
          </label>
          <label>
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
          </label>
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
            <button type="button" className="primary-btn" onClick={generate} disabled={!words || !writer}>
              <Icon name="sparkle" /> Generate cards
            </button>
          )}
        </div>
      </section>

      <section className="import-preview">
        <div className="pane-head">
          <div>
            <div className="pane-title">{state.cards.length ? `${state.cards.length} suggested cards` : "Review"}</div>
            <div className="muted small">{describeRef(writer)}</div>
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
                    {(problems.length > 0 || bare.length > 0) && (
                      <div className="review-flags">
                        {problems.length > 0 && <span className="flag">LaTeX error in {problems.join(", ")}</span>}
                        {bare.length > 0 && <span className="flag">Math outside $…$ in {bare.join(", ")}</span>}
                      </div>
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
