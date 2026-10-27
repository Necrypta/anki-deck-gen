import { useState } from "react";
import type { DuplicateMatch } from "../lib/duplicates";
import type { MacroDef } from "../types";
import { MathPreview } from "./MathPreview";

/** "Already in the deck", "Same as card 4 above", … */
export function duplicateLabel(m: DuplicateMatch): string {
  if (m.where === "deck") return m.kind === "same" ? "Already in the deck" : "Very similar to a card in the deck";
  return `${m.kind === "same" ? "Same as" : "Very similar to"} card ${m.index + 1} above`;
}

interface Props {
  match: DuplicateMatch;
  other: { fields: Record<string, string> };
  fields: string[];
  macros: MacroDef[];
  keepLabel?: string;
  onKeepBoth?: () => void;
  onKeepThis?: () => void;
}

/** The card this one seems to repeat, with ways to keep it anyway. */
export function DuplicateBox({ match, other, fields, macros, keepLabel = "Keep both", onKeepBoth, onKeepThis }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mismatch duplicate">
      <div className="mismatch-head">
        <span className="flag">{duplicateLabel(match)}</span>
        <span className="duplicate-actions">
          <button type="button" className="link-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "Hide" : "Compare"}
          </button>
          {onKeepThis && (
            <button type="button" className="link-btn" onClick={onKeepThis}>
              Keep this one instead
            </button>
          )}
          {onKeepBoth && (
            <button type="button" className="link-btn" onClick={onKeepBoth}>
              {keepLabel}
            </button>
          )}
        </span>
      </div>
      {open && (
        <div className="mismatch-source">
          <span className="review-label">{match.where === "deck" ? "In the deck" : `Card ${match.index + 1}`}</span>
          {fields.map((f, fi) =>
            other.fields[f]?.trim() ? (
              <div key={f} className={fi === 0 ? "review-front" : "review-back"}>
                <MathPreview text={other.fields[f]} macros={macros} />
              </div>
            ) : null,
          )}
        </div>
      )}
    </div>
  );
}
