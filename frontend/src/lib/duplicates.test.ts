import { describe, expect, it } from "vitest";
import { cardKey, compareKeys, findDuplicates, importPlan, indexDeck, normalizeMath, plainText } from "./duplicates";

const order = ["Front", "Back", "Extra"];
const card = (Front: string, Back = "", Extra = "") => ({ fields: { Front, Back, Extra } });
const compare = (a: ReturnType<typeof card>, b: ReturnType<typeof card>) =>
  compareKeys(cardKey(a.fields, order), cardKey(b.fields, order));

describe("compareKeys", () => {
  it("treats markup, case, spacing and question wording as the same question", () => {
    expect(compare(card("What is the <b>Pauli</b> exclusion principle?", "No two fermions…"), card("State the Pauli exclusion principle.", "Two identical fermions can't share a state")))
      .toMatchObject({ kind: "same" });
    expect(compare(card("Energy of a photon: $E = h\\nu$"), card("energy of a photon:  $E=h \\nu$ ")))
      .toMatchObject({ kind: "same" });
  });

  it("reads cloze text without its markup", () => {
    const o = ["Text", "Extra"];
    const a = cardKey({ Text: "The {{c1::Pauli}} principle forbids {{c2::two identical fermions::who?}} in one state" }, o);
    const b = cardKey({ Text: "The Pauli principle forbids two identical fermions in one state" }, o);
    expect(compareKeys(a, b)).toMatchObject({ kind: "same" });
  });

  it("flags reworded repeats as similar", () => {
    expect(
      compare(
        card("What does the Pauli exclusion principle say about identical fermions?", "No two identical fermions can occupy the same quantum state."),
        card("What does the Pauli exclusion principle state?", "No two identical fermions can occupy the same quantum state."),
      ),
    ).toMatchObject({ kind: "similar" });
    expect(
      compare(
        card("Recurrence relation for the Hermite polynomials", "$H_{n+1} = 2xH_n - 2nH_{n-1}$"),
        card("Give the recurrence relation of Hermite polynomials", "$H_{n+1}=2xH_n-2nH_{n-1}$"),
      ),
    ).toMatchObject({ kind: "same" });
  });

  it("keeps different questions on the same topic apart", () => {
    expect(
      compare(
        card("What is the recurrence relation for the Hermite polynomials?", "$H_{n+1} = 2xH_n - 2nH_{n-1}$"),
        card("Which differential equation do the Hermite polynomials satisfy?", "$H_n'' - 2xH_n' + 2nH_n = 0$"),
      ),
    ).toBeNull();
    expect(compare(card("What is the energy of a photon?", "$E = h\\nu$"), card("What is the momentum of a photon?", "$p = h/\\lambda$"))).toBeNull();
  });

  it("tells a second derivative from a first", () => {
    expect(normalizeMath("\\frac{d^2 y}{dx^2}")).toBe(normalizeMath("\\dfrac{d^2y}{dx^2}"));
    expect(normalizeMath("\\frac{d^2 y}{dx^2}")).not.toBe(normalizeMath("\\frac{dy}{dx}"));
    expect(compare(card("ODE", "$\\frac{d^2 y}{dx^2} = -k^2 y$"), card("ODE", "$\\frac{dy}{dx} = -k^2 y$"))).toMatchObject({ kind: "same" }); // same question
    expect(
      compare(card("Harmonic oscillator equation of motion", "$\\frac{d^2 x}{dt^2} = -\\omega^2 x$"), card("Exponential decay law", "$\\frac{dN}{dt} = -\\lambda N$")),
    ).toBeNull();
  });

  it("ignores empty cards", () => {
    expect(compare(card(""), card(""))).toBeNull();
  });

  it("strips HTML entities and line breaks", () => {
    expect(plainText("a&nbsp;b<br>c &amp; d")).toBe("a b\nc & d");
  });
});

describe("findDuplicates", () => {
  const deck = indexDeck([card("What is entropy?", "A measure of disorder"), card("Newton's second law", "$F = ma$")], order);

  it("matches against the deck and only against cards above in the batch", () => {
    const review = [card("Define entropy.", "Disorder"), card("Ideal gas law", "$pV = nRT$"), card("State the ideal gas law", "$pV=nRT$"), card("Coulomb's law", "$F = kq_1q_2/r^2$")];
    const found = findDuplicates(review, deck, order);
    expect(found[0]).toMatchObject({ kind: "same", where: "deck", index: 0 });
    expect(found[1]).toBeNull();
    expect(found[2]).toMatchObject({ kind: "same", where: "batch", index: 1 });
    expect(found[3]).toBeNull();
  });

  it("prefers a deck match over a batch one", () => {
    const found = findDuplicates([card("Newton's second law", "$F=ma$"), card("Newton's second law", "$F = ma$")], deck, order);
    expect(found[1]).toMatchObject({ where: "deck", index: 1 });
  });

  it("is quick on a large deck", () => {
    const big = indexDeck(
      Array.from({ length: 3000 }, (_, i) => card(`Question ${i} about topic${i % 97} and item${i}`, `Answer $x_{${i}} = ${i}$`)),
      order,
    );
    const review = Array.from({ length: 60 }, (_, i) => card(`New question ${i} about topic${i}`, `Answer $y = ${i}$`));
    const t = performance.now();
    findDuplicates(review, big, order);
    expect(performance.now() - t).toBeLessThan(500);
  });
});

describe("importPlan", () => {
  const deck = indexDeck([card("What is entropy?", "Disorder")], order);
  const pasted = [card("Define entropy", "Disorder"), card("Ohm's law", "$V = IR$"), card("State Ohm's law", "$V=IR$")];

  it("skips deck and in-paste duplicates unless kept or skipping is off", () => {
    expect(importPlan(pasted, deck, order, true).include).toEqual([false, true, false]);
    expect(importPlan(pasted, deck, order, true, new Set([2])).include).toEqual([false, true, true]);
    expect(importPlan(pasted, deck, order, false).include).toEqual([true, true, true]);
  });

  it("only looks within the paste when there's no deck (Replace deck)", () => {
    expect(importPlan(pasted, null, order, true).include).toEqual([true, true, false]);
  });
});
