// Choosing AI models and turning generated cards into deck cards.

import type { AiSettings, AiStatus, Card, GeneratedCard, ModelRef } from "../types";
import { uid } from "./deck";

export interface ModelChoice {
  ref: ModelRef;
  label: string;
  group: string;
  hint: string;
}

export const refKey = (r: ModelRef | null | undefined) => (r ? `${r.backend}|${r.url}|${r.model}` : "");
export const sameRef = (a: ModelRef | null | undefined, b: ModelRef | null | undefined) => refKey(a) === refKey(b);

/** Every model the user can pick right now: running local runtimes, then Gemini. */
export function modelChoices(status: AiStatus | null, stage: "cards" | "read" = "cards"): ModelChoice[] {
  if (!status) return [];
  const out: ModelChoice[] = [];
  for (const r of status.runtimes) {
    if (!r.status) continue;
    for (const m of r.models) {
      if (stage === "read" && m.vision === false) continue;
      const hints = [m.detail, m.thinking ? "thinking model" : ""].filter(Boolean);
      out.push({
        ref: { backend: r.backend, url: r.url, model: m.id },
        label: m.id,
        group: `${r.name} · on this computer`,
        hint: hints.join(" · "),
      });
    }
  }
  const g = status.gemini;
  if (g.has_key) {
    const ids = g.models.map((m) => m.id);
    // Newest first; the default and the fast model at the top.
    const ordered = [g.default, g.fast, ...ids.filter((i) => i !== g.default && i !== g.fast).reverse()].filter(
      (i): i is string => !!i,
    );
    for (const id of ordered) {
      out.push({
        ref: { backend: "gemini", url: "", model: id },
        label: id,
        group: "Gemini · online",
        hint: id === g.default ? "best quality · slow on the free tier" : id === g.fast ? "faster, slightly lower quality" : "",
      });
    }
  }
  return out;
}

/** The model that will actually write cards: the saved choice if it's still there, else a suggestion. */
export function effectiveWriter(ai: AiSettings, status: AiStatus | null): ModelRef | null {
  const choices = modelChoices(status);
  if (ai.writer && choices.some((c) => sameRef(c.ref, ai.writer))) return ai.writer;
  if (!status) return ai.writer;
  if (status.suggested.cards) return status.suggested.cards;
  const gemini = status.gemini.has_key && status.gemini.default;
  if (gemini) return { backend: "gemini", url: "", model: gemini };
  return choices[0]?.ref ?? null;
}

export function describeRef(ref: ModelRef | null): string {
  if (!ref) return "no model";
  if (ref.backend === "gemini") return `${ref.model} (Gemini)`;
  if (ref.backend === "ollama") return `${ref.model} (Ollama)`;
  return ref.model;
}

export function isLocal(ref: ModelRef | null): boolean {
  return !!ref && ref.backend !== "gemini";
}

/** Generated cards → deck cards with exactly the deck's fields. */
export function toDeckCards(generated: GeneratedCard[], fields: string[], extraTags: string[] = []): Card[] {
  return generated.map((g) => ({
    id: uid(),
    fields: Object.fromEntries(fields.map((f) => [f, g.fields[f] ?? ""])),
    tags: [...new Set([...g.tags, ...extraTags])],
  }));
}

/** LaTeX outside $…$ (shows as raw \frac in Anki). Mirrors ankigen/ai/cards.py. */
export function bareLatex(text: string): boolean {
  const outside = text.replace(/\$\$[\s\S]+?\$\$|\$(?:\\.|[^$\\])+\$/g, "");
  return /\\[A-Za-z]+|[_^]\{/.test(outside);
}

export function formatElapsed(seconds: number): string {
  const s = Math.round(seconds);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}
