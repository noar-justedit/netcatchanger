# NetCatChanger — WireGuard for Windows: which tunnels are running, and what
# `wg show <tunnel> dump` says about each (last handshake, bytes received).
# Run by src/main/vpn.js; the dump is parsed by src/main/netinfo.js.
#
# Prints one line of JSON: { "installed": bool, "tunnels": [ { name, dump } ] }
# Each tunnel of WireGuard for Windows is a service named WireGuardTunnel$<name>.

$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$wg = Join-Path $env:ProgramFiles 'WireGuard\wg.exe'
$installed = Test-Path $wg
$out = @()
$svc = @(Get-Service -Name 'WireGuardTunnel$*' | Where-Object { $_.Status -eq 'Running' })
foreach ($s in $svc) {
    $name = $s.Name.Substring('WireGuardTunnel$'.Length)
    $dump = ''
    if ($installed) { $dump = (& $wg show $name dump 2>$null) -join "`n" }
    $out += [ordered]@{ name = $name; dump = "$dump" }
}
ConvertTo-Json -InputObject ([ordered]@{ installed = $installed; tunnels = $out }) -Compress -Depth 4
