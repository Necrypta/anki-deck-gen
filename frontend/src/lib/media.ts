// Images on decks opened from an .apkg: field previews ask for them by file
// name, and the backend sends them as data URLs. Cached per package.

import { createContext } from "react";
import { api } from "../api";

/** The package whose media the previews below should show. */
export const MediaContext = createContext<string | null>(null);

const cache = new Map<string, Map<string, string | null>>();
const pending = new Map<string, Promise<void>>();

function forPackage(packageId: string) {
  let m = cache.get(packageId);
  if (!m) cache.set(packageId, (m = new Map()));
  return m;
}

/** Set the src of every `img[data-media]` under `root`, fetching what isn't cached yet. */
export async function resolveMedia(root: HTMLElement, packageId: string): Promise<void> {
  const imgs = [...root.querySelectorAll<HTMLImageElement>("img[data-media]")];
  if (!imgs.length) return;
  const known = forPackage(packageId);
  const missing = [...new Set(imgs.map((i) => i.dataset.media!).filter((n) => !known.has(n)))];
  if (missing.length) {
    const key = `${packageId}|${missing.join("|")}`;
    let job = pending.get(key);
    if (!job) {
      job = api.mediaData(packageId, missing).then((res) => {
        for (const n of missing) known.set(n, res.ok ? res.media[n] ?? null : null);
        pending.delete(key);
      });
      pending.set(key, job);
    }
    await job;
  }
  for (const img of imgs) {
    const url = known.get(img.dataset.media!);
    if (url && img.isConnected) img.src = url;
  }
}
