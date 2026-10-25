import { exportableCards } from "../lib/deck";
import type { Deck } from "../types";
import { Icon } from "./Icon";

interface Props {
  decks: Deck[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDuplicate: (id: string) => void;
  onDelete: (id: string) => void;
}

export function DeckList({ decks, activeId, onSelect, onNew, onDuplicate, onDelete }: Props) {
  return (
    <section className="deck-list" aria-label="Decks">
      <div className="deck-list-head">
        <span>Decks</span>
        <button type="button" className="icon-btn xs" title="New deck (Ctrl+Shift+N)" onClick={onNew}>
          <Icon name="plus" size={14} />
        </button>
      </div>
      <ul className="deck-items">
        {decks.map((d) => {
          const count = exportableCards(d).length;
          return (
            <li key={d.id} className={`deck-item ${d.id === activeId ? "is-active" : ""}`}>
              <button type="button" className="deck-select" onClick={() => onSelect(d.id)} title={d.name}>
                <span className="deck-name-text">{d.name || "Untitled"}</span>
                <span className="deck-count">{count}</span>
              </button>
              <span className="deck-actions">
                <button type="button" className="icon-btn xs" title="Duplicate deck" onClick={() => onDuplicate(d.id)}>
                  <Icon name="copy" size={12} />
                </button>
                <button
                  type="button"
                  className="icon-btn xs danger"
                  title={decks.length === 1 ? "Can't delete the only deck" : "Delete deck"}
                  disabled={decks.length === 1}
                  onClick={() => onDelete(d.id)}
                >
                  <Icon name="trash" size={12} />
                </button>
              </span>
            </li>
          );
        })}
      </ul>
      <button type="button" className="new-deck-btn" onClick={onNew}>
        <Icon name="plus" size={14} /> New deck
      </button>
    </section>
  );
}
