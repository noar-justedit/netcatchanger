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
  return cfg;
}

function saveConfig(cfg) {
  try {
    fs.mkdirSync(DIR, { recursive: true });
    const tmp = CONFIG_PATH + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(cfg, null, 2), 'utf8');
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
    fs.mkdirSync(DIR, { recursive: true });
    fs.appendFileSync(LOG_PATH, `${stamp()} | ${String(kind).padEnd(9)} | ${msg}\n`, 'utf8');
  } catch (_) {}
}

module.exports = { loadConfig, saveConfig, logEvent, setLogEnabled, CONFIG_PATH, LOG_PATH, DIR };
