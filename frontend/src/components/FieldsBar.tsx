import { useLayoutEffect, useRef, useState } from "react";
import { FIELD_PRESETS, addField, applyPreset, cardsUsingField, moveField, removeField, renameField } from "../lib/deck";
import type { Deck } from "../types";
import { Icon } from "./Icon";

interface Props {
  deck: Deck;
  onDeckChange: (deck: Deck) => void;
  /** Field name to focus for renaming (e.g. one just added). */
  focusField?: string | null;
  onFocused?: () => void;
}

/** Deck-wide field designer for the Custom note type. */
export function FieldsBar({ deck, onDeckChange, focusField, onFocused }: Props) {
  const [error, setError] = useState<string | null>(null);
  const inputs = useRef(new Map<string, HTMLInputElement>());
  const sameLayout = (fields: string[]) =>
    fields.length === deck.fields.length && fields.every((f, i) => f === deck.fields[i]);

  const remove = (name: string) => {
    const used = cardsUsingField(deck, name);
    if (used && !window.confirm(`Remove “${name}”? ${used} card${used === 1 ? " has" : "s have"} content in it, which will be deleted.`)) return;
    onDeckChange(removeField(deck, name));
  };

  // A field to focus once it's in the DOM: from the parent (switching to
  // Custom, "+ Field") or from "Add field" here.
  const [pending, setPending] = useState<string | null>(null);
  const target = pending ?? focusField ?? null;

  useLayoutEffect(() => {
    if (!target) return;
    const el = inputs.current.get(target);
    if (!el) return;
    el.focus();
    el.select();
    setPending(null);
    onFocused?.();
  }, [target, onFocused, deck.fields]);

  const commitRename = (from: string, el: HTMLInputElement) => {
    const to = el.value.trim();
    if (to === from) return setError(null);
    const next = renameField(deck, from, to);
    if (!next) {
      setError(to ? `There's already a field called “${to}”` : "Field names can't be empty");
      el.value = from;
      return;
    }
    setError(null);
    onDeckChange(next);
  };

  const add = () => {
    const next = addField(deck);
    onDeckChange(next);
    setPending(next.fields[next.fields.length - 1]);
  };

  return (
    <section className="fields-bar" aria-label="Custom fields">
      <div className="fields-bar-head">
        <div>
          <div className="fields-bar-title">Custom fields</div>
          <div className="muted small">
            The first field is the question side; the rest appear on the answer side. Applies to every card in this deck.
          </div>
        </div>
      </div>

      <ol className="field-chips">
        {deck.fields.map((f, i) => (
          <li key={f} className={`field-chip ${i === 0 ? "is-front" : ""}`}>
            <span className="chip-side">{i === 0 ? "Front" : "Back"}</span>
            <input
              ref={(el) => {
                if (el) inputs.current.set(f, el);
                else inputs.current.delete(f);
              }}
              defaultValue={f}
              aria-label={`Rename field ${f}`}
              size={Math.max(4, f.length)}
              onBlur={(e) => commitRename(f, e.target)}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                if (e.key === "Escape") {
                  (e.target as HTMLInputElement).value = f;
                  (e.target as HTMLInputElement).blur();
                }
              }}
            />
            <span className="chip-actions">
              <button
                type="button"
                className="icon-btn xs"
                title="Move left"
                disabled={i === 0}
                onClick={() => onDeckChange(moveField(deck, f, -1))}
              >
                ‹
              </button>
              <button
                type="button"
                className="icon-btn xs"
                title="Move right"
                disabled={i === deck.fields.length - 1}
                onClick={() => onDeckChange(moveField(deck, f, 1))}
              >
                ›
              </button>
              <button
                type="button"
                className="icon-btn xs danger"
                title={deck.fields.length <= 2 ? "A card needs at least two fields" : "Remove field"}
                disabled={deck.fields.length <= 2}
                onClick={() => remove(f)}
              >
                <Icon name="x" size={12} />
              </button>
            </span>
          </li>
        ))}
        <li>
          <button type="button" className="ghost-btn add-field" onClick={add}>
            <Icon name="plus" size={14} /> Add field
          </button>
        </li>
      </ol>
      {error && <div className="field-error">{error}</div>}

      <div className="presets">
        <span className="muted small">Layouts:</span>
        {FIELD_PRESETS.map((p) => {
          const active = sameLayout(p.fields);
          return (
            <button
              key={p.label}
              type="button"
              className={`preset-btn ${active ? "is-active" : ""}`}
              aria-pressed={active}
              title="Renames the fields in order; card content is kept"
              onClick={() => onDeckChange(applyPreset(deck, p.fields))}
            >
              {p.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}
