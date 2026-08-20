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

# --- report -----------------------------------------------------------------
if fails:
    print("FAILED:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("all parsing checks passed")
