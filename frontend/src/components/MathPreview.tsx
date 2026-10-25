import { useMemo } from "react";
import { renderField } from "../lib/math";

interface Props {
  text: string;
  macros: Record<string, string>;
  className?: string;
  placeholder?: string;
  showErrors?: boolean;
}

export function MathPreview({ text, macros, className = "", placeholder, showErrors = false }: Props) {
  const { html, errors } = useMemo(() => renderField(text, macros), [text, macros]);
  if (!text.trim()) {
    return placeholder ? <div className={`preview is-empty ${className}`}>{placeholder}</div> : null;
  }
  return (
    <>
      <div className={`preview ${className}`} dangerouslySetInnerHTML={{ __html: html }} />
      {showErrors && errors.length > 0 && <div className="field-error">{errors[0]}</div>}
    </>
  );
}
