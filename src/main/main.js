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

'use strict';

const { app, BrowserWindow, ipcMain, shell, screen, net } = require('electron');
const path = require('path');
const { fileURLToPath } = require('url');
const store = require('./store');
const netdata = require('./netdata');
const actions = require('./actions');
const { semverGt, ipSnapshot, validIp, validMask, predictVpnExit, parseWgDump, tunnelHealth,
        sendsEverything, vpnState } = require('./netinfo');
const vpn = require('./vpn');

const DEV = process.argv.includes('--dev');
const GITHUB_URL = 'https://github.com/noar-justedit/netcatchanger';
const UPDATE_URL = 'https://raw.githubusercontent.com/noar-justedit/netcatchanger/main/version.json';
const PAGE_BG = '#0a0b0e';

// One window, one instance: a second launch brings the first one forward.
if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

// Chromium's own caches go to %LOCALAPPDATA%\NetCatChanger, away from the
// settings folder that 2.x users know (%APPDATA%\NetCatChanger).
if (process.env.LOCALAPPDATA) {
  app.setPath('userData', path.join(process.env.LOCALAPPDATA, 'NetCatChanger'));
}

let win = null;
let cfg = store.loadConfig();
store.setLogEnabled(cfg.log_enabled !== false);

// Only these addresses ever leave the app for the browser: the window runs
// with administrator rights and must not become a way to open anything else.
function openExternalSafely(url) {
  if (typeof url === 'string' && (url === GITHUB_URL || url.startsWith(GITHUB_URL + '/'))) {
    shell.openExternal(url);
  }
}

function validGeometry(g) {
  if (!g || typeof g !== 'object') return null;
  const { x, y, width, height } = g;
  if (![x, y, width, height].every(Number.isFinite)) return null;
  // Still on a connected screen? (a laptop unplugged from its second monitor)
  const visible = screen.getAllDisplays().some(d => {
    const a = d.workArea;
    return x + 80 > a.x && x < a.x + a.width - 80 && y >= a.y - 10 && y < a.y + a.height - 60;
  });
  return visible ? { x, y, width, height } : null;
}

function createWindow() {
  const g = validGeometry(cfg.geometry);
  win = new BrowserWindow(Object.assign({
    width: 900, height: 720, minWidth: 760, minHeight: 560,
    backgroundColor: PAGE_BG,
    show: false,
    titleBarStyle: 'hidden',          // our own title bar, as in ingesto / syncto
    autoHideMenuBar: true,
    title: 'NetCatChanger',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  }, g || {}));
  win.removeMenu();

  // The page holds the whole IPC surface, with administrator rights behind
  // it: it must never become a page we did not write.
  const OWN_PAGE = path.join(__dirname, '..', 'renderer', 'index.html');
  win.webContents.setWindowOpenHandler(({ url }) => { openExternalSafely(url); return { action: 'deny' }; });
  const blockNavigation = (e, url) => {
    let own = false;
    try { own = url.startsWith('file://') && path.normalize(fileURLToPath(url)) === path.normalize(OWN_PAGE); }
    catch (_) {}
    if (!own) e.preventDefault();
  };
  win.webContents.on('will-navigate', blockNavigation);
  win.webContents.on('will-redirect', blockNavigation);
  win.webContents.on('will-attach-webview', e => e.preventDefault());
  win.webContents.session.setPermissionRequestHandler((_wc, _perm, cb) => cb(false));
  win.webContents.session.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: Object.assign({}, details.responseHeaders, {
        'Content-Security-Policy': [
          "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
          "img-src 'self' data:; font-src 'self'; connect-src 'none'; " +
          "form-action 'none'; base-uri 'none'; frame-ancestors 'none'",
        ],
      }),
    });
  });

  win.loadFile(OWN_PAGE);
  win.webContents.once('did-finish-load', () => setTimeout(checkForUpdate, 1500));
  win.once('ready-to-show', () => {
    win.show();
    if (DEV) win.webContents.openDevTools({ mode: 'detach' });
  });

  const keepGeometry = () => {
    if (win && !win.isMaximized() && !win.isMinimized()) cfg.geometry = win.getBounds();
  };
  win.on('close', () => { keepGeometry(); store.saveConfig(cfg); });
  win.on('closed', () => { win = null; });

  netdata.startWatcher(() => { if (win) win.webContents.send('net-changed'); });
}

app.on('second-instance', () => {
  if (win) { if (win.isMinimized()) win.restore(); win.focus(); }
});

// No tray, nothing resident: closing the window quits the app, and the
// change watcher goes with it.
app.on('window-all-closed', () => { netdata.stopWatcher(); app.quit(); });

// An IP change still waiting for "Keep" when the app closes is put back
// first: the app must never leave a card on settings nobody confirmed.
let quitting = false;
app.on('before-quit', async e => {
  netdata.stopWatcher();
  if (quitting || !pendingIp.size) return;
  e.preventDefault();
  quitting = true;
  for (const [guid, p] of pendingIp) {
    await actions.restoreIp(p.alias, p.snap);
    store.logEvent('ipconfig', `${p.alias} : reverted (app closed before confirming)`);
    pendingIp.delete(guid);
  }
  app.quit();
});

app.whenReady().then(() => {
  store.logEvent('session', `start v${app.getVersion()}`);
  createWindow();
});
app.on('will-quit', () => store.logEvent('session', 'exit'));

// ── IPC: a closed list of what the page may ask ───────────────────────────

ipcMain.handle('app-info', () => ({
  version: app.getVersion(),
  platform: process.platform,
  github: GITHUB_URL,
}));
// The adapters of the last reading. An action may only name one of them:
// the window cannot make the app touch a card it never showed.
let known = new Map();          // guid -> adapter
let tunnelsSeen = [];          // names of the WireGuard tunnels last seen running
ipcMain.handle('net-read', async () => {
  const [data, wg] = await Promise.all([netdata.readAll(), vpn.wireguard()]);
  if (data.ok) known = new Map(data.interfaces.filter(a => a.guid).map(a => [a.guid, a]));
  const now = Date.now() / 1000;
  const tunnels = wg.tunnels.map(t => {
    const peers = parseWgDump(t.dump);
    return Object.assign({ name: t.name, endpoint: peers.length ? peers[0].endpoint : '',
                           sendsEverything: sendsEverything(peers) }, tunnelHealth(peers, now));
  });
  tunnelsSeen = tunnels.map(t => t.name);

  // Has Windows put things back on its own (restart, card re-enabled)?
  let endedByWindows = false;
  let state = 'off';
  if (data.ok) {
    state = vpnState(cfg.vpn, data.interfaces).state;
    if (state === 'ended') {
      store.logEvent('vpn', `ended by Windows (${cfg.vpn.method}), ${cfg.vpn.retreat.alias} already back`);
      cfg.vpn = null;
      store.saveConfig(cfg);
      endedByWindows = true;
      state = 'off';
    }
  } else if (cfg.vpn && cfg.vpn.active) {
    state = 'on';
  }
  data.vpn = {
    state, endedByWindows,
    journal: cfg.vpn || null,
    prefs: cfg.vpn_prefs || null,
    exit: data.ok ? predictVpnExit(data.interfaces) : null,
    wireguard: { installed: wg.installed, tunnels },
  };
  return data;
});

const GUID_RE = /^\{?[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}?$/;   // braces or not, as Windows prints it
function adapterOf(guid) {
  return typeof guid === 'string' && GUID_RE.test(guid) ? known.get(guid) || null : null;
}
const NOT_FOUND = { ok: false, message: 'This adapter is no longer there. Refresh and try again.' };

ipcMain.handle('act-profile', (_e, guid, category) => {
  const a = adapterOf(guid);
  return a ? actions.setProfile(guid, a.alias, category) : NOT_FOUND;
});
ipcMain.handle('act-adapter-enabled', (_e, guid, enable) => {
  const a = adapterOf(guid);
  return a ? actions.setAdapterEnabled(guid, a.alias, enable === true) : NOT_FOUND;
});
ipcMain.handle('act-rename', (_e, guid, newName) => {
  const a = adapterOf(guid);
  return a ? actions.renameAdapter(guid, a.alias, newName) : NOT_FOUND;
});
ipcMain.handle('act-renew', (_e, guid) => {
  const a = adapterOf(guid);
  return a ? actions.renewDhcp(a.alias) : NOT_FOUND;
});
ipcMain.handle('act-flush-dns', () => actions.flushDns());

// ── VPN exit ──────────────────────────────────────────────────────────────

const saveJournal = j => { cfg.vpn = j; return store.saveConfig(cfg); };

// The window only says which connection the VPN must use. The one put aside
// is the one WireGuard uses now; the method is always the priority one
// (Noar, 10.2026: simple for non-specialists; it keeps the other connection's
// local network, and a restart of Windows undoes it).
ipcMain.handle('vpn-on', async (_e, preferredGuid) => {
  if (cfg.vpn && cfg.vpn.active) return { ok: true };
  const pref = adapterOf(preferredGuid);
  if (!pref || pref.tunnel) return { ok: false, message: 'Choose a connection' };
  const exit = predictVpnExit([...known.values()]);
  const ret = exit ? adapterOf(exit.guid) : null;
  if (!ret || ret.guid === pref.guid) return { ok: false, message: `The VPN already goes through ${pref.alias}` };
  cfg.vpn_prefs = { method: 'metric', preferred: { guid: pref.guid, alias: pref.alias } };
  return vpn.turnOn({ method: 'metric', preferred: { guid: pref.guid, alias: pref.alias },
                      retreat: { guid: ret.guid, alias: ret.alias } }, saveJournal);
});
ipcMain.handle('vpn-off', () => vpn.turnOff(cfg.vpn, saveJournal));
ipcMain.handle('vpn-restart-tunnel', (_e, name) =>
  tunnelsSeen.includes(name) ? vpn.restartTunnel(name) : { ok: false, message: 'This tunnel is not running' });
ipcMain.handle('act-firewall', (_e, enable, profiles) =>
  actions.setFirewall(enable === true, Array.isArray(profiles) ? profiles : null));

// ── IP settings: apply, then keep or put back ─────────────────────────────

const pendingIp = new Map();     // guid -> { alias, snap }, until Keep / Revert

ipcMain.handle('ip-apply', async (_e, guid, c) => {
  const a = adapterOf(guid);
  if (!a) return NOT_FOUND;
  if (!c || (c.mode !== 'dhcp' && c.mode !== 'static')) return { ok: false, message: 'Unknown mode' };
  const snap = pendingIp.has(guid) ? pendingIp.get(guid).snap : ipSnapshot(a);
  let r;
  if (c.mode === 'dhcp') {
    r = await actions.applyDhcp(a.alias, a.dhcp);
  } else {
    const conf = {
      ip: String(c.ip || '').trim(), mask: String(c.mask || '').trim(), gw: String(c.gw || '').trim(),
      dns: (Array.isArray(c.dns) ? c.dns : []).slice(0, 2).map(d => String(d || '').trim()).filter(Boolean),
    };
    r = await actions.applyStatic(a.alias, conf);
  }
  if (r.ok) {
    pendingIp.set(guid, { alias: a.alias, snap });
  } else {
    // Half-applied is the worst state: put the previous settings back now.
    await actions.restoreIp(a.alias, snap);
  }
  return r;
});
ipcMain.handle('ip-keep', (_e, guid) => {
  const p = pendingIp.get(guid);
  if (!p) return { ok: false };
  pendingIp.delete(guid);
  store.logEvent('ipconfig', `${p.alias} : confirmed by user`);
  return { ok: true };
});
ipcMain.handle('ip-revert', async (_e, guid, why) => {
  const p = pendingIp.get(guid);
  if (!p) return { ok: false, message: 'Nothing to put back' };
  pendingIp.delete(guid);
  const r = await actions.restoreIp(p.alias, p.snap);
  store.logEvent('ipconfig', `${p.alias} : reverted (${why === 'timeout' ? 'not confirmed' : 'by user'})`);
  return r;
});

// ── Presets (same format as 2.x: { name, mode, ip, mask, gw, dns:[..] }) ──

function cleanPreset(p) {
  if (!p || typeof p.name !== 'string') return null;
  const name = p.name.trim();
  if (!name || name.length > 60 || /[\u0000-\u001f\u007f]/.test(name)) return null;
  if (p.mode === 'dhcp') return { name, mode: 'dhcp', ip: '', mask: '', gw: '', dns: [] };
  if (p.mode !== 'static') return null;
  const ip = String(p.ip || '').trim(), mask = String(p.mask || '').trim(), gw = String(p.gw || '').trim();
  const dns = (Array.isArray(p.dns) ? p.dns : []).map(d => String(d || '').trim()).filter(Boolean).slice(0, 2);
  if (!validIp(ip) || !validMask(mask) || (gw && !validIp(gw)) || dns.some(d => !validIp(d))) return null;
  return { name, mode: 'static', ip, mask, gw, dns };
}
ipcMain.handle('presets-get', () => (cfg.presets || []).map(cleanPreset).filter(Boolean));
ipcMain.handle('preset-save', (_e, p) => {
  const c = cleanPreset(p);
  if (!c) return { ok: false, message: 'Invalid preset' };
  const list = (cfg.presets || []).filter(x => x && x.name !== c.name);
  if (list.length >= 50) return { ok: false, message: 'Too many presets (50 at most)' };
  list.push(c);
  cfg.presets = list;
  return { ok: store.saveConfig(cfg), presets: list };
});
ipcMain.handle('preset-delete', (_e, name) => {
  cfg.presets = (cfg.presets || []).filter(x => x && x.name !== name);
  return { ok: store.saveConfig(cfg), presets: cfg.presets };
});

// ── Settings ──────────────────────────────────────────────────────────────

ipcMain.handle('get-settings', () => ({
  confirm_switch: cfg.confirm_switch === true,
  log_enabled: cfg.log_enabled !== false,
}));
ipcMain.handle('set-setting', (_e, key, value) => {
  if (!['confirm_switch', 'log_enabled'].includes(key) || typeof value !== 'boolean') return { ok: false };
  cfg[key] = value;
  if (key === 'log_enabled') store.setLogEnabled(value);
  return { ok: store.saveConfig(cfg) };
});

// ── Update check: once at launch, silent on any failure ───────────────────
// Through Chromium's network stack (net.fetch), which follows the system
// proxy settings; Node's own fetch could not even reach GitHub on SERVAL.

async function checkForUpdate() {
  try {
    const res = await net.fetch(UPDATE_URL, { cache: 'no-store' });
    if (!res.ok) return;
    const data = JSON.parse(await res.text());
    const ver = String(data.version || '');
    if (!/^\d+\.\d+\.\d+$/.test(ver)) return;
    // version.json on GitHub is untrusted input: only our own releases page
    // is ever opened, whatever it says.
    let url = String(data.url || '');
    if (!(url === GITHUB_URL || url.startsWith(GITHUB_URL + '/'))) url = GITHUB_URL + '/releases/latest';
    if (semverGt(ver, app.getVersion()) && cfg.update_dismissed !== ver && win) {
      win.webContents.send('update-available', { version: ver, url });
    }
  } catch (_) {}
}
ipcMain.handle('update-dismiss', (_e, ver) => {
  if (typeof ver === 'string' && /^\d+\.\d+\.\d+$/.test(ver)) { cfg.update_dismissed = ver; store.saveConfig(cfg); }
  return true;
});
ipcMain.handle('net-diagnose', (_e, gateways) => {
  if (!Array.isArray(gateways)) return null;
  const clean = gateways
    .filter(g => g && typeof g.alias === 'string' && typeof g.gateway === 'string')
    .filter(g => /^[0-9a-fA-F:.]{2,45}$/.test(g.gateway))   // an address, nothing else
    .map(g => ({ alias: g.alias, gateway: g.gateway }));
  return netdata.diagnose(clean);
});
ipcMain.handle('open-external', (_e, url) => openExternalSafely(url));
ipcMain.handle('open-log', async () => {
  const err = await shell.openPath(store.LOG_PATH);
  return !err;
});

ipcMain.on('win-minimize', () => win && win.minimize());
ipcMain.on('win-maximize', () => { if (!win) return; win.isMaximized() ? win.unmaximize() : win.maximize(); });
ipcMain.on('win-close', () => win && win.close());
