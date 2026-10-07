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

// The ONLY door between the page and the machine. Each entry is one named
// action; the page never gets a generic "run this command".

'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ncc', {
  info        : ()         => ipcRenderer.invoke('app-info'),
  read        : ()         => ipcRenderer.invoke('net-read'),
  diagnose    : (gateways) => ipcRenderer.invoke('net-diagnose', gateways),
  settings    : ()         => ipcRenderer.invoke('get-settings'),
  setProfile  : (guid, category) => ipcRenderer.invoke('act-profile', guid, category),
  setEnabled  : (guid, enable)   => ipcRenderer.invoke('act-adapter-enabled', guid, enable),
  rename      : (guid, newName)  => ipcRenderer.invoke('act-rename', guid, newName),
  renewDhcp   : (guid)           => ipcRenderer.invoke('act-renew', guid),
  flushDns    : ()               => ipcRenderer.invoke('act-flush-dns'),
  setFirewall : (enable, profiles) => ipcRenderer.invoke('act-firewall', enable, profiles),
  ipApply     : (guid, conf)     => ipcRenderer.invoke('ip-apply', guid, conf),
  ipKeep      : (guid)           => ipcRenderer.invoke('ip-keep', guid),
  ipRevert    : (guid, why)      => ipcRenderer.invoke('ip-revert', guid, why),
  presets     : ()               => ipcRenderer.invoke('presets-get'),
  savePreset  : (preset)         => ipcRenderer.invoke('preset-save', preset),
  deletePreset: (name)           => ipcRenderer.invoke('preset-delete', name),
  setSetting  : (key, value)     => ipcRenderer.invoke('set-setting', key, value),
  dismissUpdate: (version)       => ipcRenderer.invoke('update-dismiss', version),
  onUpdate    : (cb) => {
    const h = (_e, info) => cb(info);
    ipcRenderer.on('update-available', h);
    return () => ipcRenderer.removeListener('update-available', h);
  },
  vpnOn       : (preferredGuid)  => ipcRenderer.invoke('vpn-on', preferredGuid),
  vpnOff      : ()               => ipcRenderer.invoke('vpn-off'),
  restartTunnel: (name)          => ipcRenderer.invoke('vpn-restart-tunnel', name),
  openExternal: (url)      => ipcRenderer.invoke('open-external', url),
  openLog     : ()         => ipcRenderer.invoke('open-log'),
  onChanged   : (cb) => {
    const h = () => cb();
    ipcRenderer.on('net-changed', h);
    return () => ipcRenderer.removeListener('net-changed', h);
  },
  winMinimize : () => ipcRenderer.send('win-minimize'),
  winMaximize : () => ipcRenderer.send('win-maximize'),
  winClose    : () => ipcRenderer.send('win-close'),
});
