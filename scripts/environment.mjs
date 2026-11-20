import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { mkdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

export const root = fileURLToPath(new URL('../', import.meta.url));
export const env = {
  ...process.env,
  UV_CACHE_DIR: path.join(root, '.cache/uv'),
  UV_PYTHON_INSTALL_DIR: path.join(root, '.python'),
  UV_PROJECT_ENVIRONMENT: path.join(root, '.venv'),
  HF_HOME: path.join(root, '.data/models'),
  HF_HUB_CACHE: path.join(root, '.data/models/hub'),
  TMPDIR: path.join(root, '.data/tmp'),
  XDG_CACHE_HOME: path.join(root, '.cache'),
  npm_config_cache: path.join(root, '.cache/npm'),
};

for (const directory of [env.UV_CACHE_DIR, env.TMPDIR]) {
  mkdirSync(directory, { recursive: true });
}

export function run(command, args, cwd = root) {
  const result = spawnSync(command, args, { cwd, env, stdio: 'inherit' });
  if (result.error) {
    console.error(`Could not run ${command}: ${result.error.message}`);
    if (command === 'uv') console.error('Install uv first: https://docs.astral.sh/uv/getting-started/installation/');
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status ?? 1);
}
