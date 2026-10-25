/** Build label baked in at build time (see vite.config.ts). */
declare const __UI_BUILD__: string;

// Only vite.config.ts (run by Node) uses this; the project has no @types/node.
declare module "node:fs" {
  export function readFileSync(path: URL | string, encoding: "utf8"): string;
}
