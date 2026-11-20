import { spawn } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { env, root, run } from './environment.mjs';

// Install only when dependencies change. All generated state stays in this repo.
run('uv', ['sync', '--frozen', '--no-dev']);
const frontend = path.join(root, 'frontend');
const fingerprint = createHash('sha256')
  .update(readFileSync(path.join(frontend, 'package-lock.json')))
  .update(readFileSync(path.join(frontend, 'package.json')))
  .digest('hex');
const stamp = path.join(frontend, 'node_modules/.dependency-hash');
if (!existsSync(stamp) || readFileSync(stamp, 'utf8') !== fingerprint) {
  run('npm', ['ci', '--no-audit', '--no-fund'], frontend);
  writeFileSync(stamp, fingerprint);
}
run('npm', ['run', 'build'], frontend);

const port = process.env.PORT || '8000';
if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) {
  console.error('PORT must be a number between 1 and 65535.');
  process.exit(1);
}
console.log(`\nFast Transcriber: http://127.0.0.1:${port}\nPress Ctrl+C to stop.\n`);
const server = spawn('uv', [
  'run', '--frozen', '--no-sync', 'uvicorn', 'backend.main:app',
  '--host', '127.0.0.1', '--port', port, '--timeout-graceful-shutdown', '5',
], { cwd: root, env, stdio: 'inherit' });

// Forward termination when started outside an interactive terminal, too.
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.kill(signal));
}
server.on('error', (error) => { console.error(error.message); process.exit(1); });
server.on('exit', (code, signal) => process.exit(code ?? (signal === 'SIGINT' ? 0 : 1)));
