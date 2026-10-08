# Changelog

## [3.1.0] - 2026-10-08

### Added

- **Secondary IP**: a second fixed IPv4 address on another range, next to the
  DHCP one (or the fixed one), to reach a local network (a NAS, a switch,
  event equipment) without losing DHCP or the Internet. Never a gateway.
  - ON / OFF on the adapter card, one switch per address, lined up with the
    card's other addresses; OFF removes it from Windows and keeps it in the
    list, ready to go back on. A SECONDARY IP badge, green while one is on.
  - "Secondary IP" window: add (address + prefix or mask, a name), remove,
    presets for any card (one click adds and turns on), addresses kept for a
    card that is no longer there ("Use here" / "Forget").
  - Checked before it is added: a valid address, not the network or
    broadcast address of its range, no overlap with the card's main address
    or another connected card. Windows' duplicate address detection is read
    back: an address someone else already uses is removed and reported.
  - On a DHCP card, DHCP / fixed coexistence is turned on before adding and
    off when the last address goes (Windows 10 2004 or later; older versions
    are told so).
  - If the card loses the Internet within 15 s of an address going on, the
    address goes back off by itself.
  - A red badge when a new DHCP lease lands in the same range, or Windows
    finds a duplicate.
- **Use for Internet**: when several cards reach the Internet (Wi-Fi and
  Ethernet), one click sends Internet traffic (and the VPN) through the
  chosen card; the others keep their local network. An INTERNET ROUTE badge
  shows which card carries it (blue when chosen, grey when it is Windows'
  choice). "Automatic" in one click, or by itself when Windows restarts.

### Changed

- The VPN card's "Use another connection" now does the same as "Use for
  Internet" (one mechanism instead of two).

### Fixed

- A card with two IPv4 addresses could show the second one as its address:
  the main address is now the DHCP one (on a fixed card, the one in the
  gateway's range).
- Changing IP settings (DHCP / fixed) erased the card's secondary addresses
  without a word; they are now put back, also by the 15 s undo.

## [3.0.0] - 2026-10-06

A complete rewrite: Electron instead of Python / tkinter, on the shared UI
charter of Just Edit's applications.

### Added

- **VPN** card, shown only while a WireGuard tunnel runs: which connection
  the VPN uses and whether its server answers, in plain words. When it gets no
  answer (an event network that blocks VPNs), one button sends it through
  another connection: the current one gets a lower priority, keeps working
  for everything else, and a restart of Windows undoes it; the VPN is then
  reconnected. "Back to normal" and "Try again" buttons.
- **INTERNET badge** per adapter, from Windows' own connectivity check.
- An ON / OFF switch on each adapter turns it on or off (replaces the
  Disable / Enable button).
- Rename an adapter with a right-click on its name; renew a DHCP lease from
  IP settings. Each adapter card keeps one button: IP settings.
- Subnet masks are now checked (contiguous bits) before anything is applied.
- An IP change still waiting for confirmation is put back if the app closes.
- The installer removes NetCatChanger 2.x and its "Launch with Windows" task.

### Changed

- Nothing resident any more: no tray icon, no start with Windows, no start
  minimized. Closing the window quits.
- Administrator rights are required at launch; the read-only mode is gone.
- Adapters are designated by their Windows GUID, matched exactly: a name with
  brackets ("Ethernet [2]") or a rename no longer misleads an action.
- A gateway counts as answering only when the ping reply carries `TTL=`.
- The firewall can no longer be switched off for a limited time (10 min / 1 h):
  it stays off until switched back on.
- Builds are made on Windows with `scripts\build_windows.cmd` (no more GitHub
  Actions workflow). Electron is fetched once with curl, resumable, checksum
  verified.
- Colours: blue for what is chosen; badges grey by default, green when what
  they name works (Internet, link, DHCP, gateway, tunnel), red when it does
  not (cable unplugged, no DHCP answer, gateway silent).

### Removed

- Global Internet / DNS lights (replaced by the per-adapter INTERNET badge).
- The Python sources, the Inno Setup script and the `.bat` launchers.

## 2.2.1 and earlier

Python / tkinter versions; see the GitHub history.
