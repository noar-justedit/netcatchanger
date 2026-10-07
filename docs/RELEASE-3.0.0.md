# NetCatChanger 3.0.0

A complete rewrite. Same job, new window: network adapters, IP settings,
Windows Firewall, and now your WireGuard VPN, in one place. Open it, change
what you need, close it.

## Upgrading from 2.x

Run `NetCatChanger-Setup-3.0.0.exe`. It removes NetCatChanger 2.x and its
"Launch with Windows" task, and keeps your settings and IP presets.
Administrator rights are asked once at launch.

## New

- **VPN** (WireGuard for Windows): shows which connection your VPN uses and
  whether its server answers. On a network that blocks VPNs (events, hotels),
  one button sends it through another connection, the Wi-Fi for instance,
  and reconnects it. "Back to normal" in one click, or by itself when Windows
  restarts.
- **Badges that tell what works**: green for Internet, link, DHCP, gateway,
  tunnel; red for an unplugged cable, no DHCP answer, a silent gateway.
- **ON / OFF switch** on each adapter.
- **Rename** with a right-click on an adapter's name; **Renew** the DHCP
  lease from IP settings.
- IP settings: subnet masks are checked, and a change still waiting for
  confirmation is undone if the app closes.

## Changed

- Nothing stays running in the background: no tray icon, no start with
  Windows.
- The firewall is switched off until you switch it back on (no more timed
  disable).

## Requirements

Windows 10 or 11, 64-bit. The installer is not signed: SmartScreen may ask
for confirmation (*More info*, then *Run anyway*).

Full list of changes: [CHANGELOG.md](../CHANGELOG.md).
