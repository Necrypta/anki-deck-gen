import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { formatElapsed, parsePageRange } from "../lib/ai";
import type { AiStatus, JobStatus, ModelRef, ReadMode, SourceFile } from "../types";
import { Icon } from "./Icon";
import { ModelSelect } from "./ModelSelect";
import { Segmented } from "./Segmented";

interface Props {
  file: SourceFile;
  pageSpec: string;
  mode: ReadMode;
  job: Omit<JobStatus, "cards"> | null;
  reader: ModelRef | null;
  status: AiStatus | null;
  onPageSpec: (spec: string) => void;
  onMode: (mode: ReadMode) => void;
  onReader: (ref: ModelRef) => void;
  onRead: () => void;
  onStop: () => void;
  onRemove: () => void;
}

const MAX_THUMBS = 12;

/** A PDF or image waiting to be read into the material box. */
export function SourceCard({ file, pageSpec, mode, job, reader, status, onPageSpec, onMode, onReader, onRead, onStop, onRemove }: Props) {
  const pages = file.kind === "pdf" ? parsePageRange(pageSpec, file.pages) : [1];
  const running = job?.state === "running";
  const scanned = pages?.filter((n) => !file.text_pages.includes(n)) ?? [];
  const canText = file.kind === "pdf" && file.text_pages.length > 0;
  const effectiveMode: ReadMode = canText ? mode : "ai";
  const thumbs = useThumbnails(file.path, (pages ?? []).slice(0, MAX_THUMBS));

  return (
    <div className="source-card">
      <div className="source-head">
        <Icon name="file" size={14} />
        <span className="file-name" title={file.name}>
          {file.name}
        </span>
        <span className="muted small">
          {file.kind === "pdf" ? `${file.pages} page${file.pages === 1 ? "" : "s"}` : "image"}
          {file.kind === "pdf" && file.text_pages.length === 0 && " · scanned"}
        </span>
        <button type="button" className="icon-btn xs" title="Remove file" onClick={onRemove} disabled={running}>
          <Icon name="x" size={14} />
        </button>
      </div>

      {file.kind === "pdf" && (
        <label className="source-pages">
          <span>Pages</span>
          <input
            value={pageSpec}
            onChange={(e) => onPageSpec(e.target.value)}
            placeholder={`all ${file.pages}, or e.g. 12-15`}
            aria-invalid={pages === null}
            disabled={running}
          />
          <span className={`small ${pages === null ? "is-error" : "muted"}`}>
            {pages === null ? `Use page numbers 1–${file.pages}, like 3-5, 8` : `${pages.length} selected`}
          </span>
        </label>
      )}

      {pages && pages.length > 0 && (
        <div className="thumb-strip" aria-label="Selected pages">
          {pages.slice(0, MAX_THUMBS).map((n) => (
            <figure key={n} className={job?.pages[String(n)] !== undefined ? "is-read" : ""}>
              {thumbs[n] ? <img src={thumbs[n]} alt={`Page ${n}`} /> : <div className="thumb-blank" />}
              <figcaption>{file.kind === "pdf" ? n : ""}</figcaption>
            </figure>
          ))}
          {pages.length > MAX_THUMBS && <div className="thumb-more muted small">+{pages.length - MAX_THUMBS} more</div>}
        </div>
      )}

      <div className="source-options">
        {canText && (
          <div className="option">
            <span>Read with</span>
            <Segmented<ReadMode>
              label="How to read the pages"
              value={effectiveMode}
              onChange={onMode}
              options={[
                { value: "ai", label: "AI model" },
                { value: "text", label: "Text layer" },
              ]}
            />
          </div>
        )}
        {effectiveMode === "ai" && (
          <label className="grow">
            <span>Reads pages with</span>
            <ModelSelect status={status} value={reader} stage="read" label="Model that reads the pages" onChange={onReader} />
          </label>
        )}
      </div>
      <div className="source-hint muted small">
        {effectiveMode === "ai"
          ? "A vision model reads each page, so equations come out as LaTeX. Best for textbooks and scans."
          : "Instant and offline, but equations usually come out garbled."}
        {effectiveMode === "text" && scanned.length > 0 && ` ${scanned.length} selected page(s) have no text layer.`}
      </div>

      <div className="generate-actions">
        <span className="muted small">
          {running ? `${job.message || "Reading…"} · ${formatElapsed(job.elapsed)}` : "The text appears below for you to check and trim."}
        </span>
        {running ? (
          <button type="button" className="ghost-btn" onClick={onStop}>
            Stop
          </button>
        ) : (
          <button
            type="button"
            className="primary-btn"
            onClick={onRead}
            disabled={!pages?.length || (effectiveMode === "ai" && !reader)}
          >
            Read {pages?.length ?? 0} page{pages?.length === 1 ? "" : "s"}
          </button>
        )}
      </div>
      {running && (
        <div className="progress" aria-hidden="true">
          <div
            className={`progress-fill ${job.total ? "" : "is-indeterminate"}`}
            style={{ width: job.total ? `${Math.max(4, Math.round((job.done / job.total) * 100))}%` : undefined }}
          />
        </div>
      )}
    </div>
  );
}

/** Thumbnails for the selected pages, fetched in the background and cached per file. */
function useThumbnails(path: string, pages: number[]): Record<number, string> {
  const cache = useRef<{ path: string; thumbs: Record<number, string> }>({ path, thumbs: {} });
  const [, bump] = useState(0);
  if (cache.current.path !== path) cache.current = { path, thumbs: {} };
  const missing = pages.filter((n) => !(n in cache.current.thumbs));
  const key = `${path}|${missing.join(",")}`;

  useEffect(() => {
    if (!missing.length) return;
    const t = window.setTimeout(async () => {
      const res = await api.sourceThumbnails(path, missing);
      if (!res.ok || cache.current.path !== path) return;
      for (const [n, url] of Object.entries(res.thumbs)) cache.current.thumbs[Number(n)] = url;
      bump((x) => x + 1);
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return cache.current.thumbs;
}
