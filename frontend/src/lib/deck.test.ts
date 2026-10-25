import { describe, expect, it } from "vitest";
import { addField, duplicateDeck, migrateSession, moveField, newDeck, removeField, renameField, setNoteType } from "./deck";

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

describe("custom fields", () => {
  const base = () => {
    const d = newDeck();
    d.cards[0].fields = { Front: "q", Back: "a", Extra: "e" };
    return d;
  };

  it("switching to custom keeps fields and values", () => {
    const d = setNoteType(base(), "custom");
    expect(d.noteType).toBe("custom");
    expect(d.fields).toEqual(["Front", "Back", "Extra"]);
    expect(d.cards[0].fields.Back).toBe("a");
  });

  it("renames, moves, adds and removes fields across cards", () => {
    let d = renameField(base(), "Front", "Quantity")!;
    expect(d.fields).toEqual(["Quantity", "Back", "Extra"]);
    expect(d.cards[0].fields.Quantity).toBe("q");
    expect(renameField(d, "Back", "quantity")).toBeNull();
    d = moveField(d, "Extra", -1);
    expect(d.fields).toEqual(["Quantity", "Extra", "Back"]);
    d = addField(d);
    expect(d.fields).toHaveLength(4);
    d = removeField(d, "Extra");
    expect(d.fields).toEqual(["Quantity", "Back", "Field 4"]);
    expect(d.cards[0].fields.Extra).toBeUndefined();
  });

  it("never drops below two fields", () => {
    let d = removeField(base(), "Extra");
    d = removeField(d, "Back");
    expect(d.fields).toHaveLength(2);
  });
});
