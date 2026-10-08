# NetCatChanger 3.1.0

## New

- **Secondary IP**: add a second fixed address on another range to a card
  that gets its address by DHCP, to reach a NAS, a switch or event
  equipment, without losing DHCP or the Internet. One ON / OFF switch per
  address on the card, presets, and no gateway ever (it would take the
  Internet and the VPN away from the card). An address someone else already
  uses is refused, and if the card loses the Internet right after, the
  address goes back off by itself. Windows 10 2004 or later.
- **Use for Internet**: Wi-Fi and Ethernet both connected? One click picks
  which one carries the Internet (and the VPN); the other keeps its local
  network. Back to automatic in one click, or when Windows restarts.

## Fixed

- A card with two addresses could show the wrong one.
- Changing IP settings no longer erases secondary addresses.

## Upgrading

Run `NetCatChanger-Setup-3.1.0.exe` over 3.0.0 (or 2.x): settings and
presets are kept.

## Requirements

Windows 10 or 11, 64-bit. The installer is not signed: SmartScreen may ask
for confirmation (*More info*, then *Run anyway*).

Full list of changes: [CHANGELOG.md](../CHANGELOG.md).
