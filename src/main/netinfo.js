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

// Pure functions only: no Electron, no PowerShell, no file access. Everything
// that turns raw Windows output into what the window shows lives here, so it
// is covered by test/run-tests.js on any machine, a Mac included.

'use strict';

// ── Small helpers ─────────────────────────────────────────────────────────

function semverGt(a, b) {
  const parse = v => {
    const p = (String(v).match(/\d+/g) || ['0']).slice(0, 3).map(Number);
    while (p.length < 3) p.push(0);
    return p;
  };
  const pa = parse(a), pb = parse(b);
  for (let i = 0; i < 3; i++) {
    if (pa[i] !== pb[i]) return pa[i] > pb[i];
  }
  return false;
}

function prefixToMask(prefix) {
  if (prefix === null || prefix === undefined || prefix === '') return '';
  const p = Number(prefix);
  if (!Number.isInteger(p) || p < 0 || p > 32) return '';
  const v = p === 0 ? 0 : (0xFFFFFFFF << (32 - p)) >>> 0;
  return [24, 16, 8, 0].map(s => (v >>> s) & 0xFF).join('.');
}

function validIp(s) {
  const parts = String(s == null ? '' : s).trim().split('.');
  if (parts.length !== 4) return false;
  return parts.every(p => /^\d{1,3}$/.test(p) && Number(p) <= 255 && String(Number(p)) === p);
}

// A subnet mask: four bytes whose bits are all ones then all zeros
// (255.255.255.0 yes, 255.0.255.0 no, 0.0.0.0 no).
function validMask(s) {
  if (!validIp(s)) return false;
  const n = String(s).trim().split('.').reduce((acc, p) => (acc * 256) + Number(p), 0);
  if (n === 0) return false;
  const inv = (~n) >>> 0;                    // the host part: must be 0…01…1
  return (inv & (inv + 1)) === 0;
}

// The IP settings of one adapter, as read last, kept to put them back if a
// change goes wrong (2.x: capture_ip_config).
function ipSnapshot(a) {
  return {
    dhcp: a.dhcp !== false,
    ip: a.ipv4 || '',
    mask: a.mask || '',
    gw: a.gateway || '',
    dns: Array.isArray(a.dns) ? a.dns.slice(0, 2) : [],
  };
}

function isApipa(ip) {
  return String(ip || '').startsWith('169.254.');
}

// PowerShell single quotes are literal: the only escape is doubling a quote.
// Kept for the rare command that must embed a value; NetCatChanger prefers to
// hand values to PowerShell through environment variables (see ps.js).
function psQuote(s) {
  return "'" + String(s).replace(/'/g, "''") + "'";
}

// ── netsh wlan show interfaces ────────────────────────────────────────────
// netsh translates its field labels ("Radio type" -> "Type de radio",
// "Band" -> "Bande", "Channel" -> "Canal"...), so matching on labels only
// ever worked on an English Windows. Everything here matches the VALUE shape
// instead, which is identical in every locale. A block starts on the line
// whose value is one of the adapter names.
//
// In 2.x this ran inside PowerShell and the test re-implemented it in Python.
// Here the shipped code and the tested code are the same function.

function parseNetshWlan(text, aliases) {
  const names = new Set(aliases || []);
  const blocks = {};
  let cur = null;
  for (const raw of String(text || '').split(/\r?\n/)) {
    const i = raw.indexOf(':');
    if (i < 1) continue;
    const label = raw.slice(0, i).trim();
    const value = raw.slice(i + 1).trim();
    if (!value) continue;

    if (names.has(value) && !(value in blocks)) {
      cur = value;
      blocks[cur] = { signal: -1, radioType: '', band: '', channel: -1 };
      continue;
    }
    if (!cur) continue;
    const b = blocks[cur];

    let m = value.match(/^(\d{1,3})\s*%$/);
    if (m) { b.signal = Number(m[1]); continue; }
    if (value.includes('802.11')) { b.radioType = value; continue; }
    if (/\d+([.,]\d+)?\s*GHz/.test(value)) { b.band = value; continue; }
    // The channel is the only bare integer left once the rate lines are
    // skipped (their label carries the unit: Mbps / Mbit/s / Mbits/s / MBit/s).
    if (!/b(it|ps)/i.test(label) && /^\d{1,3}$/.test(value) && Number(value) <= 233) {
      if (b.channel < 0) b.channel = Number(value);
      continue;
    }
  }
  return blocks;
}

function parseWifiStandard(radioType) {
  const rt = String(radioType || '').toLowerCase().replace(/\s/g, '');
  const table = [
    ['802.11be', 'Wi-Fi 7', '802.11be'], ['802.11ax', 'Wi-Fi 6', '802.11ax'],
    ['802.11ac', 'Wi-Fi 5', '802.11ac'], ['802.11n', 'Wi-Fi 4', '802.11n'],
    ['802.11g', 'Wi-Fi 3', '802.11g'],   ['802.11b', 'Wi-Fi 2', '802.11b'],
    ['802.11a', 'Wi-Fi 1', '802.11a'],
  ];
  for (const [k, gen, std] of table) {
    if (rt.includes(k)) return { gen, std };
  }
  const s = String(radioType || '').trim();
  return s ? { gen: '', std: s } : null;
}

function parseWifiBand(bandStr, channel) {
  // A French Windows prints "2,4 GHz" — hence the comma handling.
  const b = String(bandStr || '').toLowerCase().replace(/,/g, '.');
  const m = b.match(/(\d+(?:\.\d+)?)\s*ghz/);
  if (m) {
    const v = parseFloat(m[1]);
    if (Math.abs(v - 2.4) < 0.3) return '2.4 GHz';
    if (Math.abs(v - 5.0) < 0.6) return '5 GHz';
    if (Math.abs(v - 6.0) < 0.6) return '6 GHz';
    return `${m[1]} GHz`;
  }
  const ch = Number(channel);
  if (ch > 0) {
    if (ch <= 14) return '2.4 GHz';
    if (ch <= 177) return '5 GHz';
    return '6 GHz';
  }
  return '';
}

function parseLinkSpeed(speedStr) {
  const raw = String(speedStr == null ? '' : speedStr).trim();
  if (!raw || raw === '0') return '';
  const s = raw.toLowerCase();
  if (s.includes('gbps') || s.includes('mbps')) {
    return /^0(\.0+)?\s*[gm]bps$/.test(s) ? '' : raw;
  }
  if (s === '0 bps') return '';
  const digits = s.replace(/[^\d]/g, '');
  if (!digits) return raw;
  const bps = Number(digits);
  if (bps >= 10e9) return '10 Gbps';
  if (bps >= 5e9) return '5 Gbps';
  if (bps >= 2.5e9) return '2.5 Gbps';
  if (bps >= 1e9) return '1 Gbps';
  if (bps >= 100e6) return '100 Mbps';
  if (bps >= 10e6) return '10 Mbps';
  if (bps === 0) return '';
  return `${Math.floor(bps / 1e6)} Mbps`;
}

const WIFI_WORDS = ['wi-fi', 'wifi', 'wireless', 'wlan', '802.11', 'wi fi',
                    'airport', 'sans fil', 'drahtlos', 'inalámbrica'];

function detectIfaceType(alias, mediaType, wifiSeen) {
  // wifiSeen wins: if netsh reported a Wi-Fi block for this alias it IS
  // Wi-Fi, whatever the adapter happens to be named in the user's language.
  if (wifiSeen) return 'wifi';
  const a = String(alias || '').toLowerCase();
  if (WIFI_WORDS.some(k => a.includes(k))) return 'wifi';
  if (String(mediaType || '').toLowerCase().includes('802.11')) return 'wifi';
  return 'ethernet';
}

// WireGuardNT and the older Wintun adapters describe themselves this way.
function isTunnel(description) {
  return /wireguard|wintun/i.test(String(description || ''));
}

// ── Assembling the adapter list ───────────────────────────────────────────

const CATEGORY = { 0: 'Public', 1: 'Private', 2: 'DomainAuthenticated' };

function statusRank(a) {
  if (a.hasProfile && a.status === 'Up') return 0;
  if (a.status === 'Up') return 1;
  if (a.status === 'Disconnected') return 2;
  return 3;
}

// `raw` is what src/main/ps/interfaces.ps1 prints: { adapters:[...], netsh:"" }.
// Returns the adapters the window shows, sorted: connected first.
function buildInterfaces(raw) {
  if (!raw || typeof raw !== 'object') return [];
  let list = raw.adapters;
  if (!list) return [];
  if (!Array.isArray(list)) list = [list];       // PowerShell unwraps a single item
  const aliases = list.map(a => a && a.InterfaceAlias).filter(Boolean);
  const wifi = parseNetshWlan(raw.netsh, aliases);

  const out = list.filter(a => a && a.InterfaceAlias && a.Status !== 'Not Present').map(a => {
    const alias = String(a.InterfaceAlias);
    const w = wifi[alias] || null;
    const type = detectIfaceType(alias, a.MediaType, !!w);
    const cat = CATEGORY[Number(a.NetworkCategory)] || null;
    const v4 = a.IPv4Address && a.IPv4Address !== 'N/A' ? String(a.IPv4Address) : '';
    const v6 = a.IPv6Address && a.IPv6Address !== 'N/A' ? String(a.IPv6Address) : '';
    return {
      alias,
      description: String(a.Description || ''),
      guid: String(a.InterfaceGuid || ''),
      ifIndex: Number.isInteger(a.IfIndex) ? a.IfIndex : -1,
      status: String(a.Status || ''),
      hasProfile: !!a.HasProfile,
      profileName: String(a.ProfileName || ''),
      category: a.HasProfile ? cat : null,
      type,
      tunnel: isTunnel(a.Description),
      ipv4: v4,
      prefix: Number.isInteger(a.PrefixLength) ? a.PrefixLength : -1,
      mask: prefixToMask(Number.isInteger(a.PrefixLength) && a.PrefixLength >= 0 ? a.PrefixLength : ''),
      ipv6: v6,
      gateway: String(a.Gateway || ''),
      dns: String(a.Dns || '').split(',').map(s => s.trim()).filter(Boolean),
      dhcp: a.DhcpEnabled !== false,
      // Windows' own answer to "does this network reach the Internet?"
      // (NCSI: an HTTP probe to Microsoft, the taskbar globe), per profile.
      internet: !!a.HasProfile &&
                (a.IPv4Connectivity === 'Internet' || a.IPv6Connectivity === 'Internet'),
      apipa: isApipa(v4),
      linkSpeed: type === 'ethernet' ? parseLinkSpeed(a.LinkSpeed) : '',
      metric: Number.isInteger(a.InterfaceMetric) ? a.InterfaceMetric : -1,
      autoMetric: a.AutomaticMetric !== false,
      routeMetric: Number.isInteger(a.RouteMetric) ? a.RouteMetric : -1,
      wifi: w ? {
        signal: w.signal,
        standard: parseWifiStandard(w.radioType),
        band: parseWifiBand(w.band, w.channel),
      } : null,
    };
  });

  out.sort((x, y) => (statusRank(x) - statusRank(y)) ||
                     x.alias.toLowerCase().localeCompare(y.alias.toLowerCase()));
  return out;
}

// "Domain=True\nPrivate=True\nPublic=False" -> { on, total, profiles }
function parseFirewall(text) {
  const profiles = {};
  for (const line of String(text || '').split(/\r?\n/)) {
    const i = line.indexOf('=');
    if (i < 1) continue;
    profiles[line.slice(0, i).trim()] = line.slice(i + 1).trim().toLowerCase() === 'true';
  }
  const names = Object.keys(profiles);
  if (!names.length) return { on: null, total: null, profiles: {} };
  return { on: names.filter(n => profiles[n]).length, total: names.length, profiles };
}

// ── VPN exit ──────────────────────────────────────────────────────────────

// The adapter WireGuard will leave through: WireGuard for Windows does not
// ask Windows for a route to its server, it takes the default route with the
// lowest RouteMetric + InterfaceMetric among the other adapters and pins its
// socket there. (That is why Find-NetRoute can disagree with it.)
function predictVpnExit(list) {
  let best = null;
  for (const a of list || []) {
    if (a.tunnel || a.status !== 'Up' || !a.gateway || a.metric < 0 || a.routeMetric < 0) continue;
    const total = a.metric + a.routeMetric;
    if (!best || total < best.total) best = { alias: a.alias, guid: a.guid, total };
  }
  return best;
}

// `wg show <tunnel> dump`: one line for the interface (4 fields), then one
// line per peer, tab-separated: public-key, preshared-key, endpoint,
// allowed-ips, latest-handshake (Unix seconds, 0 = never), rx, tx, keepalive.
function parseWgDump(text) {
  const lines = String(text || '').split(/\r?\n/).filter(l => l.trim());
  const peers = [];
  for (const line of lines.slice(1)) {
    const f = line.split('\t');
    if (f.length < 8) continue;
    peers.push({
      endpoint: f[2] === '(none)' ? '' : f[2],
      allowedIps: f[3] === '(none)' ? [] : f[3].split(','),
      handshake: Number(f[4]) || 0,
      rx: Number(f[5]) || 0,
      tx: Number(f[6]) || 0,
    });
  }
  return peers;
}

// ok: a handshake in the last 3 minutes (WireGuard renews it every 2);
// never: no answer ever received (the UDP-blocked case); stale: it stopped.
function tunnelHealth(peers, nowSec) {
  if (!peers.length) return { state: 'never', age: -1, rx: 0 };
  const last = Math.max(...peers.map(p => p.handshake));
  const rx = peers.reduce((n, p) => n + p.rx, 0);
  if (!last) return { state: 'never', age: -1, rx };
  const age = Math.max(0, Math.round(nowSec - last));
  return { state: age <= 180 ? 'ok' : 'stale', age, rx };
}

// One peer that takes everything: WireGuard for Windows then turns on its
// "Block untunneled traffic" kill-switch by itself, unless it was unticked.
function sendsEverything(peers) {
  return peers.length === 1 &&
         peers[0].allowedIps.some(x => x === '0.0.0.0/0' || x === '::/0');
}

// Where the VPN mode stands, from what was written when it was turned on
// (`journal`, in config.json) and what Windows shows now.
//   off      nothing recorded
//   on       recorded and still true
//   waiting  recorded, but the set-aside adapter is not there (unplugged)
//   ended    recorded, but Windows put things back (restart, re-enabled card)
const RETREAT_METRIC = 9000;
function vpnState(journal, list) {
  if (!journal || !journal.active || !journal.retreat) return { state: 'off' };
  const r = (list || []).find(a => a.guid === journal.retreat.guid);
  if (!r) return { state: 'waiting' };
  if (journal.method === 'disable') {
    return { state: r.status === 'Disabled' ? 'on' : 'ended' };
  }
  return { state: r.metric === RETREAT_METRIC && !r.autoMetric ? 'on' : 'ended' };
}

module.exports = {
  predictVpnExit, parseWgDump, tunnelHealth, sendsEverything, vpnState, RETREAT_METRIC,
  semverGt, prefixToMask, validIp, validMask, ipSnapshot, isApipa, psQuote,
  parseNetshWlan, parseWifiStandard, parseWifiBand, parseLinkSpeed,
  detectIfaceType, isTunnel, buildInterfaces, parseFirewall, CATEGORY,
};
