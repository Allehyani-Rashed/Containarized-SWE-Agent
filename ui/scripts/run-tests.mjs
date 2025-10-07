import { spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const filename = fileURLToPath(import.meta.url);
const baseDir = dirname(filename);

const rawArgs = process.argv.slice(2);
const vitestArgs = [];

for (const arg of rawArgs) {
  if (arg === '--runInBand' || arg === '--run-in-band' || arg === '-i') {
    vitestArgs.push('--maxWorkers=1');
    vitestArgs.push('--minWorkers=1');
    vitestArgs.push('--fileParallelism=false');
    continue;
  }

  vitestArgs.push(arg);
}

const vitestBin = resolve(baseDir, '../node_modules/.bin/vitest');

const child = spawn(vitestBin, vitestArgs, {
  stdio: 'inherit'
});

child.on('error', (error) => {
  console.error('[vitest] failed to start:', error);
  process.exit(1);
});

child.on('exit', (code, signal) => {
  if (signal) {
    console.error(`[vitest] terminated with signal ${signal}`);
    process.exit(1);
  }

  process.exit(code ?? 1);
});
