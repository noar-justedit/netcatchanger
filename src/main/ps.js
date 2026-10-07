/*
 * NetCatChanger — Windows network profile manager and firewall control
 * Copyright (C) 2026 Just Edit (Arnaud Augst)
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */

// Running PowerShell and the plain Windows tools (netsh, ipconfig, ping).
//
// Three rules, all inherited from 2.x where each one was paid for once:
//  1. Never a command line glued together from strings: every program gets a
//     LIST of arguments, so an adapter called "Bob's Wi-Fi" cannot break it.
//  2. A value typed by the user (an adapter name, an address) reaches a
//     PowerShell script through an ENVIRONMENT VARIABLE, never pasted into
//     the script text. Nothing in a name can then be read as code.
//  3. Success is the EXIT CODE, never "stderr is empty": PowerShell writes
//     its warnings to stderr too, and some cmdlets fail without a word.
//
// Every program is called by its full path in System32. The app runs as
// administrator, and Windows looks in the current folder first when given a
// bare name: a stray powershell.exe lying there would run with full rights.

'use strict';

const { execFile, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const SYS32 = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32');
const EXE = {
  powershell: path.join(SYS32, 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
  netsh:      path.join(SYS32, 'netsh.exe'),
  ipconfig:   path.join(SYS32, 'ipconfig.exe'),
  ping:       path.join(SYS32, 'PING.EXE'),
};
const PS_ARGS = ['-NoProfile', '-NonInteractive', '-Command'];

const scriptCache = {};
function script(name) {
  if (!scriptCache[name]) {
    // Read by Node, which sees inside the asar archive; PowerShell would not.
    scriptCache[name] = fs.readFileSync(path.join(__dirname, 'ps', name), 'utf8')
      .replace(/^\uFEFF/, '');
  }
  return scriptCache[name];
}

function run(exe, args, opts = {}) {
  return new Promise(resolve => {
    execFile(exe, args, {
      windowsHide: true,
      encoding: 'buffer',
      maxBuffer: 16 * 1024 * 1024,
      timeout: opts.timeout || 30000,
      env: Object.assign({}, process.env, opts.env || {}),
    }, (err, stdout, stderr) => {
      const code = err ? (typeof err.code === 'number' ? err.code : -1) : 0;
      resolve({
        ok: code === 0,
        code,
        stdout: Buffer.from(stdout || '').toString('utf8').trim(),
        stderr: (Buffer.from(stderr || '').toString('utf8') ||
                 (err && typeof err.code !== 'number' ? String(err.message) : '')).trim(),
      });
    });
  });
}

// A read-only PowerShell script (by file name in ./ps, or inline text).
function runPs(nameOrText, env, timeout) {
  const text = nameOrText.endsWith('.ps1') ? script(nameOrText) : nameOrText;
  return run(EXE.powershell, PS_ARGS.concat([text]), { env, timeout });
}

// A state-changing PowerShell command: any terminating error comes back as
// exit code 1 with its message, so { ok } is the truth.
async function runPsAction(cmd, env, timeout) {
  const wrapped = "$ErrorActionPreference='Stop'; try { " + cmd +
    " } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }; exit 0";
  const r = await run(EXE.powershell, PS_ARGS.concat([wrapped]), { env, timeout });
  return { ok: r.ok, message: r.stderr };
}

// netsh / ipconfig / ping, by name, with a list of arguments.
function runCmd(tool, args, timeout) {
  if (!EXE[tool] || tool === 'powershell') {
    return Promise.resolve({ ok: false, code: -1, stdout: '', stderr: 'unknown tool' });
  }
  return run(EXE[tool], args, { timeout });
}

// A long-lived PowerShell script; `onLine` gets each line it prints.
function spawnPs(name, onLine) {
  const child = spawn(EXE.powershell, PS_ARGS.concat([script(name)]), {
    windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'],
  });
  let buf = '';
  child.stdout.on('data', d => {
    buf += d.toString('utf8');
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) onLine(line);
    }
  });
  return child;
}

module.exports = { runPs, runPsAction, runCmd, spawnPs, EXE };
