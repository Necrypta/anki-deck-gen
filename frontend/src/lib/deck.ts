import {
  type AiSettings,
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

/** A copy of a card that's a new note in Anki: no GUID or link to an opened .apkg. */
export function copyCard(c: Card): Card {
  const { guid: _g, noteId: _n, original: _o, ...rest } = c;
  return {
    ...rest,
    id: uid(),
    fields: { ...c.fields },
    tags: [...c.tags],
    ...(c.hidden ? { hidden: [...c.hidden] } : {}),
  };
}

export function duplicateDeck(deck: Deck, existing: Deck[]): Deck {
  // The copy is an ordinary deck: it exports as new notes, not over the original's.
  const { source: _s, ...rest } = deck;
  return {
    ...rest,
    id: uid(),
    name: uniqueDeckName(existing, `${deck.name} copy`),
    cards: deck.cards.map(copyCard),
    tags: [...deck.tags],
    updatedAt: Date.now(),
  };
}

export function defaultAiSettings(): AiSettings {
  return { writer: null, reader: null, extraUrls: [], density: "normal", focus: "balanced", tagSource: true, useMacros: false };
}

export function defaultSettings(): Settings {
  return { theme: "system", macros: defaultMacros(), ai: defaultAiSettings() };
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
  const settings: Settings = {
    theme: rawSettings.theme ?? "system",
    macros,
    ai: { ...defaultAiSettings(), ...(rawSettings.ai ?? {}) },
  };

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
      customFields: d.customFields ?? (d.noteType === "custom" ? [...d.fields!] : undefined),
      ...(d.source ? { source: d.source } : {}),
    }));
  if (!decks.length) return { ...newSession(), settings };
  const active = decks.some((d) => d.id === s.activeDeckId) ? (s.activeDeckId as string) : decks[0].id;
  return { version: 2, decks, activeDeckId: active, settings };
}

// ----- Field layouts -----
//
// A card's values are ordered slots; a note type only decides how many slots
// are shown and what they're called. Switching type relabels the slots and
// parks any that don't fit in `card.hidden`, so nothing is ever thrown away.

const trimTrailingEmpty = (values: string[]) => {
  let n = values.length;
  while (n > 0 && !values[n - 1].trim()) n--;
  return values.slice(0, n);
};

/** All of a card's values in slot order: visible fields first, then hidden. */
function slotValues(card: Card, fields: string[]): string[] {
  return [...fields.map((f) => card.fields[f] ?? ""), ...(card.hidden ?? [])];
}

function withSlots(card: Card, to: string[], values: string[]): Card {
  const fields = Object.fromEntries(to.map((f, i) => [f, values[i] ?? ""]));
  const hidden = trimTrailingEmpty(values.slice(to.length));
  const { hidden: _old, ...rest } = card;
  return hidden.length ? { ...rest, fields, hidden } : { ...rest, fields };
}

/** The one place a deck's field list changes: relabel every card's slots. */
export function relayout(deck: Deck, to: string[], noteType: NoteType): Deck {
  return {
    ...deck,
    noteType,
    fields: [...to],
    customFields: noteType === "custom" ? [...to] : deck.customFields,
    cards: deck.cards.map((c) => withSlots(c, to, slotValues(c, deck.fields))),
  };
}

export function setNoteType(deck: Deck, noteType: NoteType): Deck {
  if (noteType === deck.noteType) return deck;
  // Remember the custom layout when leaving it, and restore it when coming back.
  const remembered = deck.noteType === "custom" ? { ...deck, customFields: [...deck.fields] } : deck;
  const to = noteType === "custom" ? remembered.customFields ?? deck.fields : DEFAULT_FIELDS[noteType];
  return relayout(remembered, to, noteType);
}

/** Use exactly these field names (switches to Custom); content keeps its slots. */
export function setFields(deck: Deck, fields: string[]): Deck {
  return relayout(deck, fields, "custom");
}

export const applyPreset = setFields;

export function nextFieldName(deck: Deck): string {
  let n = deck.fields.length + 1;
  while (deck.fields.includes(`Field ${n}`)) n++;
  return `Field ${n}`;
}

/** Add a slot at the end. It picks up hidden content first, if any. */
export function addField(deck: Deck, name = nextFieldName(deck)): Deck {
  return setFields(deck, [...deck.fields, name]);
}

/** Rename a field across all cards. Returns null if the new name is invalid or taken. */
export function renameField(deck: Deck, from: string, to: string): Deck | null {
  to = to.trim();
  if (!to || to === from) return null;
  if (deck.fields.some((f) => f.toLowerCase() === to.toLowerCase() && f !== from)) return null;
  return setFields(
    deck,
    deck.fields.map((f) => (f === from ? to : f)),
  );
}

/** Number of cards with content in a field (to warn before removing it). */
export function cardsUsingField(deck: Deck, name: string): number {
  return deck.cards.filter((c) => (c.fields[name] ?? "").trim()).length;
}

/** Remove a field and its content from every card (the only deleting operation). */
export function removeField(deck: Deck, name: string): Deck {
  const i = deck.fields.indexOf(name);
  if (i < 0 || deck.fields.length <= 2) return deck;
  const to = deck.fields.filter((f) => f !== name);
  return {
    ...deck,
    noteType: "custom",
    fields: to,
    customFields: [...to],
    cards: deck.cards.map((c) => {
      const values = slotValues(c, deck.fields);
      values.splice(i, 1);
      return withSlots(c, to, values);
    }),
  };
}

export function moveField(deck: Deck, name: string, delta: -1 | 1): Deck {
  const i = deck.fields.indexOf(name);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= deck.fields.length) return deck;
  const to = [...deck.fields];
  [to[i], to[j]] = [to[j], to[i]];
  // Values move with their field, so cards are re-keyed by name, not by slot.
  return {
    ...deck,
    noteType: "custom",
    fields: to,
    customFields: [...to],
    cards: deck.cards.map((c) => withSlots(c, to, [...to.map((f) => c.fields[f] ?? ""), ...(c.hidden ?? [])])),
  };
}

/** Cards with content the current layout doesn't show. */
export function cardsWithHiddenContent(deck: Deck): number {
  return deck.cards.filter((c) => c.hidden?.some((v) => v.trim())).length;
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
