# NetCatChanger — change watcher, run by src/main/netdata.js while the window
# is open (and killed when it closes: NetCatChanger keeps nothing resident).
#
# One long-lived PowerShell process that polls every 3 s and prints the line
# CHANGED only when something actually moved: a connection profile or its
# internet access, the firewall, an adapter's status, or an adapter's
# priority (InterfaceMetric: the VPN mode, or Windows putting it back).

$ErrorActionPreference = 'SilentlyContinue'
$last  = ''
$first = $true
while ($true) {
    try {
        $s = (Get-NetConnectionProfile |
              Sort-Object InterfaceAlias |
              ForEach-Object { "$($_.InterfaceAlias)=$([int]$_.NetworkCategory)/$($_.IPv4Connectivity)/$($_.IPv6Connectivity)" }) -join ';'
        $f = (Get-NetFirewallProfile -All |
              ForEach-Object { "$($_.Enabled)" }) -join ','
        $a = (Get-NetAdapter |
              Sort-Object Name |
              ForEach-Object { "$($_.Name)=$($_.Status)" }) -join ';'
        $m = (Get-NetIPInterface -AddressFamily IPv4 |
              Sort-Object ifIndex |
              ForEach-Object { "$($_.ifIndex)=$($_.InterfaceMetric)" }) -join ';'
        $cur = "$s|$f|$a|$m"
        if ($first) { $last = $cur; $first = $false }
        elseif ($cur -ne $last) {
            $last = $cur
            Write-Output 'CHANGED'
            [Console]::Out.Flush()
        }
    } catch {}
    Start-Sleep -Seconds 3
}
