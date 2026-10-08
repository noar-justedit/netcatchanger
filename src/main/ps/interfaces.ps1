# NetCatChanger — read every network adapter in ONE PowerShell call.
# Run by src/main/netdata.js, which parses the result with src/main/netinfo.js.
#
# Prints one line of JSON: { "adapters": [...], "netsh": "<raw text>" }
# The adapter list is the primary list (a disabled or unplugged card is
# visible too); the connection profile is attached when one exists.
# The Wi-Fi details are NOT parsed here: the raw `netsh wlan` text goes back
# to Node, where the parser is covered by tests on any machine.

$ErrorActionPreference = 'SilentlyContinue'

# netsh writes in the console code page (850 on a French Windows). It must be
# captured BEFORE the output is switched to UTF-8 below, or its accented
# letters would be decoded with the wrong table.
$netsh = ''
try { $netsh = (netsh wlan show interfaces 2>$null) -join "`n" } catch {}

# Everything printed from here on is UTF-8, which is what Node decodes: an
# adapter named "Connexion réseau" keeps its accent.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$adapters = @(Get-NetAdapter)

$profiles = @{}
Get-NetConnectionProfile | ForEach-Object { $profiles[$_.InterfaceAlias] = $_ }

$allIPs = @{}
Get-NetIPAddress | Where-Object { $_.AddressFamily -eq 'IPv4' -or $_.AddressFamily -eq 'IPv6' } |
    ForEach-Object {
        if (-not $allIPs.ContainsKey($_.InterfaceAlias)) { $allIPs[$_.InterfaceAlias] = @() }
        $allIPs[$_.InterfaceAlias] += $_
    }

$gateways = @{}
$routeMetric = @{}
Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | ForEach-Object {
    if (-not $gateways.ContainsKey($_.InterfaceAlias)) {
        $gateways[$_.InterfaceAlias] = $_.NextHop
        $routeMetric[$_.InterfaceAlias] = [int]$_.RouteMetric
    }
}

$dnsMap = @{}
Get-DnsClientServerAddress -AddressFamily IPv4 |
    ForEach-Object { $dnsMap[$_.InterfaceAlias] = @($_.ServerAddresses) -join ',' }

$dhcpMap = @{}
$ifMetric = @{}
$autoMetric = @{}
Get-NetIPInterface -AddressFamily IPv4 |
    ForEach-Object {
        $dhcpMap[$_.InterfaceAlias]    = ("$($_.Dhcp)" -eq 'Enabled')
        $ifMetric[$_.InterfaceAlias]   = [int]$_.InterfaceMetric
        $autoMetric[$_.InterfaceAlias] = ("$($_.AutomaticMetric)" -eq 'Enabled')
    }

$result = @()
foreach ($ad in $adapters) {
    $a  = $ad.Name
    $st = "$($ad.Status)"
    if ($st -eq 'Not Present') { continue }
    $obj = [ordered]@{
        InterfaceAlias  = $a
        Description     = "$($ad.InterfaceDescription)"
        InterfaceGuid   = "$($ad.InterfaceGuid)"
        IfIndex         = [int]$ad.ifIndex
        Status          = $st
        MacAddress      = "$($ad.MacAddress)"
        LinkSpeed       = "$($ad.LinkSpeed)"
        MediaType       = "$($ad.MediaType)"
        HasProfile      = $false
        ProfileName     = ''
        NetworkCategory = -1
        IPv4Connectivity = ''
        IPv6Connectivity = ''
        IPv4Address     = 'N/A'
        PrefixLength    = -1
        IPv6Address     = 'N/A'
        Gateway         = ''
        Dns             = ''
        DhcpEnabled     = $true
        # Priority (lower wins). WireGuard picks the adapter whose default
        # route has the lowest RouteMetric + InterfaceMetric: the VPN mode
        # reads and changes these.
        InterfaceMetric = -1
        AutomaticMetric = $true
        RouteMetric     = -1
        IPv4List        = @()
    }
    if ($profiles.ContainsKey($a)) {
        $p = $profiles[$a]
        $obj.HasProfile      = $true
        $obj.ProfileName     = "$($p.Name)"
        $obj.NetworkCategory = [int]$p.NetworkCategory
        # Windows' own verdict (the globe / no-globe of the taskbar icon):
        # Internet, LocalNetwork, Subnet, NoTraffic, Disconnected.
        $obj.IPv4Connectivity = "$($p.IPv4Connectivity)"
        $obj.IPv6Connectivity = "$($p.IPv6Connectivity)"
    }
    if ($allIPs.ContainsKey($a)) {
        $v4e = $allIPs[$a] | Where-Object { $_.AddressFamily -eq 'IPv4' } | Select-Object -First 1
        $v6  = $allIPs[$a] | Where-Object { $_.AddressFamily -eq 'IPv6' -and
               $_.PrefixOrigin -ne 'WellKnown' } |
               Select-Object -First 1 -ExpandProperty IPAddress
        if ($v4e) { $obj.IPv4Address = "$($v4e.IPAddress)"; $obj.PrefixLength = [int]$v4e.PrefixLength }
        # Every IPv4 address with its origin (Dhcp / Manual / WellKnown) and
        # state (Preferred / Tentative / Duplicate): the secondary addresses,
        # and the main one chosen by netinfo.js, not by whichever comes first.
        $obj.IPv4List = @($allIPs[$a] | Where-Object { $_.AddressFamily -eq 'IPv4' } | ForEach-Object {
            [ordered]@{ IPAddress = "$($_.IPAddress)"; PrefixLength = [int]$_.PrefixLength
                        PrefixOrigin = "$($_.PrefixOrigin)"; AddressState = "$($_.AddressState)" } })
        if ($v6)  { $obj.IPv6Address = "$v6" }
    }
    if ($gateways.ContainsKey($a)) { $obj.Gateway = "$($gateways[$a])" }
    if ($dnsMap.ContainsKey($a))   { $obj.Dns = "$($dnsMap[$a])" }
    if ($dhcpMap.ContainsKey($a))  { $obj.DhcpEnabled = $dhcpMap[$a] }
    if ($ifMetric.ContainsKey($a)) { $obj.InterfaceMetric = $ifMetric[$a]; $obj.AutomaticMetric = $autoMetric[$a] }
    if ($routeMetric.ContainsKey($a)) { $obj.RouteMetric = $routeMetric[$a] }
    $result += $obj
}

# -InputObject, not the pipeline: piped, a one-adapter list would lose its
# brackets and arrive as a bare object (Node accepts both anyway).
ConvertTo-Json -InputObject ([ordered]@{ adapters = $result; netsh = $netsh }) -Compress -Depth 5
