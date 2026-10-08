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

// VPN exit: make WireGuard leave through a chosen adapter (the Wi-Fi) when
// the other one (an event network's Ethernet that blocks UDP) would win.
//
// Two methods, chosen in the window:
//  - "metric" (recommended): the set-aside adapter gets a very low priority
//    (InterfaceMetric 9000), so WireGuard picks the other one. It keeps its
//    address and its local network. The change is written to Windows'
//    ACTIVE store only: a restart of Windows puts the original priority back
//    by itself, so a crash or a forgotten mode can never stick.
//  - "disable": the set-aside adapter is switched off. Certain, but its local
//    network is lost, and Windows keeps it off after a restart.
//
// The mode survives closing the app (Noar's decision). What was changed is
// written in config.json BEFORE it is changed (the journal), so the app can
// always put it back, and recognises at the next opening whether Windows
// already did.

'use strict';

const { runPs, runPsAction } = require('./ps');
const { logEvent } = require('./store');
const { RETREAT_METRIC, ROUTE_METRIC } = require('./netinfo');

const PICK = "$a = @(Get-NetAdapter | Where-Object { \"$($_.InterfaceGuid)\" -eq $env:NCC_GUID }); " +
             "if ($a.Count -ne 1) { throw 'Adapter not found (unplugged or removed?)' }; ";

function short(msg) {
  return String(msg || '').split(/\r?\n/).map(s => s.trim()).filter(Boolean)[0] || '';
}

// The priority of one adapter as it is now, IPv4 and IPv6, to put it back.
async function readMetrics(guid) {
  const r = await runPs(
    "$ErrorActionPreference='SilentlyContinue'; " + PICK.replace("throw 'Adapter not found (unplugged or removed?)'", "exit 1") +
    "$o = @{}; foreach ($f in 'IPv4','IPv6') { " +
    "  $i = Get-NetIPInterface -InterfaceIndex $a[0].ifIndex -AddressFamily $f; " +
    "  if ($i) { $o[$f] = @{ metric = [int]$i.InterfaceMetric; auto = (\"$($i.AutomaticMetric)\" -eq 'Enabled') } } }; " +
    "ConvertTo-Json -InputObject $o -Compress",
    { NCC_GUID: guid });
  try {
    const o = JSON.parse(r.stdout);
    const out = {};
    for (const f of ['IPv4', 'IPv6']) {
      if (o[f] && Number.isInteger(o[f].metric)) out[f] = { metric: o[f].metric, auto: o[f].auto === true };
    }
    return out.IPv4 ? out : null;
  } catch (_) { return null; }
}

// Active store only: gone at the next restart of Windows.
async function setMetric(guid, metric) {
  return runPsAction(PICK +
    "Set-NetIPInterface -InterfaceIndex $a[0].ifIndex -AddressFamily IPv4 " +
    "-InterfaceMetric ([int]$env:NCC_METRIC) -PolicyStore ActiveStore; " +
    // IPv6 may be unbound from this card: then there is nothing to change.
    "try { Set-NetIPInterface -InterfaceIndex $a[0].ifIndex -AddressFamily IPv6 " +
    "-InterfaceMetric ([int]$env:NCC_METRIC) -PolicyStore ActiveStore -ErrorAction Stop } catch {}",
    { NCC_GUID: guid, NCC_METRIC: String(metric) });
}

async function restoreMetrics(guid, snap) {
  const parts = [];
  for (const f of ['IPv4', 'IPv6']) {
    const m = snap && snap[f];
    if (!m) continue;
    const set = m.auto
      ? `-AutomaticMetric Enabled`
      : `-InterfaceMetric ${Number.isInteger(m.metric) ? m.metric : 0}`;
    const cmd = `Set-NetIPInterface -InterfaceIndex $a[0].ifIndex -AddressFamily ${f} ${set} -PolicyStore ActiveStore`;
    parts.push(f === 'IPv4' ? cmd + '; ' : `try { ${cmd} -ErrorAction Stop } catch {}; `);
  }
  if (!parts.length) {
    // No snapshot (should not happen): automatic priority is Windows' default.
    parts.push('Set-NetIPInterface -InterfaceIndex $a[0].ifIndex -AutomaticMetric Enabled -PolicyStore ActiveStore; ');
  }
  return runPsAction(PICK + parts.join(''), { NCC_GUID: guid });
}

async function setEnabled(guid, enable) {
  return runPsAction(PICK + `$a | ${enable ? 'Enable' : 'Disable'}-NetAdapter -Confirm:$false`,
                     { NCC_GUID: guid });
}

// prefs: { method, preferred:{guid,alias}, retreat:{guid,alias} }
// saveJournal(j) writes config.json; it is called BEFORE Windows is touched.
async function turnOn(prefs, saveJournal) {
  const { method, retreat, preferred } = prefs;
  let snapshot = null;
  if (method === 'metric') {
    snapshot = await readMetrics(retreat.guid);
    if (!snapshot) return { ok: false, message: `Could not read the priority of ${retreat.alias}` };
  }
  const journal = { active: true, method, preferred, retreat, snapshot, since: new Date().toISOString() };
  if (!saveJournal(journal)) return { ok: false, message: 'Could not write the settings file' };

  const r = method === 'metric' ? await setMetric(retreat.guid, RETREAT_METRIC)
                                : await setEnabled(retreat.guid, false);
  logEvent('vpn', `on (${method}) via ${preferred.alias}, ${retreat.alias} set aside : ` +
                  `${r.ok ? 'ok' : 'FAILED ' + short(r.message)}`);
  if (!r.ok) {
    // Leave nothing half-done: put back whatever may have changed.
    if (method === 'metric') await restoreMetrics(retreat.guid, snapshot);
    saveJournal(null);
    return { ok: false, message: short(r.message) };
  }
  return { ok: true, journal };
}

// "Use for Internet" (3.1.0), also what the VPN card's "Use another
// connection" does now. plan = { preferred:{guid,alias}, aside:[{guid,alias}] }.
// Every priority touched is read and written in the journal first.
async function routeOn(plan, saveJournal) {
  const touched = [plan.preferred].concat(plan.aside || []);
  const changed = [];
  for (const t of touched) {
    const snapshot = await readMetrics(t.guid);
    if (!snapshot) return { ok: false, message: `Could not read the priority of ${t.alias}` };
    changed.push({ guid: t.guid, alias: t.alias, snapshot });
  }
  const journal = { active: true, method: 'route', preferred: plan.preferred, changed,
                    since: new Date().toISOString() };
  if (!saveJournal(journal)) return { ok: false, message: 'Could not write the settings file' };
  let r = await setMetric(plan.preferred.guid, ROUTE_METRIC);
  for (const a of plan.aside || []) {
    if (!r.ok) break;
    r = await setMetric(a.guid, RETREAT_METRIC);
  }
  logEvent('route', `Internet via ${plan.preferred.alias}` +
    ((plan.aside || []).length ? `, set aside ${plan.aside.map(a => a.alias).join(', ')}` : '') +
    ` : ${r.ok ? 'ok' : 'FAILED ' + short(r.message)}`);
  if (!r.ok) {
    for (const c of changed) await restoreMetrics(c.guid, c.snapshot);
    saveJournal(null);
    return { ok: false, message: short(r.message) };
  }
  return { ok: true, journal };
}

async function turnOff(journal, saveJournal) {
  if (journal && journal.method === 'route') {
    let ok = true, message = '';
    for (const c of journal.changed || []) {
      const r = await restoreMetrics(c.guid, c.snapshot);
      // A card that is gone took its priority with it: nothing to put back.
      if (!r.ok && !/not found/i.test(r.message)) { ok = false; message = r.message; }
    }
    logEvent('route', `automatic again (was ${journal.preferred.alias}) : ${ok ? 'ok' : 'FAILED ' + short(message)}`);
    if (ok) saveJournal(null);
    return { ok, message: short(message) };
  }
  if (!journal || !journal.retreat) { saveJournal(null); return { ok: true }; }
  const { method, retreat } = journal;
  const r = method === 'metric' ? await restoreMetrics(retreat.guid, journal.snapshot)
                                : await setEnabled(retreat.guid, true);
  logEvent('vpn', `off (${method}), ${retreat.alias} back : ${r.ok ? 'ok' : 'FAILED ' + short(r.message)}`);
  if (r.ok) saveJournal(null);
  return { ok: r.ok, message: short(r.message) };
}

// Running WireGuard tunnels and their `wg show dump` (raw; parsed by netinfo).
async function wireguard() {
  const r = await runPs('wireguard.ps1', null, 20000);
  try {
    const o = JSON.parse(r.stdout);
    const tunnels = (Array.isArray(o.tunnels) ? o.tunnels : (o.tunnels ? [o.tunnels] : []))
      .filter(t => t && typeof t.name === 'string')
      .map(t => ({ name: t.name, dump: String(t.dump || '') }));
    return { installed: o.installed === true, tunnels };
  } catch (_) { return { installed: false, tunnels: [] }; }
}

// WireGuard tunnel names: letters, digits and = + . _ - , 32 at most.
const TUNNEL_RE = /^[A-Za-z0-9_=+.-]{1,32}$/;
async function restartTunnel(name) {
  if (!TUNNEL_RE.test(String(name || ''))) return { ok: false, message: 'Unknown tunnel' };
  const r = await runPsAction("Restart-Service -Name ('WireGuardTunnel$' + $env:NCC_TUNNEL) -Force",
                              { NCC_TUNNEL: name }, 30000);
  logEvent('vpn', `restart tunnel ${name} : ${r.ok ? 'ok' : 'FAILED ' + short(r.message)}`);
  return { ok: r.ok, message: short(r.message) };
}

module.exports = { turnOn, routeOn, turnOff, wireguard, restartTunnel, readMetrics, TUNNEL_RE };
