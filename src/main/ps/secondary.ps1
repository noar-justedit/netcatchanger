# NetCatChanger: add or remove one secondary IPv4 address on one card.
# Copyright (C) 2026 Just Edit (Arnaud Augst), GPL-3.0-or-later
#
# Run by src/main/actions.js. Every value comes through the environment,
# never inside this text:
#   NCC_OP    add | remove
#   NCC_GUID  the card (matched exactly, the name may hold [ ] * ?)
#   NCC_IP    the address
#   NCC_MASK  its mask (add only), checked by netinfo.js before
#
# Prints one JSON line: { ok, message, state, checked, gone }.
#
# On a DHCP card, Windows only keeps a fixed address next to the DHCP one
# when "dhcpstaticipcoexistence" is on (Windows 10 2004, build 19041, and
# later): it is turned on before adding, and off when the last fixed address
# is removed. A fixed card needs nothing of the kind.
# NEVER a gateway: a second default route would take the Internet and the
# VPN away from the card.

$ErrorActionPreference = 'Stop'
$netsh = Join-Path $env:SystemRoot 'System32\netsh.exe'

# UTF-8 only for the answer: netsh writes in the console code page, and its
# messages (French accents) must be read before the switch.
function Send($o) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    ConvertTo-Json -InputObject $o -Compress
    exit 0
}
# netsh, its output as one line. In a try: under 'Stop', Windows PowerShell
# 5.1 turns any line netsh writes on stderr into a fatal error.
function Netsh {
    try { $o = (& $netsh @args 2>&1 | Out-String) } catch { $o = "$($_.Exception.Message)" }
    return ($o -replace '\s+', ' ').Trim()
}
function Fail($msg) { Send ([ordered]@{ ok = $false; message = $msg }) }

try {
    $a = @(Get-NetAdapter | Where-Object { "$($_.InterfaceGuid)" -eq $env:NCC_GUID })
    if ($a.Count -ne 1) { Fail 'Adapter not found (unplugged or removed?)' }
    $idx = [int]$a[0].ifIndex
    $up  = "$($a[0].Status)" -eq 'Up'
    $ipi = Get-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue
    $dhcp = $ipi -and ("$($ipi.Dhcp)" -eq 'Enabled')

    # Always counted as @(& $find).Count: a scriptblock unrolls its list, and
    # a single Windows (CIM) object has no .Count in Windows PowerShell 5.1,
    # so "(& $find).Count" read 0 and an address present looked gone (bug
    # found on SERVAL in 3.1.0: OFF said ok and removed nothing).
    $find = {
        @(Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue |
          Where-Object { "$($_.IPAddress)" -eq $env:NCC_IP })
    }
    $manualLeft = {
        @(Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue |
          Where-Object { "$($_.PrefixOrigin)" -eq 'Manual' }).Count
    }
    $coexOff = {
        if ($dhcp -and (& $manualLeft) -eq 0) {
            $null = Netsh interface ipv4 set interface "interface=$idx" 'dhcpstaticipcoexistence=disabled'
        }
    }

    if ($env:NCC_OP -eq 'add') {
        $x = @(& $find)
        if ($x.Count -gt 0) {
            Send ([ordered]@{ ok = $true; message = ''; state = "$($x[0].AddressState)"; checked = $false; gone = $false })
        }
        if ($dhcp) {
            if ([Environment]::OSVersion.Version.Build -lt 19041) {
                Fail 'This version of Windows cannot keep a fixed address next to DHCP (Windows 10 2004 or later needed)'
            }
            $said = Netsh interface ipv4 set interface "interface=$idx" 'dhcpstaticipcoexistence=enabled'
            if ($LASTEXITCODE -ne 0) { Fail "Windows refused to mix DHCP and a fixed address on this card: $said" }
        }
        $said = Netsh interface ipv4 add address "name=$idx" "address=$env:NCC_IP" "mask=$env:NCC_MASK"
        if ($LASTEXITCODE -ne 0) { & $coexOff; Fail "Windows refused this address: $said" }

        # Windows asks the network whether someone already has the address
        # (duplicate address detection): Tentative while it asks, then
        # Preferred, or Duplicate. Only possible on a connected card.
        $state = ''
        if ($up) {
            for ($i = 0; $i -lt 12; $i++) {
                Start-Sleep -Milliseconds 500
                $x = @(& $find)
                if ($x.Count -gt 0) {
                    $state = "$($x[0].AddressState)"
                    if ($state -ne 'Tentative') { break }
                }
            }
        }
        if ($state -eq 'Duplicate') {
            $null = Netsh interface ipv4 delete address "name=$idx" "address=$env:NCC_IP"
            & $coexOff
            Send ([ordered]@{ ok = $false; conflict = $true; message = "Another device on this network already uses $env:NCC_IP" })
        }
        Send ([ordered]@{ ok = $true; message = ''; state = $state; checked = $up; gone = $false })
    }
    elseif ($env:NCC_OP -eq 'remove') {
        if (@(& $find).Count -gt 0) {
            $said = Netsh interface ipv4 delete address "name=$idx" "address=$env:NCC_IP"
            if (@(& $find).Count -gt 0) {
                # netsh refused or left it: PowerShell's own command, then
                # the saved copy Windows would bring back at the next start.
                try {
                    Remove-NetIPAddress -InterfaceIndex $idx -IPAddress $env:NCC_IP -Confirm:$false -ErrorAction Stop
                } catch { $said = "$said $($_.Exception.Message)".Trim() }
                try {
                    Remove-NetIPAddress -InterfaceIndex $idx -IPAddress $env:NCC_IP -PolicyStore PersistentStore -Confirm:$false -ErrorAction Stop
                } catch {}
            }
            if (@(& $find).Count -gt 0) { Fail "Windows refused to remove this address: $said" }
        }
        # Already gone (removed outside the app): not an error.
        & $coexOff
        Send ([ordered]@{ ok = $true; message = ''; state = ''; checked = $false; gone = $true })
    }
    else { Fail 'Unknown operation' }
}
catch { Fail "$($_.Exception.Message)" }
