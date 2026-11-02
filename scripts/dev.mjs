import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
const executable = process.env.PYTHON_EXECUTABLE || (process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
if (!existsSync(executable)) throw new Error('Configure the project Python environment first, or set PYTHON_EXECUTABLE.');
const child = spawn(executable, ['-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', process.env.PORT || '8000'], { stdio: 'inherit' });
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
child.on('exit', code => process.exit(code || 0));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
