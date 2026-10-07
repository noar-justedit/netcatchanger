/*
 * NetCatChanger — Windows network profile manager and firewall control
 * Copyright (C) 2026 Just Edit (Arnaud Augst) — GPL-3.0-or-later
 */

// The window. It only displays what the main process reads and asks it, by
// name, for the few actions it offers (preload.js is the closed list).
//
// Every piece of text that comes from the machine (an adapter name, a
// description) is written with textContent, never as HTML: a name cannot
// inject markup into a window that runs with administrator rights.

'use strict';

const $ = id => document.getElementById(id);

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

function icon(name) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  const use = document.createElementNS(NS, 'use');
  use.setAttribute('href', '#i-' + name);
  svg.appendChild(use);
  return svg;
}

function badge(text, color, extra) {
  return el('span', 'badge' + (color ? ' ' + color : '') + (extra ? ' ' + extra : ''), text);
}

function setBadge(node, text, color) {
  node.className = 'badge' + (color ? ' ' + color : '');
  node.textContent = text;
}

// Colours (Noar, 10.2026: "too many colours"). ONE accent, blue, for what
// is active or chosen; grey for every piece of information; red only for a
// real problem (cable unplugged, no DHCP answer, gateway silent, firewall
// not fully on, a failed action).


// ── State ─────────────────────────────────────────────────────────────────

let loading = false;
let reloadAgain = false;
let diagGen = 0;
let lastData = null;
let settings = { confirm_switch: false };
const gwChips = new Map();

// ── Toast ─────────────────────────────────────────────────────────────────

let toastTimer = null;
function toast(msg, opts = {}) {
  const old = $('toast');
  if (old) old.remove();
  clearTimeout(toastTimer);
  const t = el('div', opts.error ? 'err' : '');
  t.id = 'toast';
  t.setAttribute('role', 'status');
  t.appendChild(el('span', null, msg));
  if (opts.action && opts.onAction) {
    const b = el('button', null, opts.action);
    b.addEventListener('click', () => { t.remove(); opts.onAction(); });
    t.appendChild(b);
  }
  document.body.appendChild(t);
  toastTimer = setTimeout(() => t.remove(), opts.ms || (opts.error ? 6000 : 3500));
}

// ── Dialogs (charter: a card on a black veil, full-width buttons) ─────────
// Each returns a Promise. Escape and a click on the veil mean "Cancel":
// most dialogs here ask before changing something, so cancelling is the
// answer that changes nothing. A dialog that carries a decision already
// under way (keep or revert an IP change) passes { locked: true }: only its
// buttons close it (charter: closing it with a key would decide for you).

function dialog(build, opts = {}) {
  return new Promise(resolve => {
    const prevFocus = document.activeElement;
    const veil = el('div', 'veil');
    const box = el('div', 'dlg');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    veil.appendChild(box);
    const close = value => {
      document.removeEventListener('keydown', onKey, true);
      veil.remove();
      if (prevFocus && prevFocus.focus) prevFocus.focus();
      resolve(value);
    };
    const onKey = e => {
      if (e.key === 'Escape') { e.preventDefault(); if (!opts.locked) close(null); }
    };
    document.addEventListener('keydown', onKey, true);
    veil.addEventListener('mousedown', e => { if (e.target === veil && !opts.locked) close(null); });
    if (opts.wide) box.classList.add('wide');
    build(box, close);
    document.body.appendChild(veil);
    const first = box.querySelector('[data-autofocus]') || box.querySelector('button');
    if (first) first.focus();
  });
}

function buttons(box, close, okLabel, okColor, getValue) {
  const row = el('div', 'dlg-btns');
  const cancel = el('button', 'act', 'Cancel');
  cancel.addEventListener('click', () => close(null));
  const ok = el('button', 'act ' + (okColor || 'blue'), okLabel);
  ok.addEventListener('click', () => { const v = getValue(); if (v !== undefined) close(v); });
  row.append(cancel, ok);
  box.appendChild(row);
  return ok;
}

function confirmDialog(title, text, okLabel, okColor) {
  return dialog((box, close) => {
    box.appendChild(el('div', 'dlg-title', title));
    if (text) box.appendChild(el('div', 'dlg-text', text));
    const ok = buttons(box, close, okLabel, okColor, () => true);
    ok.dataset.autofocus = '1';
  });
}

function renameDialog(alias) {
  return dialog((box, close) => {
    box.appendChild(el('div', 'dlg-title', 'Rename adapter'));
    const wrap = el('label', 'field-wrap');
    wrap.appendChild(el('span', 'lbl', 'New name'));
    const input = el('input', 'field');
    input.value = alias;
    input.maxLength = 255;
    input.spellcheck = false;
    input.dataset.autofocus = '1';
    wrap.appendChild(input);
    box.appendChild(wrap);
    const value = () => {
      const v = input.value.trim();
      return v && v !== alias ? v : undefined;
    };
    const ok = buttons(box, close, 'Rename', 'blue', value);
    const sync = () => { ok.disabled = value() === undefined; };
    input.addEventListener('input', sync);
    input.addEventListener('keydown', e => { if (e.key === 'Enter' && value() !== undefined) close(value()); });
    sync();
    setTimeout(() => input.select(), 0);
  });
}

// Which firewall profiles the connected networks use right now (2.x logic).
function activeFirewallProfiles() {
  const set = new Set();
  for (const a of (lastData && lastData.interfaces) || []) {
    if (!a.hasProfile || a.status !== 'Up' || !a.category) continue;
    set.add(a.category === 'DomainAuthenticated' ? 'Domain' : a.category);
  }
  return [...set].sort();
}

function firewallOffDialog() {
  const active = activeFirewallProfiles();
  return dialog((box, close) => {
    box.appendChild(el('div', 'dlg-title', 'Turn off Windows Firewall'));
    box.appendChild(el('div', 'dlg-text',
      'It stays off until you turn it back on here or in Windows Security.'));
    const opts = el('div', 'opts');
    opts.setAttribute('role', 'radiogroup');
    let choice = active.length ? 'active' : 'all';
    const items = [];
    const add = (key, title, sub) => {
      const b = el('button', 'opt');
      b.setAttribute('role', 'radio');
      const txt = el('span');
      txt.appendChild(el('span', null, title));
      if (sub) txt.appendChild(el('small', null, sub));
      b.append(txt, el('span', 'tick', '✓'));
      b.addEventListener('click', () => { choice = key; paint(); });
      items.push([key, b]);
      opts.appendChild(b);
    };
    const paint = () => items.forEach(([k, b]) => {
      b.classList.toggle('on', k === choice);
      b.setAttribute('aria-checked', k === choice ? 'true' : 'false');
    });
    if (active.length) {
      add('active', `Only the active profile${active.length > 1 ? 's' : ''}`, active.join(', '));
    }
    add('all', 'All profiles', 'Domain, Private, Public');
    paint();
    box.appendChild(opts);
    buttons(box, close, 'Turn off', 'red', () => (choice === 'active' ? active : 'all'));
  });
}

// ── Context menu ──────────────────────────────────────────────────────────

function contextMenu(x, y, items) {
  const old = document.querySelector('.ctxmenu');
  if (old) old.remove();
  const m = el('div', 'ctxmenu');
  m.setAttribute('role', 'menu');
  const close = () => {
    m.remove();
    document.removeEventListener('mousedown', outside, true);
    document.removeEventListener('keydown', onKey, true);
    window.removeEventListener('blur', close);
    $('main').removeEventListener('scroll', close);
  };
  const outside = e => { if (!m.contains(e.target)) close(); };
  const onKey = e => { if (e.key === 'Escape') { e.preventDefault(); close(); } };
  for (const [label, run] of items) {
    const it = el('button', 'ctx-it', label);
    it.setAttribute('role', 'menuitem');
    it.addEventListener('click', () => { close(); run(); });
    m.appendChild(it);
  }
  document.body.appendChild(m);
  const w = m.offsetWidth, h = m.offsetHeight;
  m.style.left = Math.min(x, window.innerWidth - w - 8) + 'px';
  m.style.top = Math.min(y, window.innerHeight - h - 8) + 'px';
  document.addEventListener('mousedown', outside, true);
  document.addEventListener('keydown', onKey, true);
  window.addEventListener('blur', close);
  $('main').addEventListener('scroll', close);
  m.querySelector('button').focus();
}

// ── IP settings ───────────────────────────────────────────────────────────

const IP_FIELDS = [
  ['ip', 'IP address'], ['mask', 'Subnet mask'], ['gw', 'Gateway'],
  ['dns1', 'DNS 1'], ['dns2', 'DNS 2'],
];

function isIp(s) {
  const p = String(s || '').trim().split('.');
  return p.length === 4 && p.every(x => /^\d{1,3}$/.test(x) && Number(x) <= 255 && String(Number(x)) === x);
}
function isMask(s) {
  if (!isIp(s)) return false;
  const n = String(s).trim().split('.').reduce((acc, x) => acc * 256 + Number(x), 0);
  const inv = (~n) >>> 0;
  return n !== 0 && (inv & (inv + 1)) === 0;
}

async function ipSettingsDialog(a) {
  let presets = [];
  try { presets = await window.ncc.presets(); } catch (_) {}
  return dialog((box, close) => {
    box.appendChild(el('div', 'dlg-title', 'IP settings'));
    const cur = a.dhcp ? 'Automatic (DHCP)'
      : `Manual · ${a.ipv4 || 'no address'}${a.mask ? ' / ' + a.mask : ''}${a.gateway ? ' · gateway ' + a.gateway : ''}`;
    const sub = el('div', 'dlg-text');
    sub.appendChild(el('b', null, a.alias));
    sub.appendChild(document.createTextNode(' · now: ' + cur));
    box.appendChild(sub);

    if (a.dhcp && a.status === 'Up') {
      const renew = el('div', 'renew-row');
      const t = el('div', 'set-txt');
      t.appendChild(el('div', null, 'Renew the DHCP lease'));
      t.appendChild(el('small', null, 'Ask the network for a fresh address, without changing anything else'));
      const b = el('button', 'btn', 'Renew');
      b.addEventListener('click', () => close({ renew: true }));
      renew.append(t, b);
      box.appendChild(renew);
    }

    // Mode: a choice between two, the chosen one on a surface.
    let mode = a.dhcp ? 'dhcp' : 'static';
    const opts = el('div', 'opts');
    opts.setAttribute('role', 'radiogroup');
    const modeBtns = {};
    for (const [key, title, hint] of [['dhcp', 'Automatic (DHCP)', 'The network hands out the address'],
                                       ['static', 'Manual', 'Fixed address, mask, gateway and DNS']]) {
      const b = el('button', 'opt');
      b.setAttribute('role', 'radio');
      const t = el('span');
      t.appendChild(el('span', null, title));
      t.appendChild(el('small', null, hint));
      b.append(t, el('span', 'tick', '✓'));
      b.addEventListener('click', () => { mode = key; paint(); });
      modeBtns[key] = b;
      opts.appendChild(b);
    }
    box.appendChild(opts);

    // Fields, in a hollow grid.
    const grid = el('div', 'ipgrid');
    const f = {};
    const start = {
      ip: a.ipv4 && !a.apipa ? a.ipv4 : '', mask: a.mask || '255.255.255.0', gw: a.gateway || '',
      dns1: a.dns[0] || '', dns2: a.dns[1] || '',
    };
    for (const [key, label] of IP_FIELDS) {
      grid.appendChild(el('span', 'lbl', label));
      const input = el('input', 'field mono');
      input.value = start[key];
      input.spellcheck = false;
      input.maxLength = 15;
      input.addEventListener('input', () => { input.classList.remove('bad'); err.textContent = ''; });
      f[key] = input;
      grid.appendChild(input);
    }
    box.appendChild(grid);
    const err = el('div', 'dlg-err');
    box.appendChild(err);

    // Presets: pick one to fill the fields; save the fields under a name.
    const pre = el('div', 'presets');
    pre.appendChild(el('span', 'lbl', 'Presets'));
    const row = el('div', 'prow');
    const sel = el('select', 'field');
    const nameIn = el('input', 'field');
    nameIn.placeholder = 'Name of the new preset';
    nameIn.maxLength = 60;
    const fillSel = () => {
      sel.replaceChildren();
      const ph = el('option', null, presets.length ? 'Choose a preset…' : 'No preset yet');
      ph.value = '';
      sel.appendChild(ph);
      for (const p of presets) {
        const o = el('option', null, p.mode === 'dhcp' ? `${p.name} · DHCP` : `${p.name} · ${p.ip}`);
        o.value = p.name;
        sel.appendChild(o);
      }
      del.disabled = true;
    };
    const del = el('button', 'btn', 'Delete');
    sel.addEventListener('change', () => {
      const p = presets.find(x => x.name === sel.value);
      del.disabled = !p;
      if (!p) return;
      mode = p.mode;
      if (p.mode === 'static') {
        f.ip.value = p.ip; f.mask.value = p.mask; f.gw.value = p.gw || '';
        f.dns1.value = p.dns[0] || ''; f.dns2.value = p.dns[1] || '';
      }
      paint();
    });
    del.addEventListener('click', async () => {
      const name = sel.value;
      if (!name) return;
      const r = await window.ncc.deletePreset(name);
      if (r && r.ok) { presets = r.presets; fillSel(); toast(`Preset “${name}” deleted`); }
    });
    row.append(sel, del);
    const row2 = el('div', 'prow');
    const save = el('button', 'btn', 'Save as preset');
    save.addEventListener('click', async () => {
      const name = nameIn.value.trim();
      if (!name) { nameIn.focus(); return; }
      const conf = collect();
      if (!conf) return;
      const r = await window.ncc.savePreset(Object.assign({ name }, conf.mode === 'dhcp'
        ? { mode: 'dhcp' } : { mode: 'static', ip: conf.ip, mask: conf.mask, gw: conf.gw, dns: conf.dns }));
      if (r && r.ok) {
        presets = r.presets; fillSel(); sel.value = name; del.disabled = false; nameIn.value = '';
        toast(`Preset “${name}” saved`);
      } else {
        err.textContent = (r && r.message) || 'Could not save the preset';
      }
    });
    row2.append(nameIn, save);
    pre.append(row, row2);
    box.appendChild(pre);
    fillSel();

    function paint() {
      for (const [k, b] of Object.entries(modeBtns)) {
        b.classList.toggle('on', k === mode);
        b.setAttribute('aria-checked', k === mode ? 'true' : 'false');
      }
      for (const input of Object.values(f)) input.disabled = mode !== 'static';
      grid.classList.toggle('off', mode !== 'static');
      err.textContent = '';
    }

    // The values, checked here for a quick answer (and checked again by the
    // main process, which is what counts).
    function collect() {
      if (mode === 'dhcp') return { mode: 'dhcp' };
      const v = k => f[k].value.trim();
      const bad = [];
      if (!isIp(v('ip'))) bad.push('ip');
      if (!isMask(v('mask'))) bad.push('mask');
      if (v('gw') && !isIp(v('gw'))) bad.push('gw');
      if (v('dns1') && !isIp(v('dns1'))) bad.push('dns1');
      if (v('dns2') && !isIp(v('dns2'))) bad.push('dns2');
      for (const k of Object.keys(f)) f[k].classList.toggle('bad', bad.includes(k));
      if (bad.length) {
        err.textContent = 'Check the fields outlined in red.';
        f[bad[0]].focus();
        return null;
      }
      return { mode: 'static', ip: v('ip'), mask: v('mask'), gw: v('gw'),
               dns: [v('dns1'), v('dns2')].filter(Boolean) };
    }

    paint();
    const ok = buttons(box, close, 'Apply', 'blue', () => collect() || undefined);
    ok.dataset.autofocus = '1';
  }, { wide: true });
}

// After an IP change: keep it, or it is put back by itself in 15 s (2.x).
function keepDialog(alias, secs = 15) {
  return dialog((box, close) => {
    box.appendChild(el('div', 'dlg-title', 'Keep these settings?'));
    const t = el('div', 'dlg-text');
    t.appendChild(document.createTextNode('New IP settings applied on '));
    t.appendChild(el('b', null, alias));
    t.appendChild(document.createTextNode('.'));
    box.appendChild(t);
    const cd = el('div', 'dlg-text countdown');
    box.appendChild(cd);
    let left = secs;
    const tick = () => {
      cd.textContent = `Back to the previous settings in ${left} s unless you keep them.`;
      if (left-- <= 0) { clearInterval(timer); close('timeout'); }
    };
    const timer = setInterval(tick, 1000);
    tick();
    const row = el('div', 'dlg-btns');
    const rev = el('button', 'act', 'Revert now');
    rev.addEventListener('click', () => { clearInterval(timer); close('revert'); });
    const keep = el('button', 'act blue', 'Keep settings');
    keep.dataset.autofocus = '1';
    keep.addEventListener('click', () => { clearInterval(timer); close('keep'); });
    row.append(rev, keep);
    box.appendChild(row);
  }, { locked: true });
}

async function openIpSettings(a) {
  const conf = await ipSettingsDialog(a);
  if (!conf) return;
  if (conf.renew) { await renewLease(a); return; }
  const r = await act(() => window.ncc.ipApply(a.guid, conf), null,
                      `Could not apply the IP settings on ${a.alias} (previous settings put back)`);
  if (!r || !r.ok) return;
  const answer = await keepDialog(a.alias);
  if (answer === 'keep') {
    await window.ncc.ipKeep(a.guid);
    toast('Settings kept');
  } else {
    await act(() => window.ncc.ipRevert(a.guid, answer), 'Previous settings restored',
              `Could not restore the previous settings on ${a.alias}`);
  }
  load();
}

// ── Settings and About ────────────────────────────────────────────────────

function settingRow(label, hint, key) {
  const row = el('div', 'set-row');
  const t = el('div', 'set-txt');
  t.appendChild(el('div', null, label));
  if (hint) t.appendChild(el('small', null, hint));
  const sw = el('button', 'switch' + (settings[key] ? ' on' : ''));
  sw.setAttribute('role', 'switch');
  sw.setAttribute('aria-label', label);
  sw.setAttribute('aria-checked', settings[key] ? 'true' : 'false');
  sw.addEventListener('click', async () => {
    const v = !settings[key];
    const r = await window.ncc.setSetting(key, v);
    if (r && r.ok) {
      settings[key] = v;
      sw.classList.toggle('on', v);
      sw.setAttribute('aria-checked', v ? 'true' : 'false');
    } else {
      toast('Could not save the setting', { error: true });
    }
  });
  row.append(t, sw);
  return row;
}

function settingsDialog(info) {
  return dialog((box, close) => {
    box.appendChild(el('div', 'dlg-title', 'Settings'));
    const list = el('div', 'set-list');
    list.appendChild(settingRow('Keep a session log', 'Every change, with date and result, in session.log', 'log_enabled'));
    list.appendChild(settingRow('Ask before switching a profile', 'Otherwise the switch is immediate, with Undo', 'confirm_switch'));
    box.appendChild(list);

    box.appendChild(el('span', 'lbl', 'About'));
    const about = el('div', 'about');
    const name = el('div', 'about-name');
    name.appendChild(el('span', null, 'NetCatChanger '));
    name.appendChild(el('span', 'mono', info.version));
    about.appendChild(name);
    about.appendChild(el('div', null, 'Windows network profiles, IP settings and firewall.'));
    about.appendChild(el('div', null, 'GNU General Public License v3. This program comes with ABSOLUTELY NO WARRANTY.'));
    about.appendChild(el('div', null, 'Icons: Lucide (ISC). Typeface: Poppins (SIL Open Font License 1.1).'));
    const gh = el('a', 'about-link', 'github.com/noar-justedit/netcatchanger');
    gh.addEventListener('click', () => window.ncc.openExternal(info.github));
    about.appendChild(gh);
    box.appendChild(about);

    const row = el('div', 'dlg-btns');
    const done = el('button', 'act', 'Close');
    done.dataset.autofocus = '1';
    done.addEventListener('click', () => close(true));
    row.appendChild(done);
    box.appendChild(row);
  });
}

function updateDialog(u) {
  return dialog((box, close) => {
    box.appendChild(el('div', 'dlg-title', 'New version available'));
    const t = el('div', 'dlg-text');
    t.appendChild(document.createTextNode('NetCatChanger '));
    t.appendChild(el('b', null, u.version));
    t.appendChild(document.createTextNode(` is out. You have ${u.current}.`));
    box.appendChild(t);
    buttons(box, close, 'Get it', 'blue', () => true).dataset.autofocus = '1';
    box.querySelector('.dlg-btns .act').textContent = 'Later';
  });
}

// ── VPN ───────────────────────────────────────────────────────────────────
// Shown only while a WireGuard tunnel runs (or while NetCatChanger sends the
// VPN through another connection), in plain words (Noar, 10.2026): which
// connection the VPN uses, whether it answers, and one button to fix it.

function vpnView() {
  const v = lastData && lastData.vpn;
  if (!v) return null;
  const tunnels = (v.wireguard && v.wireguard.tunnels) || [];
  const tunnel = tunnels[0] || null;
  const on = v.state === 'on' || v.state === 'waiting';
  return { v, tunnel, on };
}

// Other connections the VPN could use: connected, with a way out, not a tunnel.
function vpnAlternatives(excludeGuid) {
  return ((lastData && lastData.interfaces) || [])
    .filter(a => !a.tunnel && a.status === 'Up' && a.gateway && a.guid !== excludeGuid);
}

function vpnButton(label, onClick, primary, title) {
  const b = el('button', primary ? 'btn primary' : 'btn', label);
  b.addEventListener('click', onClick);
  if (title) b.title = title;
  return b;
}

function renderVpn() {
  const view = vpnView();
  const section = $('vpn-section');
  if (!view || (!view.tunnel && !view.on)) { section.hidden = true; return; }
  section.hidden = false;
  const { v, tunnel, on } = view;
  const tile = $('vpn-tile'), st = $('vpn-state'), hint = $('vpn-hint'), acts = $('vpn-actions');
  acts.replaceChildren();
  $('vpn-name').textContent = tunnel ? `VPN · ${tunnel.name}` : 'VPN';
  const answers = tunnel && tunnel.state === 'ok';
  const exitName = v.exit ? v.exit.alias : 'no connection';
  tile.className = 'tile' + (answers ? ' blue' : (tunnel ? ' red' : ''));
  st.className = 'state' + (answers ? ' blue' : (tunnel ? ' red' : ''));
  hint.textContent = '';

  if (on) {
    const j = v.journal;
    if (!tunnel) {
      st.textContent = 'Your VPN is off.';
    } else if (answers) {
      st.textContent = `Connected through ${j.preferred.alias}.`;
    } else {
      st.textContent = `No answer from the VPN server through ${j.preferred.alias} either.`;
    }
    hint.textContent = v.state === 'waiting'
      ? `${j.retreat.alias} is unplugged.`
      : `${j.retreat.alias} is not used for the VPN, but still works for the rest. ` +
        'Everything goes back to normal when Windows restarts.';
    if (tunnel && !answers) acts.appendChild(vpnButton('Try again', reconnectTunnel, false, 'Reconnect the VPN'));
    acts.appendChild(vpnButton('Back to normal', vpnBackToNormal, false,
      `Let the VPN use ${j.retreat.alias} again`));
    return;
  }

  const others = vpnAlternatives(v.exit && v.exit.guid);
  if (answers) {
    st.textContent = `Connected through ${exitName}.`;
    if (others.length) {
      acts.appendChild(vpnButton('Use another connection', () => vpnUseOther(others, false), false,
        'Send the VPN through another connection'));
    }
  } else {
    st.textContent = tunnel.state === 'stale'
      ? `The VPN server stopped answering through ${exitName}.`
      : `No answer from the VPN server through ${exitName}.`;
    hint.textContent = 'This network may be blocking VPNs.' +
      (others.length ? ' Another connection can be used instead.' : '');
    acts.appendChild(vpnButton('Try again', reconnectTunnel, false, 'Reconnect the VPN'));
    if (others.length === 1) {
      acts.appendChild(vpnButton(`Use ${others[0].alias}`, () => vpnUseOther(others, true), true,
        `Send the VPN through ${others[0].alias}`));
    } else if (others.length > 1) {
      acts.appendChild(vpnButton('Use another connection', () => vpnUseOther(others, true), true));
    }
  }
}

function chooseConnectionDialog(others, current, sendsEverything) {
  return dialog((box, close) => {
    box.appendChild(el('div', 'dlg-title', 'Send the VPN through'));
    let pick = others[0].guid;
    const last = lastData.vpn.prefs && lastData.vpn.prefs.preferred;
    if (last && others.some(a => a.guid === last.guid)) pick = last.guid;
    const opts = el('div', 'opts');
    opts.setAttribute('role', 'radiogroup');
    const items = [];
    for (const a of others) {
      const b = el('button', 'opt');
      b.setAttribute('role', 'radio');
      const t = el('span');
      t.appendChild(el('span', null, a.alias));
      t.appendChild(el('small', null, a.internet ? 'Has Internet' : a.description));
      b.append(t, el('span', 'tick', '✓'));
      b.addEventListener('click', () => { pick = a.guid; paint(); });
      items.push([a.guid, b]);
      opts.appendChild(b);
    }
    const paint = () => items.forEach(([g, b]) => {
      b.classList.toggle('on', g === pick);
      b.setAttribute('aria-checked', g === pick ? 'true' : 'false');
    });
    paint();
    box.appendChild(opts);
    box.appendChild(el('div', 'dlg-text',
      `${current} keeps working for everything else. Back to normal with one click, ` +
      'or by itself when Windows restarts.'));
    if (sendsEverything) {
      box.appendChild(el('div', 'dlg-note',
        `If your VPN app blocks traffic outside the VPN, devices reached through ${current} ` +
        '(a local network, a NAS) may not answer meanwhile.'));
    }
    buttons(box, close, 'Use it', 'blue', () => pick).dataset.autofocus = '1';
  });
}

async function vpnUseOther(others, wasFailing) {
  const view = vpnView();
  if (!view) return;
  let guid = others[0].guid;
  if (others.length > 1 || !wasFailing) {
    guid = await chooseConnectionDialog(others, view.v.exit ? view.v.exit.alias : 'The other connection',
                                        !!(view.tunnel && view.tunnel.sendsEverything));
    if (!guid) return;
  }
  const name = others.find(a => a.guid === guid).alias;
  const r = await act(() => window.ncc.vpnOn(guid), `The VPN now goes through ${name}`,
                      `Could not send the VPN through ${name}`);
  // It was not getting through: reconnect it right away on the new path.
  if (r && r.ok && wasFailing && view.tunnel) {
    await act(() => window.ncc.restartTunnel(view.tunnel.name), null, 'Could not reconnect the VPN');
  }
}

async function vpnBackToNormal() {
  await act(() => window.ncc.vpnOff(), 'Back to normal', 'Could not go back to normal');
}

async function reconnectTunnel() {
  const view = vpnView();
  if (!view || !view.tunnel) return;
  await act(() => window.ncc.restartTunnel(view.tunnel.name), 'VPN reconnected', 'Could not reconnect the VPN');
}

// ── Running an action ─────────────────────────────────────────────────────
// One at a time: the controls are locked while Windows works, then the
// window reads the network again (the watcher would too, a little later).

let acting = false;
async function act(run, okMsg, failMsg, toastOpts) {
  if (acting) return null;
  acting = true;
  document.body.classList.add('busy-lock');
  setStatus('busy', 'Applying…');
  let r = null;
  try { r = await run(); } catch (_) { r = { ok: false, message: '' }; }
  acting = false;
  document.body.classList.remove('busy-lock');
  if (r && r.ok) {
    if (okMsg) toast(okMsg, toastOpts);
  } else {
    toast(failMsg + (r && r.message ? ` · ${r.message}` : ''), { error: true });
  }
  load();
  return r;
}

async function switchProfile(a, target, isUndo) {
  if (settings.confirm_switch && !isUndo) {
    const ok = await confirmDialog('Change network profile',
      `Switch “${a.alias}” to ${target}?`, `Make it ${target}`, 'blue');
    if (!ok) return;
  }
  const prev = a.category;
  await act(() => window.ncc.setProfile(a.guid, target),
    isUndo ? `${a.alias} back to ${target}` : `${a.alias} → ${target}`,
    `Could not change the profile of ${a.alias}`,
    isUndo ? {} : { action: 'Undo', ms: 7000,
                    onAction: () => switchProfile(Object.assign({}, a, { category: target }), prev, true) });
}

async function toggleAdapter(a) {
  const enable = a.status === 'Disabled';
  if (!enable) {
    const ok = await confirmDialog('Turn off adapter',
      `Turn off “${a.alias}”? Any connection on it drops immediately.`, 'Turn off', 'red');
    if (!ok) return;
  }
  await act(() => window.ncc.setEnabled(a.guid, enable),
    `${a.alias} turned ${enable ? 'on' : 'off'}`, `Could not turn ${a.alias} ${enable ? 'on' : 'off'}`);
}

async function renameAdapter(a) {
  const name = await renameDialog(a.alias);
  if (!name) return;
  await act(() => window.ncc.rename(a.guid, name), `Renamed to ${name}`, 'Rename failed');
}

async function renewLease(a) {
  toast(`Renewing the DHCP lease on ${a.alias}…`, { ms: 60000 });
  await act(() => window.ncc.renewDhcp(a.guid), 'Lease renewed', `Renew failed on ${a.alias}`);
}

async function flushDns() {
  await act(() => window.ncc.flushDns(), 'DNS cache flushed', 'Flush failed');
}

async function onFirewallSwitch() {
  const fw = lastData && lastData.firewall;
  const isOn = fw && fw.on > 0;
  if (!isOn) {
    await act(() => window.ncc.setFirewall(true, null), 'Firewall on', 'Could not turn the firewall on');
    return;
  }
  const choice = await firewallOffDialog();
  if (!choice) return;
  await act(() => window.ncc.setFirewall(false, choice === 'all' ? null : choice),
    'Firewall off', 'Could not turn the firewall off');
}

function setStatus(kind, text) {
  const s = $('status');
  s.className = kind;
  s.textContent = text;
}

// ── Firewall card ─────────────────────────────────────────────────────────

function renderFirewall(fw) {
  const tile = $('fw-tile'), st = $('fw-state'), b = $('fw-badge'), sw = $('fw-switch');
  tile.replaceChildren();
  if (!fw || fw.on === null) {
    tile.className = 'tile';
    tile.appendChild(icon('shield-off'));
    st.className = 'state';
    st.textContent = 'Status unknown';
    setBadge(b, '?', '');
    sw.classList.remove('on');
    sw.setAttribute('aria-checked', 'false');
    return;
  }
  const { on, total, profiles } = fw;
  let color, text, label;
  if (on === total && total > 0) {
    color = 'blue'; label = 'ON';
    text = `Active · ${total} profile${total > 1 ? 's' : ''} protected`;
  } else if (on === 0) {
    color = 'red'; label = 'OFF';
    text = 'Disabled · this computer is not protected';
  } else {
    color = 'red'; label = `${on}/${total}`;
    const off = Object.keys(profiles).filter(n => !profiles[n]).join(', ');
    text = `Partially active · off: ${off}`;
  }
  tile.className = 'tile ' + color;
  tile.appendChild(icon(on > 0 ? 'shield-check' : 'shield-off'));
  st.className = 'state ' + color;
  st.textContent = text;
  setBadge(b, label, color);
  sw.classList.toggle('on', on > 0);
  sw.setAttribute('aria-checked', on > 0 ? 'true' : 'false');
}

// ── Adapter cards ─────────────────────────────────────────────────────────

function ipRow(grid, label, value, cls) {
  grid.appendChild(el('span', 'lbl', label));
  grid.appendChild(el('span', 'v ' + (value ? (cls || '') : 'none'), value || 'none'));
}

function actionButton(text, onClick, title) {
  const b = el('button', 'btn', text);
  b.addEventListener('click', onClick);
  if (title) b.title = title;
  return b;
}

function adapterCard(a) {
  const active = a.hasProfile && a.status === 'Up';

  const card = el('div', 'card ad' + (a.apipa ? ' alert' : ''));

  // Tile: the adapter kind, green when the adapter is connected, red when
  // its cable is unplugged, grey when it is disabled (Noar, 10.2026: the one
  // place green is used).
  const tileColor = { Up: ' green', Disconnected: ' red' }[a.status] || '';
  const tile = el('div', 'tile' + tileColor);
  tile.appendChild(icon(a.type === 'wifi' ? 'wifi' : 'network'));
  card.appendChild(tile);

  // Middle column.
  const body = el('div', 'body');
  const head = el('div', 'head');
  // Rename: right-click on the name (or the Menu key when it has focus).
  const nameEl = el('span', 'obj-name' + (active ? '' : ' dim'), a.alias);
  nameEl.tabIndex = 0;
  nameEl.title = 'Right-click to rename';
  nameEl.addEventListener('contextmenu', e => {
    e.preventDefault();
    const r = nameEl.getBoundingClientRect();
    const x = e.clientX || r.left, y = e.clientY || r.bottom;
    contextMenu(x, y, [['Rename…', () => renameAdapter(a)]]);
  });
  head.appendChild(nameEl);
  const sub = a.profileName && a.profileName !== a.alias ? a.profileName : a.description;
  if (sub) {
    const d = el('span', 'desc', sub);
    d.title = a.description;
    head.appendChild(d);
  }
  body.appendChild(head);

  const badges = el('div', 'badges');
  if (active) {
    if (a.internet) {
      const net = badge('INTERNET', 'green');
      net.title = 'Windows reaches the Internet through this adapter';
      badges.appendChild(net);
    }
    if (a.wifi) {
      const std = a.wifi.standard;
      if (std) badges.appendChild(badge(std.gen ? `${std.gen} · ${std.std}` : std.std, 'green'));
      if (a.wifi.band) badges.appendChild(badge(a.wifi.band, 'green'));
    } else if (a.linkSpeed && !a.tunnel) {
      badges.appendChild(badge(a.linkSpeed, 'green'));
    }
    badges.appendChild(a.dhcp ? badge('DHCP', 'green') : badge('STATIC'));
    if (a.gateway) {
      const gw = badge('GATEWAY');
      gw.title = 'Does the router of this network answer? (checking…)';
      gwChips.set(a.alias, gw);
      badges.appendChild(gw);
    }
  } else {
    // Turned off on purpose: grey. Anything else that keeps it from working: red.
    const st = { Disconnected: 'CABLE UNPLUGGED', Disabled: 'ADAPTER DISABLED',
                 Up: 'NO NETWORK PROFILE' }[a.status] || String(a.status || 'unknown').toUpperCase();
    badges.appendChild(badge(st, a.status === 'Disabled' ? '' : 'red'));
  }
  const vj = lastData && lastData.vpn && lastData.vpn.state !== 'off' ? lastData.vpn.journal : null;
  if (vj && vj.preferred.guid === a.guid) badges.appendChild(badge('VPN', 'blue'));
  if (a.apipa) badges.appendChild(badge('169.254 · NO DHCP ANSWER', 'red'));
  if (a.tunnel) badges.appendChild(badge('TUNNEL', active ? 'green' : ''));
  body.appendChild(badges);

  if (active && a.wifi && a.wifi.signal >= 0) {
    const s = el('div', 'signal');
    const pct = Math.max(0, Math.min(100, a.wifi.signal));
    const c = 'var(--blue)';
    const t = el('span', null, `Signal ${pct}%`);
    t.style.color = 'var(--text3)';
    const bar = el('span', 'bar');
    const fill = el('i');
    fill.style.width = pct + '%';
    fill.style.background = c;
    bar.appendChild(fill);
    s.append(t, bar);
    body.appendChild(s);
  }

  const acts = el('div', 'acts');
  acts.appendChild(actionButton('IP settings', () => openIpSettings(a), 'DHCP or a fixed address, with presets'));
  body.appendChild(acts);
  card.appendChild(body);

  // Right column: addresses, then the profile. Last column: the adapter's
  // on / off switch (Noar, 10.2026: instead of a Disable button).
  const side = el('div', 'side');
  const isOn = a.status !== 'Disabled';
  const sw = el('button', 'switch' + (isOn ? ' on' : ''));
  sw.setAttribute('role', 'switch');
  sw.setAttribute('aria-checked', isOn ? 'true' : 'false');
  sw.setAttribute('aria-label', `${a.alias}: ${isOn ? 'on' : 'off'}`);
  sw.title = isOn ? 'Turn this adapter off' : 'Turn this adapter back on';
  sw.addEventListener('click', () => toggleAdapter(a));
  const ips = el('div', 'ips');
  ipRow(ips, 'IPv4', a.ipv4, '');
  ipRow(ips, 'IPv6', a.ipv6, '');
  if (a.gateway) ipRow(ips, 'Gateway', a.gateway, '');
  side.appendChild(ips);

  if (active && (a.category === 'Private' || a.category === 'Public')) {
    const ch = el('div', 'choice');
    ch.setAttribute('role', 'radiogroup');
    ch.setAttribute('aria-label', 'Network profile');
    for (const [cat, cls] of [['Public', 'public'], ['Private', 'private']]) {
      const b = el('button', 'badge ' + cls + (a.category === cat ? ' on' : ''), cat.toUpperCase());
      b.setAttribute('role', 'radio');
      b.setAttribute('aria-checked', a.category === cat ? 'true' : 'false');
      if (a.category === cat) {
        b.title = `This network is ${cat}`;
      } else {
        b.title = `Make this network ${cat}`;
        b.addEventListener('click', () => switchProfile(a, cat, false));
      }
      ch.appendChild(b);
    }
    side.appendChild(ch);
  } else if (active && a.category === 'DomainAuthenticated') {
    side.appendChild(badge('DOMAIN', 'blue'));
    side.appendChild(el('div', 'managed', 'Managed by IT'));
  }
  card.appendChild(side);
  card.appendChild(sw);
  return card;
}

function renderAdapters(list) {
  const box = $('adapters');
  box.replaceChildren();
  gwChips.clear();
  $('ad-count').textContent = list.length ? String(list.length) : '';
  if (!list.length) {
    box.appendChild(el('div', 'card empty', 'No network adapter found.'));
    return;
  }
  for (const a of list) box.appendChild(adapterCard(a));
}

function renderError(msg) {
  const box = $('adapters');
  box.replaceChildren();
  const c = el('div', 'card empty');
  c.appendChild(el('b', null, 'Windows did not answer.'));
  c.appendChild(el('div', null, 'NetCatChanger reads the network through PowerShell, and the call failed.'));
  if (msg) c.appendChild(el('div', 'mono', msg));
  box.appendChild(c);
}

// ── Diagnostics ───────────────────────────────────────────────────────────

async function runDiagnostics(list) {
  const gen = ++diagGen;
  const gateways = list.filter(a => a.status === 'Up' && a.gateway)
                       .map(a => ({ alias: a.alias, gateway: a.gateway }));
  let r = null;
  try { r = await window.ncc.diagnose(gateways); } catch (_) {}
  if (gen !== diagGen || !r) return;
  for (const [alias, ok] of Object.entries(r.gateways || {})) {
    const chip = gwChips.get(alias);
    if (chip) {
      setBadge(chip, 'GATEWAY', ok ? 'green' : 'red');
      chip.title = ok ? 'The router of this network answers'
                      : 'The router of this network does not answer the ping (some routers never do)';
    }
  }
}

// ── Load ──────────────────────────────────────────────────────────────────

async function load() {
  if (loading) { reloadAgain = true; return; }
  loading = true;
  $('btn-refresh').classList.add('spin');
  setStatus('busy', 'Reading the network…');
  let data = null;
  try { data = await window.ncc.read(); } catch (_) {}
  if (!data) {
    renderError('');
    setStatus('error', 'Error');
  } else {
    lastData = data;
    renderFirewall(data.firewall);
    renderVpn();
    if (data.vpn && data.vpn.endedByWindows) {
      toast('VPN back to normal: Windows has restarted since', { ms: 7000 });
    }
    if (data.ok) {
      renderAdapters(data.interfaces);
      setStatus('ok', 'Ready');
      runDiagnostics(data.interfaces);
    } else {
      renderError(data.error);
      setStatus('error', 'Error');
    }
  }
  $('btn-refresh').classList.remove('spin');
  loading = false;
  if (reloadAgain) { reloadAgain = false; load(); }
}

// ── Wiring ────────────────────────────────────────────────────────────────

async function init() {
  const info = await window.ncc.info();
  $('ver').textContent = 'v' + info.version;
  document.title = 'NetCatChanger ' + info.version;
  $('gh').addEventListener('click', () => window.ncc.openExternal(info.github));

  try { settings = await window.ncc.settings(); } catch (_) {}

  $('btn-refresh').addEventListener('click', () => load());
  $('btn-flush').addEventListener('click', () => flushDns());
  $('btn-settings').addEventListener('click', () => settingsDialog(info));
  window.ncc.onUpdate(async u => {
    const go = await updateDialog(Object.assign({ current: info.version }, u));
    await window.ncc.dismissUpdate(u.version);   // never shown twice for the same version
    if (go) window.ncc.openExternal(u.url);
  });
  $('fw-switch').addEventListener('click', () => onFirewallSwitch());
  $('btn-log').addEventListener('click', async () => {
    const ok = await window.ncc.openLog();
    if (!ok) setStatus('busy', 'No log file yet');
  });
  $('win-min').addEventListener('click', () => window.ncc.winMinimize());
  $('win-max').addEventListener('click', () => window.ncc.winMaximize());
  $('win-close').addEventListener('click', () => window.ncc.winClose());
  $('titlebar').addEventListener('dblclick', e => {
    if (e.target.closest('.t-actions')) return;
    window.ncc.winMaximize();
  });

  // The watcher in the main process says when something moved; wait half a
  // second so a burst of changes becomes one reload.
  let t = null;
  window.ncc.onChanged(() => { clearTimeout(t); t = setTimeout(load, 500); });

  load();
}

init();
