// Render field text with `$...$` / `$$...$$` math into HTML.
// Mirrors ankigen/latex.py so the preview matches what Anki will show.

import katex from "katex";
import "katex/contrib/mhchem";
import type { MacroDef } from "../types";
import { expandMacros } from "./macros";

type Segment = { kind: "text"; value: string } | { kind: "math"; value: string; display: boolean };

export function splitMath(text: string): Segment[] {
  const out: Segment[] = [];
  let buf = "";
  let i = 0;
  const flush = () => {
    if (buf) out.push({ kind: "text", value: buf });
    buf = "";
  };
  while (i < text.length) {
    const ch = text[i];
    if (ch === "\\" && i + 1 < text.length) {
      buf += text[i + 1] === "$" ? "$" : text.slice(i, i + 2);
      i += 2;
      continue;
    }
    if (ch === "`") {
      const end = text.indexOf("`", i + 1);
      if (end !== -1) {
        buf += text.slice(i, end + 1);
        i = end + 1;
        continue;
      }
    }
    if (ch === "$") {
      const display = text.startsWith("$$", i);
      const delim = display ? "$$" : "$";
      const end = findClosing(text, i + delim.length, delim);
      if (end !== -1) {
        flush();
        out.push({ kind: "math", value: text.slice(i + delim.length, end), display });
        i = end + delim.length;
        continue;
      }
    }
    buf += ch;
    i++;
  }
  flush();
  return out;
}

function findClosing(text: string, start: number, delim: string): number {
  let i = start;
  while (i < text.length) {
    if (text[i] === "\\") {
      i += 2;
      continue;
    }
    if (text.startsWith(delim, i)) {
      if (delim === "$" && text.startsWith("$$", i)) return i === start ? -1 : i;
      return i > start ? i : -1;
    }
    i++;
  }
  return -1;
}

const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function renderText(s: string): string {
  return escapeHtml(s)
    .replace(/\{\{c(\d+)::/g, '<span class="cloze" data-c="$1">')
    .replace(/::[^{}]*?\}\}/g, "</span>")
    .replace(/\}\}/g, "</span>")
    .replace(/\n/g, "<br>");
}

export interface RenderResult {
  html: string;
  errors: string[];
}

export function renderField(text: string, macros: MacroDef[]): RenderResult {
  const errors: string[] = [];
  const html = splitMath(text)
    .map((seg) => {
      if (seg.kind === "text") return renderText(seg.value);
      try {
        return katex.renderToString(expandMacros(seg.value, macros), {
          displayMode: seg.display,
          throwOnError: true,
          strict: "ignore",
        });
      } catch (e) {
        errors.push(e instanceof Error ? e.message.replace(/^KaTeX parse error: /, "") : String(e));
        const raw = seg.display ? `$$${seg.value}$$` : `$${seg.value}$`;
        return `<span class="math-error">${escapeHtml(raw)}</span>`;
      }
    })
    .join("");
  return { html, errors };
}

/** Pre-export check: an unclosed `$`, or math KaTeX can't parse. */
export function hasMathProblem(text: string, macros: MacroDef[]): boolean {
  const unescaped = text.replace(/\\\$/g, "");
  if (!unescaped.includes("$")) return false;
  if (splitMath(unescaped).some((s) => s.kind === "text" && s.value.includes("$"))) return true;
  return renderField(text, macros).errors.length > 0;
}
