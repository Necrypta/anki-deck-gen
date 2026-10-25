import { describe, expect, it } from "vitest";
import { findAll } from "./FindTextarea";

describe("findAll", () => {
  it("finds every match, case-insensitively unless asked", () => {
    expect(findAll("Hermite hermite HERMITE", "hermite", false)).toEqual([0, 8, 16]);
    expect(findAll("Hermite hermite HERMITE", "hermite", true)).toEqual([8]);
    expect(findAll("aaaa", "aa", false)).toEqual([0, 2]);
    expect(findAll("abc", "", false)).toEqual([]);
    expect(findAll("$\\frac{d^2H}{dx^2}$", "\\frac", true)).toEqual([1]);
  });
});
