// Typed bridge to the Python backend.
//
// Inside the desktop app, pywebview injects `window.pywebview.api`. In a plain
// browser (`npm run dev`), calls go over HTTP to `python -m ankigen.devserver`
// through Vite's /api proxy, so the UI can be developed with hot reload.

import type { Deck, MacroDef, ParseResult, Session } from "./types";

type Result<T> = ({ ok: true } & T) | { ok: false; error: string };

declare global {
  interface Window {
    pywebview?: { api: Record<string, (...args: unknown[]) => Promise<unknown>> };
  }
}

let ready: Promise<void> | null = null;

function waitForBridge(): Promise<void> {
  if (ready) return ready;
  ready = new Promise((resolve) => {
    if (window.pywebview?.api) return resolve();
    let settled = false;
    const done = () => {
      if (!settled) {
        settled = true;
        resolve();
      }
    };
    window.addEventListener("pywebviewready", done, { once: true });
    // No pywebview after a moment means we're in a normal browser.
    setTimeout(done, 400);
  });
  return ready;
}

async function call<T>(method: string, ...args: unknown[]): Promise<Result<T>> {
  await waitForBridge();
  try {
    if (window.pywebview?.api?.[method]) {
      return (await window.pywebview.api[method](...args)) as Result<T>;
    }
    const res = await fetch(`/api/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(args),
    });
    return (await res.json()) as Result<T>;
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

/** Shape the backend's DeckSpec expects. */
function toSpec(deck: Deck, macros: MacroDef[]) {
  return {
    name: deck.name.trim() || "Untitled",
    note_type: deck.noteType,
    fields: deck.fields,
    tags: deck.tags,
    macros,
    cards: deck.cards.map((c) => ({ fields: c.fields, tags: c.tags })),
  };
}

export const api = {
  info: () =>
    call<{
      version: string;
      build: string;
      release: boolean;
      data_dir: string;
      formats: string[];
      default_macros: MacroDef[];
    }>("info"),
  parseText: (text: string, fmt: string, options: Record<string, unknown>) =>
    call<ParseResult>("parse_text", text, fmt, options),
  openTextFile: () =>
    call<{ cancelled?: boolean; path?: string; name?: string; text?: string }>("open_text_file"),
  exportDeck: (deck: Deck, macros: MacroDef[]) =>
    call<{ cancelled?: boolean; path?: string; count?: number }>("export_deck", toSpec(deck, macros)),
  reveal: (path: string) => call<object>("reveal", path),
  // Saved sessions may be older shapes; App runs them through migrateSession().
  loadSession: () => call<{ session: unknown }>("load_session"),
  saveSession: (session: Session) => call<object>("save_session", session),
};
