import { run } from './environment.mjs';

run('uv', ['sync', '--frozen']);
run('uv', ['run', '--frozen', '--no-sync', 'pytest', '-q']);
