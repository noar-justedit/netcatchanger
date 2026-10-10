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

// Settings and session log, in the SAME place and format as 2.x
// (%APPDATA%\NetCatChanger\config.json and session.log), so an upgrade keeps
// the IP presets and the history of changes.

'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');

const DIR = path.join(process.env.APPDATA || os.homedir(), 'NetCatChanger');
const CONFIG_PATH = path.join(DIR, 'config.json');
const LOG_PATH = path.join(DIR, 'session.log');

// Keys that 2.x wrote and 3.x no longer uses (tray, autostart, timed
// firewall) are simply ignored: they stay in the file, harmless.
const DEFAULTS = {
  geometry: null,           // { x, y, width, height }
  log_enabled: true,
  confirm_switch: false,
  update_dismissed: '',
  presets: [],              // [{ name, mode, ip, mask, gw, dns:[..] }]
  vpn_prefs: null,          // { method, preferred:{guid,alias} }: the last connection chosen for the VPN
  vpn: null,                // journal of the VPN exit while it is on (see vpn.js)
};

function loadConfig() {
  const cfg = Object.assign({}, DEFAULTS);
  try {
    const data = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    if (data && typeof data === 'object' && !Array.isArray(data)) Object.assign(cfg, data);
  } catch (_) {}
  // 2.x stored the geometry as a Tk string ("880x700+10+10"); that format
  // is not reused, the window simply opens centred once.
  if (typeof cfg.geometry === 'string') cfg.geometry = null;
  if (!Array.isArray(cfg.presets)) cfg.presets = [];
  // The folder belongs to the user while the app runs as administrator:
  // what comes back from it is checked before anything acts on it.
  if (!Array.isArray(cfg.secondary)) cfg.secondary = [];
  if (!Array.isArray(cfg.secondary_presets)) cfg.secondary_presets = [];
  if (cfg.vpn !== null && !validJournal(cfg.vpn)) cfg.vpn = null;
  return cfg;
}

const GUID_RE = /^\{?[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}?$/;
const ref = r => !!r && typeof r === 'object' && typeof r.guid === 'string' && GUID_RE.test(r.guid) &&
                 typeof r.alias === 'string' && r.alias.length <= 256;
const metricSnap = s => !!s && typeof s === 'object' && ['IPv4', 'IPv6'].every(f =>
  s[f] === undefined || (s[f] && Number.isInteger(s[f].metric) && s[f].metric >= 0 && s[f].metric <= 9999 &&
                         typeof s[f].auto === 'boolean'));
// A VPN / Internet route journal (vpn.js): the only shapes the app writes.
function validJournal(j) {
  if (!j || typeof j !== 'object' || j.active !== true || !ref(j.preferred)) return false;
  if (j.method === 'route') {
    return Array.isArray(j.changed) && j.changed.length >= 1 && j.changed.length <= 16 &&
           j.changed.every(c => ref(c) && metricSnap(c.snapshot));
  }
  if (j.method === 'metric') return ref(j.retreat) && metricSnap(j.snapshot);
  if (j.method === 'disable') return ref(j.retreat);
  return false;
}

// Never write through a link: a junction or symbolic link put in place of
// the folder or a file would make an administrator write anywhere.
function isLink(p) {
  try { return fs.lstatSync(p).isSymbolicLink(); } catch (_) { return false; }
}
function safeDir() {
  fs.mkdirSync(DIR, { recursive: true });
  return !isLink(DIR);
}

function saveConfig(cfg) {
  try {
    if (!safeDir() || isLink(CONFIG_PATH)) return false;
    const tmp = CONFIG_PATH + '.tmp';
    try { fs.unlinkSync(tmp); } catch (_) {}            // a link is removed, not followed
    fs.writeFileSync(tmp, JSON.stringify(cfg, null, 2), { encoding: 'utf8', flag: 'wx' });
    fs.renameSync(tmp, CONFIG_PATH);    // never a half-written config
    return true;
  } catch (_) { return false; }
}

let logEnabled = true;
function setLogEnabled(on) { logEnabled = !!on; }

function stamp() {
  const d = new Date(), p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
         `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function logEvent(kind, msg) {
  if (!logEnabled) return;
  try {
    if (!safeDir() || isLink(LOG_PATH)) return;
    fs.appendFileSync(LOG_PATH, `${stamp()} | ${String(kind).padEnd(9)} | ${msg}\n`, 'utf8');
  } catch (_) {}
}

module.exports = { loadConfig, saveConfig, logEvent, setLogEnabled, validJournal, CONFIG_PATH, LOG_PATH, DIR };
