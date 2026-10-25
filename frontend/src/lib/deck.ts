import { DEFAULT_FIELDS, type Card, type Deck, type NoteType, type ParseResult, type Session } from "../types";

export const uid = () => Math.random().toString(36).slice(2, 10);

export function emptyCard(fields: string[]): Card {
  return { id: uid(), fields: Object.fromEntries(fields.map((f) => [f, ""])), tags: [] };
}

export function newDeck(): Deck {
  const fields = DEFAULT_FIELDS.basic;
  return { name: "New deck", noteType: "basic", fields: [...fields], cards: [emptyCard(fields)], tags: [] };
}

export const DEFAULT_MACROS: Record<string, string> = {
  "\\vb": "\\mathbf{#1}",
  "\\vu": "\\hat{\\mathbf{#1}}",
  "\\dv": "\\frac{d#1}{d#2}",
  "\\pdv": "\\frac{\\partial #1}{\\partial #2}",
  "\\abs": "\\left|#1\\right|",
  "\\norm": "\\left\\lVert#1\\right\\rVert",
  "\\ev": "\\left\\langle#1\\right\\rangle",
  "\\bra": "\\left\\langle#1\\right|",
  "\\ket": "\\left|#1\\right\\rangle",
  "\\braket": "\\left\\langle#1\\middle|#2\\right\\rangle",
  "\\grad": "\\nabla",
  "\\curl": "\\nabla\\times",
  "\\divg": "\\nabla\\cdot",
};

export function newSession(): Session {
  return { version: 1, deck: newDeck(), settings: { theme: "system", macros: { ...DEFAULT_MACROS } } };
}

/**
 * Fill new field names positionally so content survives a note-type switch.
 * Old values are kept (only the deck's current fields are exported), so
 * switching Basic → Cloze → Basic round-trips without losing anything.
 */
function remap(card: Card, from: string[], to: string[]): Card {
  const fields = { ...card.fields };
  to.forEach((f, i) => {
    if (fields[f] === undefined) fields[f] = from[i] !== undefined ? card.fields[from[i]] ?? "" : "";
  });
  return { ...card, fields };
}

export function setNoteType(deck: Deck, noteType: NoteType): Deck {
  const fields = noteType === "custom" ? deck.fields : [...DEFAULT_FIELDS[noteType]];
  return { ...deck, noteType, fields, cards: deck.cards.map((c) => remap(c, deck.fields, fields)) };
}

export function setFields(deck: Deck, fields: string[]): Deck {
  return { ...deck, noteType: "custom", fields, cards: deck.cards.map((c) => remap(c, deck.fields, fields)) };
}

export function isEmptyCard(card: Card, fields?: string[]): boolean {
  return (fields ?? Object.keys(card.fields)).every((f) => !(card.fields[f] ?? "").trim());
}

/** Cards that will actually be exported (first field non-empty). */
export function exportableCards(deck: Deck): Card[] {
  return deck.cards.filter((c) => (c.fields[deck.fields[0]] ?? "").trim());
}

export function cardsFromParse(result: ParseResult, fields: string[]): Card[] {
  const byLower = new Map(fields.map((f) => [f.toLowerCase(), f]));
  return result.cards.map((c) => {
    const out: Record<string, string> = Object.fromEntries(fields.map((f) => [f, ""]));
    for (const [k, v] of Object.entries(c.fields)) {
      const target = byLower.get(k.toLowerCase());
      if (target) out[target] = v;
    }
    return { id: uid(), fields: out, tags: [...new Set([...result.tags, ...c.tags])] };
  });
}

export function parseMacros(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const m = line.match(/^\s*(\\[A-Za-z]+)\s*=\s*(.+?)\s*$/);
    if (m) out[m[1]] = m[2];
  }
  return out;
}

export function formatMacros(macros: Record<string, string>): string {
  return Object.entries(macros)
    .map(([k, v]) => `${k} = ${v}`)
    .join("\n");
}
