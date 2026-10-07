/*
 * NetCatChanger — offline checks. Run with:  npm test   (or node test/run-tests.js)
 *
 * Nothing here touches Windows, PowerShell or Electron: these are the pure
 * functions that turn Windows' raw output into what the window shows, plus
 * a few promises of the UI charter that could regress in silence. They run
 * on any machine, a Mac included.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const ni = require('../src/main/netinfo');

const fails = [];
let count = 0;
function check(label, got, want) {
  count++;
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g !== w) fails.push(`${label}: got ${g}, expected ${w}`);
}

// ── netsh output samples (EN, FR with "2,4 GHz", DE without a band line) ──
const NETSH_EN = `
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz
    GUID                   : 8f2c1a44-1c0e-4a1b-9e3e-2f0b6d5a7c11
    Physical address       : 3c:58:c2:11:22:33
    State                  : connected
    SSID                   : HomeNet
    BSSID                  : a4:2b:b0:44:55:66
    Network type           : Infrastructure
    Radio type             : 802.11ax
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Profile
    Band                   : 5 GHz
    Channel                : 44
    Receive rate (Mbps)    : 1201
    Transmit rate (Mbps)   : 1201
    Signal                 : 92%
    Profile                : HomeNet
`;

const NETSH_FR = `
Il y a 1 interface sur le systeme :

    Nom                            : Wi-Fi
    Description                    : Intel(R) Wi-Fi 6 AX201 160MHz
    GUID                           : 8f2c1a44-1c0e-4a1b-9e3e-2f0b6d5a7c11
    Adresse physique               : 3c:58:c2:11:22:33
    Etat                           : connecte
    SSID                           : HomeNet
    BSSID                          : a4:2b:b0:44:55:66
    Type de reseau                 : Infrastructure
    Type de radio                  : 802.11ax
    Authentification               : WPA2-Personal
    Chiffrement                    : CCMP
    Mode de connexion              : Profil
    Bande                          : 2,4 GHz
    Canal                          : 6
    Taux de reception (Mbits/s)    : 144
    Taux de transmission (Mbits/s) : 144
    Signal                         : 78%
    Profil                         : HomeNet
`;

const NETSH_DE_NO_BAND = `
Es ist 1 Schnittstelle auf dem System vorhanden:

    Name                   : WLAN
    Beschreibung           : Realtek 8822CE Wireless LAN
    Physische Adresse      : 3c:58:c2:11:22:33
    Status                 : Verbunden
    SSID                   : HomeNet
    Netzwerktyp            : Infrastruktur
    Funktyp                : 802.11ac
    Authentifizierung      : WPA2-Personal
    Kanal                  : 36
    Empfangsrate (MBit/s)  : 866
    Sendrate (MBit/s)      : 866
    Signal                 : 55%
`;

// Windows line endings, as PowerShell really hands them over.
const en = ni.parseNetshWlan(NETSH_EN.replace(/\n/g, '\r\n'), ['Wi-Fi'])['Wi-Fi'];
check('EN signal', en.signal, 92);
check('EN radio', en.radioType, '802.11ax');
check('EN band', en.band, '5 GHz');
check('EN channel', en.channel, 44);

const fr = ni.parseNetshWlan(NETSH_FR, ['Wi-Fi'])['Wi-Fi'];
check('FR signal', fr.signal, 78);
check('FR radio', fr.radioType, '802.11ax');
check('FR band', fr.band, '2,4 GHz');
check('FR channel', fr.channel, 6);

const de = ni.parseNetshWlan(NETSH_DE_NO_BAND, ['WLAN'])['WLAN'];
check('DE signal', de.signal, 55);
check('DE radio', de.radioType, '802.11ac');
check('DE band', de.band, '');          // not reported by this Windows build
check('DE channel', de.channel, 36);    // the rate lines must not win

// A slow link printed BEFORE the channel: the rate (144, a plausible
// channel number) must not be taken for it. This is what the label guard
// "b(it|ps)" is for; the samples above never put a rate first.
const RATES_FIRST = `
    Name                   : Wi-Fi
    Radio type             : 802.11n
    Receive rate (Mbps)    : 144
    Transmit rate (Mbps)   : 144
    Channel                : 11
    Signal                 : 40%
`;
check('rates before channel', ni.parseNetshWlan(RATES_FIRST, ['Wi-Fi'])['Wi-Fi'].channel, 11);

check('netsh: unknown adapter ignored', Object.keys(ni.parseNetshWlan(NETSH_EN, ['Ethernet'])), []);
check('netsh: empty text', ni.parseNetshWlan('', ['Wi-Fi']), {});

// ── band normalisation ────────────────────────────────────────────────────
check('band 5', ni.parseWifiBand('5 GHz', -1), '5 GHz');
check('band 2,4 FR', ni.parseWifiBand('2,4 GHz', -1), '2.4 GHz');
check('band 2.4 EN', ni.parseWifiBand('2.4 GHz', -1), '2.4 GHz');
check('band 6', ni.parseWifiBand('6 GHz', -1), '6 GHz');
check('band via ch36', ni.parseWifiBand('', 36), '5 GHz');
check('band via ch6', ni.parseWifiBand('', 6), '2.4 GHz');
check('band unknown', ni.parseWifiBand('', -1), '');

// ── standards ─────────────────────────────────────────────────────────────
check('std ax', ni.parseWifiStandard('802.11ax'), { gen: 'Wi-Fi 6', std: '802.11ax' });
check('std ac', ni.parseWifiStandard('802.11ac'), { gen: 'Wi-Fi 5', std: '802.11ac' });
check('std be', ni.parseWifiStandard('802.11be'), { gen: 'Wi-Fi 7', std: '802.11be' });
check('std ??', ni.parseWifiStandard('weird'), { gen: '', std: 'weird' });
check('std none', ni.parseWifiStandard(''), null);

// ── link speed ────────────────────────────────────────────────────────────
check('speed 1g', ni.parseLinkSpeed('1000000000'), '1 Gbps');
check('speed 2.5', ni.parseLinkSpeed('2500000000'), '2.5 Gbps');
check('speed 10g', ni.parseLinkSpeed('10000000000'), '10 Gbps');
check('speed str', ni.parseLinkSpeed('1 Gbps'), '1 Gbps');
check('speed nil', ni.parseLinkSpeed(''), '');
check('speed unplugged', ni.parseLinkSpeed('0 bps'), '');

// ── interface type ────────────────────────────────────────────────────────
check('type wifi seen', ni.detectIfaceType('Connexion 2', '', true), 'wifi');
check('type wifi name', ni.detectIfaceType('Wi-Fi'), 'wifi');
check('type wlan de', ni.detectIfaceType('WLAN'), 'wifi');
check('type media', ni.detectIfaceType('Connexion 3', 'Native 802.11'), 'wifi');
check('type eth', ni.detectIfaceType('Ethernet'), 'ethernet');
check('tunnel wireguard', ni.isTunnel('WireGuard Tunnel'), true);
check('tunnel no', ni.isTunnel('OWC 10Gbit Network Adapter'), false);

// ── PowerShell quoting ────────────────────────────────────────────────────
check('quote plain', ni.psQuote('Wi-Fi'), "'Wi-Fi'");
check('quote apos', ni.psQuote("Bob's Wi-Fi"), "'Bob''s Wi-Fi'");
check('quote inject', ni.psQuote('"; Remove-Item C:\\ #'), "'\"; Remove-Item C:\\ #'");

// ── versions, masks, addresses ────────────────────────────────────────────
check('semver gt', ni.semverGt('2.1.0', '2.0.2'), true);
check('semver lt', ni.semverGt('2.0.2', '2.1.0'), false);
check('semver eq', ni.semverGt('2.1.0', '2.1.0'), false);
check('semver 10', ni.semverGt('2.10.0', '2.9.9'), true);
check('semver major', ni.semverGt('3.0.0', '2.9.9'), true);

check('mask /24', ni.prefixToMask(24), '255.255.255.0');
check('mask /16', ni.prefixToMask(16), '255.255.0.0');
check('mask /25', ni.prefixToMask(25), '255.255.255.128');
check('mask /8', ni.prefixToMask(8), '255.0.0.0');
check('mask /32', ni.prefixToMask(32), '255.255.255.255');
check('mask /0', ni.prefixToMask(0), '0.0.0.0');
check('mask bad', ni.prefixToMask(-1), '');
check('mask junk', ni.prefixToMask('x'), '');

check('mask ok /22', ni.validMask('255.255.252.0'), true);
check('mask holes', ni.validMask('255.0.255.0'), false);
check('mask zero', ni.validMask('0.0.0.0'), false);
check('mask /32', ni.validMask('255.255.255.255'), true);
check('mask junk', ni.validMask('255.255.255'), false);
check('ip ok', ni.validIp('192.168.10.5'), true);
check('ip bad oct', ni.validIp('192.168.10.256'), false);
check('ip short', ni.validIp('192.168.10'), false);
check('ip leading0', ni.validIp('192.168.010.5'), false);
check('ip empty', ni.validIp(''), false);
check('ip text', ni.validIp('abc.def.ghi.jkl'), false);

check('apipa yes', ni.isApipa('169.254.12.7'), true);
check('apipa no', ni.isApipa('192.168.1.10'), false);
check('apipa nil', ni.isApipa(''), false);

// ── assembling the adapter list from interfaces.ps1 output ───────────────
const RAW = {
  netsh: NETSH_FR.replace('Nom                            : Wi-Fi',
                          'Nom                            : WiFi'),
  adapters: [
    { InterfaceAlias: 'Ethernet 2', Description: 'Realtek USB GbE', Status: 'Disconnected',
      LinkSpeed: '0 bps', MediaType: '802.3', HasProfile: false, NetworkCategory: -1,
      IPv4Address: '169.254.12.4', PrefixLength: 16, IPv6Address: 'N/A', Gateway: '',
      Dns: '', DhcpEnabled: true, InterfaceGuid: '{B}', IfIndex: 9 },
    { InterfaceAlias: 'WiFi', Description: 'Intel(R) Wi-Fi 7 BE200 320MHz', Status: 'Up',
      LinkSpeed: '2.4 Gbps', MediaType: 'Native 802.11', HasProfile: true,
      ProfileName: 'Deco', NetworkCategory: 1, IPv4Address: '192.168.68.54',
      PrefixLength: 22, IPv6Address: 'fe80::1', Gateway: '192.168.68.1',
      Dns: '192.168.68.1,1.1.1.1', DhcpEnabled: true, InterfaceGuid: '{A}', IfIndex: 12,
      IPv4Connectivity: 'Internet', IPv6Connectivity: 'LocalNetwork' },
    { InterfaceAlias: 'Ghost', Status: 'Not Present' },
    { InterfaceAlias: 'OWC Ethernet 10G', Description: 'OWC 10Gbit Network Adapter',
      Status: 'Up', LinkSpeed: '10 Gbps', MediaType: '802.3', HasProfile: true,
      ProfileName: 'EVENT', NetworkCategory: 0, IPv4Address: '10.20.0.15', PrefixLength: 24,
      IPv6Address: 'N/A', Gateway: '10.20.0.1', Dns: '', DhcpEnabled: false,
      InterfaceGuid: '{C}', IfIndex: 5, IPv4Connectivity: 'LocalNetwork', IPv6Connectivity: 'NoTraffic' },
  ],
};
const list = ni.buildInterfaces(RAW);
check('build: Not Present dropped', list.length, 3);
check('build: connected first, then by name', list.map(a => a.alias), ['OWC Ethernet 10G', 'WiFi', 'Ethernet 2']);
const wifi = list.find(a => a.alias === 'WiFi');
check('build: wifi type from netsh', wifi.type, 'wifi');
check('build: wifi signal', wifi.wifi.signal, 78);
check('build: wifi band', wifi.wifi.band, '2.4 GHz');
check('build: wifi category', wifi.category, 'Private');
check('build: wifi mask', wifi.mask, '255.255.252.0');
check('build: wifi dns list', wifi.dns, ['192.168.68.1', '1.1.1.1']);
check('build: wifi no link speed badge', wifi.linkSpeed, '');
const owc = list.find(a => a.alias === 'OWC Ethernet 10G');
check('build: eth type', owc.type, 'ethernet');
check('build: eth speed', owc.linkSpeed, '10 Gbps');
check('build: eth public', owc.category, 'Public');
check('build: eth static', owc.dhcp, false);
check('build: eth no ipv6', owc.ipv6, '');
check('build: guid kept (VPN mode keys on it)', owc.guid, '{C}');
check('build: internet from Windows (IPv4)', wifi.internet, true);
check('build: local network only -> no internet badge', owc.internet, false);
check('build: no profile -> no internet', list.find(a => a.alias === 'Ethernet 2').internet, false);
check('build: IPv6-only internet counts', ni.buildInterfaces({ netsh: '', adapters: [Object.assign({},
  RAW.adapters[1], { IPv4Connectivity: 'NoTraffic', IPv6Connectivity: 'Internet' })] })[0].internet, true);
const e2 = list.find(a => a.alias === 'Ethernet 2');
check('build: apipa flagged', e2.apipa, true);
check('build: no profile -> no category', e2.category, null);
check('build: unplugged speed hidden', e2.linkSpeed, '');
// PowerShell turns a one-item list into a bare object
check('build: single adapter object', ni.buildInterfaces({ adapters: RAW.adapters[1], netsh: '' }).length, 1);
check('build: junk', ni.buildInterfaces(null), []);
check('build: no adapters', ni.buildInterfaces({ netsh: '' }), []);

// ── VPN exit: who wins, tunnel health, state ─────────────────────────────
const vlist = [
  { alias: 'OWC', guid: 'o', status: 'Up', gateway: '10.0.0.1', metric: 5, routeMetric: 0, tunnel: false },
  { alias: 'WiFi', guid: 'w', status: 'Up', gateway: '192.168.1.1', metric: 35, routeMetric: 0, tunnel: false },
  { alias: 'Deco', guid: 'd', status: 'Up', gateway: '', metric: 0, routeMetric: 0, tunnel: true },
  { alias: 'Eth2', guid: 'e', status: 'Disconnected', gateway: '', metric: -1, routeMetric: -1, tunnel: false },
];
check('vpn exit: lowest route + interface metric wins', ni.predictVpnExit(vlist).alias, 'OWC');
check('vpn exit: set aside at 9000 -> WiFi', ni.predictVpnExit(vlist.map(a => a.guid === 'o' ? Object.assign({}, a, { metric: 9000 }) : a)).alias, 'WiFi');
check('vpn exit: tunnel never counts', ni.predictVpnExit([vlist[2]]), null);
const DUMP = 'privkey\tpubkey\t51820\toff\npeerkey\t(none)\t203.0.113.7:51820\t0.0.0.0/0,::/0\t1759750000\t1234567\t89012\t25';
const peers = ni.parseWgDump(DUMP.replace(/\n/g, '\r\n'));
check('wg dump: peer read', peers, [{ endpoint: '203.0.113.7:51820', allowedIps: ['0.0.0.0/0', '::/0'], handshake: 1759750000, rx: 1234567, tx: 89012 }]);
check('wg: fresh handshake', ni.tunnelHealth(peers, 1759750008), { state: 'ok', age: 8, rx: 1234567 });
check('wg: stale handshake', ni.tunnelHealth(peers, 1759750000 + 600).state, 'stale');
check('wg: never answered (UDP blocked)', ni.tunnelHealth(ni.parseWgDump(DUMP.replace('1759750000', '0')), 1759750008).state, 'never');
check('wg: everything through one peer', ni.sendsEverything(peers), true);
check('wg: split tunnel', ni.sendsEverything(ni.parseWgDump(DUMP.replace('0.0.0.0/0,::/0', '192.168.68.0/22'))), false);
const J = { active: true, method: 'metric', retreat: { guid: 'o' }, preferred: { guid: 'w' } };
check('vpn state: nothing recorded', ni.vpnState(null, vlist).state, 'off');
check('vpn state: still on', ni.vpnState(J, vlist.map(a => a.guid === 'o' ? Object.assign({}, a, { metric: 9000, autoMetric: false }) : a)).state, 'on');
check('vpn state: Windows restarted -> ended', ni.vpnState(J, vlist.map(a => a.guid === 'o' ? Object.assign({}, a, { metric: 5, autoMetric: true }) : a)).state, 'ended');
check('vpn state: adapter unplugged -> waiting', ni.vpnState(J, vlist.filter(a => a.guid !== 'o')).state, 'waiting');
check('vpn state: disable method on', ni.vpnState(Object.assign({}, J, { method: 'disable' }), vlist.map(a => a.guid === 'o' ? Object.assign({}, a, { status: 'Disabled' }) : a)).state, 'on');
check('vpn state: disabled card re-enabled -> ended', ni.vpnState(Object.assign({}, J, { method: 'disable' }), vlist).state, 'ended');

// ── firewall ──────────────────────────────────────────────────────────────
check('fw all on', ni.parseFirewall('Domain=True\r\nPrivate=True\r\nPublic=True'),
      { on: 3, total: 3, profiles: { Domain: true, Private: true, Public: true } });
check('fw partial', ni.parseFirewall('Domain=True\nPrivate=False\nPublic=True').on, 2);
check('fw no answer', ni.parseFirewall(''), { on: null, total: null, profiles: {} });

// ── actions: what reaches PowerShell ──────────────────────────────────────
// ps.js is replaced by a recorder, so nothing runs; the session log is off.
require('../src/main/store').setLogEnabled(false);
const calls = [];
let psActionOk = true;
let readMetricsAnswer = '{"IPv4":{"metric":25,"auto":true},"IPv6":{"metric":25,"auto":true}}';
require.cache[require.resolve('../src/main/ps')] = { exports: {
  runPs: async (cmd, env) => { calls.push({ read: cmd, env }); return { ok: true, stdout: readMetricsAnswer, stderr: '' }; },
  runPsAction: async (cmd, env) => { calls.push({ cmd, env }); return { ok: psActionOk, message: psActionOk ? '' : 'Access denied' }; },
  runCmd: async (tool, args) => { calls.push({ tool, args }); return { ok: true, stdout: '' }; },
} };
const actions = require('../src/main/actions');

(async () => {
  const GUID = '{11111111-2222-3333-4444-555555555555}';
  const NASTY = "Bob's [Wi-Fi] $(Remove-Item C:\\ -Recurse) \"x\"";

  calls.length = 0;
  check('action: unknown profile refused', (await actions.setProfile(GUID, 'x', 'Nonsense; rm')).ok, false);
  check('action: refused profile runs nothing', calls.length, 0);

  await actions.setProfile(GUID, NASTY, 'Private');
  check('action: profile by GUID through env', calls[0].env, { NCC_GUID: GUID });
  check('action: profile command carries no adapter name', calls[0].cmd.includes('Bob'), false);
  check('action: adapter matched exactly, no wildcard parameter', /-InterfaceAlias|-Name\s/.test(calls[0].cmd), false);

  calls.length = 0;
  await actions.renameAdapter(GUID, 'Wi-Fi', NASTY);
  check('action: new name only through env', calls[0].cmd.includes('Remove-Item'), false);
  check('action: new name passed intact', calls[0].env.NCC_NEWNAME, NASTY);
  check('action: empty name refused', (await actions.renameAdapter(GUID, 'Wi-Fi', '   ')).ok, false);
  check('action: control char refused', actions.validNewName('a\nb'), false);
  check('action: 256 chars refused', actions.validNewName('x'.repeat(256)), false);

  calls.length = 0;
  await actions.setAdapterEnabled(GUID, 'Wi-Fi', false);
  check('action: disable uses Disable-NetAdapter', /\| Disable-NetAdapter -Confirm:\$false$/.test(calls[0].cmd), true);

  calls.length = 0;
  await actions.renewDhcp(NASTY);
  check('action: renew is a list of arguments', calls[0], { tool: 'ipconfig', args: ['/renew', NASTY] });

  calls.length = 0;
  await actions.setFirewall(false, ['Private', 'Evil; Stop-Computer']);
  check('action: firewall keeps only known profiles', calls[0].cmd, 'Set-NetFirewallProfile -Profile Private -Enabled False');
  calls.length = 0;
  check('action: firewall with no valid profile refused', (await actions.setFirewall(false, ['Evil'])).ok, false);
  check('action: refused firewall runs nothing', calls.length, 0);
  await actions.setFirewall(true, null);
  check('action: firewall all on', calls[0].cmd, 'Set-NetFirewallProfile -All -Enabled True');

  // IP configuration: netsh with a list of arguments, checked first
  calls.length = 0;
  let r = await actions.applyStatic(NASTY, { ip: '10.0.0.5', mask: '255.255.255.0', gw: '10.0.0.1', dns: ['1.1.1.1', '8.8.8.8'] });
  check('ip: static ok', r.ok, true);
  check('ip: address set with a list', calls[0], { tool: 'netsh', args: ['interface', 'ipv4', 'set', 'address',
    `name=${NASTY}`, 'source=static', 'address=10.0.0.5', 'mask=255.255.255.0', 'gateway=10.0.0.1', 'gwmetric=1'] });
  check('ip: first DNS primary', calls[1].args.slice(-3), ['address=1.1.1.1', 'register=primary', 'validate=no']);
  check('ip: second DNS added at index 2', calls[2].args.slice(-3), ['address=8.8.8.8', 'index=2', 'validate=no']);
  calls.length = 0;
  r = await actions.applyStatic('Wi-Fi', { ip: '10.0.0.5', mask: '255.0.255.0', gw: '', dns: [] });
  check('ip: bad mask refused before netsh', [r.ok, calls.length], [false, 0]);
  check('ip: fields reported', actions.checkStatic({ ip: '1.2.3', mask: '255.255.255.0', gw: 'x', dns: ['', '9.9.9.999'] }), ['ip', 'gw', 'dns2']);
  calls.length = 0;
  await actions.applyStatic('Wi-Fi', { ip: '10.0.0.5', mask: '255.255.255.0', gw: '', dns: [] });
  check('ip: no gateway, no gateway argument', calls[0].args.some(x => x.startsWith('gateway=')), false);
  check('ip: no DNS clears them', calls[1].args.includes('address=none'), true);
  calls.length = 0;
  await actions.applyDhcp('Wi-Fi', true);
  check('ip: DHCP already on -> only DNS back to DHCP', calls.map(c => c.args[3]), ['dnsservers']);
  calls.length = 0;
  await actions.restoreIp('Wi-Fi', { dhcp: false, ip: 'N/A', mask: '', gw: '', dns: [] });
  check('ip: nothing sane to restore -> DHCP', calls.map(c => c.args[3]), ['address', 'dnsservers']);
  calls.length = 0;
  await actions.restoreIp('Wi-Fi', ni.ipSnapshot(owc));
  check('ip: snapshot restored as static', calls[0].args.includes('address=10.20.0.15'), true);

  // VPN exit: journal first, active store only, clean failure
  const vpnmod = require('../src/main/vpn');
  const PREF = { guid: '{AAAAAAAA-0000-0000-0000-000000000001}', alias: 'WiFi' };
  const RET = { guid: '{AAAAAAAA-0000-0000-0000-000000000002}', alias: 'OWC Ethernet 10G' };
  const saved = [];
  const saver = j => { saved.push({ j: JSON.parse(JSON.stringify(j)), callsSoFar: calls.length }); return true; };
  calls.length = 0;
  let v = await vpnmod.turnOn({ method: 'metric', preferred: PREF, retreat: RET }, saver);
  check('vpn: on ok', v.ok, true);
  check('vpn: priority read first, of the set-aside adapter', [calls[0].read !== undefined, calls[0].env.NCC_GUID], [true, RET.guid]);
  check('vpn: journal written BEFORE Windows is touched', saved[0].callsSoFar, 1);
  check('vpn: journal keeps the original priority', saved[0].j.snapshot, { IPv4: { metric: 25, auto: true }, IPv6: { metric: 25, auto: true } });
  check('vpn: only the set-aside adapter changes', calls[1].env, { NCC_GUID: RET.guid, NCC_METRIC: '9000' });
  check('vpn: active store only (a restart undoes it)', (calls[1].cmd.match(/-PolicyStore ActiveStore/g) || []).length, 2);
  check('vpn: never the persistent store', /PersistentStore/.test(calls[1].cmd), false);

  calls.length = 0; saved.length = 0;
  await vpnmod.turnOff(v.journal, saver);
  check('vpn: off puts automatic priority back', (calls[0].cmd.match(/-AutomaticMetric Enabled -PolicyStore ActiveStore/g) || []).length, 2);
  check('vpn: off clears the journal', saved[0].j, null);

  calls.length = 0; saved.length = 0;
  readMetricsAnswer = '{"IPv4":{"metric":15,"auto":false}}';
  await vpnmod.turnOff({ active: true, method: 'metric', retreat: RET, snapshot: { IPv4: { metric: 15, auto: false } } }, saver);
  check('vpn: a manual priority is put back as it was', /-InterfaceMetric 15 -PolicyStore ActiveStore/.test(calls[0].cmd), true);

  calls.length = 0; saved.length = 0; psActionOk = false;
  readMetricsAnswer = '{"IPv4":{"metric":25,"auto":true}}';
  v = await vpnmod.turnOn({ method: 'metric', preferred: PREF, retreat: RET }, saver);
  check('vpn: refused by Windows -> failure', v.ok, false);
  check('vpn: refused -> previous priority put back', /-AutomaticMetric Enabled/.test(calls[calls.length - 1].cmd), true);
  check('vpn: refused -> journal cleared', saved[saved.length - 1].j, null);
  psActionOk = true;

  calls.length = 0; saved.length = 0;
  await vpnmod.turnOn({ method: 'disable', preferred: PREF, retreat: RET }, saver);
  check('vpn: disable method disables the set-aside adapter', /\| Disable-NetAdapter -Confirm:\$false$/.test(calls[0].cmd), true);
  check('vpn: disable method reads no priority', calls.some(c => c.read), false);

  calls.length = 0;
  check('vpn: tunnel name checked', (await vpnmod.restartTunnel('Deco; Stop-Computer')).ok, false);
  check('vpn: refused tunnel runs nothing', calls.length, 0);
  await vpnmod.restartTunnel('Deco');
  check('vpn: tunnel name through env', calls[0].env, { NCC_TUNNEL: 'Deco' });

  report();
})();

// ── UI charter promises that can regress in silence ──────────────────────
const html = fs.readFileSync(path.join(__dirname, '..', 'src', 'renderer', 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, '..', 'src', 'renderer', 'style.css'), 'utf8');
const js = fs.readFileSync(path.join(__dirname, '..', 'src', 'renderer', 'app.js'), 'utf8');

// Every icon-only button carries an aria-label AND a title: an icon is not read.
const iconButtons = html.match(/<button[^>]*class="ibtn"[^>]*>/g) || [];
check('charter: icon buttons found', iconButtons.length > 0, true);
check('charter: icon buttons have aria-label',
      iconButtons.filter(b => !/aria-label="[^"]+"/.test(b)), []);
check('charter: icon buttons have title',
      iconButtons.filter(b => !/title="[^"]+"/.test(b)), []);
// No structural border: a 1px border in the sheet would be a line doing the
// background's job. Outlines are box-shadows, and only for states.
check('charter: no border declarations',
      (css.match(/border\s*:\s*(?!none|0)[^;}]+/g) || []), []);
// One accent in the window (blue), grey information, red for problems only
// (Noar, 10.2026): no orange or violet may creep back in, and green only on
// the icon of a connected adapter and the badges of what works.
check('colours: no orange / violet in the window',
      [...(css + js).matchAll(/--(orange|violet)\b|'(orange|violet)'|\.(orange|violet)\b/g)].map(m => m[0]), []);
const codeOnly = (css + '\n' + js).replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
check('colours: green only for what works (tile, badges)',
      [...codeOnly.matchAll(/[^\n]*\bgreen\b[^\n]*/g)].map(m => m[0].trim())
        .filter(l => !/^\.tile\.green|^\.badge\.green|--green:|Up: ' green'|badge\([^)]*'green'|'green' : |\? 'green'|active \? 'green'/.test(l)), []);
// The accent belongs to the logo only.
check('charter: accent used once (logo)', (css.match(/var\(--accent\)/g) || []).length, 1);
// Machine text never goes through innerHTML.
check('safety: no innerHTML in the window', /innerHTML/.test(js), false);

// Icons: Lucide only, and copied verbatim. Every <symbol> in the window has
// its source in assets/lucide/ and every path of it is found there unchanged.
const SRC = { 'i-wifi': 'wifi', 'i-network': 'network', 'i-shield-check': 'shield-check',
  'i-shield-off': 'shield-off', 'i-refresh': 'refresh-cw', 'i-eraser': 'eraser',
  'i-file-text': 'file-text', 'i-settings': 'settings', 'i-minus': 'minus',
  'i-square': 'square', 'i-x': 'x', 'i-route': 'route' };
const symbols = [...html.matchAll(/<symbol id="([^"]+)"[^>]*>([\s\S]*?)<\/symbol>/g)];
check('icons: every symbol has a known Lucide source',
      symbols.map(m => m[1]).filter(id => !SRC[id]), []);
for (const [, id, inner] of symbols) {
  if (!SRC[id]) continue;
  const svg = fs.readFileSync(path.join(__dirname, '..', 'assets', 'lucide', SRC[id] + '.svg'), 'utf8')
    .replace(/\s+/g, ' ');
  const shapes = inner.match(/<(path|rect|circle)\b[^>]*\/>/g) || [];
  const missing = shapes.filter(sh => !svg.includes(sh.replace(/\/>$/, '').replace(/\s+/g, ' ').trim()));
  check(`icons: ${id} copied verbatim`, missing, []);
}

// ── build_windows.cmd: a broken batch file closes its window before anything
// can be read (06.10.2026: a leftover "goto :get_electron" to a deleted label)
const cmd = fs.readFileSync(path.join(__dirname, '..', 'scripts', 'build_windows.cmd'), 'utf8');
check('build script: Windows line endings', /\r\n/.test(cmd) && !/[^\r]\n/.test(cmd), true);
const labels = new Set([...cmd.matchAll(/^:(\w+)\s*$/gm)].map(m => m[1].toLowerCase()));
const gotos = [...cmd.matchAll(/\bgoto\s+:?(\w+)/gi)].map(m => m[1].toLowerCase()).filter(l => l !== 'eof');
check('build script: every goto has its label', gotos.filter(l => !labels.has(l)), []);
const vars = [...cmd.matchAll(/%([A-Z_]+)%/g)].map(m => m[1])
  .filter(v => !['LOCALAPPDATA'].includes(v));
const setVars = new Set([...cmd.matchAll(/\bset\s+"?([A-Z_]+)=/gi)].map(m => m[1]));
check('build script: no variable used without being set', [...new Set(vars.filter(v => !setVars.has(v)))], []);

// ── push_github (Windows): ASCII only (Windows PowerShell 5.1 reads a .ps1
// without BOM in the ANSI code page), never a forced push, version.json
// held back until the Release, and the launcher in Windows line endings.
const pushPs = fs.readFileSync(path.join(__dirname, '..', 'scripts', 'push_github.ps1'), 'utf8');
const pushCmd = fs.readFileSync(path.join(__dirname, '..', 'scripts', 'push_github.cmd'), 'utf8');
check('push script: ASCII only', /[^\x00-\x7f]/.test(pushPs), false);
check('push script: never forces', /push[^\n]*(--force|-f\b)/.test(pushPs), false);
check('push script: version.json held back until the Release', /checkout --quiet HEAD -- version\.json/.test(pushPs), true);
check('push script: no function named git (it would call itself)', /function\s+git\b/i.test(pushPs), false);
check('push launcher: Windows line endings', /\r\n/.test(pushCmd) && !/[^\r]\n/.test(pushCmd), true);
check('push launcher: runs the .ps1 next to it', pushCmd.includes('"%~dp0push_github.ps1"'), true);

// README: every picture it shows is in the repository.
const readme = fs.readFileSync(path.join(__dirname, '..', 'README.md'), 'utf8');
check('readme: images exist',
      [...readme.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g)].map(m => m[1])
        .filter(f => !/^https?:/.test(f) && !fs.existsSync(path.join(__dirname, '..', f))), []);

// ── report (called once the async action checks above are done) ──────────
function report() {
  if (fails.length) {
    console.log(`FAILED (${fails.length} of ${count}):`);
    for (const f of fails) console.log('  - ' + f);
    process.exit(1);
  }
  console.log(`all ${count} checks passed`);
}
