import { useContext, useLayoutEffect, useMemo, useRef } from "react";
import { renderField } from "../lib/math";
import { MediaContext, resolveMedia } from "../lib/media";
import type { MacroDef } from "../types";

interface Props {
  text: string;
  macros: MacroDef[];
  className?: string;
  placeholder?: string;
  showErrors?: boolean;
}

export function MathPreview({ text, macros, className = "", placeholder, showErrors = false }: Props) {
  const { html, errors } = useMemo(() => renderField(text, macros), [text, macros]);
  const packageId = useContext(MediaContext);
  const ref = useRef<HTMLDivElement>(null);

  // Images from an opened .apkg are shown by file name; fill them in.
  useLayoutEffect(() => {
    if (packageId && ref.current) resolveMedia(ref.current, packageId);
  }, [html, packageId]);

  if (!text.trim()) {
    return placeholder ? <div className={`preview is-empty ${className}`}>{placeholder}</div> : null;
  }
  return (
    <>
      <div ref={ref} className={`preview ${className}`} dangerouslySetInnerHTML={{ __html: html }} />
      {showErrors && errors.length > 0 && <div className="field-error">{errors[0]}</div>}
    </>
  );
}
