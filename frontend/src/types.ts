export type NoteType = "basic" | "reversed" | "cloze" | "custom";
export type Theme = "system" | "light" | "dark";
export type View = "editor" | "import" | "settings";

export interface Card {
  id: string;
  fields: Record<string, string>;
  tags: string[];
}

export interface Deck {
  name: string;
  noteType: NoteType;
  fields: string[];
  cards: Card[];
  tags: string[];
}

export interface Settings {
  theme: Theme;
  macros: Record<string, string>;
}

export interface BuildInfo {
  version: string;
  build: string;
  release: boolean;
  dataDir: string;
}

export interface Session {
  version: 1;
  deck: Deck;
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
