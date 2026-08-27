"""
Offline checks for the pure parsing helpers of NetCatChanger.

Nothing here touches Windows, PowerShell or Tk: tkinter is stubbed out so the
module can be imported on any machine. Run with:  python tests/test_parsing.py
"""
import os
import re
import sys
import types

# --- stub tkinter so network_switcher imports anywhere -----------------------
for name in ("tkinter", "tkinter.messagebox"):
    mod = types.ModuleType(name)
    sys.modules.setdefault(name, mod)
sys.modules["tkinter"].Tk = type("Tk", (), {})
sys.modules["tkinter"].Canvas = type("Canvas", (), {})
sys.modules["tkinter"].messagebox = sys.modules["tkinter.messagebox"]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import network_switcher as ns  # noqa: E402

fails = []

def check(label, got, want):
    if got != want:
        fails.append(f"{label}: got {got!r}, expected {want!r}")

# --- netsh output samples ---------------------------------------------------
NETSH_EN = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz
    GUID                   : 8f2c1a44-1c0e-4a1b-9e3e-2f0b6d5a7c11
    Physical address       : 3c:58:c2:11:22:33
    State                  : connected
    SSID                   : HomeNet
    BSSID                  : a4:2b:b0:44:55:66
    Network type           : Infrastructure
    Radio type             : 802.11ax
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Profile
    Band                   : 5 GHz
    Channel                : 44
    Receive rate (Mbps)    : 1201
    Transmit rate (Mbps)   : 1201
    Signal                 : 92%
    Profile                : HomeNet
"""

NETSH_FR = """
Il y a 1 interface sur le systeme :

    Nom                            : Wi-Fi
    Description                    : Intel(R) Wi-Fi 6 AX201 160MHz
    GUID                           : 8f2c1a44-1c0e-4a1b-9e3e-2f0b6d5a7c11
    Adresse physique               : 3c:58:c2:11:22:33
    Etat                           : connecte
    SSID                           : HomeNet
    BSSID                          : a4:2b:b0:44:55:66
    Type de reseau                 : Infrastructure
    Type de radio                  : 802.11ax
    Authentification               : WPA2-Personal
    Chiffrement                    : CCMP
    Mode de connexion              : Profil
    Bande                          : 2,4 GHz
    Canal                          : 6
    Taux de reception (Mbits/s)    : 144
    Taux de transmission (Mbits/s) : 144
    Signal                         : 78%
    Profil                         : HomeNet
"""

NETSH_DE_NO_BAND = """
Es ist 1 Schnittstelle auf dem System vorhanden:

    Name                   : WLAN
    Beschreibung           : Realtek 8822CE Wireless LAN
    Physische Adresse      : 3c:58:c2:11:22:33
    Status                 : Verbunden
    SSID                   : HomeNet
    Netzwerktyp            : Infrastruktur
    Funktyp                : 802.11ac
    Authentifizierung      : WPA2-Personal
    Kanal                  : 36
    Empfangsrate (MBit/s)  : 866
    Sendrate (MBit/s)      : 866
    Signal                 : 55%
"""

def parse_netsh(text, aliases):
    """Python port of the PowerShell block in _BATCH_SCRIPT.

    Kept byte-for-byte equivalent in logic so this test actually exercises the
    algorithm shipped in the app (the PowerShell itself can only run on Windows).
    """
    blocks, cur = {}, None
    for line in text.splitlines():
        i = line.find(":")
        if i < 1:
            continue
        label, value = line[:i].strip(), line[i + 1:].strip()
        if not value:
            continue
        if value in aliases and value not in blocks:
            cur = value
            blocks[cur] = {"Signal": -1, "RadioType": "", "Band": "", "Channel": -1}
            continue
        if not cur:
            continue
        m = re.match(r"^(\d{1,3})\s*%$", value)
        if m:
            blocks[cur]["Signal"] = int(m.group(1)); continue
        if "802.11" in value:
            blocks[cur]["RadioType"] = value; continue
        if re.search(r"\d+([.,]\d+)?\s*GHz", value):
            blocks[cur]["Band"] = value; continue
        if (not re.search(r"b(it|ps)", label, re.I)
                and re.match(r"^\d{1,3}$", value) and int(value) <= 233):
            if blocks[cur]["Channel"] < 0:
                blocks[cur]["Channel"] = int(value)
            continue
    return blocks

# --- netsh block parsing ----------------------------------------------------
en = parse_netsh(NETSH_EN, {"Wi-Fi"})["Wi-Fi"]
check("EN signal",  en["Signal"], 92)
check("EN radio",   en["RadioType"], "802.11ax")
check("EN band",    en["Band"], "5 GHz")
check("EN channel", en["Channel"], 44)

fr = parse_netsh(NETSH_FR, {"Wi-Fi"})["Wi-Fi"]
check("FR signal",  fr["Signal"], 78)
check("FR radio",   fr["RadioType"], "802.11ax")
check("FR band",    fr["Band"], "2,4 GHz")
check("FR channel", fr["Channel"], 6)

de = parse_netsh(NETSH_DE_NO_BAND, {"WLAN"})["WLAN"]
check("DE signal",  de["Signal"], 55)
check("DE radio",   de["RadioType"], "802.11ac")
check("DE band",    de["Band"], "")      # not reported by this Windows build
check("DE channel", de["Channel"], 36)   # rate lines must not win

# --- band normalisation -----------------------------------------------------
check("band 5",        ns.parse_wifi_band("5 GHz", -1), "5 GHz")
check("band 2,4 FR",   ns.parse_wifi_band("2,4 GHz", -1), "2.4 GHz")
check("band 2.4 EN",   ns.parse_wifi_band("2.4 GHz", -1), "2.4 GHz")
check("band 6",        ns.parse_wifi_band("6 GHz", -1), "6 GHz")
check("band via ch36", ns.parse_wifi_band("", 36), "5 GHz")
check("band via ch6",  ns.parse_wifi_band("", 6), "2.4 GHz")
check("band unknown",  ns.parse_wifi_band("", -1), "")

# --- standards --------------------------------------------------------------
check("std ax", ns.parse_wifi_standard("802.11ax"), "Wi-Fi 6  802.11ax")
check("std ac", ns.parse_wifi_standard("802.11ac"), "Wi-Fi 5  802.11ac")
check("std be", ns.parse_wifi_standard("802.11be"), "Wi-Fi 7  802.11be")
check("std ??", ns.parse_wifi_standard("weird"), "weird")

# --- link speed -------------------------------------------------------------
check("speed 1g",  ns.parse_link_speed("1000000000"), "1 Gbps")
check("speed 2.5", ns.parse_link_speed("2500000000"), "2.5 Gbps")
check("speed str", ns.parse_link_speed("1 Gbps"), "1 Gbps")
check("speed nil", ns.parse_link_speed(""), "")

# --- interface type ---------------------------------------------------------
check("type wifi seen", ns.detect_iface_type("Connexion 2", "", wifi_seen=True), "wifi")
check("type wifi name", ns.detect_iface_type("Wi-Fi"), "wifi")
check("type wlan de",   ns.detect_iface_type("WLAN"), "wifi")
check("type eth",       ns.detect_iface_type("Ethernet"), "ethernet")

# --- PowerShell quoting -----------------------------------------------------
check("quote plain",  ns.ps_quote("Wi-Fi"), "'Wi-Fi'")
check("quote apos",   ns.ps_quote("Bob's Wi-Fi"), "'Bob''s Wi-Fi'")
check("quote inject", ns.ps_quote('"; Remove-Item C:\\ #'), "'\"; Remove-Item C:\\ #'")

# --- guard rails ------------------------------------------------------------
check("bad category rejected", ns.set_network_profile("Wi-Fi", "Nonsense; rm -rf"), False)

# --- 2.1.0 helpers ----------------------------------------------------------
check("semver gt",        ns.semver_gt("2.1.0", "2.0.2"), True)
check("semver lt",        ns.semver_gt("2.0.2", "2.1.0"), False)
check("semver eq",        ns.semver_gt("2.1.0", "2.1.0"), False)
check("semver 10",        ns.semver_gt("2.10.0", "2.9.9"), True)

check("mask /24",  ns.prefix_to_mask(24), "255.255.255.0")
check("mask /16",  ns.prefix_to_mask(16), "255.255.0.0")
check("mask /25",  ns.prefix_to_mask(25), "255.255.255.128")
check("mask /8",   ns.prefix_to_mask(8),  "255.0.0.0")
check("mask /32",  ns.prefix_to_mask(32), "255.255.255.255")
check("mask /0",   ns.prefix_to_mask(0),  "0.0.0.0")
check("mask bad",  ns.prefix_to_mask(-1), "")
check("mask junk", ns.prefix_to_mask("x"), "")

check("ip ok",       ns.valid_ip("192.168.10.5"), True)
check("ip bad oct",  ns.valid_ip("192.168.10.256"), False)
check("ip short",    ns.valid_ip("192.168.10"), False)
check("ip leading0", ns.valid_ip("192.168.010.5"), False)
check("ip empty",    ns.valid_ip(""), False)
check("ip text",     ns.valid_ip("abc.def.ghi.jkl"), False)

check("apipa yes", ns.is_apipa("169.254.12.7"), True)
check("apipa no",  ns.is_apipa("192.168.1.10"), False)
check("apipa nil", ns.is_apipa(""), False)

# capture_ip_config builds a coherent rollback snapshot
snap = ns.capture_ip_config({
    "DhcpEnabled": False, "IPv4Address": "192.168.10.5", "PrefixLength": 24,
    "Gateway": "192.168.10.1", "Dns": "1.1.1.1,8.8.8.8"})
check("snap dhcp", snap["dhcp"], False)
check("snap ip",   snap["ip"], "192.168.10.5")
check("snap mask", snap["mask"], "255.255.255.0")
check("snap gw",   snap["gw"], "192.168.10.1")
check("snap dns",  snap["dns"], ["1.1.1.1", "8.8.8.8"])

snap2 = ns.capture_ip_config({"DhcpEnabled": True, "IPv4Address": "N/A",
                              "PrefixLength": -1, "Gateway": "", "Dns": ""})
check("snap2 dhcp", snap2["dhcp"], True)
check("snap2 dns",  snap2["dns"], [])

# --- elevation (run_as_admin) -----------------------------------------------
# ShellExecuteW returns > 32 on success; 5 (SE_ERR_ACCESSDENIED) is what a
# refused UAC prompt gives back. Anything <= 32 must keep us in read-only.
class _FakeShell:
    def __init__(self, rc): self.rc, self.calls = rc, []
    def ShellExecuteW(self, hwnd, verb, exe, params, cwd, show):
        self.calls.append((verb, exe, params))
        return self.rc

class _FakeCtypes:
    def __init__(self, rc): self.windll = type("W", (), {"shell32": _FakeShell(rc)})()

def _elevate_with(rc, argv, frozen=False):
    real_ctypes, real_argv, real_frozen = ns.ctypes, sys.argv, getattr(sys, "frozen", None)
    ns.ctypes = _FakeCtypes(rc)
    sys.argv = argv
    if frozen: sys.frozen = True
    try:
        ok = ns.run_as_admin()
        return ok, ns.ctypes.windll.shell32.calls
    finally:
        ns.ctypes, sys.argv = real_ctypes, real_argv
        if frozen and real_frozen is None: del sys.frozen

ok, calls = _elevate_with(42, ["ncc.py"])
check("elevate accepted", ok, True)
check("elevate uses runas", calls[0][0], "runas")
check("elevate adds guard flag", ns.NO_ELEVATE_FLAG in calls[0][2], True)
check("elevate passes script", "ncc.py" in calls[0][2], True)

ok, _ = _elevate_with(5, ["ncc.py"])          # user clicked "No"
check("elevate refused -> False", ok, False)
ok, _ = _elevate_with(32, ["ncc.py"])         # boundary
check("elevate rc=32 -> False", ok, False)
ok, _ = _elevate_with(33, ["ncc.py"])
check("elevate rc=33 -> True", ok, True)

ok, calls = _elevate_with(42, ["ncc.py", ns.NO_ELEVATE_FLAG, "--minimized"])
check("guard flag not duplicated", calls[0][2].count(ns.NO_ELEVATE_FLAG), 1)
check("other args kept", "--minimized" in calls[0][2], True)

ok, calls = _elevate_with(42, ["NetCatChanger.exe", "--minimized"], frozen=True)
check("frozen keeps args", "--minimized" in calls[0][2], True)
check("frozen guards too", ns.NO_ELEVATE_FLAG in calls[0][2], True)

# a broken ctypes must never crash the launch
real = ns.ctypes
ns.ctypes = None
try:
    check("elevate on error -> False", ns.run_as_admin(), False)
finally:
    ns.ctypes = real

# --- should_elevate: the anti-loop guard ------------------------------------
check("elevate: plain windows launch",
      ns.should_elevate(["ncc.exe"], "win32", False), True)
check("elevate: already admin",
      ns.should_elevate(["ncc.exe"], "win32", True), False)
check("elevate: relaunched copy never re-asks",
      ns.should_elevate(["ncc.exe", ns.NO_ELEVATE_FLAG], "win32", False), False)
check("elevate: not on linux",
      ns.should_elevate(["ncc.py"], "linux", False), False)
check("elevate: autostart launch still elevates",
      ns.should_elevate(["ncc.exe", "--minimized"], "win32", False), True)

# --- autostart uses a scheduled task, not HKCU\Run --------------------------
_cmds = []
_real_run_cmd = ns.run_cmd
ns.LOG_ENABLED = False        # keep the test from writing a real session log
ns.run_cmd = lambda args: (_cmds.append(args) or (True, ""))
try:
    ns.autostart_set(True)
    create = _cmds[-1]
    check("autostart uses schtasks", create[0], "schtasks")
    check("autostart creates", create[1], "/Create")
    check("autostart highest privileges", "HIGHEST" in create, True)
    check("autostart at logon", "ONLOGON" in create, True)
    check("autostart starts minimized", "--minimized" in create[create.index("/TR") + 1], True)
    _cmds.clear()
    ns.autostart_set(False)
    check("autostart delete", _cmds[-1][1], "/Delete")
finally:
    ns.run_cmd = _real_run_cmd

# removing an absent task is a success, not a failure
ns.run_cmd = lambda args: (False, "ERROR: The system cannot find the file specified.")
try:
    check("autostart remove-absent is ok", ns.autostart_set(False), True)
finally:
    ns.run_cmd = _real_run_cmd

# --- report -----------------------------------------------------------------
if fails:
    print("FAILED:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("all parsing checks passed")
