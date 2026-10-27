// A small allowlist sanitizer for field previews. Anki fields can hold HTML
// (bold, line breaks, images); the preview shows that subset and escapes the
// rest, so a stray "<" or a <script> is shown as text, never run.

const ALLOWED = new Set([
  "b", "strong", "i", "em", "u", "s", "sup", "sub", "small", "code", "pre", "br", "hr",
  "div", "p", "span", "ul", "ol", "li", "table", "thead", "tbody", "tr", "td", "th", "img",
]);
const VOID = new Set(["br", "hr", "img"]);
const IMG_ATTRS = new Set(["src", "alt", "width", "height"]);

const TAG = /<(\/?)([a-zA-Z][a-zA-Z0-9]*)\b((?:[^<>"']|"[^"]*"|'[^']*')*)>/g;
const ATTR = /([a-zA-Z-]+)\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'>]+))/g;

/** Escape text, but leave entities like &nbsp; or &amp; alone. */
export function escapeText(s: string): string {
  return s
    .replace(/&(?!(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);)/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

const escapeAttr = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** A media file name from the package (resolved later), never a link or script. */
const isMediaName = (src: string) => !!src && !/[\\/:]/.test(src) && !src.startsWith(".");

export function sanitizeHtml(s: string): string {
  let out = "";
  let last = 0;
  for (const m of s.matchAll(TAG)) {
    out += escapeText(s.slice(last, m.index));
    last = m.index! + m[0].length;
    const [, close, rawName, attrs] = m;
    const name = rawName.toLowerCase();
    if (!ALLOWED.has(name)) {
      out += escapeText(m[0]);
      continue;
    }
    if (close) {
      if (!VOID.has(name)) out += `</${name}>`;
      continue;
    }
    if (name !== "img") {
      out += `<${name}>`;
      continue;
    }
    let img = "<img";
    for (const a of attrs.matchAll(ATTR)) {
      const key = a[1].toLowerCase();
      const value = a[3] ?? a[4] ?? a[5] ?? "";
      if (!IMG_ATTRS.has(key)) continue;
      if (key !== "src") img += ` ${key}="${escapeAttr(value)}"`;
      else if (/^data:image\/[a-z+]+;base64,/i.test(value)) img += ` src="${escapeAttr(value)}"`;
      else if (isMediaName(value)) img += ` data-media="${escapeAttr(value)}" alt="${escapeAttr(value)}"`;
    }
    out += `${img}>`;
  }
  return out + escapeText(s.slice(last));
}
