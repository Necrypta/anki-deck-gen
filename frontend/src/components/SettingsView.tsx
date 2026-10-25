import { useState } from "react";
import { DEFAULT_MACROS, formatMacros, parseMacros } from "../lib/deck";
import type { BuildInfo, Deck, Settings, Theme } from "../types";
import { MathPreview } from "./MathPreview";
import { Segmented } from "./Segmented";
import { TagInput } from "./TagInput";

interface Props {
  settings: Settings;
  deck: Deck;
  build: BuildInfo;
  onSettingsChange: (s: Settings) => void;
  onDeckChange: (d: Deck) => void;
}

export function SettingsView({ settings, deck, build, onSettingsChange, onDeckChange }: Props) {
  const [macroText, setMacroText] = useState(formatMacros(settings.macros));
  const [sample, setSample] = useState("$\\pdv{\\psi}{t} = \\frac{1}{i\\hbar}\\hat H \\psi$, $\\ce{^{238}_{92}U -> ^{234}_{90}Th + \\alpha}$");

  return (
    <div className="settings">
      <section className="settings-group">
        <h2>Appearance</h2>
        <div className="setting-row">
          <div>
            <div className="setting-label">Theme</div>
          </div>
          <Segmented<Theme>
            label="Theme"
            value={settings.theme}
            onChange={(theme) => onSettingsChange({ ...settings, theme })}
            options={[
              { value: "system", label: "System" },
              { value: "light", label: "Light" },
              { value: "dark", label: "Dark" },
            ]}
          />
        </div>
      </section>

      <section className="settings-group">
        <h2>Deck</h2>
        <div className="setting-row">
          <div>
            <div className="setting-label">Deck-wide tags</div>
            <div className="setting-help">Added to every card on export.</div>
          </div>
          <div className="setting-control">
            <TagInput tags={deck.tags} onChange={(tags) => onDeckChange({ ...deck, tags })} />
          </div>
        </div>
        <div className="setting-row">
          <div>
            <div className="setting-label">Subdecks</div>
            <div className="setting-help">
              Use <code>::</code> in the deck name, e.g. <code>Physics::Quantum</code>.
            </div>
          </div>
        </div>
      </section>

      <section className="settings-group">
        <h2>LaTeX macros</h2>
        <p className="setting-help">
          One per line, <code>\name = definition</code>. Use <code>#1</code>, <code>#2</code> for arguments. These apply
          to the preview and are embedded in the exported cards, so Anki renders the same thing.
        </p>
        <textarea
          className="code-input"
          rows={10}
          spellCheck={false}
          value={macroText}
          onChange={(e) => {
            setMacroText(e.target.value);
            onSettingsChange({ ...settings, macros: parseMacros(e.target.value) });
          }}
        />
        <div className="setting-row tight">
          <button
            type="button"
            className="ghost-btn"
            onClick={() => {
              setMacroText(formatMacros(DEFAULT_MACROS));
              onSettingsChange({ ...settings, macros: { ...DEFAULT_MACROS } });
            }}
          >
            Reset to physics defaults
          </button>
        </div>
        <div className="macro-test">
          <input value={sample} onChange={(e) => setSample(e.target.value)} aria-label="Try a formula" />
          <MathPreview text={sample} macros={settings.macros} className="macro-test-out" showErrors />
        </div>
      </section>

      <footer className="settings-foot muted small">
        <div>
          Anki Deck Generator {build.version}
          {!build.release && build.build && ` · test build ${build.build}`}
        </div>
        {build.dataDir && <div>Data: {build.dataDir}</div>}
      </footer>
    </div>
  );
}
