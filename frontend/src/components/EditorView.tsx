import { useCallback, useState } from "react";
import { addField, cardsWithHiddenContent, setNoteType } from "../lib/deck";
import { NOTE_TYPE_LABELS, type Card, type Deck, type MacroDef, type NoteType } from "../types";
import { CardList } from "./CardList";
import { FieldInput } from "./FieldInput";
import { FieldsBar } from "./FieldsBar";
import { Icon } from "./Icon";
import { MathPreview } from "./MathPreview";
import { Segmented } from "./Segmented";
import { TagInput } from "./TagInput";

interface Props {
  deck: Deck;
  macros: MacroDef[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDeckChange: (deck: Deck) => void;
  onAddCard: () => void;
  onDeleteCard: (id: string) => void;
  onDuplicateCard: (id: string) => void;
  onOpenImport: () => void;
}

const TYPES = (Object.keys(NOTE_TYPE_LABELS) as NoteType[]).map((value) => ({
  value,
  label: NOTE_TYPE_LABELS[value],
}));

export function EditorView({
  deck,
  macros,
  selectedId,
  onSelect,
  onDeckChange,
  onAddCard,
  onDeleteCard,
  onDuplicateCard,
  onOpenImport,
}: Props) {
  const [focusField, setFocusField] = useState<string | null>(null);
  const clearFocus = useCallback(() => setFocusField(null), []);
  const card = deck.cards.find((c) => c.id === selectedId) ?? deck.cards[0];
  const index = card ? deck.cards.indexOf(card) + 1 : 0;
  const custom = deck.noteType === "custom";
  const hiddenCount = custom ? 0 : cardsWithHiddenContent(deck);

  const updateCard = (patch: Partial<Card>) =>
    onDeckChange({ ...deck, cards: deck.cards.map((c) => (c.id === card.id ? { ...c, ...patch } : c)) });

  const changeType = (t: NoteType) => {
    onDeckChange(setNoteType(deck, t));
    if (t === "custom") setFocusField(deck.fields[0]);
  };

  // "+ Field" on a built-in type converts the deck to Custom.
  const addCustomField = () => {
    const next = addField(deck);
    onDeckChange(next);
    setFocusField(next.fields[next.fields.length - 1]);
  };

  return (
    <div className="editor">
      <CardList
        cards={deck.cards}
        fields={deck.fields}
        selectedId={card?.id ?? null}
        macros={macros}
        onSelect={onSelect}
        onAdd={onAddCard}
      />
      <section className="editor-main">
        <div className="editor-toolbar">
          <Segmented label="Note type" value={deck.noteType} options={TYPES} onChange={changeType} />
          <button type="button" className="ghost-btn" onClick={onOpenImport} title="Create many cards from text or a file">
            <Icon name="import" size={14} /> Import batch…
          </button>
          {card && (
            <div className="toolbar-right">
              <span className="muted">
                Card {index} of {deck.cards.length}
              </span>
              <button type="button" className="icon-btn" title="Duplicate card" onClick={() => onDuplicateCard(card.id)}>
                <Icon name="copy" />
              </button>
              <button type="button" className="icon-btn danger" title="Delete card" onClick={() => onDeleteCard(card.id)}>
                <Icon name="trash" />
              </button>
            </div>
          )}
        </div>

        <div className="editor-scroll">
          {hiddenCount > 0 && (
            <div className="hidden-notice" role="note">
              <span>
                {hiddenCount} card{hiddenCount === 1 ? " has" : "s have"} content in fields {NOTE_TYPE_LABELS[deck.noteType]} doesn't
                show. It's kept, and comes back when you switch to Custom.
              </span>
              <button type="button" className="link-btn" onClick={() => changeType("custom")}>
                Switch to Custom
              </button>
            </div>
          )}
          {custom && (
            <FieldsBar deck={deck} onDeckChange={onDeckChange} focusField={focusField} onFocused={clearFocus} />
          )}
          {card ? (
            <div className="editor-grid">
              <div className="editor-fields" key={card.id}>
                {deck.fields.map((f, i) => (
                  <FieldInput
                    key={f}
                    name={f}
                    value={card.fields[f] ?? ""}
                    macros={macros}
                    cloze={deck.noteType === "cloze" && i === 0}
                    autoFocus={i === 0 && !custom}
                    placeholder={placeholderFor(deck.noteType, f)}
                    onChange={(v) => updateCard({ fields: { ...card.fields, [f]: v } })}
                  />
                ))}
                <div className="field-row-actions">
                  {!custom && (
                    <button type="button" className="ghost-btn" onClick={addCustomField} title="Adds a field and switches to Custom">
                      <Icon name="plus" size={14} /> Field
                    </button>
                  )}
                  <div className="card-tags">
                    <span className="field-name">Tags</span>
                    <TagInput tags={card.tags} onChange={(tags) => updateCard({ tags })} />
                  </div>
                </div>
              </div>

              <CardPreview deck={deck} card={card} macros={macros} />
            </div>
          ) : (
            <div className="empty-state">
              <p>No cards yet.</p>
              <div className="toolbar-right" style={{ marginLeft: 0 }}>
                <button type="button" className="primary-btn" onClick={onAddCard}>
                  <Icon name="plus" /> New card
                </button>
                <button type="button" className="ghost-btn" onClick={onOpenImport}>
                  <Icon name="import" size={14} /> Import batch…
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function placeholderFor(type: NoteType, field: string): string {
  if (type === "cloze" && field === "Text") return "Newton's second law: {{c1::$F = ma$}}";
  if (field === "Front") return "Question, e.g. Gauss's law (differential form)";
  if (field === "Back") return "Answer, e.g. $$\\nabla\\cdot\\vb{E} = \\frac{\\rho}{\\varepsilon_0}$$";
  if (field === "Extra") return "Optional notes";
  return "";
}

/** How the card will look in Anki: front, rule, back, extras. */
function CardPreview({ deck, card, macros }: { deck: Deck; card: Card; macros: MacroDef[] }) {
  const [first, second, ...rest] = deck.fields;
  const isCloze = deck.noteType === "cloze";
  return (
    <div className="card-preview" aria-label="Card preview">
      <div className="card-preview-label">Preview</div>
      <div className="card-face">
        <MathPreview text={card.fields[first] ?? ""} macros={macros} placeholder={`${first}…`} />
        {!isCloze && second && (
          <>
            <hr />
            <MathPreview text={card.fields[second] ?? ""} macros={macros} placeholder={`${second}…`} />
          </>
        )}
        {(isCloze ? [second, ...rest] : rest)
          .filter((f) => f && card.fields[f]?.trim())
          .map((f) => (
            <MathPreview key={f} text={card.fields[f]} macros={macros} className="card-extra" />
          ))}
      </div>
      {deck.noteType === "reversed" && <div className="muted small">Also creates the reverse card.</div>}
    </div>
  );
}
