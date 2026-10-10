# Changelog

## [3.1.1] - 2026-10-09

### Fixed

- Secondary IP: Windows cuts the Internet for a few seconds while it
  re-examines the network after an address goes on or off. The automatic
  turn-off could mistake that for a real loss and remove the address for
  nothing. It now looks at the card from 10 s to 25 s after ON and turns the
  address off only after a lasting cut (3 readings in a row without
  Internet).
- Use for Internet: a refresh landing in the middle of a change could drop
  the record of it and leave priorities at 1 / 9000 until a restart; when
  Windows resets the chosen adapter, the adapters set aside are put back
  too; "Automatic" no longer fails while one of them is turned off.
- Closing the window during an IP change, or during its undo, no longer
  skips putting the previous settings back.
- A warning is shown when a secondary address could not be put back after
  an IP change.
- A DHCP adapter without a lease no longer shows its secondary address as
  its main one; on a fixed adapter without a gateway, a kept secondary
  address is never taken as the main one.
- Removing a secondary address while its adapter is off also removes the
  copy Windows would bring back at the next start.
- The update notice closed with Escape comes back at the next launch (only
  "Later" skips that version).
- The window no longer stops refreshing after a drawing error.

### Security

The app runs as administrator; these close ways for another program of the
same user to borrow those rights:

- PowerShell only loads Windows' own modules (a module placed in the user's
  Documents folder could replace a command); netsh, wg.exe and other
  programs are called by their full system path.
- Electron fuses: no Node mode, no NODE_OPTIONS, no inspector from the
  command line, app code only from its archive; a debugging switch on the
  command line makes the app quit.
- The session log opens in Notepad by its full path, and GitHub links open
  through the user's own (not elevated) desktop, instead of asking Windows
  which program to use.
- config.json and session.log are never written through a link (junction,
  symbolic link), and the saved VPN / route record is checked before use.

### Changed

- Firewall card green when fully on (like the badges of what works); partly
  on, its switch shows off and a click turns every profile back on.
- VPN card green when its server answers. Its undo button for a route chosen
  with "Use for Internet" is named "Automatic", like on the adapter card.
- No "IP settings" on a VPN tunnel or a turned-off adapter, no "Secondary
  IP" on a turned-off adapter.
- Long adapter names are shortened with "…" instead of running over the
  addresses. Lucide icons for the ticks and the preset delete button.
- Wording: "adapter" everywhere, "Could not …" for every failure, the
  window is titled "Secondary IP"; Enter adds an address.

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
