import katex from "katex";
import { describe, expect, it } from "vitest";
import type { MacroDef } from "../types";
import { DEFAULT_MACROS, MacroError, exampleUsage, expandMacros, fromLegacy, validateMacro } from "./macros";

const m = (name: string, args: number, body: string, optional: string | null = null): MacroDef => ({
  name,
  args,
  optional,
  body,
});

describe("expandMacros", () => {
  const dv = m("\\dv", 3, "\\frac{d^{#1} #2}{d #3^{#1}}", "");

  it("uses the optional argument when given", () => {
    expect(expandMacros("\\dv[2]{y}{x}", [dv])).toBe("\\frac{d^{2} y}{d x^{2}}");
  });

  it("falls back to the default when the optional argument is omitted", () => {
    expect(expandMacros("\\dv{y}{x}", [dv])).toBe("\\frac{d^{} y}{d x^{}}");
    const withDefault = m("\\o", 2, "#1+#2", "1");
    expect(expandMacros("\\o{a}", [withDefault])).toBe("1+a");
  });

  it("supports many arguments", () => {
    const five = m("\\five", 5, "#1#2#3#4#5");
    expect(expandMacros("\\five{a}{b}{c}{d}{e}", [five])).toBe("abcde");
  });

  it("reads single-token and command arguments like TeX", () => {
    const vb = m("\\vb", 1, "\\mathbf{#1}");
    expect(expandMacros("\\vb E", [vb])).toBe("\\mathbf{E}");
    expect(expandMacros("\\vb\\nabla", [vb])).toBe("\\mathbf{\\nabla}");
  });

  it("keeps nested braces and brackets intact", () => {
    expect(expandMacros("\\dv[{n+1}]{\\frac{a}{b}}{x}", [dv])).toBe("\\frac{d^{n+1} \\frac{a}{b}}{d x^{n+1}}");
    // Like LaTeX, a ] inside the optional argument must be protected by braces.
    expect(expandMacros("\\dv[{f[x]}]{y}{x}", [dv])).toBe("\\frac{d^{f[x]} y}{d x^{f[x]}}");
  });

  it("does not touch longer command names that share a prefix", () => {
    expect(expandMacros("\\dvx", [dv])).toBe("\\dvx");
  });

  it("expands nested macros", () => {
    const a = m("\\a", 1, "\\b{#1}");
    const b = m("\\b", 1, "[#1]");
    expect(expandMacros("\\a{x}", [a, b])).toBe("[x]");
  });

  it("stops infinite recursion", () => {
    const loop = m("\\loop", 0, "\\loop");
    expect(() => expandMacros("\\loop", [loop])).toThrow(MacroError);
  });

  it("reports missing arguments", () => {
    expect(() => expandMacros("\\dv{y}", [dv])).toThrow(/missing an argument/);
  });

  it("keeps a control word before an argument separate", () => {
    const norm = m("\\norm", 1, "\\lVert#1\\rVert");
    expect(expandMacros("\\norm{y}", [norm])).toBe("\\lVert y\\rVert");
    expect(expandMacros("\\norm{1}", [norm])).toBe("\\lVert1\\rVert");
  });

  it("does not glue a trailing control word onto following letters", () => {
    const al = m("\\al", 1, "#1\\alpha");
    expect(expandMacros("\\al{x}y", [al])).toBe("x\\alpha y");
  });

  it("produces KaTeX-renderable output for every default macro", () => {
    for (const def of DEFAULT_MACROS) {
      expect(() => katex.renderToString(expandMacros(exampleUsage(def), DEFAULT_MACROS), { throwOnError: true })).not.toThrow();
    }
  });
});

describe("validateMacro", () => {
  it("accepts a valid macro", () => {
    const def = m("\\dv", 3, "\\frac{d^{#1}#2}{d#3^{#1}}", "");
    expect(validateMacro(def, [def])).toBeNull();
  });

  it("rejects bad names, duplicates and argument mismatches", () => {
    const ok = m("\\x", 1, "#1");
    expect(validateMacro(m("dv", 1, "#1"), [])).toMatch(/Name/);
    expect(validateMacro(ok, [ok, ok])).toMatch(/twice/);
    expect(validateMacro(m("\\y", 2, "#1#3"), [])).toMatch(/#3/);
    expect(validateMacro(m("\\y", 0, "x", ""), [])).toMatch(/optional/i);
    expect(validateMacro(m("\\y", 1, "{#1"), [])).toMatch(/braces/);
    expect(validateMacro(m("\\y", 10, "#1"), [])).toMatch(/0–9/);
  });
});

describe("helpers", () => {
  it("builds usage examples", () => {
    expect(exampleUsage(m("\\dv", 3, "", ""))).toBe("\\dv[2]{y}{x}");
    expect(exampleUsage(m("\\grad", 0, "\\nabla"))).toBe("\\grad");
  });

  it("converts legacy macro maps, upgrading untouched old defaults", () => {
    expect(fromLegacy({ "\\x": "#1+#2" })).toEqual([m("\\x", 2, "#1+#2")]);
    expect(fromLegacy({ "\\dv": "\\frac{d#1}{d#2}" })).toEqual([DEFAULT_MACROS.find((d) => d.name === "\\dv")]);
    expect(fromLegacy({ "\\dv": "\\frac{\\mathrm{d}#1}{\\mathrm{d}#2}" })[0].args).toBe(2);
  });
});
