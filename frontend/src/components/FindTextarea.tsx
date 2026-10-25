import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Icon } from "./Icon";

interface Props {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  /** Bump to open the find bar (the parent owns the Ctrl+F shortcut). */
  findSignal: number;
}

/** Start offsets of every match of ``query`` in ``text``. */
export function findAll(text: string, query: string, matchCase: boolean): number[] {
  if (!query) return [];
  const hay = matchCase ? text : text.toLowerCase();
  const needle = matchCase ? query : query.toLowerCase();
  const out: number[] = [];
  for (let i = hay.indexOf(needle); i !== -1; i = hay.indexOf(needle, i + needle.length)) out.push(i);
  return out;
}

/**
 * A textarea with a small find bar (Ctrl+F, Enter / Shift+Enter, Esc).
 * Matches are highlighted by a mirror layer drawn behind the transparent textarea,
 * since a textarea can't style parts of its own text.
 */
export function FindTextarea({ value, onChange, placeholder, className = "", findSignal }: Props) {
  const area = useRef<HTMLTextAreaElement>(null);
  const mirror = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [index, setIndex] = useState(0);
  const [focusTick, setFocusTick] = useState(0);

  const matches = useMemo(() => (open ? findAll(value, query, matchCase) : []), [open, value, query, matchCase]);
  const current = matches.length ? Math.min(index, matches.length - 1) : -1;

  // Open on Ctrl+F, seeded with the selected text.
  useEffect(() => {
    if (!findSignal) return;
    const el = area.current;
    const picked = el ? el.value.slice(el.selectionStart, el.selectionEnd) : "";
    if (picked && !picked.includes("\n") && picked.length < 80) {
      setQuery(picked);
      setIndex(0);
    }
    setOpen(true);
    setFocusTick((n) => n + 1);
  }, [findSignal]);

  // Focus the box once it's rendered (also when Ctrl+F is pressed again while open).
  useEffect(() => {
    if (!open || !focusTick) return;
    input.current?.focus();
    input.current?.select();
  }, [open, focusTick]);

  // Bring the current match into view.
  useLayoutEffect(() => {
    const el = area.current;
    const mark = mirror.current?.querySelector<HTMLElement>("mark.is-current");
    if (!el || !mark) return;
    const top = mark.offsetTop;
    if (top < el.scrollTop + 40 || top > el.scrollTop + el.clientHeight - 40) {
      el.scrollTop = Math.max(0, top - el.clientHeight / 2);
    }
    const left = mark.offsetLeft;
    if (left < el.scrollLeft || left + mark.offsetWidth > el.scrollLeft + el.clientWidth) {
      el.scrollLeft = Math.max(0, left - el.clientWidth / 3);
    }
    syncScroll();
  }, [current, matches]);

  const syncScroll = () => {
    if (area.current && mirror.current) {
      mirror.current.scrollTop = area.current.scrollTop;
      mirror.current.scrollLeft = area.current.scrollLeft;
    }
  };

  const step = (delta: number) => {
    if (!matches.length) return;
    setIndex((current + delta + matches.length) % matches.length);
  };

  const close = () => {
    setOpen(false);
    const el = area.current;
    if (!el) return;
    el.focus();
    // Leave the current match selected, so typing replaces it.
    if (current >= 0) el.setSelectionRange(matches[current], matches[current] + query.length);
  };

  const highlighted = useMemo(() => {
    if (!open || !matches.length) return null;
    const parts: React.ReactNode[] = [];
    let last = 0;
    matches.forEach((start, i) => {
      parts.push(value.slice(last, start));
      parts.push(
        <mark key={start} className={i === current ? "is-current" : ""}>
          {value.slice(start, start + query.length)}
        </mark>,
      );
      last = start + query.length;
    });
    parts.push(value.slice(last));
    return parts;
  }, [open, matches, current, value, query]);

  return (
    <div className={`find-wrap ${className}`}>
      <div ref={mirror} className="find-mirror import-text" aria-hidden="true">
        {highlighted}
        {"\n "}
      </div>
      <textarea
        ref={area}
        className="import-text find-area"
        value={value}
        spellCheck={false}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onScroll={syncScroll}
      />
      {open && (
        <div className="find-bar" role="search">
          <input
            ref={input}
            value={query}
            placeholder="Find"
            aria-label="Find in text"
            spellCheck={false}
            onChange={(e) => {
              setQuery(e.target.value);
              setIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === "F3") {
                e.preventDefault();
                step(e.shiftKey ? -1 : 1);
              } else if (e.key === "Escape") {
                e.preventDefault();
                close();
              }
            }}
          />
          <span className={`find-count ${query && !matches.length ? "is-none" : ""}`}>
            {query ? (matches.length ? `${current + 1}/${matches.length}` : "0/0") : ""}
          </span>
          <button
            type="button"
            className={`find-btn ${matchCase ? "is-on" : ""}`}
            title="Match case"
            aria-pressed={matchCase}
            onClick={() => setMatchCase(!matchCase)}
          >
            Aa
          </button>
          <button type="button" className="find-btn" title="Previous (Shift+Enter)" onClick={() => step(-1)} disabled={!matches.length}>
            <Icon name="up" size={14} />
          </button>
          <button type="button" className="find-btn" title="Next (Enter)" onClick={() => step(1)} disabled={!matches.length}>
            <Icon name="down" size={14} />
          </button>
          <button type="button" className="find-btn" title="Close (Esc)" onClick={close}>
            <Icon name="x" size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
