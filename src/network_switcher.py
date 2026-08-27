"""
NetCatChanger
Windows Network Profile Manager + Firewall Control
"""
import tkinter as tk
from tkinter import messagebox
import subprocess, json, threading, sys, os, ctypes, webbrowser, base64, re, time, socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    from icons import ICONS
except ImportError:
    ICONS = {}

# Optional at runtime: tray icon (bundled in the exe, may be absent from a
# bare source checkout). The app degrades gracefully without them.
try:
    import pystray
    from PIL import Image as PILImage
    import io as _io
except Exception:
    pystray = None
    PILImage = None

try:
    import winreg
except ImportError:
    winreg = None

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

APP_VERSION = "2.2.1"
GITHUB_URL  = "https://github.com/noar-justedit/netcatchanger"
UPDATE_URL  = "https://raw.githubusercontent.com/noar-justedit/netcatchanger/main/version.json"

# ---------------------------------------------------------------------------
# Config + session log (%APPDATA%\NetCatChanger)
# ---------------------------------------------------------------------------
def _config_dir():
    # Not created here: the folder appears on first write only, so just
    # importing the module (e.g. from the test suite) leaves no trace.
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "NetCatChanger")

CONFIG_PATH = os.path.join(_config_dir(), "config.json")
LOG_PATH    = os.path.join(_config_dir(), "session.log")

DEFAULT_CONFIG = {
    "geometry": "",
    "close_to_tray": True,
    "start_minimized": False,
    "autostart": False,
    "log_enabled": True,
    "confirm_switch": False,
    "update_dismissed": "",
    "presets": [],            # [{name, mode, ip, mask, gw, dns:[..]}]
}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except Exception:
        pass
    return cfg

def save_config(cfg):
    try:
        os.makedirs(_config_dir(), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

LOG_ENABLED = True

def log_event(kind, msg):
    if not LOG_ENABLED:
        return
    try:
        os.makedirs(_config_dir(), exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{stamp} | {kind:<9} | {msg}\n")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Pure helpers (covered by tests/test_parsing.py)
# ---------------------------------------------------------------------------
def semver_gt(a, b):
    pa = [int(x) for x in re.findall(r"\d+", str(a))[:3]] or [0]
    pb = [int(x) for x in re.findall(r"\d+", str(b))[:3]] or [0]
    while len(pa) < 3: pa.append(0)
    while len(pb) < 3: pb.append(0)
    return pa > pb

def prefix_to_mask(prefix):
    try:
        p = int(prefix)
    except (TypeError, ValueError):
        return ""
    if not 0 <= p <= 32:
        return ""
    v = (0xFFFFFFFF << (32 - p)) & 0xFFFFFFFF if p else 0
    return ".".join(str((v >> s) & 0xFF) for s in (24, 16, 8, 0))

def valid_ip(s):
    parts = str(s or "").strip().split(".")
    if len(parts) != 4:
        return False
    try:
        return all(p.isdigit() and 0 <= int(p) <= 255 and str(int(p)) == p for p in parts)
    except ValueError:
        return False

def is_apipa(ip):
    return str(ip or "").startswith("169.254.")

# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
def is_admin():
    try:    return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception: return False

NO_ELEVATE_FLAG = "--no-elevate"

def should_elevate(argv, platform, admin):
    """True when this launch must ask Windows for administrator rights."""
    return platform == "win32" and not admin and NO_ELEVATE_FLAG not in argv

def run_as_admin():
    """Relaunch this program elevated (UAC prompt).

    Returns True when Windows accepted the request (the elevated copy is
    starting, so this one should quit), False when the user refused the
    prompt or the call failed — the caller then stays in read-only mode.

    The relaunched copy carries NO_ELEVATE_FLAG so it can never ask again:
    without it, anything keeping IsUserAnAdmin() false would loop forever.
    """
    try:
        if getattr(sys, "frozen", False):
            exe  = sys.executable
            args = list(sys.argv[1:])
        else:
            exe  = sys.executable
            args = [os.path.abspath(sys.argv[0])] + list(sys.argv[1:])
        if NO_ELEVATE_FLAG not in args:
            args.append(NO_ELEVATE_FLAG)
        params = " ".join(f'"{a}"' for a in args)
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params or None, None, 1)
        return int(rc) > 32      # <= 32 means refused / failed
    except Exception:
        return False

# ---------------------------------------------------------------------------
# PowerShell + plain commands -- hidden, no console flash
# ---------------------------------------------------------------------------
PS_ARGS = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden"]

def run_ps(cmd):
    r = subprocess.run(
        PS_ARGS + ["-Command", cmd],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        creationflags=CREATE_NO_WINDOW)
    return r.stdout.strip(), r.stderr.strip()

def ps_quote(s):
    """Quote a value for PowerShell. Single quotes are literal there, so the
    only escaping needed is doubling an embedded quote."""
    return "'" + str(s).replace("'", "''") + "'"

def run_ps_action(cmd):
    """Run a state-changing command and decide success from the EXIT CODE.

    'stderr is empty' is not a success test: PowerShell writes warnings to
    stderr too (false failure), and several cmdlets report a failure without
    writing anything there (false success). Wrapping the command makes any
    terminating error come back as exit code 1.
    """
    wrapped = ("$ErrorActionPreference='Stop'; try { " + cmd +
               " } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }; exit 0")
    r = subprocess.run(
        PS_ARGS + ["-Command", wrapped],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        creationflags=CREATE_NO_WINDOW)
    return r.returncode == 0, (r.stderr or "").strip()

def run_cmd(args):
    """Run a plain command (netsh, ipconfig, ping) with list arguments --
    no shell, so names with spaces or quotes cannot break the command line."""
    try:
        r = subprocess.run(
            args, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW, timeout=30)
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return False, str(e)

# ---------------------------------------------------------------------------
# Single batched PS call -- all adapter + profile data in one shot.
# Adapters are the primary list now (a disabled or unplugged card is visible);
# the connection profile is attached when one exists.
# ---------------------------------------------------------------------------
_BATCH_SCRIPT = r"""
$result = @()
$adapters = Get-NetAdapter -ErrorAction SilentlyContinue
if (-not $adapters) { Write-Output '[]'; exit }
if ($adapters -isnot [array]) { $adapters = @($adapters) }

$profiles = @{}
try {
    Get-NetConnectionProfile -ErrorAction SilentlyContinue |
        ForEach-Object { $profiles[$_.InterfaceAlias] = $_ }
} catch {}

$allIPs = @{}
try {
    Get-NetIPAddress -ErrorAction SilentlyContinue |
        Where-Object { $_.AddressFamily -eq 'IPv4' -or $_.AddressFamily -eq 'IPv6' } |
        ForEach-Object {
            if (-not $allIPs.ContainsKey($_.InterfaceAlias)) { $allIPs[$_.InterfaceAlias] = @() }
            $allIPs[$_.InterfaceAlias] += $_
        }
} catch {}

$gateways = @{}
try {
    Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        ForEach-Object {
            if (-not $gateways.ContainsKey($_.InterfaceAlias)) { $gateways[$_.InterfaceAlias] = $_.NextHop }
        }
} catch {}

$dnsMap = @{}
try {
    Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        ForEach-Object { $dnsMap[$_.InterfaceAlias] = @($_.ServerAddresses) -join ',' }
} catch {}

$dhcpMap = @{}
try {
    Get-NetIPInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        ForEach-Object { $dhcpMap[$_.InterfaceAlias] = ("$($_.Dhcp)" -eq 'Enabled') }
} catch {}

# netsh translates its field labels ("Radio type" -> "Type de radio",
# "Band" -> "Bande", "Channel" -> "Canal"...), so matching on labels only ever
# worked on an English Windows. Everything below matches on the VALUE shape
# instead, which is identical in every locale.
$wifiBlocks = @{}
try {
    $aliases = @{}
    foreach ($ad in $adapters) { $aliases[$ad.Name] = $true }

    $netshOut = netsh wlan show interfaces 2>$null
    $cur = $null
    foreach ($line in $netshOut) {
        $i = "$line".IndexOf(':')
        if ($i -lt 1) { continue }
        $label = "$line".Substring(0, $i).Trim()
        $value = "$line".Substring($i + 1).Trim()
        if ($value -eq '') { continue }

        if ($aliases.ContainsKey($value) -and -not $wifiBlocks.ContainsKey($value)) {
            $cur = $value
            $wifiBlocks[$cur] = @{ Signal=-1; RadioType=''; Band=''; Channel=-1 }
            continue
        }
        if (-not $cur) { continue }

        if ($value -match '^(\d{1,3})\s*%$')       { $wifiBlocks[$cur].Signal    = [int]$matches[1]; continue }
        if ($value -match '802\.11')               { $wifiBlocks[$cur].RadioType = $value;           continue }
        if ($value -match '\d+([.,]\d+)?\s*GHz')   { $wifiBlocks[$cur].Band      = $value;           continue }
        # Channel is the only bare integer left once the rate lines are skipped
        # (their label carries the unit: Mbps / Mbit/s / Mbits/s / MBit/s).
        if ($label -notmatch '(?i)b(it|ps)' -and $value -match '^\d{1,3}$' -and [int]$value -le 233) {
            if ($wifiBlocks[$cur].Channel -lt 0) { $wifiBlocks[$cur].Channel = [int]$value }
            continue
        }
    }
} catch {}

foreach ($ad in $adapters) {
    $a  = $ad.Name
    $st = "$($ad.Status)"
    if ($st -eq 'Not Present') { continue }
    $obj = [ordered]@{
        InterfaceAlias  = $a
        Description     = "$($ad.InterfaceDescription)"
        Status          = $st
        MacAddress      = "$($ad.MacAddress)"
        LinkSpeed       = "$($ad.LinkSpeed)"
        MediaType       = "$($ad.MediaType)"
        HasProfile      = $false
        ProfileName     = ''
        NetworkCategory = -1
        IPv4Address     = 'N/A'
        PrefixLength    = -1
        IPv6Address     = 'N/A'
        Gateway         = ''
        Dns             = ''
        DhcpEnabled     = $true
        WifiSignal      = -1
        WifiStandard    = ''
        WifiBand        = ''
        WifiChannel     = -1
    }
    if ($profiles.ContainsKey($a)) {
        $p = $profiles[$a]
        $obj.HasProfile      = $true
        $obj.ProfileName     = "$($p.Name)"
        $obj.NetworkCategory = [int]$p.NetworkCategory
    }
    if ($allIPs.ContainsKey($a)) {
        $v4e = $allIPs[$a] | Where-Object { $_.AddressFamily -eq 'IPv4' } | Select-Object -First 1
        $v6  = $allIPs[$a] | Where-Object { $_.AddressFamily -eq 'IPv6' -and
               $_.PrefixOrigin -ne 'WellKnown' } |
               Select-Object -First 1 -ExpandProperty IPAddress
        if ($v4e) { $obj.IPv4Address = "$($v4e.IPAddress)"; $obj.PrefixLength = [int]$v4e.PrefixLength }
        if ($v6)  { $obj.IPv6Address = $v6 }
    }
    if ($gateways.ContainsKey($a)) { $obj.Gateway = "$($gateways[$a])" }
    if ($dnsMap.ContainsKey($a))   { $obj.Dns = "$($dnsMap[$a])" }
    if ($dhcpMap.ContainsKey($a))  { $obj.DhcpEnabled = $dhcpMap[$a] }
    if ($wifiBlocks.ContainsKey($a)) {
        $w = $wifiBlocks[$a]
        $obj.WifiSignal   = $w.Signal
        $obj.WifiStandard = $w.RadioType
        $obj.WifiBand     = $w.Band
        $obj.WifiChannel  = $w.Channel
    }
    $result += $obj
}
$result | ConvertTo-Json -Compress -Depth 3
"""

def get_all_interface_data():
    out, _ = run_ps(_BATCH_SCRIPT)
    if not out:
        return []
    try:
        data = json.loads(out)
        data = [data] if isinstance(data, dict) else data
    except Exception:
        return []
    def sort_key(d):
        st = d.get("Status", "")
        if d.get("HasProfile") and st == "Up": rank = 0
        elif st == "Up":                       rank = 1
        elif st == "Disconnected":             rank = 2
        else:                                  rank = 3
        return (rank, str(d.get("InterfaceAlias", "")).lower())
    return sorted(data, key=sort_key)

def get_firewall_state():
    """Returns (enabled_count, total, {profile_name: bool})."""
    out, _ = run_ps(
        "Get-NetFirewallProfile -All | ForEach-Object { \"$($_.Name)=$($_.Enabled)\" }")
    if not out:
        return None, None, {}
    d = {}
    for line in out.splitlines():
        line = line.strip()
        if "=" in line:
            name, val = line.split("=", 1)
            d[name.strip()] = val.strip().lower() == "true"
    on = sum(1 for v in d.values() if v)
    return on, len(d), d

VALID_CATEGORIES = ("Private", "Public", "DomainAuthenticated")

def set_network_profile(alias, category):
    if category not in VALID_CATEGORIES:
        return False
    ok, err = run_ps_action(
        f"Set-NetConnectionProfile -InterfaceAlias {ps_quote(alias)} "
        f"-NetworkCategory {category}")
    log_event("profile", f"{alias} -> {category} : {'ok' if ok else 'FAILED ' + err}")
    return ok

FW_PROFILE_NAMES = ("Domain", "Private", "Public")

def set_firewall_profiles(names, enable):
    names = [n for n in names if n in FW_PROFILE_NAMES]
    if not names:
        return False
    val = "True" if enable else "False"
    ok, err = run_ps_action(
        f"Set-NetFirewallProfile -Profile {','.join(names)} -Enabled {val}")
    log_event("firewall", f"{','.join(names)} -> {'ON' if enable else 'OFF'} : "
                          f"{'ok' if ok else 'FAILED ' + err}")
    return ok

def set_firewall_state(enable):
    val = "True" if enable else "False"
    ok, err = run_ps_action(f"Set-NetFirewallProfile -All -Enabled {val}")
    log_event("firewall", f"ALL -> {'ON' if enable else 'OFF'} : "
                          f"{'ok' if ok else 'FAILED ' + err}")
    return ok

# ---------------------------------------------------------------------------
# IP configuration (netsh with list args -- immune to names with spaces)
# ---------------------------------------------------------------------------
def apply_dhcp(alias, addr_already_dhcp=False):
    ok1 = True
    if not addr_already_dhcp:
        ok1, out = run_cmd(["netsh", "interface", "ipv4", "set", "address",
                            f"name={alias}", "source=dhcp"])
    ok2, out2 = run_cmd(["netsh", "interface", "ipv4", "set", "dnsservers",
                         f"name={alias}", "source=dhcp"])
    ok = ok1 and ok2
    log_event("ipconfig", f"{alias} -> DHCP : {'ok' if ok else 'FAILED'}")
    return ok

def apply_static(alias, ip, mask, gw, dns_list):
    args = ["netsh", "interface", "ipv4", "set", "address",
            f"name={alias}", "source=static", f"address={ip}", f"mask={mask}"]
    if gw:
        args += [f"gateway={gw}", "gwmetric=1"]
    ok, out = run_cmd(args)
    if ok:
        dns_list = [d for d in dns_list if d]
        if dns_list:
            ok, _ = run_cmd(["netsh", "interface", "ipv4", "set", "dnsservers",
                             f"name={alias}", "source=static",
                             f"address={dns_list[0]}", "register=primary", "validate=no"])
            for i, d in enumerate(dns_list[1:], start=2):
                run_cmd(["netsh", "interface", "ipv4", "add", "dnsservers",
                         f"name={alias}", f"address={d}", f"index={i}", "validate=no"])
        else:
            run_cmd(["netsh", "interface", "ipv4", "set", "dnsservers",
                     f"name={alias}", "source=static", "address=none", "validate=no"])
    log_event("ipconfig", f"{alias} -> static {ip}/{mask} gw={gw or '-'} "
                          f"dns={','.join(dns_list) or '-'} : {'ok' if ok else 'FAILED'}")
    return ok

def capture_ip_config(d):
    """Snapshot of one adapter's v4 config (from the last data load), used to
    roll back an IP change that went wrong."""
    return {
        "dhcp": bool(d.get("DhcpEnabled", True)),
        "ip":   d.get("IPv4Address", "N/A"),
        "mask": prefix_to_mask(d.get("PrefixLength", -1)),
        "gw":   d.get("Gateway", ""),
        "dns":  [x for x in str(d.get("Dns", "")).split(",") if x],
    }

def restore_ip_config(alias, snap):
    if snap["dhcp"]:
        return apply_dhcp(alias)
    if not valid_ip(snap["ip"]) or not snap["mask"]:
        return apply_dhcp(alias)     # nothing sane to restore -- DHCP is the safe default
    return apply_static(alias, snap["ip"], snap["mask"], snap["gw"], snap["dns"])

# ---------------------------------------------------------------------------
# Adapter management + network tools
# ---------------------------------------------------------------------------
def adapter_set_enabled(alias, enable):
    verb = "Enable-NetAdapter" if enable else "Disable-NetAdapter"
    ok, err = run_ps_action(f"{verb} -Name {ps_quote(alias)} -Confirm:$false")
    log_event("adapter", f"{alias} -> {'enabled' if enable else 'disabled'} : "
                         f"{'ok' if ok else 'FAILED ' + err}")
    return ok

def adapter_rename(alias, new_name):
    ok, err = run_ps_action(
        f"Rename-NetAdapter -Name {ps_quote(alias)} -NewName {ps_quote(new_name)}")
    log_event("adapter", f"rename {alias} -> {new_name} : {'ok' if ok else 'FAILED ' + err}")
    return ok

# ---------------------------------------------------------------------------
# Launch at logon
#
# A plain HKCU\Run entry CANNOT start an app that requires administrator
# rights: Windows either skips it or prompts for UAC at every single logon.
# A scheduled task with "run with highest privileges" starts it elevated and
# silently — that is the supported way to autostart an elevated app.
# ---------------------------------------------------------------------------
TASK_NAME = "NetCatChanger"

def _app_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    return f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}" --minimized'

def autostart_enabled():
    ok, out = run_cmd(["schtasks", "/Query", "/TN", TASK_NAME])
    return ok

def autostart_set(enable):
    # Always drop the legacy registry entry: it would double-launch the app
    # for anyone upgrading from 2.1.0 / 2.2.0.
    if winreg is not None:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            try:    winreg.DeleteValue(key, TASK_NAME)
            except OSError: pass
            winreg.CloseKey(key)
        except Exception:
            pass

    if enable:
        ok, out = run_cmd(["schtasks", "/Create", "/TN", TASK_NAME,
                           "/TR", _app_command(), "/SC", "ONLOGON",
                           "/RL", "HIGHEST", "/F"])
    else:
        ok, out = run_cmd(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
        if not ok and "cannot find" in (out or "").lower():
            ok = True          # already absent is a success
    log_event("settings", f"autostart -> {'on' if enable else 'off'} : "
                          f"{'ok' if ok else 'FAILED ' + (out or '').strip()[:80]}")
    return ok

def flush_dns():
    ok, _ = run_cmd(["ipconfig", "/flushdns"])
    log_event("tools", f"flush dns : {'ok' if ok else 'FAILED'}")
    return ok

def renew_dhcp(alias):
    ok, _ = run_cmd(["ipconfig", "/renew", alias])
    log_event("tools", f"renew dhcp {alias} : {'ok' if ok else 'FAILED'}")
    return ok

def ping_ok(host):
    if sys.platform != "win32":
        return False
    ok, _ = run_cmd(["ping", "-n", "1", "-w", "1200", host])
    return ok

def dns_ok():
    try:
        socket.getaddrinfo("www.microsoft.com", 443)
        return True
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
def detect_iface_type(alias, media_type="", wifi_seen=False):
    # wifi_seen wins: if netsh reported a Wi-Fi block for this alias it IS Wi-Fi,
    # whatever the adapter happens to be named in the user's language.
    if wifi_seen:
        return "wifi"
    kws = ["wi-fi", "wifi", "wireless", "wlan", "802.11", "wi fi", "airport",
           "sans fil", "drahtlos", "inalámbrica"]
    if any(k in alias.lower() for k in kws):
        return "wifi"
    if "802.11" in media_type.lower():
        return "wifi"
    return "ethernet"

def parse_wifi_standard(radio_type):
    rt = radio_type.lower().replace(" ", "")
    if "802.11be" in rt: return "Wi-Fi 7  802.11be"
    if "802.11ax" in rt: return "Wi-Fi 6  802.11ax"
    if "802.11ac" in rt: return "Wi-Fi 5  802.11ac"
    if "802.11n"  in rt: return "Wi-Fi 4  802.11n"
    if "802.11g"  in rt: return "Wi-Fi 3  802.11g"
    if "802.11b"  in rt: return "Wi-Fi 2  802.11b"
    if "802.11a"  in rt: return "Wi-Fi 1  802.11a"
    return radio_type.strip()

def parse_wifi_band(band_str, channel):
    # A French Windows prints "2,4 GHz" - hence the comma handling.
    b = (band_str or "").lower().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*ghz", b)
    if m:
        v = float(m.group(1))
        if abs(v - 2.4) < 0.3: return "2.4 GHz"
        if abs(v - 5.0) < 0.6: return "5 GHz"
        if abs(v - 6.0) < 0.6: return "6 GHz"
        return f"{m.group(1)} GHz"
    if channel > 0:
        if channel <= 14:  return "2.4 GHz"
        if channel <= 177: return "5 GHz"
        return "6 GHz"
    return ""

def parse_link_speed(speed_str):
    if not speed_str or speed_str.strip() in ("", "0"):
        return ""
    s = speed_str.strip().lower()
    if "gbps" in s or "mbps" in s:
        return speed_str.strip()
    try:
        bps = int(re.sub(r"[^\d]", "", s))
        if bps >= 10_000_000_000: return "10 Gbps"
        if bps >=  5_000_000_000: return "5 Gbps"
        if bps >=  2_500_000_000: return "2.5 Gbps"
        if bps >=  1_000_000_000: return "1 Gbps"
        if bps >=    100_000_000: return "100 Mbps"
        if bps >=     10_000_000: return "10 Mbps"
        return f"{bps // 1_000_000} Mbps"
    except Exception:
        return speed_str.strip()

def signal_color(pct):
    if pct >= 70: return DOMAIN
    if pct >= 40: return WARN
    return PUBLIC

# ---------------------------------------------------------------------------
# Background watcher
#
# One long-lived PowerShell process that polls internally and prints a line
# only when something actually changed: profiles, firewall, adapter status.
# ---------------------------------------------------------------------------
_WATCH_SCRIPT = r"""
$last  = ''
$first = $true
while ($true) {
    try {
        $s = (Get-NetConnectionProfile -ErrorAction SilentlyContinue |
              Sort-Object InterfaceAlias |
              ForEach-Object { "$($_.InterfaceAlias)=$([int]$_.NetworkCategory)" }) -join ';'
        $f = (Get-NetFirewallProfile -All -ErrorAction SilentlyContinue |
              ForEach-Object { "$($_.Enabled)" }) -join ','
        $a = (Get-NetAdapter -ErrorAction SilentlyContinue |
              Sort-Object Name |
              ForEach-Object { "$($_.Name)=$($_.Status)" }) -join ';'
        $cur = "$s|$f|$a"
        if ($first) { $last = $cur; $first = $false }
        elseif ($cur -ne $last) {
            $last = $cur
            Write-Output 'CHANGED'
            [Console]::Out.Flush()
        }
    } catch {}
    Start-Sleep -Seconds 3
}
"""

class NetworkWatcher:
    def __init__(self, callback):
        self._cb      = callback
        self._running = False
        self._proc    = None

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False
        p = self._proc
        self._proc = None
        if p:
            try:    p.kill()
            except Exception: pass

    def _loop(self):
        while self._running:
            try:
                self._proc = subprocess.Popen(
                    PS_ARGS + ["-Command", _WATCH_SCRIPT],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL, text=True,
                    encoding="utf-8", errors="replace",
                    creationflags=CREATE_NO_WINDOW)
                for line in self._proc.stdout:
                    if not self._running:
                        break
                    if line.strip() == "CHANGED":
                        self._cb()
            except Exception:
                pass
            if not self._running:
                break
            time.sleep(5)   # the helper died -- back off, then restart it

# ---------------------------------------------------------------------------
# Icon cache -- each key loaded once per session
# ---------------------------------------------------------------------------
_icon_cache: dict = {}

def load_icon_cached(key):
    if key in _icon_cache:
        return _icon_cache[key]
    b64 = ICONS.get(key, "")
    if not b64:
        _icon_cache[key] = None
        return None
    try:
        img = tk.PhotoImage(data=b64)
        _icon_cache[key] = img
        return img
    except Exception:
        _icon_cache[key] = None
        return None

# ---------------------------------------------------------------------------
# Color palette — ingesto design tokens ("Direction A · Sleek").
# tkinter has no alpha channel, so every rgba() tint from ingesto's CSS is
# pre-mixed here as a solid color over the surface it sits on.
# ---------------------------------------------------------------------------
BG      = "#0e0f13"   # window          (ingesto --bg)
CARD    = "#121318"   # cards           (--bg2)
BG3     = "#16181d"   # inputs, chips   (--bg3)
BG4     = "#1b1d24"   # hover, bars     (--bg4)
BORDER  = "#232428"   # white 7%  over CARD
BORDER2 = "#313236"   # white 13% over CARD
TEXT    = "#e8eaf0"   # --text
TEXT2   = "#aeb3bd"   # --text2
MUTED   = "#8b909b"   # --text3
PRIVATE = "#8b6ff0"   # --accent  -> Private profile
PUBLIC  = "#f2555a"   # --red     -> Public profile
DOMAIN  = "#35c98b"   # --green   -> Domain / healthy states
ACCENT  = "#8b6ff0"
BLUE    = "#4d90f0"   # --blue    -> DHCP
WARN    = "#f2a03d"   # --orange  -> static IP, warnings
HOVER   = "#1b1d24"
FAINT   = "#3d404b"

# tinted dims + borders (pre-mixed rgba over CARD)
PRIVATE_D, PRIVATE_BD = "#28243f", "#483c79"
GREEN_D,   GREEN_BD   = "#172c28", "#1c4638"
GREEN_BD2             = "#246e52"
RED_D,     RED_BD     = "#341d22", "#55272c"
RED_BD2               = "#823439"
BLUE_D,    BLUE_BD    = "#1a2436", "#243859"
ORANGE_D,  ORANGE_BD  = "#31271d", "#553d23"

FONT = "Segoe UI"
MONO = "Consolas"

# Poppins Bold (SIL OFL, bundled) for the logo and section titles — loaded
# privately through GDI, nothing is installed on the system.
DISPLAY_FAMILY = "Segoe UI"

def resource_path(rel):
    base = getattr(sys, "_MEIPASS",
                   os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

def load_display_font():
    global DISPLAY_FAMILY
    if sys.platform != "win32":
        return
    try:
        p = resource_path(os.path.join("fonts", "Poppins-Bold.ttf"))
        FR_PRIVATE = 0x10
        if os.path.exists(p) and \
           ctypes.windll.gdi32.AddFontResourceExW(p, FR_PRIVATE, 0) > 0:
            DISPLAY_FAMILY = "Poppins"
    except Exception:
        pass

PROFILE_MAP = {
    "Private":             {"label": "Private", "color": PRIVATE, "icon_key": "private"},
    "Public":              {"label": "Public",  "color": PUBLIC,  "icon_key": "public"},
    "DomainAuthenticated": {"label": "Domain",  "color": DOMAIN,  "icon_key": "domain"},
}
CAT_BY_INT = {0: "Public", 1: "Private", 2: "DomainAuthenticated"}

def enable_hidpi():
    """Declare DPI awareness BEFORE the Tk window exists, otherwise Windows
    scales a low-resolution bitmap of the UI and everything is blurry on
    150 % / 200 % displays."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()    # pre-8.1 fallback
        except Exception:
            pass

# ---------------------------------------------------------------------------
# PillSwitch — ingesto-style pill switch drawn on a Canvas.
# Two arbitrary states (left / right), each with its own tint colors, so the
# same widget serves Public<->Private (red/violet) and firewall OFF/ON
# (red/green) without ever looking like the other one.
# ---------------------------------------------------------------------------
class PillSwitch(tk.Canvas):
    def __init__(self, parent, on_click=None, right_active=False,
                 colors_left=None, colors_right=None,
                 w=38, h=22, bg=None):
        super().__init__(parent, width=w, height=h,
                         bg=bg or CARD, highlightthickness=0, bd=0,
                         cursor="hand2")
        # NB: tkinter widgets use self._w internally (the Tcl path name) --
        # shadowing it breaks every Canvas call, so the size gets its own names.
        self._sw_w, self._sw_h = w, h
        self._cb     = on_click
        self._right  = bool(right_active)
        self._cl     = colors_left  or (RED_D, RED_BD2, PUBLIC)
        self._cr     = colors_right or (PRIVATE_D, PRIVATE_BD, PRIVATE)
        self._knob_x = None
        self.bind("<Button-1>", lambda e: self._cb() if self._cb else None)
        self._draw(self._target_x())

    def _target_x(self):
        return (self._sw_w - self._sw_h + 3) if self._right else 3

    def set_state(self, right_active, animate=False):
        right_active = bool(right_active)
        if animate and right_active != self._right and self._knob_x is not None:
            self._right = right_active
            start, end = self._knob_x, self._target_x()
            steps = 5
            def step(i):
                try:
                    self._draw(start + (end - start) * i / steps)
                    if i < steps:
                        self.after(18, lambda: step(i + 1))
                except Exception:
                    pass
            step(1)
        else:
            self._right = right_active
            self._draw(self._target_x())

    def _draw(self, kx):
        self.delete("all")
        d, bd, fg = self._cr if self._right else self._cl
        w, h = self._sw_w, self._sw_h
        r = h // 2
        self.create_oval(0, 0, h - 1, h - 1, fill=d, outline=bd)
        self.create_oval(w - h, 0, w - 1, h - 1, fill=d, outline=bd)
        self.create_rectangle(r, 1, w - r, h - 1, fill=d, outline=d)
        self.create_line(r, 0, w - r, 0, fill=bd)
        self.create_line(r, h - 1, w - r, h - 1, fill=bd)
        k = h - 6
        kx = int(kx)
        self.create_oval(kx, 3, kx + k, 3 + k, fill=fg, outline=fg)
        self._knob_x = kx

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        global LOG_ENABLED
        self.cfg = load_config()
        LOG_ENABLED = bool(self.cfg.get("log_enabled", True))

        self.read_only = (sys.platform == "win32") and not is_admin()

        self.title(f"NetCatChanger {APP_VERSION}")
        try:
            self._scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except Exception:
            self._scale = 1.0
        s = self._scale
        w, h = int(880 * s), int(700 * s)
        self.minsize(int(720 * s), int(540 * s))
        self.configure(bg=BG)
        self.resizable(True, True)
        geo = str(self.cfg.get("geometry", ""))
        if re.match(r"^\d+x\d+\+-?\d+\+-?\d+$", geo):
            self.geometry(geo)
        else:
            self.update_idletasks()
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry(f"{w}x{h}+{max(0,(sw-w)//2)}+{max(0,(sh-h)//2)}")

        self._fw_enabled   = None
        self._fw_profiles  = {}
        self._fw_animating = False
        self._fw_deadline  = None      # epoch when the firewall auto-rearms
        self._loading      = False
        self._data         = []
        self._diag_gen     = 0
        self._gw_chips     = {}        # alias -> tk.Label for gateway diag
        self._undo_info    = None
        self._toastf       = None
        self._toast_timer  = None
        self._tray         = None

        self._build_ui()
        self._load_all()
        self._init_tray()

        self._watcher = NetworkWatcher(self._on_net_change)
        self._watcher.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close_btn)

        # Start hidden when launched by Windows autostart (--minimized) or
        # when the user chose to always start in the tray.
        if self._tray and ("--minimized" in sys.argv or self.cfg.get("start_minimized")):
            self.withdraw()

        self.after(1800, self._check_update_async)
        log_event("session", f"start v{APP_VERSION} admin={not self.read_only}")

    # -----------------------------------------------------------------------
    # Window / tray lifecycle
    # -----------------------------------------------------------------------
    def _on_close_btn(self):
        self._save_geometry()
        if self.cfg.get("close_to_tray", True) and self._tray:
            self.withdraw()
        else:
            self._quit()

    def _save_geometry(self):
        try:
            self.cfg["geometry"] = self.geometry()
        except Exception:
            pass

    def _quit(self):
        # Never leave the machine unprotected because the app died with a
        # temporary-disable timer pending.
        if self._fw_deadline is not None:
            set_firewall_state(True)
            log_event("firewall", "re-enabled on exit (timer was pending)")
        self._save_geometry()
        save_config(self.cfg)
        try:
            self._watcher.stop()
        except Exception:
            pass
        if self._tray:
            try:    self._tray.stop()
            except Exception: pass
            self._tray = None
        log_event("session", "exit")
        self.destroy()

    def _show_window(self):
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    # -----------------------------------------------------------------------
    # Tray icon
    # -----------------------------------------------------------------------
    def _init_tray(self):
        if pystray is None or PILImage is None:
            return
        b64 = ICONS.get("logo", "")
        if not b64:
            return
        try:
            img = PILImage.open(_io.BytesIO(base64.b64decode(b64)))
        except Exception:
            return

        def on_open(icon, item):
            self._show_window()

        def on_quit(icon, item):
            self.after(0, self._quit)

        def iface_items():
            items = []
            for d in self._data:
                if not d.get("HasProfile") or d.get("Status") != "Up":
                    continue
                cat = CAT_BY_INT.get(int(d.get("NetworkCategory", -1)), None)
                if cat not in ("Private", "Public"):
                    continue
                alias = d.get("InterfaceAlias", "?")
                tgt = "Public" if cat == "Private" else "Private"
                def make_cb(a=alias, t=tgt):
                    def cb(icon, item):
                        self.after(0, lambda: self._switch_profile(a, t))
                    return cb
                items.append(pystray.MenuItem(
                    f"{alias} : {PROFILE_MAP[cat]['label']}  →  {tgt}", make_cb()))
            if not items:
                items.append(pystray.MenuItem("No switchable interface",
                                              None, enabled=False))
            return items

        try:
            menu = pystray.Menu(
                pystray.MenuItem("Open NetCatChanger", on_open, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Switch profile", pystray.Menu(iface_items)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", on_quit))
            self._tray = pystray.Icon("NetCatChanger", img, "NetCatChanger", menu)
            threading.Thread(target=self._tray.run, daemon=True).start()
        except Exception:
            self._tray = None

    def _tray_refresh(self):
        if self._tray:
            try:    self._tray.update_menu()
            except Exception: pass

    # -----------------------------------------------------------------------
    def _on_net_change(self):
        if not self._loading:
            self.after(500, self._load_all)

    # -----------------------------------------------------------------------
    # Icon helpers
    # -----------------------------------------------------------------------
    def _icon(self, key):
        return load_icon_cached(key)

    def _set_img(self, label, img, fallback="", font=None, fg=TEXT):
        if img:
            label.config(image=img, text="", width=0, height=0)
        else:
            kw = {"text": fallback, "image": ""}
            if font: kw["font"] = font
            if fg:   kw["fg"]   = fg
            label.config(**kw)

    # -----------------------------------------------------------------------
    # Admin gate
    # -----------------------------------------------------------------------
    def _require_admin(self):
        if not self.read_only:
            return True
        if messagebox.askyesno(
                "Administrator rights required",
                "This change needs administrator rights.\n\n"
                "Restart NetCatChanger as administrator?", parent=self):
            if run_as_admin():
                self._quit()     # only quit once the elevated copy is starting
            else:
                messagebox.showwarning(
                    "Still read-only",
                    "Windows did not grant administrator rights, so "
                    "NetCatChanger stays in read-only mode.\n\n"
                    "You can also right-click NetCatChanger and choose "
                    "\"Run as administrator\".", parent=self)
        return False

    # -----------------------------------------------------------------------
    # Build UI
    # -----------------------------------------------------------------------
    def _build_ui(self):
        s = self._scale

        # FOOTER -- packed first so it stays at bottom
        tk.Frame(self, bg=BORDER, height=1).pack(side="bottom", fill="x")
        footer = tk.Frame(self, bg=BG)
        footer.pack(side="bottom", fill="x")
        fi = tk.Frame(footer, bg=BG, pady=8)
        fi.pack(fill="x", padx=16)

        by = tk.Frame(fi, bg=BG)
        by.pack(side="left")
        tk.Label(by, text=f"v{APP_VERSION}", font=(MONO, 8),
                 fg=MUTED, bg=BG).pack(side="left")
        self._status_lbl = tk.Label(by, text="  ·  Loading...",
                                    font=(FONT, 8), fg=MUTED, bg=BG)
        self._status_lbl.pack(side="left", padx=(0, 6))
        for txt, cb in (("GitHub", lambda: webbrowser.open(GITHUB_URL)),
                        ("About",  self._show_about),
                        ("Log",    self._open_log),
                        ("Settings", self._show_settings)):
            tk.Label(by, text=" · ", font=(FONT, 8),
                     fg=FAINT, bg=BG).pack(side="left")
            lb = tk.Label(by, text=txt, font=(FONT, 8, "bold"),
                          fg=MUTED, bg=BG, cursor="hand2")
            lb.pack(side="left")
            lb.bind("<Button-1>", lambda e, c=cb: c())
            lb.bind("<Enter>", lambda e, l=lb: l.config(fg=PRIVATE))
            lb.bind("<Leave>", lambda e, l=lb: l.config(fg=MUTED))

        self._flat_btn(fi, "Flush DNS", self._do_flush_dns).pack(side="right")

        # HEADER — titlebar-like row, ingesto style
        header = tk.Frame(self, bg=BG)
        header.pack(side="top", fill="x")

        top = tk.Frame(header, bg=BG, pady=10)
        top.pack(fill="x", padx=16)

        logo = tk.Frame(top, bg=BG)
        logo.pack(side="left")
        for part, col in (("net", TEXT), ("cat", PRIVATE), ("changer", TEXT)):
            tk.Label(logo, text=part, font=(DISPLAY_FAMILY, 15, "bold"),
                     fg=col, bg=BG, bd=0, padx=0).pack(side="left")
        tk.Label(top, text="  Windows Network Profile Manager",
                 font=(FONT, 8), fg=MUTED, bg=BG).pack(side="left", anchor="s", pady=(0, 4))

        rt = tk.Frame(top, bg=BG)
        rt.pack(side="right")
        self._refresh_btn = self._flat_btn(rt, "Refresh", self._load_all)
        self._refresh_btn.pack(side="right")
        self._dns_chip = self._chip(rt, "DNS …", MUTED, BG3, BORDER)
        self._dns_chip.pack(side="right", padx=(0, 8))
        self._inet_chip = self._chip(rt, "Internet …", MUTED, BG3, BORDER)
        self._inet_chip.pack(side="right", padx=(0, 6))
        if self.read_only:
            ro = self._chip(rt, "READ-ONLY", WARN, ORANGE_D, ORANGE_BD)
            ro.pack(side="right", padx=(0, 8))

        self._sep_frame = tk.Frame(self, bg=BORDER, height=1)
        self._sep_frame.pack(side="top", fill="x")

        # READ-ONLY BAR — only ever seen when the user refused the UAC prompt.
        # Full width and clickable: nothing on screen should leave someone
        # wondering why the switches do nothing.
        if self.read_only:
            robar = tk.Frame(self, bg=ORANGE_D, cursor="hand2")
            robar.pack(side="top", fill="x")
            roi = tk.Frame(robar, bg=ORANGE_D, padx=16, pady=7)
            roi.pack(fill="x")
            tk.Label(roi, text="⚠  Read-only mode — administrator rights were "
                               "declined, so nothing can be changed.",
                     font=(FONT, 9, "bold"), fg=WARN, bg=ORANGE_D).pack(side="left")
            tk.Label(roi, text="Restart as administrator",
                     font=(FONT, 9, "bold underline"), fg=TEXT,
                     bg=ORANGE_D, cursor="hand2").pack(side="right")
            for w in (robar, roi) + tuple(roi.winfo_children()):
                w.bind("<Button-1>", lambda e: self._require_admin())
            tk.Frame(self, bg=ORANGE_BD, height=1).pack(side="top", fill="x")

        # FIREWALL CARD
        fwrap = tk.Frame(self, bg=BG)
        fwrap.pack(side="top", fill="x", padx=16, pady=(12, 2))
        fw_b = tk.Frame(fwrap, bg=BORDER, padx=1, pady=1)
        fw_b.pack(fill="x")
        fwi = tk.Frame(fw_b, bg=CARD, padx=14, pady=11)
        fwi.pack(fill="x")

        tile = tk.Frame(fwi, bg=GREEN_D, width=int(34 * s), height=int(34 * s))
        tile.pack_propagate(False)
        tile.pack(side="left", padx=(0, 12))
        self._fw_icon_lbl = tk.Label(tile, bg=GREEN_D, bd=0)
        self._fw_icon_lbl.pack(expand=True)
        self._fw_tile = tile

        fw_txt = tk.Frame(fwi, bg=CARD)
        fw_txt.pack(side="left", fill="x", expand=True)
        tk.Label(fw_txt, text="WINDOWS FIREWALL",
                 font=(DISPLAY_FAMILY, 9, "bold"), fg=TEXT, bg=CARD).pack(anchor="w")
        self._fw_sub = tk.Label(fw_txt, text="Checking...",
                                font=(FONT, 8), fg=MUTED, bg=CARD)
        self._fw_sub.pack(anchor="w")

        rfw = tk.Frame(fwi, bg=CARD)
        rfw.pack(side="right")
        self._fw_badge = self._chip(rfw, "--", MUTED, BG3, BORDER)
        self._fw_badge.pack(side="left", padx=(0, 10))
        self._fw_switch = PillSwitch(
            rfw, on_click=self._on_fw_click, right_active=False,
            colors_left=(RED_D, RED_BD2, PUBLIC),
            colors_right=(GREEN_D, GREEN_BD2, DOMAIN), bg=CARD)
        self._fw_switch.pack(side="left")

        # SCROLLABLE CARD LIST
        outer = tk.Frame(self, bg=BG)
        outer.pack(side="top", fill="both", expand=True, padx=16, pady=(10, 12))

        scv = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        sb  = tk.Scrollbar(outer, orient="vertical", command=scv.yview,
                           bg=BG4, troughcolor=BG, activebackground=BORDER2,
                           relief="flat", bd=0, width=5)
        scv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        scv.pack(side="left", fill="both", expand=True)

        self._list_frame = tk.Frame(scv, bg=BG)
        win = scv.create_window((0, 0), window=self._list_frame, anchor="nw")
        self._list_frame.bind("<Configure>",
            lambda e: scv.configure(scrollregion=scv.bbox("all")))
        scv.bind("<Configure>",
            lambda e: scv.itemconfig(win, width=e.width))
        scv.bind_all("<MouseWheel>",
            lambda e: scv.yview_scroll(-1 * (e.delta // 120), "units"))

    def _flat_btn(self, parent, text, cmd, fg=TEXT):
        b = tk.Button(parent, text=text,
                      font=(FONT, 9, "bold"), fg=fg, bg=BG3,
                      activeforeground=TEXT, activebackground=BG4,
                      relief="flat", bd=0, cursor="hand2", padx=14, pady=5,
                      highlightthickness=1, highlightbackground=BORDER,
                      command=cmd)
        b.bind("<Enter>", lambda e: b.config(bg=BG4))
        b.bind("<Leave>", lambda e: b.config(bg=BG3))
        return b

    def _mini_btn(self, parent, text, cmd, fg=MUTED):
        b = tk.Button(parent, text=text,
                      font=(FONT, 8, "bold"), fg=fg, bg=CARD,
                      activeforeground=TEXT, activebackground=BG4,
                      relief="flat", bd=0, cursor="hand2", padx=7, pady=2,
                      command=cmd)
        b.bind("<Enter>", lambda e: b.config(fg=TEXT, bg=BG4))
        b.bind("<Leave>", lambda e: b.config(fg=fg, bg=CARD))
        return b

    def _chip(self, parent, text, fg, bg, bd):
        """Tinted badge à la ingesto: dim background, colored text, 1px border."""
        return tk.Label(parent, text=text, font=(FONT, 8, "bold"),
                        fg=fg, bg=bg, padx=8, pady=2,
                        highlightthickness=1, highlightbackground=bd)

    def _set_chip(self, chip, text, fg, bg, bd):
        chip.config(text=text, fg=fg, bg=bg, highlightbackground=bd)

    # -----------------------------------------------------------------------
    # Toast (bottom overlay, with optional action button e.g. Undo)
    # -----------------------------------------------------------------------
    def toast(self, msg, action_label=None, action_cb=None, ms=3500):
        self._toast_clear()
        f = tk.Frame(self, bg=BORDER2, padx=1, pady=1)
        inner = tk.Frame(f, bg=BG4, padx=14, pady=8)
        inner.pack()
        tk.Label(inner, text=msg, font=(FONT, 9),
                 fg=TEXT, bg=BG4).pack(side="left")
        if action_label and action_cb:
            def do_action():
                self._toast_clear()
                action_cb()
            ab = tk.Button(inner, text=action_label,
                           font=(FONT, 9, "bold"), fg=ACCENT, bg=BG4,
                           activeforeground=TEXT, activebackground=BG4,
                           relief="flat", bd=0, cursor="hand2", command=do_action)
            ab.pack(side="left", padx=(12, 0))
        f.place(relx=0.5, rely=1.0, y=-58, anchor="s")
        self._toastf = f
        self._toast_timer = self.after(ms, self._toast_clear)

    def _toast_clear(self):
        if self._toast_timer:
            try:    self.after_cancel(self._toast_timer)
            except Exception: pass
            self._toast_timer = None
        if self._toastf:
            try:    self._toastf.destroy()
            except Exception: pass
            self._toastf = None

    # -----------------------------------------------------------------------
    # Load all data (interfaces + firewall) in parallel
    # -----------------------------------------------------------------------
    def _load_all(self):
        if self._loading:
            return
        self._loading = True
        self._set_status("loading")
        self._refresh_btn.config(state="disabled")

        def fetch():
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_ifaces   = ex.submit(get_all_interface_data)
                f_firewall = ex.submit(get_firewall_state)
                ifaces               = f_ifaces.result()
                fw_on, fw_total, fwp = f_firewall.result()
            self.after(0, lambda: self._render_all(ifaces, fw_on, fw_total, fwp))

        threading.Thread(target=fetch, daemon=True).start()

    def _render_all(self, ifaces, fw_on, fw_total, fwp):
        self._data = ifaces
        self._render_cards(ifaces)
        self._fw_profiles = fwp
        self._update_fw_ui(fw_on, fw_total)
        self._refresh_btn.config(state="normal")
        self._loading = False
        self._tray_refresh()
        self._start_diagnostics()

    # -----------------------------------------------------------------------
    # Diagnostics -- gateway ping per interface, DNS + internet globally
    # -----------------------------------------------------------------------
    def _start_diagnostics(self):
        self._diag_gen += 1
        gen = self._diag_gen
        targets = [(d.get("InterfaceAlias"), d.get("Gateway"))
                   for d in self._data
                   if d.get("Status") == "Up" and d.get("Gateway")]

        def work():
            net = ping_ok("1.1.1.1")
            dns = dns_ok()
            def upd_global():
                if gen != self._diag_gen: return
                if net:
                    self._set_chip(self._inet_chip, "Internet ✓", DOMAIN, GREEN_D, GREEN_BD)
                else:
                    self._set_chip(self._inet_chip, "Internet ✗", PUBLIC, RED_D, RED_BD)
                if dns:
                    self._set_chip(self._dns_chip, "DNS ✓", DOMAIN, GREEN_D, GREEN_BD)
                else:
                    self._set_chip(self._dns_chip, "DNS ✗", PUBLIC, RED_D, RED_BD)
            self.after(0, upd_global)
            for alias, gw in targets:
                ok = ping_ok(gw)
                def upd(a=alias, o=ok):
                    if gen != self._diag_gen: return
                    chip = self._gw_chips.get(a)
                    if chip:
                        if o:
                            self._set_chip(chip, "GW ✓", DOMAIN, GREEN_D, GREEN_BD)
                        else:
                            self._set_chip(chip, "GW ✗", PUBLIC, RED_D, RED_BD)
                self.after(0, upd)

        threading.Thread(target=work, daemon=True).start()

    # -----------------------------------------------------------------------
    # Render adapter cards
    # -----------------------------------------------------------------------
    def _render_cards(self, data):
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._gw_chips = {}

        if not data:
            tk.Label(self._list_frame,
                     text="No network adapter found.",
                     font=(FONT, 11), fg=MUTED, bg=BG,
                     justify="center").pack(pady=60)
            self._set_status("error")
            return

        for d in data:
            self._make_card(self._list_frame, d).pack(fill="x", pady=(0, 10))
        self._set_status("ok")

    # -----------------------------------------------------------------------
    # Card builder
    # -----------------------------------------------------------------------
    def _make_card(self, parent, p):
        s = self._scale
        alias  = p.get("InterfaceAlias", "Unknown")
        status = p.get("Status", "")
        active = p.get("HasProfile") and status == "Up"

        cat = CAT_BY_INT.get(int(p.get("NetworkCategory", -1)), None)
        info = PROFILE_MAP.get(cat) if cat else None

        name  = p.get("ProfileName", "") or p.get("Description", "")
        v4    = p.get("IPv4Address", "N/A")
        v6    = p.get("IPv6Address", "N/A")
        gw    = p.get("Gateway", "")
        media = p.get("MediaType", "")
        dhcp  = bool(p.get("DhcpEnabled", True))

        signal   = int(p.get("WifiSignal", -1))
        standard = parse_wifi_standard(p.get("WifiStandard", ""))
        band     = parse_wifi_band(p.get("WifiBand", ""), int(p.get("WifiChannel", -1)))
        link_spd = parse_link_speed(p.get("LinkSpeed", ""))
        itype = detect_iface_type(alias, media,
                                  wifi_seen=(signal >= 0 or bool(standard)))

        apipa = is_apipa(v4)
        color = info["color"] if (active and info) else MUTED
        ikey  = info["icon_key"] if (active and info) else "muted"
        tile_bg = ({"Private": PRIVATE_D, "Public": RED_D,
                    "DomainAuthenticated": GREEN_D}.get(cat, BG3)
                   if active else BG3)

        outer = tk.Frame(parent, bg=(RED_BD2 if apipa else BORDER), padx=1, pady=1)
        card  = tk.Frame(outer, bg=CARD, padx=14, pady=11)
        card.pack(fill="both", expand=True)

        # -- Icon tile (ingesto-style tinted square) --
        tile = tk.Frame(card, bg=tile_bg, width=int(34 * s), height=int(34 * s))
        tile.pack_propagate(False)
        tile.grid(row=0, column=0, rowspan=5, padx=(0, 12), sticky="nw", pady=(2, 0))
        ico = tk.Label(tile, bg=tile_bg, bd=0)
        ico.pack(expand=True)
        icon_key = f"{'wifi' if itype == 'wifi' else 'wired'}_{ikey}"
        self._set_img(ico, self._icon(icon_key),
                      fallback="W" if itype == "wifi" else "E",
                      font=("Arial", 13, "bold"), fg=color)

        # -- Name row: alias + description inline --
        nrow = tk.Frame(card, bg=CARD)
        nrow.grid(row=0, column=1, sticky="w")
        tk.Label(nrow, text=alias, font=(FONT, 12, "bold"),
                 fg=(TEXT if active else TEXT2), bg=CARD).pack(side="left")
        sub = name if name and name != alias else \
              ("Wi-Fi" if itype == "wifi" else "Ethernet")
        tk.Label(nrow, text="  " + sub, font=(FONT, 8),
                 fg=MUTED, bg=CARD).pack(side="left", anchor="s", pady=(0, 2))

        # -- Badge row (tinted chips) --
        brow = tk.Frame(card, bg=CARD)
        brow.grid(row=1, column=1, sticky="w", pady=(4, 0))
        chips = []
        if active:
            if itype == "wifi":
                if standard: chips.append((standard, TEXT2, BG3, BORDER))
                if band:     chips.append((band, TEXT2, BG3, BORDER))
            elif link_spd:
                chips.append((link_spd, TEXT2, BG3, BORDER))
            chips.append(("DHCP", BLUE, BLUE_D, BLUE_BD) if dhcp
                         else ("STATIC", WARN, ORANGE_D, ORANGE_BD))
        else:
            st_txt = {"Disconnected": "CABLE UNPLUGGED",
                      "Disabled": "ADAPTER DISABLED",
                      "Up": "NO NETWORK PROFILE"}.get(status, status.upper())
            chips.append((st_txt, MUTED, BG3, BORDER2))
        if apipa:
            chips.append(("169.254 — NO DHCP ANSWER", PUBLIC, RED_D, RED_BD))
        for ctxt, cfg_, cbg, cbd in chips:
            self._chip(brow, ctxt, cfg_, cbg, cbd).pack(side="left", padx=(0, 5))
        if active and gw:
            chip = self._chip(brow, "GW …", MUTED, BG3, BORDER)
            chip.pack(side="left", padx=(0, 5))
            self._gw_chips[alias] = chip

        # -- WiFi signal bar --
        if active and itype == "wifi" and signal >= 0:
            srow = tk.Frame(card, bg=CARD)
            srow.grid(row=2, column=1, sticky="w", pady=(5, 0))
            sig_col = signal_color(signal)
            tk.Label(srow, text=f"Signal {signal}%", font=(FONT, 8),
                     fg=sig_col, bg=CARD).pack(side="left", padx=(0, 8))
            bar_w, bar_h = int(110 * s), int(6 * s)
            bar = tk.Canvas(srow, width=bar_w, height=bar_h,
                            bg=BG4, highlightthickness=0, bd=0)
            bar.pack(side="left")
            fill_w = int(bar_w * signal / 100)
            if fill_w > 0:
                bar.create_rectangle(0, 0, fill_w, bar_h, fill=sig_col, outline="")

        # -- Actions row --
        acts = tk.Frame(card, bg=CARD)
        acts.grid(row=3, column=1, sticky="w", pady=(6, 0))
        self._mini_btn(acts, "IP…",
                       lambda d=p: self._show_ip_dialog(d)).pack(side="left")
        self._mini_btn(acts, "Rename",
                       lambda a=alias: self._rename_adapter(a)).pack(side="left", padx=(4, 0))
        if status == "Disabled":
            self._mini_btn(acts, "Enable",
                           lambda a=alias: self._toggle_adapter(a, True),
                           fg=DOMAIN).pack(side="left", padx=(4, 0))
        else:
            self._mini_btn(acts, "Disable",
                           lambda a=alias: self._toggle_adapter(a, False)).pack(side="left", padx=(4, 0))
        if active and dhcp:
            self._mini_btn(acts, "Renew",
                           lambda a=alias: self._renew_lease(a)).pack(side="left", padx=(4, 0))

        # -- IPs --
        ipf = tk.Frame(card, bg=CARD)
        ipf.grid(row=0, column=2, rowspan=4, padx=(18, 0), sticky="e")
        v4col = PUBLIC if apipa else (DOMAIN if v4 != "N/A" else MUTED)
        self._ip_row(ipf, "IPv4", v4, v4col).pack(anchor="e", pady=1)
        self._ip_row(ipf, "IPv6", v6,
                     PRIVATE if v6 != "N/A" else MUTED).pack(anchor="e", pady=1)
        if gw:
            self._ip_row(ipf, "GW  ", gw, MUTED).pack(anchor="e", pady=1)

        # -- Control column: labeled switch / domain badge / status --
        right = tk.Frame(card, bg=CARD)
        right.grid(row=0, column=3, rowspan=5, padx=(16, 0), sticky="ne")

        if active and cat in ("Private", "Public"):
            is_priv = (cat == "Private")
            row = tk.Frame(right, bg=CARD)
            row.pack(anchor="e", pady=(6, 0))
            tk.Label(row, text="Public", font=(FONT, 8, "bold"),
                     fg=(PUBLIC if not is_priv else MUTED),
                     bg=CARD).pack(side="left", padx=(0, 7))
            sw = PillSwitch(
                row,
                on_click=lambda a=alias, c=cat: self._switch_profile(
                    a, "Public" if c == "Private" else "Private"),
                right_active=is_priv,
                colors_left=(RED_D, RED_BD2, PUBLIC),
                colors_right=(PRIVATE_D, PRIVATE_BD, PRIVATE), bg=CARD)
            sw.pack(side="left")
            tk.Label(row, text="Private", font=(FONT, 8, "bold"),
                     fg=(PRIVATE if is_priv else MUTED),
                     bg=CARD).pack(side="left", padx=(7, 0))
        elif active and cat == "DomainAuthenticated":
            self._chip(right, "DOMAIN", DOMAIN, GREEN_D, GREEN_BD).pack(anchor="e", pady=(4, 0))
            tk.Label(right, text="Managed by IT", font=(FONT, 8),
                     fg=MUTED, bg=CARD).pack(anchor="e", pady=(4, 0))
        else:
            self._chip(right, status.upper() if status else "?",
                       MUTED, BG3, BORDER2).pack(anchor="e", pady=(4, 0))

        card.columnconfigure(2, weight=1)
        return outer

    def _ip_row(self, parent, label, value, col):
        row = tk.Frame(parent, bg=CARD)
        tk.Label(row, text=f"{label} : ",
                 font=(FONT, 8), fg=MUTED, bg=CARD).pack(side="left")
        tk.Label(row, text=value,
                 font=(MONO, 8, "bold"), fg=col, bg=CARD).pack(side="left")
        return row

    # -----------------------------------------------------------------------
    # Profile switching -- immediate, with an Undo toast (config can force
    # the old confirmation dialog back)
    # -----------------------------------------------------------------------
    def _switch_profile(self, alias, target, is_undo=False):
        if not self._require_admin():
            return
        if self.cfg.get("confirm_switch") and not is_undo:
            if not messagebox.askyesno("Confirm",
                    f"Switch '{alias}' to {target} profile?", parent=self):
                return
        prev = None
        for d in self._data:
            if d.get("InterfaceAlias") == alias:
                prev = CAT_BY_INT.get(int(d.get("NetworkCategory", -1)))
        self._set_status("loading")
        def do():
            ok = set_network_profile(alias, target)
            self.after(0, lambda: self._on_switch_done(ok, alias, target, prev, is_undo))
        threading.Thread(target=do, daemon=True).start()

    def _on_switch_done(self, ok, alias, target, prev, is_undo):
        if ok:
            self._load_all()
            if is_undo:
                self.toast(f"{alias} back to {PROFILE_MAP[target]['label']}")
            elif prev in ("Private", "Public"):
                self.toast(f"{alias}  →  {PROFILE_MAP[target]['label']}",
                           action_label="Undo",
                           action_cb=lambda: self._switch_profile(alias, prev, is_undo=True),
                           ms=7000)
            else:
                self.toast(f"{alias}  →  {PROFILE_MAP[target]['label']}")
        else:
            messagebox.showerror("Error",
                f"Could not change profile for '{alias}'.\n\n"
                "Make sure the app is running as administrator.", parent=self)
            self._set_status("error")
            self._refresh_btn.config(state="normal")
            self._loading = False

    # -----------------------------------------------------------------------
    # Adapter actions
    # -----------------------------------------------------------------------
    def _toggle_adapter(self, alias, enable):
        if not self._require_admin():
            return
        if not enable and not messagebox.askyesno(
                "Disable adapter",
                f"Disable network adapter '{alias}'?\n\n"
                "Any connection on it will drop immediately.", parent=self):
            return
        self._set_status("loading")
        def do():
            ok = adapter_set_enabled(alias, enable)
            self.after(0, lambda: (self._load_all(),
                self.toast(f"{alias} {'enabled' if enable else 'disabled'}" if ok
                           else f"Could not change '{alias}'")))
        threading.Thread(target=do, daemon=True).start()

    def _rename_adapter(self, alias):
        if not self._require_admin():
            return
        from tkinter import simpledialog
        new = simpledialog.askstring("Rename adapter",
                                     f"New name for '{alias}':",
                                     initialvalue=alias, parent=self)
        if not new or new.strip() == "" or new == alias:
            return
        new = new.strip()
        self._set_status("loading")
        def do():
            ok = adapter_rename(alias, new)
            self.after(0, lambda: (self._load_all(),
                self.toast(f"Renamed to '{new}'" if ok else "Rename failed")))
        threading.Thread(target=do, daemon=True).start()

    def _renew_lease(self, alias):
        if not self._require_admin():
            return
        self.toast(f"Renewing DHCP lease on {alias}…", ms=6000)
        def do():
            ok = renew_dhcp(alias)
            self.after(0, lambda: (self._load_all(),
                self.toast("Lease renewed" if ok else "Renew failed")))
        threading.Thread(target=do, daemon=True).start()

    def _do_flush_dns(self):
        def do():
            ok = flush_dns()
            self.after(0, lambda: self.toast("DNS cache flushed" if ok
                                             else "Flush failed"))
        threading.Thread(target=do, daemon=True).start()

    # -----------------------------------------------------------------------
    # IP configuration dialog (DHCP / static / presets) with timed rollback
    # -----------------------------------------------------------------------
    def _show_ip_dialog(self, d):
        alias = d.get("InterfaceAlias", "?")
        snap  = capture_ip_config(d)

        dlg = tk.Toplevel(self)
        dlg.title(f"IP configuration — {alias}")
        dlg.configure(bg=CARD)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        pad = {"padx": 16}
        tk.Label(dlg, text=alias, font=(FONT, 12, "bold"),
                 fg=TEXT, bg=CARD).pack(anchor="w", pady=(14, 0), **pad)
        cur = "DHCP" if snap["dhcp"] else \
              f"Static {snap['ip']}/{snap['mask']}" + (f" gw {snap['gw']}" if snap['gw'] else "")
        tk.Label(dlg, text=f"Current: {cur}", font=(FONT, 8),
                 fg=MUTED, bg=CARD).pack(anchor="w", pady=(0, 10), **pad)

        mode = tk.StringVar(value="dhcp" if snap["dhcp"] else "static")
        fields = {}

        def set_state(*_):
            st = "normal" if mode.get() == "static" else "disabled"
            for e in fields.values():
                e.config(state=st)

        rb_style = dict(font=(FONT, 9), fg=TEXT, bg=CARD,
                        activeforeground=TEXT, activebackground=CARD,
                        selectcolor=BG, anchor="w")
        tk.Radiobutton(dlg, text="DHCP (automatic)", variable=mode,
                       value="dhcp", command=set_state, **rb_style).pack(fill="x", **pad)
        tk.Radiobutton(dlg, text="Static", variable=mode,
                       value="static", command=set_state, **rb_style).pack(fill="x", **pad)

        grid = tk.Frame(dlg, bg=CARD)
        grid.pack(fill="x", pady=(6, 4), **pad)
        defaults = {
            "IP address": snap["ip"] if valid_ip(snap["ip"]) else "",
            "Mask":       snap["mask"] or "255.255.255.0",
            "Gateway":    snap["gw"],
            "DNS 1":      snap["dns"][0] if len(snap["dns"]) > 0 else "",
            "DNS 2":      snap["dns"][1] if len(snap["dns"]) > 1 else "",
        }
        for i, (lab, val) in enumerate(defaults.items()):
            tk.Label(grid, text=lab, font=(FONT, 8), fg=MUTED,
                     bg=CARD).grid(row=i, column=0, sticky="w", pady=2)
            e = tk.Entry(grid, font=(MONO, 9), fg=TEXT, bg=BG,
                         insertbackground=TEXT, relief="flat", width=18)
            e.insert(0, val)
            e.grid(row=i, column=1, sticky="w", padx=(10, 0), pady=2, ipady=3)
            fields[lab] = e
        set_state()

        # Presets row
        pr = tk.Frame(dlg, bg=CARD)
        pr.pack(fill="x", pady=(8, 0), **pad)
        tk.Label(pr, text="Presets", font=(FONT, 8, "bold"),
                 fg=MUTED, bg=CARD).pack(anchor="w")
        prow = tk.Frame(dlg, bg=CARD)
        prow.pack(fill="x", pady=(2, 4), **pad)

        def preset_names():
            return [p["name"] for p in self.cfg.get("presets", [])]

        sel = tk.StringVar(value=(preset_names()[0] if preset_names() else ""))
        opt_holder = {"menu": None}

        def rebuild_menu():
            if opt_holder["menu"]:
                opt_holder["menu"].destroy()
            names = preset_names() or ["(none)"]
            om = tk.OptionMenu(prow, sel, *names)
            om.config(font=(FONT, 8), fg=TEXT, bg=HOVER,
                      activeforeground=TEXT, activebackground=BORDER,
                      relief="flat", bd=0, highlightthickness=0)
            om["menu"].config(font=(FONT, 9), fg=TEXT, bg=CARD,
                              activebackground=PRIVATE, activeforeground="white")
            om.pack(side="left")
            opt_holder["menu"] = om

        rebuild_menu()

        def load_preset():
            for p in self.cfg.get("presets", []):
                if p["name"] == sel.get():
                    mode.set(p.get("mode", "static"))
                    set_state()
                    if p.get("mode") == "static":
                        vals = {"IP address": p.get("ip", ""), "Mask": p.get("mask", ""),
                                "Gateway": p.get("gw", ""),
                                "DNS 1": (p.get("dns") or [""])[0],
                                "DNS 2": (p.get("dns") or ["", ""])[1] if len(p.get("dns") or []) > 1 else ""}
                        for k, v in vals.items():
                            fields[k].config(state="normal")
                            fields[k].delete(0, "end")
                            fields[k].insert(0, v)
                        set_state()
                    return

        def save_preset():
            from tkinter import simpledialog
            name = simpledialog.askstring("Save preset", "Preset name:", parent=dlg)
            if not name:
                return
            entry = {"name": name.strip(), "mode": mode.get(),
                     "ip": fields["IP address"].get().strip(),
                     "mask": fields["Mask"].get().strip(),
                     "gw": fields["Gateway"].get().strip(),
                     "dns": [x for x in (fields["DNS 1"].get().strip(),
                                         fields["DNS 2"].get().strip()) if x]}
            presets = [p for p in self.cfg.get("presets", []) if p["name"] != entry["name"]]
            presets.append(entry)
            self.cfg["presets"] = presets
            save_config(self.cfg)
            sel.set(entry["name"])
            rebuild_menu()

        def delete_preset():
            presets = [p for p in self.cfg.get("presets", []) if p["name"] != sel.get()]
            self.cfg["presets"] = presets
            save_config(self.cfg)
            sel.set(preset_names()[0] if preset_names() else "")
            rebuild_menu()

        self._mini_btn(prow, "Load", load_preset, fg=ACCENT).pack(side="left", padx=(8, 0))
        self._mini_btn(prow, "Save as…", save_preset).pack(side="left")
        self._mini_btn(prow, "Delete", delete_preset).pack(side="left")

        # Apply / Cancel
        ar = tk.Frame(dlg, bg=CARD)
        ar.pack(fill="x", pady=(12, 14), **pad)

        def apply_now():
            if not self._require_admin():
                return
            if mode.get() == "static":
                ip   = fields["IP address"].get().strip()
                mask = fields["Mask"].get().strip()
                gw   = fields["Gateway"].get().strip()
                dns  = [x for x in (fields["DNS 1"].get().strip(),
                                    fields["DNS 2"].get().strip()) if x]
                bad = [lab for lab, v in (("IP address", ip), ("Mask", mask)) if not valid_ip(v)]
                bad += [lab for lab, v in (("Gateway", gw),) if v and not valid_ip(v)]
                bad += [f"DNS {i+1}" for i, v in enumerate(dns) if not valid_ip(v)]
                if bad:
                    messagebox.showerror("Invalid value",
                                         "Check: " + ", ".join(bad), parent=dlg)
                    return
            dlg.destroy()
            self._apply_ip(alias, mode.get(),
                           fields["IP address"].get().strip(),
                           fields["Mask"].get().strip(),
                           fields["Gateway"].get().strip(),
                           [x for x in (fields["DNS 1"].get().strip(),
                                        fields["DNS 2"].get().strip()) if x],
                           snap)

        self._flat_btn(ar, "Apply", apply_now).pack(side="right")
        self._flat_btn(ar, "Cancel", dlg.destroy).pack(side="right", padx=(0, 8))

    def _apply_ip(self, alias, mode, ip, mask, gw, dns, snap):
        self._set_status("loading")
        def do():
            if mode == "dhcp":
                ok = apply_dhcp(alias, addr_already_dhcp=snap["dhcp"])
            else:
                ok = apply_static(alias, ip, mask, gw, dns)
            self.after(0, lambda: self._after_ip_apply(ok, alias, snap))
        threading.Thread(target=do, daemon=True).start()

    def _after_ip_apply(self, ok, alias, snap):
        if not ok:
            messagebox.showerror("Error",
                f"Could not apply the IP configuration on '{alias}'.\n"
                "The previous settings are being restored.", parent=self)
            threading.Thread(target=lambda: restore_ip_config(alias, snap),
                             daemon=True).start()
            self._load_all()
            return
        # Applied -- now the safety net: keep or auto-revert in 15 s.
        self._show_keep_dialog(alias, snap)

    def _show_keep_dialog(self, alias, snap, secs=15):
        dlg = tk.Toplevel(self)
        dlg.title("Keep these settings?")
        dlg.configure(bg=CARD)
        dlg.transient(self)
        try: dlg.grab_set()
        except Exception: pass
        dlg.resizable(False, False)
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)   # decide with the buttons

        tk.Label(dlg, text=f"New IP configuration applied on '{alias}'.",
                 font=(FONT, 10, "bold"), fg=TEXT, bg=CARD)\
            .pack(padx=20, pady=(16, 4))
        cd = tk.Label(dlg, text="", font=(FONT, 9), fg=WARN, bg=CARD)
        cd.pack(padx=20)

        state = {"left": secs, "done": False}

        def finish(revert):
            if state["done"]:
                return
            state["done"] = True
            dlg.destroy()
            if revert:
                self._set_status("loading")
                def do():
                    restore_ip_config(alias, snap)
                    self.after(0, lambda: (self._load_all(),
                                           self.toast("Previous settings restored")))
                threading.Thread(target=do, daemon=True).start()
                log_event("ipconfig", f"{alias} : reverted (not confirmed)")
            else:
                log_event("ipconfig", f"{alias} : confirmed by user")
                self._load_all()
                self.toast("Settings kept")

        def tick():
            if state["done"]:
                return
            if state["left"] <= 0:
                finish(revert=True)
                return
            cd.config(text=f"Reverting automatically in {state['left']} s "
                           "unless you confirm.")
            state["left"] -= 1
            dlg.after(1000, tick)

        br = tk.Frame(dlg, bg=CARD)
        br.pack(pady=(12, 16))
        self._flat_btn(br, "Keep settings", lambda: finish(False), fg=DOMAIN)\
            .pack(side="left", padx=(0, 8))
        self._flat_btn(br, "Revert now", lambda: finish(True)).pack(side="left")
        tick()

    # -----------------------------------------------------------------------
    # Firewall -- per active profile, with timed auto-rearm
    # -----------------------------------------------------------------------
    def _active_fw_profiles(self):
        cats = set()
        for d in self._data:
            if d.get("HasProfile") and d.get("Status") == "Up":
                c = CAT_BY_INT.get(int(d.get("NetworkCategory", -1)))
                if c == "DomainAuthenticated": cats.add("Domain")
                elif c:                        cats.add(c)
        return sorted(cats)

    def _update_fw_ui(self, on, total):
        if on is None:
            self._fw_sub.config(text="Status unknown", fg=MUTED)
            self._set_chip(self._fw_badge, "?", MUTED, BG3, BORDER)
            self._fw_enabled = None
            self._fw_tile.config(bg=BG3)
            self._fw_icon_lbl.config(bg=BG3)
            self._set_img(self._fw_icon_lbl, self._icon("fw_off"),
                          "?", (FONT, 14), PUBLIC)
            self._fw_switch.set_state(False)
            return

        self._fw_enabled = (on > 0)

        if on == total and total > 0:
            color, tint, bd = DOMAIN, GREEN_D, GREEN_BD
            sub, lbl = f"Active  -  {total} profile{'s' if total > 1 else ''} protected", "ON"
        elif on == 0:
            color, tint, bd = PUBLIC, RED_D, RED_BD
            sub, lbl = "Disabled  -  Your system is not protected", "OFF"
        else:
            off_names = ", ".join(n for n, v in self._fw_profiles.items() if not v)
            color, tint, bd = WARN, ORANGE_D, ORANGE_BD
            sub, lbl = f"Partially active ({on}/{total})  -  off: {off_names}", f"{on}/{total}"

        if self._fw_deadline is not None:
            left = int(self._fw_deadline - time.time())
            if left > 0:
                sub += f"  -  auto re-enable in {left // 60}:{left % 60:02d}"
            self.after(1000, self._fw_countdown_tick)

        self._fw_sub.config(text=sub, fg=color)
        self._set_chip(self._fw_badge, lbl, color, tint, bd)
        self._fw_tile.config(bg=tint)
        self._fw_icon_lbl.config(bg=tint)
        fw_key = "fw_on" if on > 0 else "fw_off"
        self._set_img(self._fw_icon_lbl, self._icon(fw_key),
                      "O" if on > 0 else "X", (FONT, 14), color)
        self._fw_switch.set_state(on > 0, animate=True)

    def _fw_countdown_tick(self):
        if self._fw_deadline is None:
            return
        left = int(self._fw_deadline - time.time())
        if left <= 0:
            self._fw_deadline = None
            self._set_status("loading")
            def do():
                set_firewall_state(True)
                self.after(0, lambda: (self._refresh_fw(),
                                       self.toast("Firewall re-enabled automatically")))
            threading.Thread(target=do, daemon=True).start()
        else:
            base = self._fw_sub.cget("text").split("  -  auto")[0]
            self._fw_sub.config(text=base + f"  -  auto re-enable in {left // 60}:{left % 60:02d}")
            self.after(1000, self._fw_countdown_tick)

    def _on_fw_click(self, _=None):
        if self._fw_animating:
            return
        if not self._require_admin():
            return
        if self._fw_enabled is False or self._fw_enabled is None:
            # everything off -> turn all back on, cancel any timer
            self._fw_deadline = None
            self._animate_then(True, lambda: self._fw_apply(enable=True,
                                                            profiles=None, secs=None))
        else:
            self._show_fw_dialog()

    def _show_fw_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Disable firewall")
        dlg.configure(bg=CARD)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        tk.Label(dlg, text="Disable Windows Firewall",
                 font=(FONT, 11, "bold"), fg=TEXT, bg=CARD)\
            .pack(anchor="w", padx=18, pady=(14, 2))

        active = self._active_fw_profiles()
        scope = tk.StringVar(value="active" if active else "all")
        dur   = tk.StringVar(value="600")

        rb = dict(font=(FONT, 9), fg=TEXT, bg=CARD,
                  activeforeground=TEXT, activebackground=CARD,
                  selectcolor=BG, anchor="w")
        if active:
            tk.Radiobutton(dlg, text=f"Only the active profile{'s' if len(active) > 1 else ''} "
                                     f"({', '.join(active)})",
                           variable=scope, value="active", **rb).pack(fill="x", padx=18)
        tk.Radiobutton(dlg, text="All profiles",
                       variable=scope, value="all", **rb).pack(fill="x", padx=18)

        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x", padx=18, pady=8)

        for txt, val in (("For 10 minutes, then re-enable automatically", "600"),
                         ("For 1 hour, then re-enable automatically", "3600"),
                         ("Until I turn it back on  (not recommended)", "0")):
            tk.Radiobutton(dlg, text=txt, variable=dur, value=val, **rb)\
                .pack(fill="x", padx=18)

        br = tk.Frame(dlg, bg=CARD)
        br.pack(pady=(12, 16), padx=18, anchor="e")

        def go():
            profiles = active if scope.get() == "active" and active else None
            secs = int(dur.get()) or None
            dlg.destroy()
            self._animate_then(False, lambda: self._fw_apply(enable=False,
                                                             profiles=profiles,
                                                             secs=secs))
        self._flat_btn(br, "Disable", go, fg=PUBLIC).pack(side="right")
        self._flat_btn(br, "Cancel", dlg.destroy).pack(side="right", padx=(0, 8))

    def _animate_then(self, target, cb):
        self._fw_animating = True
        self._fw_switch.set_state(target, animate=True)
        self._set_chip(self._fw_badge, "...", MUTED, BG3, BORDER)
        def go():
            self._fw_animating = False
            cb()
        self.after(160, go)

    def _fw_apply(self, enable, profiles, secs):
        def do():
            if profiles:
                ok = set_firewall_profiles(profiles, enable)
            else:
                ok = set_firewall_state(enable)
            def done():
                if not ok:
                    messagebox.showerror("Error",
                        "Could not change firewall state.\n\n"
                        "Make sure the app is running as administrator.", parent=self)
                    self._fw_deadline = None
                else:
                    if not enable and secs:
                        self._fw_deadline = time.time() + secs
                        self.after(1000, self._fw_countdown_tick)
                    elif enable:
                        self._fw_deadline = None
                self._refresh_fw()
            self.after(0, done)
        threading.Thread(target=do, daemon=True).start()

    def _refresh_fw(self):
        def fetch():
            on, total, fwp = get_firewall_state()
            def upd():
                self._fw_profiles = fwp
                self._update_fw_ui(on, total)
            self.after(0, upd)
        threading.Thread(target=fetch, daemon=True).start()

    # -----------------------------------------------------------------------
    # Update check (silent on any failure)
    # -----------------------------------------------------------------------
    def _check_update_async(self):
        def work():
            try:
                with urllib.request.urlopen(UPDATE_URL, timeout=4) as r:
                    data = json.loads(r.read().decode("utf-8", "replace"))
                ver = str(data.get("version", ""))
                url = str(data.get("url", GITHUB_URL + "/releases/latest"))
                # A remote version.json is untrusted input: only ever open
                # http(s) links, never file:// or anything else (same guard
                # as ingesto).
                if not url.lower().startswith(("http://", "https://")):
                    url = GITHUB_URL + "/releases/latest"
                if ver and semver_gt(ver, APP_VERSION) \
                        and self.cfg.get("update_dismissed") != ver:
                    self.after(0, lambda: self._show_update_dialog(ver, url))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _show_update_dialog(self, ver, url):
        """ingesto-style update notice: small modal, Later / Get it,
        never shown twice for the same version."""
        dlg = tk.Toplevel(self)
        dlg.title("Update")
        dlg.configure(bg=CARD)
        dlg.transient(self)
        try: dlg.grab_set()
        except Exception: pass
        dlg.resizable(False, False)

        tk.Label(dlg, text="New version available",
                 font=(DISPLAY_FAMILY, 11, "bold"), fg=TEXT, bg=CARD)\
            .pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(dlg, text=f"NetCatChanger v{ver} is available. "
                           f"You're on v{APP_VERSION}.",
                 font=(FONT, 9), fg=TEXT2, bg=CARD)\
            .pack(anchor="w", padx=20)

        def dismiss():
            self.cfg["update_dismissed"] = ver
            save_config(self.cfg)
            dlg.destroy()

        def get_it():
            try: webbrowser.open(url)
            except Exception: pass
            dismiss()

        br = tk.Frame(dlg, bg=CARD)
        br.pack(pady=(16, 16), padx=20, anchor="e")
        go = tk.Button(br, text="Get it", font=(FONT, 9, "bold"),
                       fg="white", bg=PRIVATE,
                       activeforeground="white", activebackground=ACCENT,
                       relief="flat", bd=0, cursor="hand2", padx=16, pady=5,
                       command=get_it)
        go.pack(side="right")
        self._flat_btn(br, "Later", dismiss).pack(side="right", padx=(0, 8))
        dlg.protocol("WM_DELETE_WINDOW", dismiss)

    # -----------------------------------------------------------------------
    # Settings
    # -----------------------------------------------------------------------
    def _show_settings(self):
        dlg = tk.Toplevel(self)
        dlg.title("Settings")
        dlg.configure(bg=CARD)
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        tk.Label(dlg, text="Settings", font=(FONT, 12, "bold"),
                 fg=TEXT, bg=CARD).pack(anchor="w", padx=18, pady=(14, 8))

        cb_style = dict(font=(FONT, 9), fg=TEXT, bg=CARD,
                        activeforeground=TEXT, activebackground=CARD,
                        selectcolor=BG, anchor="w")

        vars_ = {}

        def add_check(key, label, extra_cb=None, initial=None):
            v = tk.BooleanVar(value=bool(self.cfg.get(key)) if initial is None
                              else initial)
            def changed():
                self.cfg[key] = bool(v.get())
                save_config(self.cfg)
                if extra_cb:
                    extra_cb(bool(v.get()))
                    # the handler may have refused the change (no rights,
                    # Windows said no) — show what is actually true now
                    v.set(bool(self.cfg.get(key)))
            tk.Checkbutton(dlg, text=label, variable=v, command=changed,
                           **cb_style).pack(fill="x", padx=18, pady=1)
            vars_[key] = v

        tray_ok = self._tray is not None
        add_check("close_to_tray",
                  "Close button minimizes to the tray" +
                  ("" if tray_ok else "  (tray unavailable)"))
        add_check("start_minimized", "Start minimized in the tray")
        # read the real state: the scheduled task is the source of truth
        real_autostart = autostart_enabled() if sys.platform == "win32" \
                         else bool(self.cfg.get("autostart"))
        self.cfg["autostart"] = real_autostart
        add_check("autostart", "Launch NetCatChanger with Windows (elevated)",
                  extra_cb=self._set_autostart, initial=real_autostart)
        def log_changed(on):
            global LOG_ENABLED
            LOG_ENABLED = on
        add_check("log_enabled", "Keep a session log of every change",
                  extra_cb=log_changed)
        add_check("confirm_switch",
                  "Ask for confirmation before switching a profile")

        br = tk.Frame(dlg, bg=CARD)
        br.pack(pady=(12, 16), padx=18, anchor="e")
        self._flat_btn(br, "Close", dlg.destroy).pack(side="right")

    def _set_autostart(self, on):
        # Creating the scheduled task needs the rights we may not have.
        if on and self.read_only:
            self.cfg["autostart"] = False
            save_config(self.cfg)
            messagebox.showwarning(
                "Administrator rights required",
                "Launching NetCatChanger with Windows needs administrator "
                "rights to set up.\n\nRestart as administrator and try again.",
                parent=self)
            return
        if not autostart_set(on):
            self.cfg["autostart"] = not on
            save_config(self.cfg)
            messagebox.showerror(
                "Could not change the setting",
                "Windows refused to " + ("create" if on else "remove") +
                " the startup task.\nSee the log for details.", parent=self)

    # -----------------------------------------------------------------------
    # About / log
    # -----------------------------------------------------------------------
    def _open_log(self):
        try:
            if sys.platform == "win32":
                os.startfile(LOG_PATH)          # noqa
            else:
                webbrowser.open("file://" + LOG_PATH)
        except Exception:
            self.toast("No log file yet")

    def _show_about(self):
        messagebox.showinfo(
            "About NetCatChanger",
            f"NetCatChanger {APP_VERSION}\n"
            "Windows Network Profile Manager + Firewall Control\n\n"
            f"{GITHUB_URL}\n\n"
            "Licensed under the GNU General Public License v3.0.\n"
            "This program comes with ABSOLUTELY NO WARRANTY.\n"
            "This is free software, and you are welcome to redistribute it\n"
            "under certain conditions. See the LICENSE file for details.\n\n"
            "Third-party components:\n"
            "   Icons by Lucide (lucide.dev) — ISC License\n"
            "   Poppins typeface — SIL Open Font License 1.1",
            parent=self)

    # -----------------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------------
    def _set_status(self, state):
        d = {"ok":      (DOMAIN, "  ·  Ready"),
             "loading": (ACCENT, "  ·  Loading..."),
             "error":   (PUBLIC, "  ·  Error")}
        col, txt = d.get(state, d["error"])
        if self.read_only and state == "ok":
            txt = "  ·  Ready (read-only)"
        self._status_lbl.config(fg=col, text=txt)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # NetCatChanger cannot do its job without administrator rights, so it asks
    # for them itself instead of relying only on the exe's requireAdministrator
    # manifest: the manifest is lost when running from source, and can be
    # stripped by repackaging. Belt and braces — a normal launch shows exactly
    # one UAC prompt either way (already elevated -> is_admin() is true here).
    if should_elevate(sys.argv, sys.platform, is_admin()):
        if run_as_admin():
            sys.exit(0)          # the elevated copy takes over
        # UAC refused: fall through and start read-only rather than vanish

    enable_hidpi()
    load_display_font()
    App().mainloop()
