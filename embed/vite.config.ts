import { defineConfig } from "vite";

// One classic script (IIFE): works on every site, including WordPress optimisers that mangle
// type="module". The panel code is in the same file but only built when the chat is first opened.
export default defineConfig({
  build: {
    lib: {
      entry: "src/index.ts",
      name: "ColtekChat",
      formats: ["iife"],
      fileName: () => "coltek-chat.js",
    },
    outDir: "dist",
    emptyOutDir: true,
    target: "es2018",
    minify: "esbuild",
    sourcemap: false,
  },
});
