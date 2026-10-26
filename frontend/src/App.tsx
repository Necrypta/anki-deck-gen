import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { DeckList } from "./components/DeckList";
import { EditorView } from "./components/EditorView";
import {
  emptyGenerateState,
  type GenerateState,
  GenerateView,
} from "./components/GenerateView";
import { Icon, type IconName } from "./components/Icon";
import { ImportView } from "./components/ImportView";
import { SettingsView } from "./components/SettingsView";
import {
  copyCard,
  duplicateDeck,
  emptyCard,
  exportableCards,
  isEmptyCard,
  migrateSession,
  newDeck,
  newSession,
  uid,
  uniqueDeckName,
} from "./lib/deck";
import { hasMathProblem } from "./lib/math";
import type {
  AiStatus,
  BuildInfo,
  Card,
  Deck,
  Session,
  Settings,
  View,
} from "./types";

interface Toast {
  id: number;
  message: string;
  kind: "info" | "error";
  action?: { label: string; run: () => void };
}

const NAV: { view: View; label: string; icon: IconName }[] = [
  { view: "editor", label: "Editor", icon: "edit" },
  { view: "generate", label: "Generate", icon: "sparkle" },
  { view: "import", label: "Import", icon: "import" },
  { view: "settings", label: "Settings", icon: "settings" },
];

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [view, setView] = useState<View>("editor");
  // Selected card, remembered per deck.
  const [selected, setSelected] = useState<Record<string, string | null>>({});
  const [toast, setToast] = useState<Toast | null>(null);
  const [build, setBuild] = useState<BuildInfo>({
    version: "",
    build: "",
    release: true,
    dataDir: "",
  });
  const [exporting, setExporting] = useState(false);
  const toastTimer = useRef<number>();
  const noSave = useRef(false);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [aiChecking, setAiChecking] = useState(false);
  // Generate page work, per deck, so switching pages keeps it (and any running job).
  const [generate, setGenerate] = useState<Record<string, GenerateState>>({});

  // Load the saved session (or start fresh).
  useEffect(() => {
    (async () => {
      const [saved, info] = await Promise.all([api.loadSession(), api.info()]);
      // If the saved file couldn't even be asked for, don't autosave over it.
      if (!saved.ok) {
        noSave.current = true;
        notify(
          `Couldn't load your saved decks (${saved.error}). Changes won't be saved until you restart.`,
          "error",
        );
      } else if (saved.notice) {
        const dir = info.ok ? info.data_dir : "";
        notify(
          saved.notice,
          "error",
          dir
            ? {
                label: "Show folder",
                run: () => api.reveal(`${dir}/session.json`),
              }
            : undefined,
        );
      }
      setSession(
        saved.ok && saved.session
          ? migrateSession(saved.session)
          : newSession(),
      );
      if (info.ok)
        setBuild({
          version: info.version,
          build: info.build,
          release: info.release,
          dataDir: info.data_dir,
        });
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Autosave, debounced.
  useEffect(() => {
    if (!session || noSave.current) return;
    const t = window.setTimeout(() => api.saveSession(session), 400);
    return () => clearTimeout(t);
  }, [session]);

  // Theme.
  useEffect(() => {
    const theme = session?.settings.theme ?? "system";
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  }, [session?.settings.theme]);

  const extraUrls = session?.settings.ai.extraUrls;
  const refreshAi = useCallback(async () => {
    setAiChecking(true);
    const res = await api.aiStatus(extraUrls ?? []);
    setAiChecking(false);
    if (res.ok)
      setAiStatus({
        runtimes: res.runtimes,
        gemini: res.gemini,
        suggested: res.suggested,
      });
  }, [extraUrls]);

  // Look for AI the first time the Generate or Settings page opens.
  useEffect(() => {
    if (
      (view === "generate" || view === "settings") &&
      !aiStatus &&
      !aiChecking
    )
      refreshAi();
  }, [view, aiStatus, aiChecking, refreshAi]);

  const notify = useCallback(
    (
      message: string,
      kind: "info" | "error" = "info",
      action?: Toast["action"],
    ) => {
      window.clearTimeout(toastTimer.current);
      setToast({ id: Date.now(), message, kind, action });
      toastTimer.current = window.setTimeout(
        () => setToast(null),
        action ? 6000 : 3200,
      );
    },
    [],
  );

  const deck =
    session?.decks.find((d) => d.id === session.activeDeckId) ??
    session?.decks[0];
  const selectedId = deck
    ? (selected[deck.id] ?? deck.cards[0]?.id ?? null)
    : null;
  const setSelectedId = useCallback(
    (id: string | null) =>
      deck && setSelected((s) => ({ ...s, [deck.id]: id })),
    [deck],
  );

  /** Replace the active deck (matched by id). */
  const setDeck = useCallback(
    (next: Deck) =>
      setSession((s) =>
        s
          ? {
              ...s,
              decks: s.decks.map((d) =>
                d.id === next.id ? { ...next, updatedAt: Date.now() } : d,
              ),
            }
          : s,
      ),
    [],
  );
  const deckId = deck?.id;
  const updateGenerate = useCallback(
    (update: (s: GenerateState) => GenerateState) =>
      deckId &&
      setGenerate((g) => ({
        ...g,
        [deckId]: update(g[deckId] ?? emptyGenerateState()),
      })),
    [deckId],
  );
  const setSettings = useCallback(
    (settings: Settings) => setSession((s) => (s ? { ...s, settings } : s)),
    [],
  );

  // ----- Decks -----

  const selectDeck = (id: string) => {
    setSession((s) => (s ? { ...s, activeDeckId: id } : s));
    setView("editor");
  };

  const createDeck = useCallback(() => {
    setSession((s) => {
      if (!s) return s;
      const d = newDeck(s.decks);
      return { ...s, decks: [...s.decks, d], activeDeckId: d.id };
    });
    setView("editor");
  }, []);

  const copyDeck = (id: string) => {
    if (!session) return;
    const src = session.decks.find((d) => d.id === id);
    if (!src) return;
    const copy = duplicateDeck(src, session.decks);
    const idx = session.decks.indexOf(src);
    const decks = [...session.decks];
    decks.splice(idx + 1, 0, copy);
    setSession({ ...session, decks, activeDeckId: copy.id });
    notify(`Duplicated as “${copy.name}”`);
  };

  const deleteDeck = (id: string) => {
    if (!session || session.decks.length <= 1) return;
    const idx = session.decks.findIndex((d) => d.id === id);
    const removed = session.decks[idx];
    const decks = session.decks.filter((d) => d.id !== id);
    const activeDeckId =
      session.activeDeckId === id
        ? decks[Math.min(idx, decks.length - 1)].id
        : session.activeDeckId;
    setSession({ ...session, decks, activeDeckId });
    notify(`Deleted “${removed.name}”`, "info", {
      label: "Undo",
      run: () => {
        const wasActive = session.activeDeckId === id;
        setSession((s) => {
          if (!s) return s;
          const next = [...s.decks];
          next.splice(idx, 0, removed);
          return {
            ...s,
            decks: next,
            activeDeckId: wasActive ? removed.id : s.activeDeckId,
          };
        });
        setToast(null);
      },
    });
  };

  // ----- Cards -----

  const addCard = useCallback(() => {
    if (!deck) return;
    setView("editor");
    // Reuse a trailing blank card instead of stacking empties.
    const last = deck.cards[deck.cards.length - 1];
    if (last && isEmptyCard(last, deck.fields)) {
      setSelectedId(last.id);
      return;
    }
    const card = emptyCard(deck.fields);
    setDeck({ ...deck, cards: [...deck.cards, card] });
    setSelectedId(card.id);
  }, [deck, setDeck, setSelectedId]);

  const deleteCard = (id: string) => {
    if (!deck) return;
    const idx = deck.cards.findIndex((c) => c.id === id);
    const removed = deck.cards[idx];
    const cards = deck.cards.filter((c) => c.id !== id);
    setDeck({ ...deck, cards });
    setSelectedId(cards[Math.min(idx, cards.length - 1)]?.id ?? null);
    if (!isEmptyCard(removed, deck.fields)) {
      const deckId = deck.id;
      notify("Card deleted", "info", {
        label: "Undo",
        run: () => {
          setSession((s) => {
            if (!s) return s;
            return {
              ...s,
              decks: s.decks.map((d) => {
                if (d.id !== deckId) return d;
                const next = [...d.cards];
                next.splice(idx, 0, removed);
                return { ...d, cards: next };
              }),
            };
          });
          setSelected((s) => ({ ...s, [deckId]: removed.id }));
          setToast(null);
        },
      });
    }
  };

  const duplicateCard = (id: string) => {
    if (!deck) return;
    const idx = deck.cards.findIndex((c) => c.id === id);
    const copy: Card = copyCard(deck.cards[idx]);
    const cards = [...deck.cards];
    cards.splice(idx + 1, 0, copy);
    setDeck({ ...deck, cards });
    setSelectedId(copy.id);
  };

  const exportDeck = useCallback(async () => {
    if (!session || !deck || exporting) return;
    const { settings } = session;
    const cards = exportableCards(deck);
    if (!cards.length)
      return notify(
        `Add at least one card with a ${deck.fields[0]} first`,
        "error",
      );
    const broken = cards.filter((c) =>
      deck.fields.some((f) =>
        hasMathProblem(c.fields[f] ?? "", settings.macros),
      ),
    ).length;
    const warn = broken
      ? ` · ${broken} card${broken === 1 ? " has" : "s have"} a LaTeX error`
      : "";
    setExporting(true);
    if (deck.source) {
      // Opened from an .apkg: write that file back with every deck that came from it.
      const packageId = deck.source.packageId;
      const decks = session.decks.filter((d) => d.source?.packageId === packageId);
      const res = await api.exportPackage(packageId, decks, settings.macros);
      setExporting(false);
      if (!res.ok) return notify(res.error, "error");
      if (res.cancelled || !res.changes) return;
      const c = res.changes;
      const parts = [
        c.updated && `${c.updated} updated`,
        c.added && `${c.added} added`,
        c.deleted && `${c.deleted} removed`,
      ].filter(Boolean);
      return notify(
        `Saved ${res.count} notes${parts.length ? ` (${parts.join(", ")})` : ", no changes"}, scheduling kept${warn}`,
        "info",
        { label: "Show in folder", run: () => res.path && api.reveal(res.path) },
      );
    }
    const res = await api.exportDeck({ ...deck, cards }, settings.macros);
    setExporting(false);
    if (!res.ok) return notify(res.error, "error");
    if (res.cancelled) return;
    // Keep the GUIDs new cards were exported with, so later edits update them in Anki.
    const guids = res.guids ?? {};
    if (Object.keys(guids).length) {
      const id = deck.id;
      setSession((s) =>
        s && {
          ...s,
          decks: s.decks.map((d) =>
            d.id !== id ? d : { ...d, cards: d.cards.map((c) => (guids[c.id] && !c.guid ? { ...c, guid: guids[c.id] } : c)) },
          ),
        },
      );
    }
    notify(
      `Exported ${res.count} card${res.count === 1 ? "" : "s"}${warn}`,
      "info",
      {
        label: "Show in folder",
        run: () => res.path && api.reveal(res.path),
      },
    );
  }, [session, deck, exporting, notify]);

  // Global shortcuts.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!deck) return;
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "n") {
        e.preventDefault();
        createDeck();
      } else if (e.ctrlKey && e.key === "Enter") {
        e.preventDefault();
        addCard();
      } else if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        exportDeck();
      } else if (
        e.altKey &&
        (e.key === "ArrowDown" || e.key === "ArrowUp") &&
        view === "editor"
      ) {
        e.preventDefault();
        const cards = deck.cards;
        const idx = cards.findIndex((c) => c.id === selectedId);
        const next =
          cards[
            Math.max(
              0,
              Math.min(
                cards.length - 1,
                idx + (e.key === "ArrowDown" ? 1 : -1),
              ),
            )
          ];
        if (next) setSelectedId(next.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [deck, selectedId, view, addCard, exportDeck, createDeck, setSelectedId]);

  if (!session || !deck) return <div className="boot" />;

  const { settings } = session;
  const count = exportableCards(deck).length;

  return (
    <div className="app">
      <nav className="rail">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            ∂
          </span>
          <span className="brand-name">Deck Generator</span>
        </div>
        {!build.release && build.build && (
          <div className="build-badge" title={`Saves to ${build.dataDir}`}>
            Test build · {build.build}
          </div>
        )}
        {NAV.map((n) => (
          <button
            key={n.view}
            type="button"
            className={`nav-item ${view === n.view ? "is-active" : ""}`}
            onClick={() => setView(n.view)}
          >
            <Icon name={n.icon} />
            {n.label}
          </button>
        ))}

        <DeckList
          decks={session.decks}
          activeId={deck.id}
          onSelect={selectDeck}
          onNew={createDeck}
          onDuplicate={copyDeck}
          onDelete={deleteDeck}
        />

        <div className="rail-foot">
          <div className="kbd-hint">
            <kbd>Ctrl</kbd>
            <kbd>↵</kbd> new card
          </div>
          <div className="kbd-hint">
            <kbd>Ctrl</kbd>
            <kbd>M</kbd> math
          </div>
          <div className="kbd-hint">
            <kbd>Ctrl</kbd>
            <kbd>S</kbd> export
          </div>
        </div>
      </nav>

      <div className="main">
        {build.build &&
          build.build !== "dev" &&
          __UI_BUILD__ !== "dev" &&
          build.build !== __UI_BUILD__ && (
            <div className="stale-banner" role="alert">
              This window is showing a different version of the screen (screen{" "}
              {__UI_BUILD__}, app {build.build}).
              <button
                type="button"
                onClick={() =>
                  location.replace(`${location.pathname}?v=${Date.now()}`)
                }
              >
                Reload
              </button>
            </div>
          )}
        <header className="topbar">
          <input
            className="deck-name"
            value={deck.name}
            onChange={(e) => setDeck({ ...deck, name: e.target.value })}
            aria-label="Deck name"
            spellCheck={false}
          />
          <span className="pill">
            {count} card{count === 1 ? "" : "s"}
          </span>
          <div className="topbar-right">
            <button
              type="button"
              className="primary-btn"
              onClick={exportDeck}
              disabled={exporting}
            >
              <Icon name="download" />
              {exporting ? "Exporting…" : "Export .apkg"}
            </button>
          </div>
        </header>

        <main className="content">
          {view === "editor" && (
            <EditorView
              key={deck.id}
              deck={deck}
              macros={settings.macros}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onDeckChange={setDeck}
              onAddCard={addCard}
              onDeleteCard={deleteCard}
              onDuplicateCard={duplicateCard}
              onOpenImport={() => setView("import")}
            />
          )}
          {view === "generate" && (
            <GenerateView
              key={deck.id}
              deck={deck}
              macros={settings.macros}
              ai={settings.ai}
              status={aiStatus}
              state={generate[deck.id] ?? emptyGenerateState()}
              onState={updateGenerate}
              onAiChange={(ai) => setSettings({ ...settings, ai })}
              onAdd={(cards) => {
                const kept = deck.cards.filter(
                  (c) => !isEmptyCard(c, deck.fields),
                );
                setDeck({ ...deck, cards: [...kept, ...cards] });
              }}
              onOpenSettings={() => setView("settings")}
              notify={notify}
            />
          )}
          {view === "import" && (
            <ImportView
              key={deck.id}
              deck={deck}
              macros={settings.macros}
              notify={notify}
              onAppend={(cards) => {
                const kept = deck.cards.filter(
                  (c) => !isEmptyCard(c, deck.fields),
                );
                setDeck({ ...deck, cards: [...kept, ...cards] });
                setSelectedId(cards[0]?.id ?? null);
                setView("editor");
              }}
              onOpenPackage={(decks, summary) => {
                const pid = decks[0]?.source?.packageId;
                const open = session.decks.find((d) => d.source?.packageId === pid);
                if (open) {
                  setSession({ ...session, activeDeckId: open.id });
                  setView("editor");
                  return notify("That .apkg is already open: its decks are in the sidebar");
                }
                const all = [...session.decks];
                for (const d of decks) all.push({ ...d, id: uid(), name: uniqueDeckName(all, d.name), tags: [], updatedAt: Date.now() });
                const made = all.slice(session.decks.length);
                setSession({ ...session, decks: all, activeDeckId: made[0].id });
                setView("editor");
                notify(summary);
              }}
              onReplace={(next) => {
                setDeck({
                  ...next,
                  id: deck.id,
                  customFields:
                    next.noteType === "custom"
                      ? [...next.fields]
                      : deck.customFields,
                  cards: next.cards,
                });
                setSelectedId(next.cards[0]?.id ?? null);
                setView("editor");
              }}
            />
          )}
          {view === "settings" && (
            <SettingsView
              settings={settings}
              deck={deck}
              build={build}
              aiStatus={aiStatus}
              aiChecking={aiChecking}
              onRefreshAi={refreshAi}
              onGeminiChange={(gemini) =>
                setAiStatus((s) => (s ? { ...s, gemini } : s))
              }
              notify={notify}
              onSettingsChange={setSettings}
              onDeckChange={setDeck}
            />
          )}
        </main>
      </div>

      {toast && (
        <div
          key={toast.id}
          className={`toast ${toast.kind === "error" ? "is-error" : ""}`}
          role="status"
        >
          <span>{toast.message}</span>
          {toast.action && (
            <button type="button" onClick={toast.action.run}>
              {toast.action.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
