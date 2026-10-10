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

// Reading the machine's network state. Nothing here changes anything.

'use strict';

const { runPs, runCmd, spawnPs } = require('./ps');
const { buildInterfaces, parseFirewall } = require('./netinfo');

async function readInterfaces(opts) {
  const r = await runPs('interfaces.ps1', null, 45000);
  if (!r.stdout) return { ok: false, interfaces: [], error: r.stderr || 'no answer from PowerShell' };
  try {
    return { ok: true, interfaces: buildInterfaces(JSON.parse(r.stdout), opts) };
  } catch (e) {
    return { ok: false, interfaces: [], error: 'unreadable answer from PowerShell' };
  }
}

async function readFirewall() {
  const r = await runPs(
    'Get-NetFirewallProfile -All | ForEach-Object { "$($_.Name)=$($_.Enabled)" }');
  return parseFirewall(r.stdout);
}

async function readAll(opts) {
  const [ifs, fw] = await Promise.all([readInterfaces(opts), readFirewall()]);
  return { ok: ifs.ok, error: ifs.error || '', interfaces: ifs.interfaces, firewall: fw };
}

// ── Diagnostics: each gateway ─────────────────────────────────────────────

async function ping(host) {
  const r = await runCmd('ping', ['-n', '1', '-w', '1200', host], 5000);
  // ping exits 0 when the echo came back. On some Windows builds an
  // "unreachable" reply from the gateway also exits 0, so the TTL= of a real
  // answer is required as well (TTL is not translated).
  return r.ok && /TTL=/i.test(r.stdout);
}

// Each adapter's gateway answering a ping. (Internet access per adapter
// comes from Windows itself, read with the adapters: see netinfo.js.)
async function diagnose(gateways) {
  const list = (gateways || []).filter(g => g && g.alias && g.gateway).slice(0, 16);
  const gw = await Promise.all(list.map(g => ping(g.gateway)));
  const byAlias = {};
  list.forEach((g, i) => { byAlias[g.alias] = gw[i]; });
  return { gateways: byAlias };
}

// ── Change watcher (lives as long as the window) ──────────────────────────

let watcher = null;
let stopped = false;

function startWatcher(onChange) {
  stopped = false;
  const launch = () => {
    if (stopped) return;
    try {
      watcher = spawnPs('watch.ps1', line => { if (line === 'CHANGED') onChange(); });
      watcher.on('exit', () => { watcher = null; if (!stopped) setTimeout(launch, 5000); });
      watcher.on('error', () => { watcher = null; });
    } catch (_) { watcher = null; }
  };
  launch();
}

function stopWatcher() {
  stopped = true;
  if (watcher) { try { watcher.kill(); } catch (_) {} watcher = null; }
}

module.exports = { readAll, diagnose, startWatcher, stopWatcher };
