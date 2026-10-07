/*
 * NetCatChanger — Windows network profile manager and firewall control
 * Copyright (C) 2026 Just Edit (Arnaud Augst) — GPL-3.0-or-later
 *
 * Fetches the Electron zip that the Windows build packs, ONCE, into
 *     %LOCALAPPDATA%\NetCatChanger-build\electron-v<version>\
 * and prints that folder on the last line (build_windows.cmd hands it to
 * electron-builder as electronDist).
 *
 * Why not let Electron or electron-builder download it themselves:
 *  - electron-builder gives up after 10 minutes IN TOTAL (first build on
 *    SERVAL: "Timeout awaiting 'request' for 600000ms");
 *  - Electron's own installer uses Node's built-in fetch, which failed
 *    outright on the same machine ("TypeError: fetch failed").
 * curl.exe ships with Windows 10 and 11, retries on its own, and RESUMES an
 * interrupted download where it stopped instead of starting over.
 *
 * The file is checked against the SHA-256 published inside the electron npm
 * package (node_modules/electron/checksums.json): a truncated or tampered
 * download is refused, never packed into the app.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const root = path.join(__dirname, '..');
const version = require(path.join(root, 'node_modules', 'electron', 'package.json')).version;
const checksums = require(path.join(root, 'node_modules', 'electron', 'checksums.json'));

const zipName = `electron-v${version}-win32-x64.zip`;
const expected = checksums[zipName];
const url = `https://github.com/electron/electron/releases/download/v${version}/${zipName}`;
const base = process.env.LOCALAPPDATA || require('os').tmpdir();
const dir = path.join(base, 'NetCatChanger-build', `electron-v${version}`);
const zip = path.join(dir, zipName);
const part = zip + '.part';

const say = m => process.stderr.write(m + '\n');

function sha256(file) {
  const h = crypto.createHash('sha256');
  const fd = fs.openSync(file, 'r');
  const buf = Buffer.alloc(1 << 20);
  let n;
  while ((n = fs.readSync(fd, buf, 0, buf.length, null)) > 0) h.update(buf.subarray(0, n));
  fs.closeSync(fd);
  return h.digest('hex');
}

function curl() {
  const exe = process.platform === 'win32'
    ? path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'curl.exe')
    : 'curl';
  const r = spawnSync(exe, [
    '-L', '--fail', '-#',
    '--retry', '10', '--retry-delay', '5', '--retry-all-errors',
    '--connect-timeout', '60',
    '-C', '-',                 // resume a partial download
    '-o', part, url,
  ], { stdio: ['ignore', 2, 2] });
  if (r.error) say(`  curl could not start: ${r.error.message}`);
  return r.status === 0;
}

if (!expected) {
  say(`  [X] No checksum for ${zipName} in the electron package.`);
  process.exit(1);
}
fs.mkdirSync(dir, { recursive: true });

if (fs.existsSync(zip) && sha256(zip) === expected) {
  say(`  Electron ${version}: already downloaded.`);
  console.log(dir);
  process.exit(0);
}
if (fs.existsSync(zip)) fs.rmSync(zip);

for (let attempt = 1; attempt <= 3; attempt++) {
  say(`  Downloading Electron ${version} (about 110 MB)${attempt > 1 ? `, attempt ${attempt}/3` : ''}...`);
  if (curl() && fs.existsSync(part)) {
    if (sha256(part) === expected) {
      fs.renameSync(part, zip);
      say('  Download complete, checksum verified.');
      console.log(dir);
      process.exit(0);
    }
    say('  The downloaded file does not match the published checksum: starting over.');
    fs.rmSync(part, { force: true });
  }
}
say('  [X] Electron could not be downloaded. Check the Internet connection (a VPN can make GitHub very slow) and run the build again: it resumes where it stopped.');
process.exit(1);
