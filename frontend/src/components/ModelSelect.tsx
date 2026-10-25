import { modelChoices, refKey } from "../lib/ai";
import type { AiStatus, ModelRef } from "../types";

interface Props {
  status: AiStatus | null;
  value: ModelRef | null;
  onChange: (ref: ModelRef) => void;
  label?: string;
  /** "read" lists only models that can read images. */
  stage?: "cards" | "read";
}

/** A model picker grouped by where the model runs. */
export function ModelSelect({ status, value, onChange, label = "Model", stage = "cards" }: Props) {
  const choices = modelChoices(status, stage);
  const groups = [...new Set(choices.map((c) => c.group))];
  const current = refKey(value);
  const known = choices.some((c) => refKey(c.ref) === current);

  return (
    <select
      className="model-select"
      aria-label={label}
      value={current}
      disabled={!choices.length}
      onChange={(e) => {
        const pick = choices.find((c) => refKey(c.ref) === e.target.value);
        if (pick) onChange(pick.ref);
      }}
    >
      {!choices.length && <option value="">{status ? (stage === "read" ? "No vision models available" : "No models available") : "Checking…"}</option>}
      {value && !known && choices.length > 0 && <option value={current}>{value.model} (not available)</option>}
      {groups.map((g) => (
        <optgroup key={g} label={g}>
          {choices
            .filter((c) => c.group === g)
            .map((c) => (
              <option key={refKey(c.ref)} value={refKey(c.ref)}>
                {c.label}
                {c.hint ? ` — ${c.hint}` : ""}
              </option>
            ))}
        </optgroup>
      ))}
    </select>
  );
}
