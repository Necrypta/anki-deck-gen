import { useMemo, useState } from "react";
import type { Card, MacroDef } from "../types";
import { Icon } from "./Icon";
import { MathPreview } from "./MathPreview";

interface Props {
  cards: Card[];
  fields: string[];
  selectedId: string | null;
  macros: MacroDef[];
  onSelect: (id: string) => void;
  onAdd: () => void;
}

export function CardList({ cards, fields, selectedId, macros, onSelect, onAdd }: Props) {
  const [query, setQuery] = useState("");
  const [primary, secondary] = fields;

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return cards;
    return cards.filter(
      (c) => fields.some((f) => (c.fields[f] ?? "").toLowerCase().includes(q)) || c.tags.some((t) => t.includes(q)),
    );
  }, [cards, fields, query]);

  return (
    <aside className="card-list">
      <div className="card-list-head">
        <div className="search">
          <Icon name="search" size={14} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search cards" />
        </div>
        <button type="button" className="icon-btn" title="New card (Ctrl+Enter)" onClick={onAdd}>
          <Icon name="plus" />
        </button>
      </div>
      <ol className="card-items">
        {visible.map((c) => {
          const idx = cards.indexOf(c) + 1;
          return (
            <li key={c.id}>
              <button
                type="button"
                className={`card-item ${c.id === selectedId ? "is-selected" : ""}`}
                onClick={() => onSelect(c.id)}
              >
                <span className="card-index">{idx}</span>
                <span className="card-summary">
                  <MathPreview
                    text={c.fields[primary] ?? ""}
                    macros={macros}
                    className="card-primary"
                    placeholder="Empty card"
                  />
                  {secondary && c.fields[secondary]?.trim() && (
                    <MathPreview text={c.fields[secondary]} macros={macros} className="card-secondary" />
                  )}
                </span>
              </button>
            </li>
          );
        })}
        {visible.length === 0 && <li className="card-list-empty">No cards match “{query}”</li>}
      </ol>
    </aside>
  );
}
