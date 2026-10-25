import { useLayoutEffect, useRef } from "react";
import { Icon } from "./Icon";
import { MathPreview } from "./MathPreview";

interface Props {
  name: string;
  value: string;
  macros: Record<string, string>;
  onChange: (value: string) => void;
  cloze?: boolean;
  editableName?: boolean;
  onRename?: (name: string) => void;
  onRemove?: () => void;
  autoFocus?: boolean;
  placeholder?: string;
}

/** Wrap the textarea selection, keeping the cursor inside the new markup. */
function wrapSelection(el: HTMLTextAreaElement, before: string, after: string, onChange: (v: string) => void) {
  const { selectionStart: s, selectionEnd: e, value } = el;
  const next = value.slice(0, s) + before + value.slice(s, e) + after + value.slice(e);
  onChange(next);
  requestAnimationFrame(() => {
    el.focus();
    const pos = e === s ? s + before.length : e + before.length + after.length;
    el.setSelectionRange(pos, pos);
  });
}

function nextClozeNumber(text: string): number {
  const nums = [...text.matchAll(/\{\{c(\d+)::/g)].map((m) => Number(m[1]));
  return nums.length ? Math.max(...nums) + 1 : 1;
}

export function FieldInput({
  name,
  value,
  macros,
  onChange,
  cloze,
  editableName,
  onRename,
  onRemove,
  autoFocus,
  placeholder,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight + 2}px`;
  }, [value]);

  const insertMath = () => ref.current && wrapSelection(ref.current, "$", "$", onChange);
  const insertCloze = () =>
    ref.current && wrapSelection(ref.current, `{{c${nextClozeNumber(value)}::`, "}}", onChange);

  return (
    <div className="field">
      <div className="field-head">
        {editableName ? (
          <input
            className="field-name is-editable"
            defaultValue={name}
            aria-label="Field name"
            onBlur={(e) => {
              const v = e.target.value.trim();
              if (v && v !== name) onRename?.(v);
              else e.target.value = name;
            }}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          />
        ) : (
          <label className="field-name">{name}</label>
        )}
        <div className="field-tools">
          <button type="button" className="ghost-btn xs" title="Inline math (Ctrl+M)" onClick={insertMath}>
            $x$
          </button>
          {cloze && (
            <button type="button" className="ghost-btn xs" title="Cloze deletion (Ctrl+Shift+C)" onClick={insertCloze}>
              [ … ]
            </button>
          )}
          {onRemove && (
            <button type="button" className="icon-btn xs" title="Remove field" onClick={onRemove}>
              <Icon name="x" size={14} />
            </button>
          )}
        </div>
      </div>
      <textarea
        ref={ref}
        className="field-input"
        value={value}
        rows={2}
        spellCheck
        autoFocus={autoFocus}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === "m") {
            e.preventDefault();
            insertMath();
          } else if (cloze && e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "c") {
            e.preventDefault();
            insertCloze();
          }
        }}
      />
      <MathPreview text={value} macros={macros} className="field-preview" showErrors />
    </div>
  );
}
