import { useState } from "react";
import { api } from "../api";
import { effectiveReader, effectiveWriter } from "../lib/ai";
import type { AiSettings as AiSettingsT, AiStatus } from "../types";
import { ModelSelect } from "./ModelSelect";

interface Props {
  ai: AiSettingsT;
  status: AiStatus | null;
  checking: boolean;
  onAiChange: (ai: AiSettingsT) => void;
  onRefresh: () => void;
  onGeminiChange: (gemini: AiStatus["gemini"]) => void;
  notify: (msg: string, kind?: "error" | "info") => void;
}

const PULLS = ["ollama pull qwen3:8b", "ollama pull qwen2.5vl:7b"];

export function AiSettings({ ai, status, checking, onAiChange, onRefresh, onGeminiChange, notify }: Props) {
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [url, setUrl] = useState("");
  const running = status?.runtimes.filter((r) => r.status) ?? [];
  const gemini = status?.gemini;
  const writer = effectiveWriter(ai, status);
  const reader = effectiveReader(ai, status);

  const saveKey = async () => {
    setSaving(true);
    const res = await api.setApiKey(key);
    setSaving(false);
    if (!res.ok) return notify(res.error, "error");
    setKey("");
    onGeminiChange(res.gemini);
    notify(res.stored ? "Gemini key saved in Windows Credential Manager" : "Gemini key works (kept until you close the app)");
  };

  const removeKey = async () => {
    await api.clearApiKey();
    onGeminiChange({ has_key: false, models: [], error: "" });
    if (ai.writer?.backend === "gemini") onAiChange({ ...ai, writer: null });
  };

  const addUrl = () => {
    const u = url.trim().replace(/\/+$/, "");
    if (!/^https?:\/\//.test(u)) return notify("Enter a URL like http://localhost:1234", "error");
    if (!ai.extraUrls.includes(u)) onAiChange({ ...ai, extraUrls: [...ai.extraUrls, u] });
    setUrl("");
    onRefresh();
  };

  return (
    <section className="settings-group">
      <h2>AI card generation</h2>

      <div className="setting-row">
        <div>
          <div className="setting-label">Model for writing cards</div>
          <div className="setting-help">
            Local models run on this computer: free, private and offline. Gemini is online: best quality, but slow on the
            free tier.
          </div>
        </div>
        <div className="setting-control">
          <ModelSelect status={status} value={writer} onChange={(w) => onAiChange({ ...ai, writer: w })} />
        </div>
      </div>

      <div className="setting-row">
        <div>
          <div className="setting-label">Model for reading pages (PDFs, images)</div>
          <div className="setting-help">
            Needs a vision model. It turns each page into text with LaTeX before cards are written.
          </div>
        </div>
        <div className="setting-control">
          <ModelSelect
            status={status}
            value={reader}
            stage="read"
            label="Model for reading pages"
            onChange={(r) => onAiChange({ ...ai, reader: r })}
          />
        </div>
      </div>

      <div className="setting-row">
        <div>
          <div className="setting-label">Local AI</div>
          <div className="setting-help">
            Works with <a href="https://ollama.com/download" target="_blank" rel="noreferrer">Ollama</a> (easiest),{" "}
            <a href="https://lmstudio.ai" target="_blank" rel="noreferrer">LM Studio</a>, llama.cpp and Jan. Start one and
            it's found automatically.
          </div>
        </div>
        <div className="setting-control">
          <button type="button" className="ghost-btn" onClick={onRefresh} disabled={checking}>
            {checking ? "Checking…" : "Check again"}
          </button>
        </div>
      </div>
      <ul className="runtime-list">
        {(status?.runtimes ?? []).map((r) => (
          <li key={r.url} className={r.status ? "" : "is-off"}>
            <span className={`dot ${r.status ? "is-on" : ""}`} aria-hidden="true" />
            <span className="runtime-name">{r.name}</span>
            <span className="muted small">{r.url}</span>
            <span className="runtime-state small">
              {r.status ? `${r.models.length} model${r.models.length === 1 ? "" : "s"}` : "Not running"}
            </span>
          </li>
        ))}
        {!status && <li className="muted small">Looking for local AI…</li>}
      </ul>
      {status && running.length === 0 && (
        <div className="setting-help callout">
          No local AI found. To set it up: install Ollama, then run these in a terminal (about 5 GB each) and click{" "}
          <b>Check again</b>:
          <pre>{PULLS.join("\n")}</pre>
          qwen3:8b writes the cards and qwen2.5vl:7b reads PDF pages and images.
        </div>
      )}
      {running.some((r) => r.models.some((m) => m.thinking)) && (
        <p className="setting-help small">
          Thinking models are asked not to think. If one still returns nothing, use its “instruct” version.
        </p>
      )}
      <div className="setting-row tight">
        <div className="setting-help">Another OpenAI-compatible server</div>
        <div className="setting-control inline">
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://localhost:1234" aria-label="Server URL" />
          <button type="button" className="ghost-btn" onClick={addUrl} disabled={!url.trim()}>
            Add
          </button>
        </div>
      </div>
      {ai.extraUrls.length > 0 && (
        <div className="setting-help small">
          Added:{" "}
          {ai.extraUrls.map((u) => (
            <span key={u} className="url-chip">
              {u}
              <button
                type="button"
                className="link-btn"
                onClick={() => onAiChange({ ...ai, extraUrls: ai.extraUrls.filter((x) => x !== u) })}
              >
                remove
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="setting-row">
        <div>
          <div className="setting-label">Gemini API key</div>
          <div className="setting-help">
            <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">Get a free key</a>. It's stored
            in Windows Credential Manager, not in the app's files. On the free tier Google may use what you send to
            improve its models; use a local model for anything private.
          </div>
          {gemini?.has_key && (
            <div className={`setting-help small ${gemini.error ? "is-error" : ""}`}>
              {gemini.error || `Key saved · ${gemini.models.length} models · default ${gemini.default ?? "—"}`}
            </div>
          )}
        </div>
        <div className="setting-control inline">
          {gemini?.has_key ? (
            <button type="button" className="ghost-btn" onClick={removeKey}>
              Remove key
            </button>
          ) : (
            <>
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="Paste key"
                aria-label="Gemini API key"
                autoComplete="off"
              />
              <button type="button" className="primary-btn" onClick={saveKey} disabled={!key.trim() || saving}>
                {saving ? "Checking…" : "Save"}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="setting-row">
        <div>
          <div className="setting-label">Tag cards with their source</div>
          <div className="setting-help">
            Adds a tag like <code>source::Hassani_ch8</code> from the file name.
          </div>
        </div>
        <div className="setting-control">
          <input
            type="checkbox"
            checked={ai.tagSource}
            onChange={(e) => onAiChange({ ...ai, tagSource: e.target.checked })}
            aria-label="Tag cards with their source"
          />
        </div>
      </div>
    </section>
  );
}
