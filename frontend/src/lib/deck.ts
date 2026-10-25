import {
  DEFAULT_FIELDS,
  type Card,
  type Deck,
  type NoteType,
  type ParseResult,
  type Session,
  type Settings,
} from "../types";
import { defaultMacros, fromLegacy } from "./macros";

export const uid = () => Math.random().toString(36).slice(2, 10);

export function emptyCard(fields: string[]): Card {
  return { id: uid(), fields: Object.fromEntries(fields.map((f) => [f, ""])), tags: [] };
}

/** "New deck", or "New deck 2", "New deck 3"… if that name is taken. */
export function uniqueDeckName(decks: Deck[], base = "New deck"): string {
  const names = new Set(decks.map((d) => d.name));
  if (!names.has(base)) return base;
  let n = 2;
  while (names.has(`${base} ${n}`)) n++;
  return `${base} ${n}`;
}

export function newDeck(existing: Deck[] = []): Deck {
  const fields = DEFAULT_FIELDS.basic;
  return {
    id: uid(),
    name: uniqueDeckName(existing),
    noteType: "basic",
    fields: [...fields],
    cards: [emptyCard(fields)],
    tags: [],
    updatedAt: Date.now(),
  };
}

export function duplicateDeck(deck: Deck, existing: Deck[]): Deck {
  return {
    ...deck,
    id: uid(),
    name: uniqueDeckName(existing, `${deck.name} copy`),
    cards: deck.cards.map((c) => ({ ...c, id: uid(), fields: { ...c.fields }, tags: [...c.tags] })),
    tags: [...deck.tags],
    updatedAt: Date.now(),
  };
}

export function defaultSettings(): Settings {
  return { theme: "system", macros: defaultMacros() };
}

export function newSession(): Session {
  const deck = newDeck();
  return { version: 2, decks: [deck], activeDeckId: deck.id, settings: defaultSettings() };
}

/** Load any saved session shape (v1: single deck + macro map) as v2. */
export function migrateSession(raw: unknown): Session {
  if (!raw || typeof raw !== "object") return newSession();
  const s = raw as Record<string, unknown>;
  const rawSettings = (s.settings ?? {}) as Partial<Settings> & { macros?: unknown };
  const macros = Array.isArray(rawSettings.macros)
    ? rawSettings.macros
    : rawSettings.macros && typeof rawSettings.macros === "object"
      ? fromLegacy(rawSettings.macros as Record<string, string>)
      : defaultMacros();
  const settings: Settings = { theme: rawSettings.theme ?? "system", macros };

  const rawDecks = (s.version === 2 ? s.decks : s.deck ? [s.deck] : []) as Partial<Deck>[];
  const decks: Deck[] = rawDecks
    .filter((d) => d && Array.isArray(d.cards) && Array.isArray(d.fields))
    .map((d) => ({
      id: d.id ?? uid(),
      name: d.name ?? "Untitled",
      noteType: d.noteType ?? "basic",
      fields: d.fields!,
      cards: d.cards!,
      tags: d.tags ?? [],
      updatedAt: d.updatedAt ?? Date.now(),
    }));
  if (!decks.length) return { ...newSession(), settings };
  const active = decks.some((d) => d.id === s.activeDeckId) ? (s.activeDeckId as string) : decks[0].id;
  return { version: 2, decks, activeDeckId: active, settings };
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

export function nextFieldName(deck: Deck): string {
  let n = deck.fields.length + 1;
  while (deck.fields.includes(`Field ${n}`)) n++;
  return `Field ${n}`;
}

export function addField(deck: Deck, name = nextFieldName(deck)): Deck {
  return setFields(deck, [...deck.fields, name]);
}

/** Rename a field across all cards. Returns null if the new name is invalid or taken. */
export function renameField(deck: Deck, from: string, to: string): Deck | null {
  to = to.trim();
  if (!to || to === from) return null;
  if (deck.fields.some((f) => f.toLowerCase() === to.toLowerCase() && f !== from)) return null;
  return {
    ...deck,
    noteType: "custom",
    fields: deck.fields.map((f) => (f === from ? to : f)),
    cards: deck.cards.map((c) => {
      const { [from]: value, ...rest } = c.fields;
      return { ...c, fields: { ...rest, [to]: value ?? "" } };
    }),
  };
}

export function removeField(deck: Deck, name: string): Deck {
  if (deck.fields.length <= 2) return deck;
  return {
    ...deck,
    noteType: "custom",
    fields: deck.fields.filter((f) => f !== name),
    cards: deck.cards.map((c) => {
      const { [name]: _removed, ...rest } = c.fields;
      return { ...c, fields: rest };
    }),
  };
}

export function moveField(deck: Deck, name: string, delta: -1 | 1): Deck {
  const i = deck.fields.indexOf(name);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= deck.fields.length) return deck;
  const fields = [...deck.fields];
  [fields[i], fields[j]] = [fields[j], fields[i]];
  return { ...deck, noteType: "custom", fields };
}

export const FIELD_PRESETS: { label: string; fields: string[] }[] = [
  { label: "Term · Definition", fields: ["Term", "Definition"] },
  { label: "Quantity · Formula · Units", fields: ["Quantity", "Formula", "Units"] },
  { label: "Law · Statement · Equation · Notes", fields: ["Law", "Statement", "Equation", "Notes"] },
];

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
