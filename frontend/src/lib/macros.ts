// User LaTeX macros with LaTeX `\newcommand` semantics, including an optional
// first argument: \newcommand{\dv}[3][]{...} lets you write \dv[2]{y}{x}.
//
// KaTeX can't define optional arguments, so the preview expands macros here
// before rendering. On export they're embedded as real \newcommand definitions,
// which Anki's MathJax understands, so the cards keep the readable source.

import type { MacroDef } from "../types";

export const MAX_ARGS = 9;
const MAX_DEPTH = 32;

export class MacroError extends Error {}

// Physics-flavoured defaults, roughly mirroring the LaTeX `physics` package.
// Keep in sync with DEFAULT_MACROS in ankigen/latex.py.
export const DEFAULT_MACROS: MacroDef[] = [
  { name: "\\vb", args: 1, optional: null, body: "\\mathbf{#1}" },
  { name: "\\vu", args: 1, optional: null, body: "\\hat{\\mathbf{#1}}" },
  { name: "\\dv", args: 3, optional: "", body: "\\frac{d^{#1} #2}{d #3^{#1}}" },
  { name: "\\pdv", args: 3, optional: "", body: "\\frac{\\partial^{#1} #2}{\\partial #3^{#1}}" },
  { name: "\\abs", args: 1, optional: null, body: "\\left|#1\\right|" },
  { name: "\\norm", args: 1, optional: null, body: "\\left\\lVert#1\\right\\rVert" },
  { name: "\\ev", args: 1, optional: null, body: "\\left\\langle#1\\right\\rangle" },
  { name: "\\bra", args: 1, optional: null, body: "\\left\\langle#1\\right|" },
  { name: "\\ket", args: 1, optional: null, body: "\\left|#1\\right\\rangle" },
  { name: "\\braket", args: 2, optional: null, body: "\\left\\langle#1\\middle|#2\\right\\rangle" },
  { name: "\\grad", args: 0, optional: null, body: "\\nabla" },
  { name: "\\curl", args: 0, optional: null, body: "\\nabla\\times" },
  { name: "\\divg", args: 0, optional: null, body: "\\nabla\\cdot" },
];

export function defaultMacros(): MacroDef[] {
  return DEFAULT_MACROS.map((m) => ({ ...m }));
}

const isLetter = (c: string | undefined) => !!c && /[A-Za-z]/.test(c);

function skipSpaces(s: string, i: number): number {
  while (i < s.length && /\s/.test(s[i])) i++;
  return i;
}

/** Index of the `close` matching the `open` at `start`, honouring {} nesting and escapes. */
function matchGroup(s: string, start: number, open: string, close: string): number {
  let depth = 0;
  let braces = 0;
  for (let i = start; i < s.length; i++) {
    const c = s[i];
    if (c === "\\") {
      i++;
      continue;
    }
    if (open === "[") {
      if (c === "{") braces++;
      else if (c === "}") braces--;
      else if (c === "]" && braces === 0) return i;
      continue;
    }
    if (c === open) depth++;
    else if (c === close && --depth === 0) return i;
  }
  return -1;
}

/** TeX drops one brace pair that wraps a whole delimited argument: [{a]b}] → a]b. */
function stripOuterBraces(arg: string): string {
  return arg.startsWith("{") && matchGroup(arg, 0, "{", "}") === arg.length - 1 ? arg.slice(1, -1) : arg;
}

/** Read one TeX argument at `i`: a {group}, a \command, or a single character. */
function readArg(s: string, i: number, name: string): [string, number] {
  i = skipSpaces(s, i);
  if (i >= s.length) throw new MacroError(`${name} is missing an argument`);
  const c = s[i];
  if (c === "{") {
    const end = matchGroup(s, i, "{", "}");
    if (end === -1) throw new MacroError(`Unclosed { in an argument of ${name}`);
    return [s.slice(i + 1, end), end + 1];
  }
  if (c === "}") throw new MacroError(`${name} is missing an argument`);
  if (c === "\\") {
    let j = i + 1;
    if (isLetter(s[j])) while (isLetter(s[j])) j++;
    else j++;
    return [s.slice(i, j), j];
  }
  return [c, i + 1];
}

function expand(s: string, defs: Map<string, MacroDef>, depth: number): string {
  if (depth > MAX_DEPTH) throw new MacroError("Macros expand into each other forever (check for a loop)");
  let out = "";
  let i = 0;
  while (i < s.length) {
    if (s[i] !== "\\") {
      out += s[i++];
      continue;
    }
    let j = i + 1;
    if (!isLetter(s[j])) {
      out += s.slice(i, i + 2); // control symbol like \\ or \{
      i += 2;
      continue;
    }
    while (isLetter(s[j])) j++;
    const name = s.slice(i, j);
    const def = defs.get(name);
    if (!def) {
      out += name;
      i = j;
      continue;
    }

    const args: string[] = [];
    let k = j;
    let mandatory = def.args;
    if (def.optional !== null && def.args > 0) {
      const at = skipSpaces(s, k);
      if (s[at] === "[") {
        const end = matchGroup(s, at, "[", "]");
        if (end === -1) throw new MacroError(`Unclosed [ after ${name}`);
        args.push(stripOuterBraces(s.slice(at + 1, end)));
        k = end + 1;
      } else {
        args.push(def.optional);
      }
      mandatory--;
    }
    for (let n = 0; n < mandatory; n++) {
      const [arg, next] = readArg(s, k, name);
      args.push(arg);
      k = next;
    }

    // TeX tokenises the body first, so `\\lVert#1` with #1 = "y" is \\lVert then y,
    // not \\lVerty. Keep that boundary with a space when gluing would merge them.
    const body = def.body.replace(/#([1-9])/g, (m, d: string, offset: number) => {
      const arg = args[Number(d) - 1];
      if (arg === undefined) return m;
      return isLetter(arg[0]) && /\\[A-Za-z]+$/.test(def.body.slice(0, offset)) ? ` ${arg}` : arg;
    });
    let result = expand(body, defs, depth + 1);
    // Don't let a trailing control word swallow the next letter (\alpha + x ≠ \alphax).
    if (/\\[A-Za-z]+$/.test(result) && isLetter(s[k])) result += " ";
    out += result;
    i = k;
  }
  return out;
}

export function expandMacros(tex: string, macros: MacroDef[]): string {
  if (!macros.length || !tex.includes("\\")) return tex;
  return expand(tex, new Map(macros.map((m) => [m.name, m])), 0);
}

export function validateMacro(def: MacroDef, all: MacroDef[]): string | null {
  if (!/^\\[A-Za-z]+$/.test(def.name)) return "Name must be a backslash and letters, e.g. \\dv";
  if (all.filter((m) => m.name === def.name).length > 1) return `${def.name} is defined twice`;
  if (!Number.isInteger(def.args) || def.args < 0 || def.args > MAX_ARGS) return `Arguments must be 0–${MAX_ARGS}`;
  if (def.optional !== null && def.args === 0) return "An optional argument needs at least 1 argument";
  if (!def.body.trim()) return "Definition is empty";
  const used = [...def.body.matchAll(/#(\d)/g)].map((m) => Number(m[1]));
  const bad = used.find((n) => n < 1 || n > def.args);
  if (bad !== undefined) {
    return def.args ? `#${bad} used but there are only ${def.args} argument${def.args === 1 ? "" : "s"}` : `#${bad} used but there are no arguments`;
  }
  let depth = 0;
  for (let i = 0; i < def.body.length; i++) {
    if (def.body[i] === "\\") i++;
    else if (def.body[i] === "{") depth++;
    else if (def.body[i] === "}" && --depth < 0) return "Unbalanced braces: extra }";
  }
  if (depth !== 0) return "Unbalanced braces: missing }";
  return null;
}

const SAMPLE_ARGS = ["y", "x", "z", "a", "b", "c", "d", "e", "f"];

/** A usage example, e.g. \dv[2]{y}{x}, for the editor's live preview. */
export function exampleUsage(def: MacroDef): string {
  let s = def.name;
  let n = def.args;
  if (def.optional !== null && n > 0) {
    s += "[2]";
    n--;
  }
  for (let i = 0; i < n; i++) s += `{${SAMPLE_ARGS[i]}}`;
  return s;
}

// v1 defaults whose definitions changed; untouched copies get the new version.
const V1_DEFAULT_BODIES: Record<string, string> = {
  "\\dv": "\\frac{d#1}{d#2}",
  "\\pdv": "\\frac{\\partial #1}{\\partial #2}",
};

/**
 * Convert the v1 `{ "\\name": "body" }` map, inferring the argument count.
 * Macros still equal to an old default are upgraded (e.g. \\dv gains [order]).
 */
export function fromLegacy(map: Record<string, string>): MacroDef[] {
  return Object.entries(map).map(([name, body]) => {
    if (V1_DEFAULT_BODIES[name] === body) {
      const upgraded = DEFAULT_MACROS.find((d) => d.name === name);
      if (upgraded) return { ...upgraded };
    }
    const nums = [...body.matchAll(/#(\d)/g)].map((m) => Number(m[1]));
    return { name, body, args: nums.length ? Math.max(...nums) : 0, optional: null };
  });
}
