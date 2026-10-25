export type NoteType = "basic" | "reversed" | "cloze" | "custom";
export type Theme = "system" | "light" | "dark";
export type View = "editor" | "import" | "settings";

export interface Card {
  id: string;
  fields: Record<string, string>;
  tags: string[];
  /** Values beyond the current note type's fields: kept, not shown or exported. */
  hidden?: string[];
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
}

export interface MacroDef {
  name: string;
  /** Total number of arguments, 0–9. */
  args: number;
  /** Default for #1 when the first argument is optional (`[…]`), else null. */
  optional: string | null;
  body: string;
}

export interface Settings {
  theme: Theme;
  macros: MacroDef[];
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
