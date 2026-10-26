import { describe, expect, it } from "vitest";
import { sanitizeHtml } from "./html";
import { renderField } from "./math";

describe("sanitizeHtml", () => {
  it("keeps simple formatting and escapes everything else", () => {
    expect(sanitizeHtml("<b>bold</b> <i class=x>it</i><br>")).toBe("<b>bold</b> <i>it</i><br>");
    expect(sanitizeHtml('<script>alert(1)</script><a href="x">l</a>')).toBe(
      '&lt;script&gt;alert(1)&lt;/script&gt;&lt;a href="x"&gt;l&lt;/a&gt;',
    );
    expect(sanitizeHtml("a < b && c &amp; d &nbsp;")).toBe("a &lt; b &amp;&amp; c &amp; d &nbsp;");
    expect(sanitizeHtml('<b onclick="x()">x</b>')).toBe("<b>x</b>");
  });

  it("turns media images into placeholders and drops unsafe sources", () => {
    expect(sanitizeHtml('<img src="wave.png" width="50">')).toBe('<img data-media="wave.png" alt="wave.png" width="50">');
    expect(sanitizeHtml('<img src="javascript:alert(1)">')).toBe("<img>");
    expect(sanitizeHtml('<img src="https://x/y.png" onerror="z()">')).toBe("<img>");
    expect(sanitizeHtml('<img src="../secret.png">')).toBe("<img>");
  });

  it("is what field previews use, alongside math and sounds", () => {
    const { html } = renderField("<b>E</b> = $mc^2$ [sound:a.mp3]", []);
    expect(html.startsWith("<b>E</b> = ")).toBe(true);
    expect(html).toContain("katex");
    expect(html).toContain('<span class="media-chip">♪ a.mp3</span>');
  });
});
