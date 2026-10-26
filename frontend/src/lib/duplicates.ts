// Spot suggested cards that repeat a card in the deck, or one suggested above them.
// Plain text similarity, no AI: words that only frame a question ("what is",
// "state", "define") are ignored, and each equation counts as one token, so
// "What is X?" and "State X." match while two different questions about X don't.

import { splitMath } from "./math";

export interface CardKey {
  /** Content tokens of the first field, in order. */
  front: string[];
  frontSet: Set<string>;
  /** Content tokens of every field. */
  all: Set<string>;
  /** All fields, normalised, for an exact match. */
  exact: string;
}

export interface DuplicateMatch {
  /** "same": the same question (or the same card); "similar": close enough to look like a repeat. */
  kind: "same" | "similar";
  where: "deck" | "batch";
  /** Index into the deck's cards, or into the review list. */
  index: number;
  score: number;
}

/** Front Jaccard similarity at or above this counts as similar… */
export const SIMILAR_FRONT = 0.7;
/** …and so does this over all fields together. */
export const SIMILAR_ALL = 0.75;

// Question framing and function words. Subject words ("equation", "law",
// "energy") are kept: they're what tells two questions apart.
const STOP = new Set(
  (
    "a an the of to in on at by for from with as and or but not no is are was were be been being do does did " +
    "it its this that these those there their what which who whom whose why how when where whether " +
    "state define definition describe explain give write name list express expression formula " +
    "mean meaning means called term refer refers known can could would should will may might must " +
    "you your we our one some any about into than then so if also such between used use using"
  ).split(" "),
);

function stem(word: string): string {
  if (word.length > 4 && word.endsWith("ies")) return `${word.slice(0, -3)}y`;
  if (word.length > 3 && word.endsWith("s") && !word.endsWith("ss") && !word.endsWith("us")) return word.slice(0, -1);
  return word;
}

/** A spacing- and markup-insensitive form of a math segment. Mirrors ankigen/ai/equations.py normalize. */
export function normalizeMath(math: string): string {
  let s = math.trim();
  s = s.replace(/\\tag\*?\{[^}]*\}/g, "");
  s = s.replace(/\\(left|right)\.|\\(left|right|big|Big|bigg|Bigg)(?![A-Za-z])/g, "");
  s = s.replace(/\\[,;:! ]|\\q?quad(?![A-Za-z])/g, "");
  s = s.replace(/\\[dt]frac/g, "\\frac");
  s = s.replace(/\s+/g, "");
  s = s.replace(/\{(\\?[A-Za-z0-9])\}/g, "$1");
  return s.replace(/[.,;]+$/, "");
}

/** Field text without HTML or cloze markup: `{{c1::x::hint}}` → `x`. */
export function plainText(text: string): string {
  return text
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/\{\{c\d+::([\s\S]*?)(?:::[^{}]*?)?\}\}/g, "$1");
}

export function tokens(text: string): string[] {
  const out: string[] = [];
  for (const seg of splitMath(plainText(text))) {
    if (seg.kind === "math") {
      const m = normalizeMath(seg.value);
      if (m) out.push(`$${m}`);
      continue;
    }
    for (const w of seg.value.toLowerCase().split(/[^\p{L}\p{N}]+/u)) {
      if (w && !STOP.has(w)) out.push(stem(w));
    }
  }
  return out;
}

export function cardKey(fields: Record<string, string>, order: string[]): CardKey {
  const perField = order.map((f) => tokens(fields[f] ?? ""));
  const front = perField[0] ?? [];
  return {
    front,
    frontSet: new Set(front),
    all: new Set(perField.flat()),
    exact: perField.map((t) => t.join(" ")).join(" | "),
  };
}

function jaccard(a: Set<string>, b: Set<string>): number {
  if (!a.size || !b.size) return 0;
  let shared = 0;
  const [small, big] = a.size < b.size ? [a, b] : [b, a];
  for (const t of small) if (big.has(t)) shared++;
  return shared / (a.size + b.size - shared);
}

/** How alike two cards are, or null when they aren't duplicates. */
export function compareKeys(a: CardKey, b: CardKey): { kind: "same" | "similar"; score: number } | null {
  if (!a.all.size || !b.all.size) return null;
  if (a.exact === b.exact) return { kind: "same", score: 1 };
  if (a.front.length && a.front.join(" ") === b.front.join(" ")) return { kind: "same", score: 1 };
  const front = a.frontSet.size >= 2 && b.frontSet.size >= 2 ? jaccard(a.frontSet, b.frontSet) : 0;
  const all = a.all.size >= 4 && b.all.size >= 4 ? jaccard(a.all, b.all) : 0;
  if (front >= SIMILAR_FRONT || all >= SIMILAR_ALL) return { kind: "similar", score: Math.max(front, all) };
  return null;
}

function better(a: DuplicateMatch | null, b: DuplicateMatch | null): DuplicateMatch | null {
  if (!a) return b;
  if (!b) return a;
  if (a.kind !== b.kind) return a.kind === "same" ? a : b;
  return b.score > a.score ? b : a;
}

/** The deck's cards, keyed and indexed by token, ready to compare against. */
export interface DeckIndex {
  keys: CardKey[];
  byToken: Map<string, number[]>;
}

export function indexDeck(cards: { fields: Record<string, string> }[], order: string[]): DeckIndex {
  const keys = cards.map((c) => cardKey(c.fields, order));
  const byToken = new Map<string, number[]>();
  keys.forEach((k, i) => {
    for (const t of k.all) {
      const list = byToken.get(t);
      if (list) list.push(i);
      else byToken.set(t, [i]);
    }
  });
  return { keys, byToken };
}

/** For each review card: its closest match in the deck or above it in the list, if any. */
export function findDuplicates(
  review: { fields: Record<string, string> }[],
  deck: DeckIndex,
  order: string[],
): (DuplicateMatch | null)[] {
  const keys = review.map((c) => cardKey(c.fields, order));
  return keys.map((key, i) => {
    let best: DuplicateMatch | null = null;
    // Duplicates share at least one token, so only those deck cards are compared.
    const seen = new Set<number>();
    for (const t of key.all) {
      for (const j of deck.byToken.get(t) ?? []) {
        if (seen.has(j)) continue;
        seen.add(j);
        const m = compareKeys(key, deck.keys[j]);
        if (m) best = better(best, { ...m, where: "deck", index: j });
      }
    }
    for (let j = 0; j < i; j++) {
      const m = compareKeys(key, keys[j]);
      if (m) best = better(best, { ...m, where: "batch", index: j });
    }
    return best;
  });
}
