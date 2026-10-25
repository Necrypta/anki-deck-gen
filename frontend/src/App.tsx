import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { EditorView } from "./components/EditorView";
import { Icon, type IconName } from "./components/Icon";
import { ImportView } from "./components/ImportView";
import { SettingsView } from "./components/SettingsView";
import { emptyCard, exportableCards, isEmptyCard, newSession, uid } from "./lib/deck";
import { hasMathProblem } from "./lib/math";
import type { Card, Deck, Session, Settings, View } from "./types";

interface Toast {
  id: number;
  message: string;
  kind: "info" | "error";
  action?: { label: string; run: () => void };
}

const NAV: { view: View; label: string; icon: IconName }[] = [
  { view: "editor", label: "Editor", icon: "edit" },
  { view: "import", label: "Import", icon: "import" },
  { view: "settings", label: "Settings", icon: "settings" },
];

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [view, setView] = useState<View>("editor");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [version, setVersion] = useState("");
  const [exporting, setExporting] = useState(false);
  const toastTimer = useRef<number>();

  // Load the saved session (or start fresh).
  useEffect(() => {
    (async () => {
      const [saved, info] = await Promise.all([api.loadSession(), api.info()]);
      const s = saved.ok && saved.session?.version === 1 ? saved.session : newSession();
      setSession(s);
      setSelectedId(s.deck.cards[0]?.id ?? null);
      if (info.ok) setVersion(info.version);
    })();
  }, []);

  // Autosave, debounced.
  useEffect(() => {
    if (!session) return;
    const t = window.setTimeout(() => api.saveSession(session), 400);
    return () => clearTimeout(t);
  }, [session]);

  // Theme.
  useEffect(() => {
    const theme = session?.settings.theme ?? "system";
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  }, [session?.settings.theme]);

  const notify = useCallback((message: string, kind: "info" | "error" = "info", action?: Toast["action"]) => {
    window.clearTimeout(toastTimer.current);
    setToast({ id: Date.now(), message, kind, action });
    toastTimer.current = window.setTimeout(() => setToast(null), action ? 6000 : 3200);
  }, []);

  const setDeck = useCallback((deck: Deck) => setSession((s) => (s ? { ...s, deck } : s)), []);
  const setSettings = useCallback((settings: Settings) => setSession((s) => (s ? { ...s, settings } : s)), []);

  const addCard = useCallback(() => {
    if (!session) return;
    const { deck } = session;
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
  }, [session, setDeck]);

  const deleteCard = (id: string) => {
    if (!session) return;
    const { deck } = session;
    const idx = deck.cards.findIndex((c) => c.id === id);
    const removed = deck.cards[idx];
    const cards = deck.cards.filter((c) => c.id !== id);
    setDeck({ ...deck, cards });
    setSelectedId(cards[Math.min(idx, cards.length - 1)]?.id ?? null);
    if (!isEmptyCard(removed, deck.fields)) {
      notify("Card deleted", "info", {
        label: "Undo",
        run: () => {
          setSession((s) => {
            if (!s) return s;
            const next = [...s.deck.cards];
            next.splice(idx, 0, removed);
            return { ...s, deck: { ...s.deck, cards: next } };
          });
          setSelectedId(removed.id);
          setToast(null);
        },
      });
    }
  };

  const duplicateCard = (id: string) => {
    if (!session) return;
    const { deck } = session;
    const idx = deck.cards.findIndex((c) => c.id === id);
    const copy: Card = { ...deck.cards[idx], id: uid(), fields: { ...deck.cards[idx].fields } };
    const cards = [...deck.cards];
    cards.splice(idx + 1, 0, copy);
    setDeck({ ...deck, cards });
    setSelectedId(copy.id);
  };

  const exportDeck = useCallback(async () => {
    if (!session || exporting) return;
    const { deck, settings } = session;
    const cards = exportableCards(deck);
    if (!cards.length) return notify(`Add at least one card with a ${deck.fields[0]} first`, "error");
    const broken = cards.filter((c) => deck.fields.some((f) => hasMathProblem(c.fields[f] ?? "", settings.macros))).length;
    setExporting(true);
    const res = await api.exportDeck({ ...deck, cards }, settings.macros);
    setExporting(false);
    if (!res.ok) return notify(res.error, "error");
    if (res.cancelled) return;
    const warn = broken ? ` · ${broken} card${broken === 1 ? " has" : "s have"} a LaTeX error` : "";
    notify(`Exported ${res.count} card${res.count === 1 ? "" : "s"}${warn}`, "info", {
      label: "Show in folder",
      run: () => res.path && api.reveal(res.path),
    });
  }, [session, exporting, notify]);

  // Global shortcuts.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!session) return;
      if (e.ctrlKey && e.key === "Enter") {
        e.preventDefault();
        addCard();
      } else if (e.ctrlKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        exportDeck();
      } else if (e.altKey && (e.key === "ArrowDown" || e.key === "ArrowUp") && view === "editor") {
        e.preventDefault();
        const cards = session.deck.cards;
        const idx = cards.findIndex((c) => c.id === selectedId);
        const next = cards[Math.max(0, Math.min(cards.length - 1, idx + (e.key === "ArrowDown" ? 1 : -1)))];
        if (next) setSelectedId(next.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [session, selectedId, view, addCard, exportDeck]);

  if (!session) return <div className="boot" />;

  const { deck, settings } = session;
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
            <button type="button" className="primary-btn" onClick={exportDeck} disabled={exporting}>
              <Icon name="download" />
              {exporting ? "Exporting…" : "Export .apkg"}
            </button>
          </div>
        </header>

        <main className="content">
          {view === "editor" && (
            <EditorView
              deck={deck}
              macros={settings.macros}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onDeckChange={setDeck}
              onAddCard={addCard}
              onDeleteCard={deleteCard}
              onDuplicateCard={duplicateCard}
            />
          )}
          {view === "import" && (
            <ImportView
              deck={deck}
              macros={settings.macros}
              notify={notify}
              onAppend={(cards) => {
                const kept = deck.cards.filter((c) => !isEmptyCard(c, deck.fields));
                setDeck({ ...deck, cards: [...kept, ...cards] });
                setSelectedId(cards[0]?.id ?? null);
                setView("editor");
              }}
              onReplace={(next) => {
                setDeck(next);
                setSelectedId(next.cards[0]?.id ?? null);
                setView("editor");
              }}
            />
          )}
          {view === "settings" && (
            <SettingsView
              settings={settings}
              deck={deck}
              version={version}
              onSettingsChange={setSettings}
              onDeckChange={setDeck}
            />
          )}
        </main>
      </div>

      {toast && (
        <div key={toast.id} className={`toast ${toast.kind === "error" ? "is-error" : ""}`} role="status">
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
