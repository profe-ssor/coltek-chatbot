// Fails the build if dist/coltek-chat.js is over 25 KB gzipped.
import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const LIMIT_BYTES = 25 * 1024;
const file = new URL("../dist/coltek-chat.js", import.meta.url);
const raw = readFileSync(file);
const gzipped = gzipSync(raw, { level: 9 }).length;
const kb = (n) => (n / 1024).toFixed(1) + " KB";

console.log(`dist/coltek-chat.js: ${kb(raw.length)} raw, ${kb(gzipped)} gzipped (limit ${kb(LIMIT_BYTES)} gzipped)`);
if (gzipped > LIMIT_BYTES) {
  console.error("Size check FAILED: the widget is over the 25 KB gzipped budget.");
  process.exit(1);
}
