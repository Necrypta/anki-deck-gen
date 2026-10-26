import { useState } from "react";
import { api } from "../api";
import type { AiStatus, BuildInfo, Deck, Settings, Theme } from "../types";
import { AiSettings } from "./AiSettings";
import { MacroEditor } from "./MacroEditor";
import { MathPreview } from "./MathPreview";
import { Segmented } from "./Segmented";
import { TagInput } from "./TagInput";

interface Props {
  settings: Settings;
  deck: Deck;
  build: BuildInfo;
  aiStatus: AiStatus | null;
  aiChecking: boolean;
  onRefreshAi: () => void;
  onGeminiChange: (gemini: AiStatus["gemini"]) => void;
  onSettingsChange: (s: Settings) => void;
  onDeckChange: (d: Deck) => void;
  notify: (msg: string, kind?: "error" | "info") => void;
}

export function SettingsView({
  settings,
  deck,
  build,
  aiStatus,
  aiChecking,
  onRefreshAi,
  onGeminiChange,
  onSettingsChange,
  onDeckChange,
  notify,
}: Props) {
  const [sample, setSample] = useState(
    "$\\dv[2]{x}{t} = -\\omega^2 x$, $\\pdv{\\psi}{t} = \\frac{1}{i\\hbar}\\hat H \\psi$, $\\ce{^{238}_{92}U -> ^{234}_{90}Th + \\alpha}$",
  );

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
            <div className="setting-help">
              Added to every card in “{deck.name}” on export.
            </div>
          </div>
          <div className="setting-control">
            <TagInput
              tags={deck.tags}
              onChange={(tags) => onDeckChange({ ...deck, tags })}
            />
          </div>
        </div>
        <div className="setting-row">
          <div>
            <div className="setting-label">Subdecks</div>
            <div className="setting-help">
              Use <code>::</code> in the deck name, e.g.{" "}
              <code>Physics::Quantum</code>.
            </div>
          </div>
        </div>
      </section>

      <AiSettings
        ai={settings.ai}
        status={aiStatus}
        checking={aiChecking}
        onAiChange={(ai) => onSettingsChange({ ...settings, ai })}
        onRefresh={onRefreshAi}
        onGeminiChange={onGeminiChange}
        notify={notify}
      />

      <section className="settings-group">
        <h2>LaTeX macros</h2>
        <p className="setting-help">
          Write <code>#1</code>…<code>#9</code> in a definition for its
          arguments. Tick <b>Optional #1</b> to make the first argument
          optional, written in square brackets: <code>\dv[2]{"{y}{x}"}</code> is
          a second derivative and <code>\dv{"{y}{x}"}</code> uses the default.
          Saved macros apply to the preview and are embedded in exported cards,
          so Anki renders the same thing.
        </p>
        <MacroEditor
          macros={settings.macros}
          notify={notify}
          onSave={(macros) => onSettingsChange({ ...settings, macros })}
        />
        <div className="macro-test">
          <input
            value={sample}
            onChange={(e) => setSample(e.target.value)}
            aria-label="Try a formula"
          />
          <MathPreview
            text={sample}
            macros={settings.macros}
            className="macro-test-out"
            showErrors
          />
        </div>
        <p className="setting-help small">
          The test line above uses your saved macros.
        </p>
      </section>

      <footer className="settings-foot muted small">
        <div>
          Anki Deck Generator {build.version}
          {!build.release && build.build && ` · test build ${build.build}`}
        </div>
        <div>Screen build: {__UI_BUILD__}</div>
        {build.dataDir && (
          <>
            <div>
              Data: {build.dataDir}{" "}
              <button
                type="button"
                className="link-btn"
                onClick={() => api.reveal(`${build.dataDir}/session.json`)}
              >
                Open data folder
              </button>{" "}
              ·{" "}
              <button
                type="button"
                className="link-btn"
                onClick={() => api.reveal(`${build.dataDir}/app.log`)}
              >
                Show log file
              </button>
            </div>
            <div>
              Your decks are saved in session.json. A copy is kept in backups\
              each time the app starts (the last 10).
            </div>
          </>
        )}
      </footer>
    </div>
  );
}
