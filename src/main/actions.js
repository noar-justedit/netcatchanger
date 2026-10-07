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

// Everything that CHANGES the machine. Each function returns { ok, message }
// and writes one line in the session log, as 2.x did.
//
// An adapter is designated by its GUID, which Windows never reuses for
// another card and which survives a rename; the alias is only used for the
// log and for ipconfig, which knows nothing else. The GUID and every typed
// value reach PowerShell through environment variables (NCC_*), never inside
// the script text, and adapters are matched with -eq (exact), never through
// the cmdlets' -Name / -InterfaceAlias parameters, which treat [ ] * ? as
// wildcards: a card called "Ethernet [2]" would not have been found.

'use strict';

const { runPsAction, runCmd } = require('./ps');
const { logEvent } = require('./store');
const { validIp, validMask } = require('./netinfo');

// One adapter, by GUID, or a clear failure.
const PICK = "$a = @(Get-NetAdapter | Where-Object { \"$($_.InterfaceGuid)\" -eq $env:NCC_GUID }); " +
             "if ($a.Count -ne 1) { throw 'Adapter not found (unplugged or removed?)' }; ";

const CATEGORIES = ['Private', 'Public'];
const FW_PROFILES = ['Domain', 'Private', 'Public'];

function short(msg) {
  return String(msg || '').split(/\r?\n/).map(s => s.trim()).filter(Boolean)[0] || '';
}

async function setProfile(guid, alias, category) {
  if (!CATEGORIES.includes(category)) return { ok: false, message: 'Unknown profile' };
  const r = await runPsAction(PICK +
    `$p = @(Get-NetConnectionProfile -InterfaceIndex $a[0].ifIndex); ` +
    `if ($p.Count -eq 0) { throw 'This adapter has no network profile' }; ` +
    `$p | Set-NetConnectionProfile -NetworkCategory ${category}`,
    { NCC_GUID: guid });
  logEvent('profile', `${alias} -> ${category} : ${r.ok ? 'ok' : 'FAILED ' + short(r.message)}`);
  return { ok: r.ok, message: short(r.message) };
}

async function setAdapterEnabled(guid, alias, enable) {
  const verb = enable ? 'Enable-NetAdapter' : 'Disable-NetAdapter';
  const r = await runPsAction(PICK + `$a | ${verb} -Confirm:$false`, { NCC_GUID: guid });
  logEvent('adapter', `${alias} -> ${enable ? 'enabled' : 'disabled'} : ${r.ok ? 'ok' : 'FAILED ' + short(r.message)}`);
  return { ok: r.ok, message: short(r.message) };
}

// What Windows accepts as an adapter name, kept simple: printable, no
// control character, at most 255 characters, not only spaces.
function validNewName(name) {
  return typeof name === 'string' && name.trim().length > 0 && name.length <= 255 &&
         !/[\u0000-\u001f\u007f]/.test(name);
}

async function renameAdapter(guid, alias, newName) {
  if (!validNewName(newName)) return { ok: false, message: 'Invalid name' };
  const name = newName.trim();
  const r = await runPsAction(PICK + '$a | Rename-NetAdapter -NewName $env:NCC_NEWNAME',
    { NCC_GUID: guid, NCC_NEWNAME: name });
  logEvent('adapter', `rename ${alias} -> ${name} : ${r.ok ? 'ok' : 'FAILED ' + short(r.message)}`);
  return { ok: r.ok, message: short(r.message) };
}

async function renewDhcp(alias) {
  const r = await runCmd('ipconfig', ['/renew', alias], 60000);
  logEvent('tools', `renew dhcp ${alias} : ${r.ok ? 'ok' : 'FAILED'}`);
  return { ok: r.ok, message: '' };
}

async function flushDns() {
  const r = await runCmd('ipconfig', ['/flushdns']);
  logEvent('tools', `flush dns : ${r.ok ? 'ok' : 'FAILED'}`);
  return { ok: r.ok, message: '' };
}

// profiles: null = all of them, or a list among Domain / Private / Public.
async function setFirewall(enable, profiles) {
  let target = '-All';
  let label = 'ALL';
  if (Array.isArray(profiles)) {
    const names = profiles.filter(p => FW_PROFILES.includes(p));
    if (!names.length) return { ok: false, message: 'No firewall profile chosen' };
    target = '-Profile ' + names.join(',');
    label = names.join(',');
  }
  const r = await runPsAction(`Set-NetFirewallProfile ${target} -Enabled ${enable ? 'True' : 'False'}`);
  logEvent('firewall', `${label} -> ${enable ? 'ON' : 'OFF'} : ${r.ok ? 'ok' : 'FAILED ' + short(r.message)}`);
  return { ok: r.ok, message: short(r.message) };
}

// ── IP configuration, with netsh (lists of arguments, as in 2.x) ──────────

async function applyDhcp(alias, addressAlreadyDhcp) {
  let ok1 = true;
  if (!addressAlreadyDhcp) {
    ok1 = (await runCmd('netsh', ['interface', 'ipv4', 'set', 'address',
                                  `name=${alias}`, 'source=dhcp'])).ok;
  }
  const ok2 = (await runCmd('netsh', ['interface', 'ipv4', 'set', 'dnsservers',
                                      `name=${alias}`, 'source=dhcp'])).ok;
  const ok = ok1 && ok2;
  logEvent('ipconfig', `${alias} -> DHCP : ${ok ? 'ok' : 'FAILED'}`);
  return { ok, message: ok ? '' : 'netsh refused the change' };
}

// Returns the list of fields that are wrong, empty when everything is fine.
function checkStatic(c) {
  const bad = [];
  if (!validIp(c.ip)) bad.push('ip');
  if (!validMask(c.mask)) bad.push('mask');
  if (c.gw && !validIp(c.gw)) bad.push('gw');
  (c.dns || []).forEach((d, i) => { if (d && !validIp(d)) bad.push('dns' + (i + 1)); });
  return bad;
}

async function applyStatic(alias, c) {
  const bad = checkStatic(c);
  if (bad.length) return { ok: false, message: 'Invalid value: ' + bad.join(', ') };
  const args = ['interface', 'ipv4', 'set', 'address', `name=${alias}`, 'source=static',
                `address=${c.ip}`, `mask=${c.mask}`];
  if (c.gw) args.push(`gateway=${c.gw}`, 'gwmetric=1');
  let ok = (await runCmd('netsh', args)).ok;
  const dns = (c.dns || []).filter(Boolean);
  if (ok) {
    if (dns.length) {
      ok = (await runCmd('netsh', ['interface', 'ipv4', 'set', 'dnsservers', `name=${alias}`,
        'source=static', `address=${dns[0]}`, 'register=primary', 'validate=no'])).ok;
      for (let i = 1; i < dns.length; i++) {
        await runCmd('netsh', ['interface', 'ipv4', 'add', 'dnsservers', `name=${alias}`,
          `address=${dns[i]}`, `index=${i + 1}`, 'validate=no']);
      }
    } else {
      await runCmd('netsh', ['interface', 'ipv4', 'set', 'dnsservers', `name=${alias}`,
        'source=static', 'address=none', 'validate=no']);
    }
  }
  logEvent('ipconfig', `${alias} -> static ${c.ip}/${c.mask} gw=${c.gw || '-'} ` +
                       `dns=${dns.join(',') || '-'} : ${ok ? 'ok' : 'FAILED'}`);
  return { ok, message: ok ? '' : 'netsh refused the change' };
}

// Put back what ipSnapshot() kept. Nothing sane to restore -> DHCP, the safe
// default (2.x behaviour).
async function restoreIp(alias, snap) {
  if (!snap || snap.dhcp || !validIp(snap.ip) || !validMask(snap.mask)) {
    return applyDhcp(alias, false);
  }
  return applyStatic(alias, snap);
}

module.exports = {
  applyDhcp, applyStatic, restoreIp, checkStatic,
  setProfile, setAdapterEnabled, renameAdapter, renewDhcp, flushDns, setFirewall,
  validNewName, CATEGORIES, FW_PROFILES,
};
