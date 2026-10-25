import { describe, expect, it } from "vitest";
import type { Deck } from "../types";
import {
  addField,
  applyPreset,
  cardsUsingField,
  cardsWithHiddenContent,
  duplicateDeck,
  migrateSession,
  moveField,
  newDeck,
  removeField,
  renameField,
  setNoteType,
} from "./deck";

describe("migrateSession", () => {
  it("turns a v1 single-deck session into v2 with converted macros", () => {
    const v1 = {
      version: 1,
      deck: { name: "Old", noteType: "basic", fields: ["Front", "Back", "Extra"], cards: [{ id: "c1", fields: { Front: "q" }, tags: [] }], tags: [] },
      settings: { theme: "dark", macros: { "\\vb": "\\mathbf{#1}" } },
    };
    const s = migrateSession(v1);
    expect(s.version).toBe(2);
    expect(s.decks).toHaveLength(1);
    expect(s.decks[0].name).toBe("Old");
    expect(s.activeDeckId).toBe(s.decks[0].id);
    expect(s.settings.theme).toBe("dark");
    expect(s.settings.macros).toEqual([{ name: "\\vb", args: 1, optional: null, body: "\\mathbf{#1}" }]);
  });

  it("keeps v2 sessions and falls back to the first deck if the active id is gone", () => {
    const a = newDeck();
    const b = newDeck([a]);
    const s = migrateSession({ version: 2, decks: [a, b], activeDeckId: "missing", settings: { theme: "system", macros: [] } });
    expect(s.decks.map((d) => d.name)).toEqual(["New deck", "New deck 2"]);
    expect(s.activeDeckId).toBe(a.id);
  });

  it("starts fresh on garbage", () => {
    expect(migrateSession(null).decks).toHaveLength(1);
    expect(migrateSession({ version: 2, decks: [{ nope: true }] }).decks).toHaveLength(1);
  });
});

describe("decks", () => {
  it("names new and duplicated decks uniquely", () => {
    const a = newDeck();
    const b = newDeck([a]);
    expect(b.name).toBe("New deck 2");
    const c = duplicateDeck(a, [a, b]);
    expect(c.name).toBe("New deck copy");
    expect(c.id).not.toBe(a.id);
    expect(c.cards[0].id).not.toBe(a.cards[0].id);
  });
});

describe("custom fields and switching note types", () => {
  const values = (d: Deck) => d.cards.map((c) => d.fields.map((f) => c.fields[f]));

  /** The user's case: a custom layout chosen via preset, then a 4th field added. */
  const customDeck = () => {
    let d = newDeck();
    d = applyPreset(d, ["Quantity", "Formula", "Units"]);
    d = addField(d, "Notes");
    d.cards = [
      { id: "a", tags: [], fields: { Quantity: "Force", Formula: "$F=ma$", Units: "N", Notes: "Newton II" } },
      { id: "b", tags: [], fields: { Quantity: "Energy", Formula: "$E=mc^2$", Units: "J", Notes: "" } },
    ];
    return d;
  };

  it("Custom → Basic → Reversed → Custom keeps every name and value", () => {
    const start = customDeck();
    let d = setNoteType(start, "basic");
    expect(d.fields).toEqual(["Front", "Back", "Extra"]);
    expect(values(d)).toEqual([
      ["Force", "$F=ma$", "N"],
      ["Energy", "$E=mc^2$", "J"],
    ]);
    expect(d.cards[0].hidden).toEqual(["Newton II"]);
    expect(d.cards[1].hidden).toBeUndefined();
    expect(cardsWithHiddenContent(d)).toBe(1);

    d = setNoteType(d, "reversed");
    d = setNoteType(d, "custom");
    expect(d.fields).toEqual(["Quantity", "Formula", "Units", "Notes"]);
    expect(values(d)).toEqual(values(start));
    expect(d.cards[0].hidden).toBeUndefined();
  });

  it("edits made in Basic show up back in Custom", () => {
    let d = setNoteType(customDeck(), "basic");
    d.cards[0].fields.Back = "$\\vb{F}=m\\vb{a}$";
    d = setNoteType(d, "custom");
    expect(d.cards[0].fields.Formula).toBe("$\\vb{F}=m\\vb{a}$");
    expect(d.cards[0].fields.Notes).toBe("Newton II");
  });

  it("Basic → Cloze → Basic is lossless", () => {
    let d = newDeck();
    d.cards[0].fields = { Front: "q", Back: "a", Extra: "e" };
    d = setNoteType(d, "cloze");
    expect(d.cards[0].fields).toEqual({ Text: "q", Extra: "a" });
    expect(d.cards[0].hidden).toEqual(["e"]);
    d = setNoteType(d, "basic");
    expect(d.cards[0].fields).toEqual({ Front: "q", Back: "a", Extra: "e" });
  });

  it("ignores stale keys left over from older layouts", () => {
    const d = newDeck();
    d.noteType = "custom";
    d.fields = ["Term", "Definition"];
    d.cards[0].fields = { Front: "", Back: "", Extra: "", Term: "Work", Definition: "$W = F d$" };
    const basic = setNoteType(d, "basic");
    expect(basic.cards[0].fields).toEqual({ Front: "Work", Back: "$W = F d$", Extra: "" });
  });

  it("presets relabel slots, park overflow, and addField brings it back", () => {
    let d = applyPreset(customDeck(), ["Term", "Definition"]);
    expect(d.fields).toEqual(["Term", "Definition"]);
    expect(d.cards[0].fields).toEqual({ Term: "Force", Definition: "$F=ma$" });
    expect(d.cards[0].hidden).toEqual(["N", "Newton II"]);
    d = addField(d, "Units");
    expect(d.cards[0].fields.Units).toBe("N");
    expect(d.cards[0].hidden).toEqual(["Newton II"]);
  });

  it("renames, moves and removes fields with their content", () => {
    let d = renameField(customDeck(), "Units", "SI unit")!;
    expect(d.fields).toEqual(["Quantity", "Formula", "SI unit", "Notes"]);
    expect(d.cards[0].fields["SI unit"]).toBe("N");
    expect(renameField(d, "Notes", "quantity")).toBeNull();
    d = moveField(d, "Notes", -1);
    expect(d.fields).toEqual(["Quantity", "Formula", "Notes", "SI unit"]);
    expect(d.cards[0].fields.Notes).toBe("Newton II");
    expect(cardsUsingField(d, "Notes")).toBe(1);
    d = removeField(d, "Notes");
    expect(d.fields).toEqual(["Quantity", "Formula", "SI unit"]);
    expect(d.cards[0].fields).toEqual({ Quantity: "Force", Formula: "$F=ma$", "SI unit": "N" });
    // The remembered layout follows edits.
    expect(setNoteType(setNoteType(d, "basic"), "custom").fields).toEqual(["Quantity", "Formula", "SI unit"]);
  });

  it("never drops below two fields", () => {
    let d = removeField(newDeck(), "Extra");
    d = removeField(d, "Back");
    expect(d.fields).toHaveLength(2);
  });

  it("migration remembers an existing custom layout", () => {
    const s = migrateSession({
      version: 2,
      activeDeckId: "x",
      settings: { theme: "system", macros: [] },
      decks: [{ id: "x", name: "C", noteType: "custom", fields: ["Term", "Def"], cards: [], tags: [] }],
    });
    expect(s.decks[0].customFields).toEqual(["Term", "Def"]);
  });
});
