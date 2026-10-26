export type NoteType = "basic" | "reversed" | "cloze" | "custom";
export type Theme = "system" | "light" | "dark";
export type View = "editor" | "generate" | "import" | "settings";

export interface Card {
  id: string;
  fields: Record<string, string>;
  tags: string[];
  /** Values beyond the current note type's fields: kept, not shown or exported. */
  hidden?: string[];
  /** Anki's id for the note, kept so a re-export updates it instead of adding a copy. */
  guid?: string;
  /** Opened from an .apkg: the note's id there, and a hash of its content as opened. */
  noteId?: string;
  original?: string;
}

/** Where a deck opened from an .apkg came from; its note type stays as Anki has it. */
export interface DeckSource {
  packageId: string;
  notetypeId: string;
  notetypeName: string;
  ankiDeckId: string;
  format: "modern" | "legacy";
}

export interface Deck {
  id: string;
  name: string;
  noteType: NoteType;
  fields: string[];
  cards: Card[];
  tags: string[];
  updatedAt: number;
  /** The Custom layout, remembered while a built-in type is selected. */
  customFields?: string[];
  /** Opened from an .apkg: exporting patches that file, keeping its scheduling. */
  source?: DeckSource;
}

export interface MacroDef {
  name: string;
  /** Total number of arguments, 0–9. */
  args: number;
  /** Default for #1 when the first argument is optional (`[…]`), else null. */
  optional: string | null;
  body: string;
}

/** Which model to use: a backend ("ollama", "openai", "gemini"), its URL and the model id. */
export interface ModelRef {
  backend: string;
  url: string;
  model: string;
}

export type Density = "few" | "normal" | "thorough";
export type Focus = "balanced" | "equations" | "definitions" | "concepts";

export interface AiSettings {
  /** Writes cards from the material. null = use the suggested model. */
  writer: ModelRef | null;
  /** Reads PDF pages and images (needs vision); used from v0.4. */
  reader: ModelRef | null;
  /** Extra OpenAI-compatible servers the user added. */
  extraUrls: string[];
  density: Density;
  focus: Focus;
  tagSource: boolean;
  /** Let the model rewrite math with the user's macros (small models slip doing this). */
  useMacros: boolean;
}

export interface Settings {
  theme: Theme;
  macros: MacroDef[];
  ai: AiSettings;
}

export interface BuildInfo {
  version: string;
  build: string;
  release: boolean;
  dataDir: string;
}

export interface Session {
  version: 2;
  decks: Deck[];
  activeDeckId: string;
  settings: Settings;
}

export interface ParseError {
  line: number;
  message: string;
}

export interface ParseResult {
  cards: { fields: Record<string, string>; tags: string[] }[];
  errors: ParseError[];
  deck: string | null;
  note_type: NoteType | null;
  fields: string[] | null;
  tags: string[];
}

export const DEFAULT_FIELDS: Record<Exclude<NoteType, "custom">, string[]> = {
  basic: ["Front", "Back", "Extra"],
  reversed: ["Front", "Back", "Extra"],
  cloze: ["Text", "Extra"],
};

export const NOTE_TYPE_LABELS: Record<NoteType, string> = {
  basic: "Basic",
  reversed: "Reversed",
  cloze: "Cloze",
  custom: "Custom",
};

export interface AiModel {
  id: string;
  vision: boolean | null;
  thinking: boolean;
  detail: string;
}

export interface AiRuntime {
  name: string;
  backend: string;
  url: string;
  /** null when it isn't running. */
  status: string | null;
  error: string;
  models: AiModel[];
}

export interface AiStatus {
  runtimes: AiRuntime[];
  gemini: { has_key: boolean; models: AiModel[]; default?: string | null; fast?: string | null; error: string };
  suggested: { read: ModelRef | null; cards: ModelRef | null };
}

export interface GeneratedCard {
  fields: Record<string, string>;
  tags: string[];
  flags: {
    bare_latex: string[];
    /** Math the model retyped that nearly matches the material: the material's version is in `source`. */
    mismatch?: { field: string; got: string; source: string }[];
    /** [E7]-style labels that didn't match any equation. */
    unknown_labels?: string[];
  };
}

export interface JobStatus {
  id: string;
  state: "running" | "done" | "error" | "cancelled";
  error: string;
  done: number;
  total: number;
  message: string;
  elapsed: number;
  cards: GeneratedCard[];
  card_count: number;
  warnings: string[];
  /** Reading jobs: page number → Markdown. */
  pages: Record<string, string>;
}

/** A PDF or image picked on the Generate page (text files go straight into the material). */
export interface SourceFile {
  kind: "pdf" | "image";
  path: string;
  name: string;
  pages: number;
  /** Pages with a usable text layer (none for scans and images). */
  text_pages: number[];
}

export type ReadMode = "ai" | "text";
