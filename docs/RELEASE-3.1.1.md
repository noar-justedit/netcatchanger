# NetCatChanger 3.1.1

## Fixed

- **Secondary IP**: Windows cuts the Internet for a few seconds when an
  address goes on or off; NetCatChanger no longer mistakes that for a real
  loss and no longer turns the address back off for nothing.

- **Use for Internet**: switching from one adapter to another, or Windows
  resetting the priorities, no longer leaves an adapter set aside until the
  next restart.
- Closing the window during an IP change no longer skips putting the
  previous settings back.

## Security

NetCatChanger runs as administrator. This version closes several ways for
another program on the same Windows account to borrow those rights
(PowerShell modules, Electron launch options, programs chosen through the
user's registry, links in the settings folder). No known attack used them.

## Changed

- Firewall card green when fully on; partly on, one click turns it fully on.
- Clearer, more consistent wording and buttons (see the changelog).

## Upgrading

Run `NetCatChanger-Setup-3.1.1.exe` over any earlier version: settings and
presets are kept.

## Requirements

Windows 10 or 11, 64-bit. The installer is not signed: SmartScreen may ask
for confirmation (*More info*, then *Run anyway*).

Full list of changes: [CHANGELOG.md](https://github.com/noar-justedit/netcatchanger/blob/main/CHANGELOG.md)
