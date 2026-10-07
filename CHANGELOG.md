# Changelog

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
