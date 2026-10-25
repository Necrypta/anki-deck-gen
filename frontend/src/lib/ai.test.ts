import { describe, expect, it } from "vitest";
import type { AiStatus } from "../types";
import { bareLatex, effectiveReader, effectiveWriter, formatElapsed, modelChoices, parsePageRange, toDeckCards } from "./ai";
import { defaultAiSettings, migrateSession } from "./deck";

const status: AiStatus = {
  runtimes: [
    {
      name: "Ollama",
      backend: "ollama",
      url: "http://localhost:11434",
      status: "Ollama 0.12",
      error: "",
      models: [
        { id: "qwen3:8b", vision: false, thinking: true, detail: "8.2B" },
        { id: "qwen2.5vl:7b", vision: true, thinking: false, detail: "" },
      ],
    },
    { name: "LM Studio", backend: "openai", url: "http://localhost:1234", status: null, error: "", models: [] },
  ],
  gemini: {
    has_key: true,
    models: [{ id: "gemini-3.8-flash", vision: true, thinking: false, detail: "" }, { id: "gemini-3.8-flash-lite", vision: true, thinking: false, detail: "" }],
    default: "gemini-3.8-flash",
    fast: "gemini-3.8-flash-lite",
    error: "",
  },
  suggested: { read: null, cards: { backend: "ollama", url: "http://localhost:11434", model: "qwen3:8b" } },
};

describe("model choices", () => {
  it("lists running local models, then Gemini with hints", () => {
    const c = modelChoices(status);
    expect(c.map((x) => x.label)).toEqual(["qwen3:8b", "qwen2.5vl:7b", "gemini-3.8-flash", "gemini-3.8-flash-lite"]);
    expect(c[0].hint).toContain("thinking model");
    expect(c[2].hint).toContain("slow on the free tier");
    expect(modelChoices(status, "read").map((x) => x.label)).not.toContain("qwen3:8b");
  });

  it("keeps a saved model that's still available, else suggests one", () => {
    const ai = defaultAiSettings();
    expect(effectiveWriter(ai, status)?.model).toBe("qwen3:8b");
    const gemini = { backend: "gemini", url: "", model: "gemini-3.8-flash" };
    expect(effectiveWriter({ ...ai, writer: gemini }, status)).toEqual(gemini);
    const gone = { backend: "ollama", url: "http://localhost:11434", model: "removed:1b" };
    expect(effectiveWriter({ ...ai, writer: gone }, status)?.model).toBe("qwen3:8b");
    const noLocal = { ...status, runtimes: [], suggested: { read: null, cards: null } };
    expect(effectiveWriter(ai, noLocal)?.model).toBe("gemini-3.8-flash");
    expect(effectiveWriter(ai, null)).toBeNull();
  });
});

describe("generated cards", () => {
  it("maps onto exactly the deck's fields", () => {
    const [card] = toDeckCards([{ fields: { Front: "Q", Back: "A", Junk: "x" }, tags: ["source::ch8"], flags: { bare_latex: [] } }], [
      "Front",
      "Back",
      "Extra",
    ]);
    expect(card.fields).toEqual({ Front: "Q", Back: "A", Extra: "" });
    expect(card.tags).toEqual(["source::ch8"]);
  });

  it("flags LaTeX outside $…$", () => {
    expect(bareLatex("p_n(x) = \\frac{1}{K_n}")).toBe(true);
    expect(bareLatex("$\\frac{1}{2}$ and $$a^{2}$$")).toBe(false);
    expect(bareLatex("plain x_n")).toBe(false);
  });

  it("formats elapsed time", () => {
    expect(formatElapsed(42.4)).toBe("42s");
    expect(formatElapsed(125)).toBe("2m 05s");
  });
});

describe("settings migration", () => {
  it("adds AI defaults to older sessions and keeps saved choices", () => {
    expect(migrateSession({ version: 2, decks: [], settings: { theme: "dark" } }).settings.ai).toEqual(defaultAiSettings());
    const writer = { backend: "gemini", url: "", model: "g" };
    const s = migrateSession({ version: 2, decks: [], settings: { ai: { writer, density: "few" } } });
    expect(s.settings.ai.writer).toEqual(writer);
    expect(s.settings.ai.density).toBe("few");
    expect(s.settings.ai.focus).toBe("balanced");
  });
});

describe("reading pages", () => {
  it("picks a vision model to read with", () => {
    const ai = defaultAiSettings();
    expect(effectiveReader(ai, status)?.model).toBe("qwen2.5vl:7b");
    const withSuggestion = { ...status, suggested: { ...status.suggested, read: { backend: "ollama", url: "u", model: "x" } } };
    expect(effectiveReader(ai, withSuggestion)?.model).toBe("x");
    const textOnly = { ...status, runtimes: [{ ...status.runtimes[0], models: [status.runtimes[0].models[0]] }] };
    expect(effectiveReader(ai, textOnly)?.model).toBe("gemini-3.8-flash");
  });

  it("parses page ranges like the backend", () => {
    expect(parsePageRange("", 3)).toEqual([1, 2, 3]);
    expect(parsePageRange("1-2, 5, 2", 6)).toEqual([1, 2, 5]);
    expect(parsePageRange("4-", 6)).toEqual([4, 5, 6]);
    for (const bad of ["0", "3-1", "9", "a"]) expect(parsePageRange(bad, 6)).toBeNull();
  });
});
