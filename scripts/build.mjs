// Package the actual FastAPI-served UI. Backend API routes still need FastAPI.
import { cp, mkdir, readFile, access } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
for (const module of ['app.js', 'financial-format.js']) {
  const check = spawnSync(process.execPath, ['--check', path.join(root, 'static', module)], { stdio: 'inherit' });
  if (check.status !== 0) process.exit(check.status || 1);
}
const universe = JSON.parse(await readFile(path.join(root, 'static/sector-universe.json'), 'utf8'));
if (universe.groups.length !== 16 || universe.groups.some(g => g.stocks.length !== 10)) throw new Error('Invalid approved universe');
for (const group of universe.groups) await access(path.join(root, 'static/sectors', group.id + '.webp'));
for (const animal of ['bull', 'bear']) for (const suffix of ['', '-small']) {
  await access(path.join(root, 'static/hero', animal + '-premium' + suffix + '.webp'));
}
await access(path.join(root, 'static/dashboard-upgrade.css'));
const target = path.join(root, 'dist/terminal');
await mkdir(target, { recursive: true });
await cp(path.join(root, 'static'), path.join(target, 'static'), { recursive: true });
await cp(path.join(root, 'static/index.html'), path.join(target, 'index.html'));
console.log('DIVINE CODE 369: scanner UI packaged in dist/terminal. Serve with the existing FastAPI backend.');
