import { useEffect, useMemo, useState } from "react";
import { MAX_ARGS, defaultMacros, exampleUsage, validateMacro } from "../lib/macros";
import type { MacroDef } from "../types";
import { Icon } from "./Icon";
import { MathPreview } from "./MathPreview";

interface Props {
  macros: MacroDef[];
  onSave: (macros: MacroDef[]) => void;
  notify: (msg: string, kind?: "error" | "info") => void;
}

interface Row extends MacroDef {
  key: string;
  /** Custom example text; null = auto-generated from the definition. */
  example: string | null;
}

let rowKey = 0;
const toRows = (ms: MacroDef[]): Row[] => ms.map((m) => ({ ...m, key: `m${rowKey++}`, example: null }));
const strip = (rows: Row[]): MacroDef[] => rows.map(({ name, args, optional, body }) => ({ name, args, optional, body }));
const same = (a: MacroDef[], b: MacroDef[]) => JSON.stringify(a) === JSON.stringify(b);

export function MacroEditor({ macros, onSave, notify }: Props) {
  const [rows, setRows] = useState<Row[]>(() => toRows(macros));
  const draft = useMemo(() => strip(rows), [rows]);
  const dirty = !same(draft, macros);
  const errors = useMemo(() => draft.map((m) => validateMacro(m, draft)), [draft]);
  const invalid = errors.some(Boolean);
  // Preview each row with the draft so unsaved edits show up immediately;
  // rows with errors are left out so one mistake doesn't break every preview.
  const previewMacros = useMemo(() => draft.filter((_, i) => !errors[i]), [draft, errors]);

  // Pick up external changes (e.g. a reset) when there's no local draft.
  useEffect(() => {
    if (!dirty) setRows(toRows(macros));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [macros]);

  const update = (key: string, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const save = () => {
    if (invalid) return;
    onSave(draft);
    notify(`Saved ${draft.length} macro${draft.length === 1 ? "" : "s"}`);
  };

  return (
    <div className="macro-editor">
      <div className="macro-list">
        {rows.map((r, i) => {
          const err = errors[i];
          const example = r.example ?? exampleUsage(r);
          return (
            <div key={r.key} className={`macro-row ${err ? "has-error" : ""}`}>
              <div className="macro-fields">
                <label className="macro-name">
                  <span>Name</span>
                  <input value={r.name} spellCheck={false} onChange={(e) => update(r.key, { name: e.target.value.trim() })} />
                </label>
                <label className="macro-args">
                  <span>Arguments</span>
                  <select
                    value={r.args}
                    onChange={(e) => {
                      const args = Number(e.target.value);
                      update(r.key, { args, optional: args === 0 ? null : r.optional });
                    }}
                  >
                    {Array.from({ length: MAX_ARGS + 1 }, (_, n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="macro-optional" title="Make #1 optional, written in [ ] (like \dv[2]{y}{x})">
                  <span>Optional #1</span>
                  <span className="macro-optional-ctl">
                    <input
                      type="checkbox"
                      checked={r.optional !== null}
                      disabled={r.args === 0}
                      onChange={(e) => update(r.key, { optional: e.target.checked ? "" : null })}
                    />
                    <input
                      className="macro-default"
                      placeholder="default"
                      value={r.optional ?? ""}
                      disabled={r.optional === null}
                      spellCheck={false}
                      onChange={(e) => update(r.key, { optional: e.target.value })}
                    />
                  </span>
                </label>
                <label className="macro-body">
                  <span>Definition</span>
                  <input value={r.body} spellCheck={false} onChange={(e) => update(r.key, { body: e.target.value })} />
                </label>
                <button
                  type="button"
                  className="icon-btn danger macro-delete"
                  title="Delete macro"
                  onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}
                >
                  <Icon name="trash" />
                </button>
              </div>
              <div className="macro-example">
                <input
                  value={example}
                  spellCheck={false}
                  aria-label={`Example for ${r.name}`}
                  onChange={(e) => update(r.key, { example: e.target.value })}
                />
                <span className="macro-arrow">→</span>
                {err ? (
                  <span className="field-error inline">{err}</span>
                ) : (
                  <MathPreview text={`$${example}$`} macros={previewMacros} className="macro-example-out" showErrors />
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="macro-actions">
        <button
          type="button"
          className="ghost-btn"
          onClick={() =>
            setRows((rs) => [...rs, { name: "\\new", args: 1, optional: null, body: "#1", key: `m${rowKey++}`, example: null }])
          }
        >
          <Icon name="plus" size={14} /> Add macro
        </button>
        <button
          type="button"
          className="link-btn"
          onClick={() => {
            if (window.confirm("Replace all macros with the physics defaults?")) setRows(toRows(defaultMacros()));
          }}
        >
          Reset to physics defaults
        </button>
        <div className="toolbar-right">
          {dirty && <span className={`small ${invalid ? "error-text" : "muted"}`}>{invalid ? "Fix errors to save" : "Unsaved changes"}</span>}
          <button type="button" className="ghost-btn" disabled={!dirty} onClick={() => setRows(toRows(macros))}>
            Discard
          </button>
          <button type="button" className="primary-btn" disabled={!dirty || invalid} onClick={save}>
            Save macros
          </button>
        </div>
      </div>
    </div>
  );
}
