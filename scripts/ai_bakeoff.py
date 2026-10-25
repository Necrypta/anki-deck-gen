"""Compare local (and optionally Gemini) models on your own study material.

Each "reading" model transcribes the chosen pages into Markdown + LaTeX, then
each "card" model writes flashcards from one transcription. The results go
into an HTML report with the page images, rendered output, timings and how
much of each Ollama model fitted on the GPU.

    ai-bakeoff.exe chapter.pdf --pages 12-13
    python scripts/ai_bakeoff.py chapter.pdf --pages 12-13 --read qwen2.5vl:7b --cards qwen3:8b
    python scripts/ai_bakeoff.py --list        # show runtimes, models and suggestions

Models are ``[runtime/]model``; the runtime defaults to ollama. Runtimes:
ollama, lmstudio, llamacpp, jan, openai (needs --openai URL), gemini (needs a
key via --gemini-key or GEMINI_API_KEY; ``gemini/auto`` picks the newest Flash). For example ``lmstudio/qwen/qwen2.5-vl-7b``.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ankigen.ai.cards import bare_latex, card_schema, parse_cards
from ankigen.ai.http import AiError, request_json
from ankigen.ai.prompts import (
    READ_SYSTEM,
    card_messages,
    is_ocr_model,
    read_messages,
    read_pdf_user,
)
from ankigen.ai.providers import (
    GEMINI_URL,
    ModelInfo,
    Provider,
    detect_local,
    make_provider,
    newest_gemini,
)
from ankigen.ai.sources import (
    Page,
    load_image,
    load_pdf,
    parse_page_range,
    pdf_page_count,
    pdf_subset,
    source_kind,
)
from ankigen.ai.text import clean_markdown, collapse_repeats, split_page_marks, strip_special_tokens
from ankigen.latex import DEFAULT_MACROS

# Candidates for an 8 GB GPU. Tags change over time: missing ones are skipped
# and listed with the command to download them.
SUGGESTED_READ = [
    ("qwen2.5vl:7b", "Qwen2.5-VL 7B: best so far, fast and clean LaTeX"),
    ("minicpm-v:8b", "MiniCPM-V 8B: good OCR for its size"),
    ("gemma3:4b", "Gemma 3 4B: small and fast"),
    ("deepseek-ocr", "DeepSeek-OCR 3B: very fast, but can loop or leak tokens (experimental)"),
]
# qwen3-vl:8b is left out: its default tag thinks for minutes per page and
# returns nothing. An "-instruct" tag may work if you want to try it.
SUGGESTED_CARDS = [
    ("qwen3:8b", "Qwen3 8B: best so far, fast and accurate (thinking switched off)"),
    ("deepseek-r1:8b", "DeepSeek-R1 8B: always thinks (minutes), often drops the $...$"),
    ("llama3.1:8b", "Llama 3.1 8B"),
    ("gemma3:4b", "Gemma 3 4B: small and fast"),
    ("phi4-mini", "Phi-4-mini 3.8B: small, decent at maths"),
]
RUNTIME_URLS = {
    "ollama": ("ollama", "http://localhost:11434", "Ollama"),
    "lmstudio": ("openai", "http://localhost:1234", "LM Studio"),
    "llamacpp": ("openai", "http://localhost:8080", "llama.cpp"),
    "jan": ("openai", "http://localhost:1337", "Jan"),
    "openai": ("openai", "", "OpenAI-compatible"),
    "gemini": ("gemini", GEMINI_URL, "Gemini"),
}
MAX_DEFAULT_MODELS = 6
FIELDS = ["Front", "Back"]


@dataclass
class Model:
    runtime: str
    id: str
    provider: Provider

    @property
    def label(self) -> str:
        return self.id if self.runtime == "ollama" else f"{self.runtime}/{self.id}"


class Runtimes:
    """Lazily created providers, keyed by runtime name."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self._providers: dict[str, Provider] = {}
        self._models: dict[str, list[ModelInfo]] = {}
        self.retries = 0

    def provider(self, runtime: str) -> Provider:
        if runtime not in RUNTIME_URLS:
            raise SystemExit(f"Unknown runtime {runtime!r}; use one of {', '.join(RUNTIME_URLS)}")
        if runtime not in self._providers:
            kind, url, name = RUNTIME_URLS[runtime]
            url = getattr(self.args, runtime, None) or url
            kw: dict = {}
            if runtime == "gemini":
                kw["api_key"] = self.args.gemini_key or ""
            elif runtime == "openai":
                if not url:
                    raise SystemExit("openai/... models need --openai URL")
                kw["api_key"] = self.args.openai_key
            if runtime == "ollama":
                kw["num_ctx"] = self.args.num_ctx
            provider = make_provider(kind, url, name, **kw)
            provider.on_retry = self._retrying
            self._providers[runtime] = provider
        return self._providers[runtime]

    def _retrying(self, status: int, seconds: float) -> None:
        self.retries += 1
        why = "rate limited" if status == 429 else f"server busy (HTTP {status})"
        print(f"[{why}, waiting {seconds:.0f}s] ", end="", flush=True)

    def models(self, runtime: str) -> list[ModelInfo]:
        if runtime not in self._models:
            try:
                self._models[runtime] = self.provider(runtime).list_models()
            except AiError:
                self._models[runtime] = []
        return self._models[runtime]

    def parse(self, spec: str) -> Model:
        runtime, _, rest = spec.partition("/")
        if rest and runtime in RUNTIME_URLS:
            if runtime == "gemini" and rest == "auto":
                rest = default_gemini(self.models("gemini")) or "auto"
                print(f"gemini/auto -> gemini/{rest}")
            return Model(runtime, rest, self.provider(runtime))
        return Model("ollama", spec, self.provider("ollama"))


def _matches(installed: str, tag: str) -> bool:
    return installed == tag or installed == f"{tag}:latest" or installed.split(":")[0] == tag


def default_gemini(models: list[ModelInfo]) -> str | None:
    return newest_gemini([m.id for m in models])


def pick_defaults(rt: Runtimes, stage: str) -> list[Model]:
    """Installed models worth trying, suggested ones first."""
    suggested = [t for t, _ in (SUGGESTED_READ if stage == "read" else SUGGESTED_CARDS)]
    installed = rt.models("ollama")
    if stage == "read":
        pool = [m for m in installed if m.vision]
    else:
        pool = [m for m in installed if not is_ocr_model(m.id)]
    ranked = sorted(
        pool,
        key=lambda m: next(
            (i for i, t in enumerate(suggested) if _matches(m.id, t)), len(suggested)
        ),
    )
    chosen = [Model("ollama", m.id, rt.provider("ollama")) for m in ranked[:MAX_DEFAULT_MODELS]]
    if rt.args.gemini_key:
        g = default_gemini(rt.models("gemini"))
        if g:
            chosen.append(Model("gemini", g, rt.provider("gemini")))
    return chosen


def print_suggestions(rt: Runtimes) -> None:
    installed = [m.id for m in rt.models("ollama")]
    for title, items in (("Reading pages", SUGGESTED_READ), ("Writing cards", SUGGESTED_CARDS)):
        print(f"\n  {title}:")
        for tag, note in items:
            have = any(_matches(i, tag) for i in installed)
            print(f"    [{'x' if have else ' '}] {tag:<18} {note}")
    missing = sorted(
        {
            t
            for t, _ in SUGGESTED_READ + SUGGESTED_CARDS
            if not any(_matches(i, t) for i in installed)
        }
    )
    if missing:
        print("\n  To download the missing ones (about 3-6 GB each):")
        for t in missing:
            print(f"    ollama pull {t}")


def cmd_list(rt: Runtimes) -> None:
    print("Local AI runtimes:")
    candidates = [
        (name, kind, getattr(rt.args, key) or url)
        for key, (kind, url, name) in RUNTIME_URLS.items()
        if kind != "gemini" and (url or getattr(rt.args, key))
    ]
    for d in detect_local(candidates):
        state = d.status or "not running"
        print(f"  {d.provider.name:<10} {d.provider.base_url:<26} {state}")
        if d.status:
            for m in d.provider.list_models():
                tags = [t for t, on in (("vision", m.vision), ("thinking", m.thinking)) if on]
                print(f"      {m.id:<40} {m.detail:<28} {' '.join(tags)}")
    if rt.args.gemini_key:
        print(
            "\nGemini models:",
            ", ".join(m.id for m in rt.models("gemini")) or "none (check the key)",
        )
    print("\nSuggested for an 8 GB GPU ([x] = installed):")
    print_suggestions(rt)
    gpu = gpu_info()
    if gpu:
        print(f"\nGPU: {gpu}")


def gpu_info() -> str:
    if not shutil.which("nvidia-smi"):
        return ""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def gpu_share(model: Model) -> float | None:
    """Fraction of an Ollama model held in VRAM (1.0 = fully on the GPU)."""
    if model.runtime != "ollama":
        return None
    try:
        loaded = (
            request_json(f"{model.provider.base_url}/api/ps", timeout=5, retries=0).get("models")
            or []
        )
    except AiError:
        return None
    for m in loaded:
        if m.get("name") == model.id or m.get("model") == model.id:
            size = m.get("size") or 0
            return (m.get("size_vram") or 0) / size if size else None
    return None


def thumb(png: bytes, width: int = 760) -> str:
    from PIL import Image

    with Image.open(io.BytesIO(png)) as img:
        img = img.convert("RGB")
        img.thumbnail((width, width * 2))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=72)
    return base64.b64encode(buf.getvalue()).decode()


def _page_record(r, text: str, seconds: float) -> dict:
    issues = []
    if collapse_repeats(strip_special_tokens(text))[1]:
        issues.append("looped")
    if strip_special_tokens(text) != text:
        issues.append("leaked tokens")
    if r.truncated:
        issues.append("hit token limit")
    tps = r.tokens_per_second
    return {
        "text": clean_markdown(text),
        "seconds": round(seconds, 1),
        "tokens": r.output_tokens,
        "thinking_tokens": r.thinking_tokens,
        "tps": round(tps, 1) if tps else None,
        "issues": issues,
    }


def run_read(rt: Runtimes, models: list[Model], pages: list[Page], pdf: Path | None) -> list[dict]:
    results = []
    for model in models:
        print(f"\n> Reading with {model.label}")
        system, user = read_messages(model.id)
        rec: dict = {"model": model.label, "pages": {}, "load": 0.0}
        retries_before = rt.retries
        if model.runtime == "gemini" and pdf is not None:
            # Gemini reads PDFs natively: one request for all pages, as the app will do.
            numbers = [p.number for p in pages]
            print(f"    pages {numbers[0]}-{numbers[-1]} in one request ... ", end="", flush=True)
            try:
                r = model.provider.chat(
                    model.id,
                    read_pdf_user(numbers),
                    system=READ_SYSTEM,
                    pdf=pdf_subset(pdf, numbers),
                    temperature=0.0,
                )
            except AiError as e:
                print(f"failed: {e}")
                rec["pages"] = {n: {"error": str(e)} for n in numbers}
            else:
                print(f"{r.seconds:.1f}s")
                rec["whole_pdf"] = round(r.seconds, 1)
                for n, text in split_page_marks(r.text, numbers).items():
                    rec["pages"][n] = _page_record(r, text, r.seconds / len(numbers))
                    rec["pages"][n]["tokens"] = None  # only known for the whole request
        else:
            for page in pages:
                print(f"    page {page.number} ... ", end="", flush=True)
                try:
                    r = model.provider.chat(
                        model.id, user, system=system, images=[page.image], temperature=0.0
                    )
                except AiError as e:
                    print(f"failed: {e}")
                    rec["pages"][page.number] = {"error": str(e)}
                    continue
                rec["load"] += r.load_seconds
                rec["pages"][page.number] = _page_record(r, r.text, r.seconds)
                issues = rec["pages"][page.number]["issues"]
                note = f" ({', '.join(issues)})" if issues else ""
                tps = r.tokens_per_second
                print(f"{r.seconds:.1f}s" + (f", {tps:.0f} tok/s" if tps else "") + note)
        rec["retries"] = rt.retries - retries_before
        rec["gpu"] = gpu_share(model)
        ok = [p for p in rec["pages"].values() if "error" not in p]
        rec["avg_seconds"] = round(sum(p["seconds"] for p in ok) / len(ok), 1) if ok else None
        speeds = [p["tps"] for p in ok if p["tps"]]
        rec["avg_tps"] = round(sum(speeds) / len(speeds), 1) if speeds else None
        rec["load"] = round(rec["load"], 1)
        results.append(rec)
    return results


def run_cards(rt: Runtimes, models: list[Model], material: str) -> list[dict]:
    system, user = card_messages(material, FIELDS, macros=DEFAULT_MACROS)
    schema = card_schema(FIELDS)
    results = []
    for model in models:
        print(f"\n> Writing cards with {model.label} ... ", end="", flush=True)
        rec: dict = {"model": model.label}
        retries_before = rt.retries
        try:
            r = model.provider.chat(model.id, user, system=system, schema=schema, temperature=0.3)
        except AiError as e:
            print(f"failed: {e}")
            rec["error"] = str(e)
            results.append(rec)
            continue
        tps = r.tokens_per_second
        rec.update(
            seconds=round(r.seconds, 1),
            load=round(r.load_seconds, 1),
            tokens=r.output_tokens,
            tps=round(tps, 1) if tps else None,
            raw=r.text,
            gpu=gpu_share(model),
            thinking_tokens=r.thinking_tokens,
        )
        try:
            rec["cards"] = parse_cards(r.text, FIELDS, DEFAULT_MACROS)
            rec["json_ok"] = True
            rec["bare_latex"] = sum(any(bare_latex(v) for v in c.values()) for c in rec["cards"])
        except ValueError as e:
            rec["cards"], rec["json_ok"], rec["error"] = [], False, str(e)
        rec["retries"] = rt.retries - retries_before
        print(
            f"{len(rec['cards'])} cards in {r.seconds:.1f}s"
            + ("" if rec["json_ok"] else " (bad JSON)")
        )
        results.append(rec)
    return results


def pick_card_input(choice: str, pages: list[Page], reads: list[dict]) -> tuple[str, str]:
    def from_read(rec: dict) -> str:
        return "\n\n".join(
            p.get("text", "") for _, p in sorted(rec["pages"].items()) if "text" in p
        )

    text_layer = "\n\n".join(p.text.strip() for p in pages if p.text.strip())
    if choice == "text":
        return "PDF text layer", text_layer
    if choice != "auto":
        for rec in reads:
            if rec["model"] == choice:
                return f"transcription by {choice}", from_read(rec)
        raise SystemExit(f"--card-input {choice!r} isn't one of the reading models")
    usable = [r for r in reads if from_read(r).strip()]
    usable.sort(key=lambda r: not r["model"].startswith("gemini/"))  # Gemini is the reference
    if usable:
        return f"transcription by {usable[0]['model']}", from_read(usable[0])
    return "PDF text layer", text_layer


def summary_table(reads: list[dict], cards: list[dict]) -> str:
    def f(v, unit=""):
        return "–" if v is None else f"{v:.0%}" if unit == "%" else f"{v}{unit}"

    rows = [
        "| Stage | Model | s/page or s | tok/s | Load | On GPU | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in reads:
        errs = sum(1 for p in r["pages"].values() if "error" in p)
        res = f"{len(r['pages']) - errs}/{len(r['pages'])} pages"
        issues = sorted({i for p in r["pages"].values() for i in p.get("issues", [])})
        if issues:
            res += f" ({', '.join(issues)})"
        if r.get("whole_pdf") is not None:
            res += f", one request ({r['whole_pdf']}s)"
        thinking = sum(p.get("thinking_tokens") or 0 for p in r["pages"].values())
        if thinking and r.get("whole_pdf") is None:
            res += f", {thinking} thinking tokens"
        elif r.get("whole_pdf") is not None:
            first = next(iter(r["pages"].values()), {})
            if first.get("thinking_tokens"):
                res += f", {first['thinking_tokens']} thinking tokens"
        if r.get("retries"):
            res += f", {r['retries']} rate-limit waits"
        if errs:
            first = next(p["error"] for p in r["pages"].values() if "error" in p)
            res += f": {first[:120]}"
        rows.append(
            f"| read | {r['model']} | {f(r['avg_seconds'])} | {f(r['avg_tps'])} | {f(r['load'], 's')} "
            f"| {f(r.get('gpu'), '%')} | {res} |"
        )
    for c in cards:
        res = (
            c.get("error")
            if "seconds" not in c
            else (
                f"{len(c['cards'])} cards"
                + ("" if c.get("json_ok") else ", bad JSON")
                + (f", {c['bare_latex']} with math outside $" if c.get("bare_latex") else "")
                + (f", {c['thinking_tokens']} thinking tokens" if c.get("thinking_tokens") else "")
                + (f", {c['retries']} rate-limit waits" if c.get("retries") else "")
            )
        )
        rows.append(
            f"| cards | {c['model']} | {f(c.get('seconds'))} | {f(c.get('tps'))} | {f(c.get('load'), 's')} "
            f"| {f(c.get('gpu'), '%')} | {res} |"
        )
    return "\n".join(rows)


def katex_macros() -> dict[str, str]:
    """The default macros for KaTeX, which can't do optional arguments: the
    report rewrites ``\\dv[2]`` to ``\\dvOPT{2}`` and ``\\dv`` alone gets the default."""
    out = {}
    for m in DEFAULT_MACROS:
        body = m.body
        if m.optional is not None:
            out[m.name + "OPT"] = body
            body = body.replace("#1", m.optional)
            for i in range(2, m.args + 1):
                body = body.replace(f"#{i}", f"#{i - 1}")
        out[m.name] = body
    return out


def write_report(out_dir: Path, data: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in data.items() if k != "images"}
    (out_dir / "results.json").write_text(json.dumps(slim, indent=2, ensure_ascii=False), "utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = REPORT_HTML.replace("__DATA__", payload).replace(
        "__TITLE__", html.escape(data["source"])
    )
    path = out_dir / "report.html"
    path.write_text(page, "utf-8")
    return path


def interactive_args() -> list[str]:
    """Double-clicked exe: ask for the essentials instead of failing."""
    print("Anki Deck Generator · local AI bake-off\n")
    print("Drag a PDF or image onto this window (or type its path), then press Enter.")
    print("Leave it empty to just list your runtimes and models.\n")
    path = input("File: ").strip().strip('"')
    if not path:
        return ["--list"]
    argv = [path]
    if source_kind(path) == "pdf":
        pages = input("Pages to test, e.g. 12-13 (fewer is faster) [1-2]: ").strip() or "1-2"
        argv += ["--pages", pages]
    key = input("Gemini API key to include as a reference (optional, Enter to skip): ").strip()
    if key:
        argv += ["--gemini-key", key]
    return argv


def main(argv: list[str] | None = None) -> int:
    interactive = argv is None and getattr(sys, "frozen", False) and len(sys.argv) == 1
    if interactive:
        argv = interactive_args()
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("source", nargs="?", help="PDF, image, .txt or .md file")
    p.add_argument("--pages", help="PDF pages, e.g. 12-13 or 3,5 (default: first 2)")
    p.add_argument(
        "--read",
        nargs="+",
        metavar="MODEL",
        help="reading models (default: installed vision models)",
    )
    p.add_argument(
        "--cards", nargs="+", metavar="MODEL", help="card models (default: installed models)"
    )
    p.add_argument(
        "--skip-read", action="store_true", help="use the PDF text layer instead of reading pages"
    )
    p.add_argument("--skip-cards", action="store_true")
    p.add_argument("--card-input", default="auto", help="auto, text, or a reading model's name")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument(
        "--num-ctx",
        type=int,
        default=6144,
        help="Ollama context size; 6144 kept qwen2.5vl:7b fully on an 8 GB GPU",
    )
    p.add_argument("--out", type=Path, help="report folder (default: bakeoff-<time> here)")
    p.add_argument("--list", action="store_true", help="list runtimes, models and suggestions")
    p.add_argument("--no-open", action="store_true", help="don't open the report when done")
    for rt in ("ollama", "lmstudio", "llamacpp", "jan", "openai", "gemini"):
        p.add_argument(f"--{rt}", metavar="URL", help=f"{rt} server URL")
    p.add_argument("--openai-key")
    p.add_argument("--gemini-key", default=os.environ.get("GEMINI_API_KEY"))
    args = p.parse_args(argv)
    rt = Runtimes(args)

    try:
        if args.list or not args.source:
            cmd_list(rt)
            return 0
        return run(args, rt)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    finally:
        if interactive:
            input("\nPress Enter to close.")


def run(args: argparse.Namespace, rt: Runtimes) -> int:
    src = Path(args.source)
    kind = source_kind(src)
    if kind == "pdf":
        count = pdf_page_count(src)
        numbers = parse_page_range(args.pages or f"1-{min(2, count)}", count)
        pages = load_pdf(src, numbers, dpi=args.dpi)
    elif kind == "image":
        pages = [load_image(src)]
    else:
        pages = [Page(1, src.read_text("utf-8", "replace"))]
    print(f"{src.name}: {len(pages)} page(s)")

    readers: list[Model] = []
    if kind != "text" and not args.skip_read:
        readers = [rt.parse(m) for m in args.read] if args.read else pick_defaults(rt, "read")
    writers: list[Model] = []
    if not args.skip_cards:
        writers = [rt.parse(m) for m in args.cards] if args.cards else pick_defaults(rt, "cards")

    if not readers and not writers:
        print("\nNo models to test. Is Ollama running? Suggested models:")
        print_suggestions(rt)
        return 1
    print("Reading models:", ", ".join(m.label for m in readers) or "none")
    print("Card models:   ", ", ".join(m.label for m in writers) or "none")
    if not args.read and not args.cards:
        print_suggestions(rt)

    started = time.monotonic()
    reads = run_read(rt, readers, pages, src if kind == "pdf" else None)
    source_label, material = pick_card_input(args.card_input, pages, reads)
    cards = run_cards(rt, writers, material) if writers and material.strip() else []

    data = {
        "source": src.name,
        "created": dt.datetime.now().astimezone().isoformat(timespec="minutes"),
        "machine": {"os": platform.platform(), "gpu": gpu_info()},
        "minutes": round((time.monotonic() - started) / 60, 1),
        "pages": [pg.number for pg in pages],
        "images": {pg.number: thumb(pg.image) for pg in pages if pg.image},
        "text_layer": {pg.number: pg.text for pg in pages},
        "read": reads,
        "card_input": {"from": source_label, "text": material},
        "cards": cards,
        "macros": katex_macros(),
    }
    out = args.out or Path.cwd() / f"bakeoff-{dt.datetime.now().astimezone():%Y%m%d-%H%M}"
    report = write_report(out, data)
    table = summary_table(reads, cards)
    (out / "summary.md").write_text(table + "\n", "utf-8")
    print("\n" + table)
    print(f"\nReport: {report}\nPaste the table above (or summary.md) back to Claude to compare.")
    if not args.no_open:
        webbrowser.open(report.as_uri())
    return 0


REPORT_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bake-off · __TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/mhchem.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<style>
:root{--bg:#f7f7f8;--panel:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e3e3e6;--accent:#4f6bed;--bad:#c4314b}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--panel:#1f1f22;--text:#ececef;--muted:#9a9aa1;--line:#2e2e33;--accent:#8ea2ff;--bad:#ff6b81}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,"Segoe UI",sans-serif}
main{max-width:1500px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 12px}
.muted{color:var(--muted)}table{border-collapse:collapse;width:100%;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;font-variant-numeric:tabular-nums}th{font-weight:600;font-size:13px;color:var(--muted)}
.grid{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(380px,1fr);gap:12px;overflow-x:auto;padding-bottom:8px}
.col{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;min-width:0}
.col h3{font-size:14px;margin:0 0 6px;display:flex;justify-content:space-between;gap:8px}.col img{width:100%;border-radius:6px;border:1px solid var(--line)}
.out{overflow-x:auto}.out pre{white-space:pre-wrap;font-size:12.5px}.bad{color:var(--bad)}
.card{border-top:1px solid var(--line);padding:8px 0}.card .q{font-weight:600}.card .a{margin-top:2px}
.tabs button{font:inherit;border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:6px;padding:2px 8px;margin-left:4px;cursor:pointer}
.tabs button[aria-pressed=true]{border-color:var(--accent);color:var(--accent)}.katex-error{color:var(--bad)!important}
</style></head><body><main id="app"></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const MATH = /\$\$[\s\S]+?\$\$|\$(?:\\\$|[^$\n])+?\$/g;
const OPT = Object.keys(D.macros).filter(k => k.endsWith("OPT")).map(k => k.slice(0, -3));
function opt(s) {
  for (const name of OPT) s = s.split(name + "[").join(name + "OPT[").replace(new RegExp(name.replace("\\", "\\\\") + "OPT\\[([^\\]]*)\\]", "g"), (_, n) => name + "OPT{" + n + "}");
  return s;
}
function md(src) {
  const math = [];
  const safe = opt(String(src || "")).replace(MATH, m => { math.push(m); return `@@M${math.length - 1}@@`; });
  const out = window.marked ? marked.parse(safe) : `<pre>${esc(safe)}</pre>`;
  return out.replace(/@@M(\d+)@@/g, (_, i) => esc(math[i]));
}
const fmt = (v, u = "") => v == null ? "–" : u === "%" ? Math.round(v * 100) + "%" : v + u;
function render() {
  const app = document.getElementById("app");
  let h = `<h1>${esc(D.source)}</h1><div class="muted">${esc(D.created)} · ${esc(D.machine.gpu || D.machine.os)} · ${D.minutes} min · pages ${D.pages.join(", ")}</div>`;
  h += `<h2>Summary</h2><table><tr><th>Stage</th><th>Model</th><th>Seconds (per page)</th><th>Tokens/s</th><th>Load</th><th>On GPU</th><th>Result</th><th>Math errors</th></tr>`;
  D.read.forEach((r, i) => { const n = Object.keys(r.pages).length, bad = Object.values(r.pages).filter(p => p.error).length, iss = [...new Set(Object.values(r.pages).flatMap(p => p.issues || []))];
    h += `<tr><td>read</td><td>${esc(r.model)}</td><td>${fmt(r.avg_seconds)}</td><td>${fmt(r.avg_tps)}</td><td>${fmt(r.load, "s")}</td><td>${fmt(r.gpu, "%")}</td><td>${n - bad}/${n} pages${iss.length ? ` <span class="bad">${esc(iss.join(", "))}</span>` : ""}</td><td id="err-r${i}">…</td></tr>`; });
  D.cards.forEach((c, i) => { const res = c.seconds == null ? `<span class="bad">${esc(c.error)}</span>` : `${c.cards.length} cards${c.json_ok ? "" : ' <span class="bad">bad JSON</span>'}${c.bare_latex ? ` <span class="bad">${c.bare_latex} with math outside $</span>` : ""}`;
    h += `<tr><td>cards</td><td>${esc(c.model)}</td><td>${fmt(c.seconds)}</td><td>${fmt(c.tps)}</td><td>${fmt(c.load, "s")}</td><td>${fmt(c.gpu, "%")}</td><td>${res}</td><td id="err-c${i}">…</td></tr>`; });
  h += `</table><p class="muted">"On GPU" below 100% means part of the model spilled into system RAM, which is much slower. Load = time to load the model into memory (once).</p>`;
  if (D.read.length) {
    h += `<h2>Reading: page → Markdown</h2>`;
    for (const n of D.pages) {
      h += `<h3>Page ${n}</h3><div class="grid">`;
      if (D.images[n]) h += `<div class="col"><h3>Original</h3><img src="data:image/jpeg;base64,${D.images[n]}" alt="Page ${n}"></div>`;
      D.read.forEach((r, i) => { const p = r.pages[n] || {};
        h += `<div class="col" data-r="${i}"><h3><span>${esc(r.model)}</span><span class="muted">${p.seconds != null ? p.seconds + "s" : ""}</span></h3>`;
        h += p.error ? `<div class="bad">${esc(p.error)}</div>` : `<div class="tabs"><button aria-pressed="true" data-v="r">Rendered</button><button aria-pressed="false" data-v="s">Source</button></div><div class="out" data-src="${esc(p.text)}">${md(p.text)}</div>`;
        h += `</div>`; });
      h += `</div>`;
    }
  }
  if (D.cards.length) {
    h += `<h2>Cards</h2><p class="muted">All card models got the same input: ${esc(D.card_input.from)}.</p><div class="grid">`;
    D.cards.forEach((c, i) => {
      h += `<div class="col" data-c="${i}"><h3><span>${esc(c.model)}</span><span class="muted">${c.seconds != null ? c.seconds + "s" : ""}</span></h3>`;
      if (c.error && !(c.cards || []).length) h += `<div class="bad">${esc(c.error)}</div>` + (c.raw ? `<pre>${esc(c.raw)}</pre>` : "");
      for (const k of c.cards || []) h += `<div class="card"><div class="q">${esc(opt(k.Front))}</div><div class="a">${esc(opt(k.Back)).replace(/\n/g, "<br>")}</div></div>`;
      h += `</div>`; });
    h += `</div><details><summary class="muted">Card input text</summary><pre>${esc(D.card_input.text)}</pre></details>`;
  }
  app.innerHTML = h;
  const opts = {delimiters: [{left: "$$", right: "$$", display: true}, {left: "$", right: "$", display: false}], throwOnError: false, strict: "ignore", macros: {...D.macros}};
  if (window.renderMathInElement) renderMathInElement(app, opts);
  D.read.forEach((_, i) => { document.getElementById(`err-r${i}`).textContent = app.querySelectorAll(`[data-r="${i}"] .katex-error`).length; });
  D.cards.forEach((_, i) => { document.getElementById(`err-c${i}`).textContent = app.querySelectorAll(`[data-c="${i}"] .katex-error`).length; });
  app.addEventListener("click", e => {
    const b = e.target.closest(".tabs button"); if (!b) return;
    const col = b.closest(".col"), out = col.querySelector(".out");
    col.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-pressed", x === b));
    if (b.dataset.v === "s") out.innerHTML = `<pre>${esc(out.dataset.src)}</pre>`;
    else { out.innerHTML = md(out.dataset.src); if (window.renderMathInElement) renderMathInElement(out, opts); }
  });
}
window.addEventListener("load", render);
</script></body></html>
"""

if __name__ == "__main__":
    sys.exit(main())
