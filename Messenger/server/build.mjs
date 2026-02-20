import { build } from 'esbuild';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.join(__dirname, 'dist');

// Clean dist
if (fs.existsSync(distDir)) {
  fs.rmSync(distDir, { recursive: true });
}
fs.mkdirSync(distDir, { recursive: true });

console.log('[BUILD] Bundling server with esbuild...');

await build({
  entryPoints: [path.join(__dirname, 'src', 'index.ts')],
  bundle: true,
  platform: 'node',
  target: 'node18',
  outfile: path.join(distDir, 'server.cjs'),
  format: 'cjs',
  sourcemap: false,
  minify: false,
  // sql.js wasm file must be loaded from disk at runtime
  external: [],
  loader: {
    '.wasm': 'file',
  },
});

// Copy sql.js wasm file
const sqlJsWasmSrc = path.join(__dirname, 'node_modules', 'sql.js', 'dist', 'sql-wasm.wasm');
if (fs.existsSync(sqlJsWasmSrc)) {
  fs.copyFileSync(sqlJsWasmSrc, path.join(distDir, 'sql-wasm.wasm'));
  console.log('[BUILD] Copied sql-wasm.wasm');
}

console.log('[BUILD] Bundle complete: dist/server.cjs');
console.log('[BUILD] Run with: node dist/server.cjs');
console.log('[BUILD] Done!');
