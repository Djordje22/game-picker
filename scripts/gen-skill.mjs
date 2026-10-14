// Generates netlify/lib/skill.ts from skills/game_analyzer.md so the Netlify
// Function and the Python agent share one source of truth for the skill text.
// Runs as the Netlify build command and via `npm run build`.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(root, "skills", "game_analyzer.md");
const target = resolve(root, "netlify", "lib", "skill.ts");

const markdown = readFileSync(source, "utf8");

const output =
  "// GENERATED FILE. Do not edit by hand.\n" +
  "// Source: skills/game_analyzer.md. Regenerate with: node scripts/gen-skill.mjs\n" +
  `export const GAME_ANALYZER_SKILL = ${JSON.stringify(markdown)};\n`;

mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, output);
console.log(`Wrote ${target} (${markdown.length} chars)`);
