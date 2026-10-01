"""
Harnais d'interface — lance la vraie fenêtre NetCatChanger avec des données
réseau simulées, sur n'importe quel système (macOS, Linux), sans Windows.

Principe : l'application ne parle à Windows qu'à travers quelques fonctions
(run_ps, run_cmd, ping_ok, dns_ok). On les remplace par des fonctions qui
renvoient des données inventées, et tout le reste de l'app — la mise en page,
les couleurs, les cartes, les dialogues — s'exécute normalement.

Usage :
    python3 tests/ui_harness.py                # fenêtre principale
    python3 tests/ui_harness.py --readonly     # état « UAC refusé »
    python3 tests/ui_harness.py --dialog ip    # ouvre le dialogue IP
    python3 tests/ui_harness.py --dialog fw    # dialogue pare-feu
    python3 tests/ui_harness.py --dialog settings
    python3 tests/ui_harness.py --dialog update
    python3 tests/ui_harness.py --shot out.png # capture puis quitte
    python3 tests/ui_harness.py --seconds 30   # garde la fenêtre 30 s

Sans --shot, la fenêtre reste ouverte : on la referme à la main.

ATTENTION : ce que ce harnais NE teste PAS — l'élévation UAC, la tâche
planifiée, le systray Windows, le chargement de la police via GDI, et tout
échange réel avec le réseau. Le rendu des polices diffère aussi de Windows.
C'est un contrôle de mise en page et de logique d'affichage, pas une recette.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import network_switcher as ns  # noqa: E402


# --- données réseau simulées -------------------------------------------------
# Quatre cas volontairement différents : Wi-Fi nominal, Ethernet en IP fixe,
# carte en APIPA (panne DHCP), carte désactivée.
MOCK_IFACES = [
    {"InterfaceAlias": "Wi-Fi", "Description": "Intel(R) Wi-Fi 6 AX201",
     "Status": "Up", "MacAddress": "AA-BB-CC", "LinkSpeed": "866.7 Mbps",
     "MediaType": "Native 802.11", "HasProfile": True, "ProfileName": "HomeNet",
     "NetworkCategory": 1, "IPv4Address": "192.168.1.20", "PrefixLength": 24,
     "IPv6Address": "fe80::1c2a:9f04", "Gateway": "192.168.1.1",
     "Dns": "1.1.1.1,8.8.8.8", "DhcpEnabled": True,
     "WifiSignal": 81, "WifiStandard": "802.11ax", "WifiBand": "5 GHz",
     "WifiChannel": 44},
    {"InterfaceAlias": "Ethernet", "Description": "Intel I225-V",
     "Status": "Up", "MacAddress": "DD-EE-FF", "LinkSpeed": "2500000000",
     "MediaType": "802.3", "HasProfile": True, "ProfileName": "Réseau 2",
     "NetworkCategory": 0, "IPv4Address": "10.0.0.5", "PrefixLength": 8,
     "IPv6Address": "N/A", "Gateway": "10.0.0.1", "Dns": "10.0.0.1",
     "DhcpEnabled": False, "WifiSignal": -1, "WifiStandard": "",
     "WifiBand": "", "WifiChannel": -1},
    {"InterfaceAlias": "Ethernet 2", "Description": "USB GbE",
     "Status": "Up", "MacAddress": "11-22-33", "LinkSpeed": "100000000",
     "MediaType": "802.3", "HasProfile": True, "ProfileName": "Réseau",
     "NetworkCategory": 0, "IPv4Address": "169.254.33.7", "PrefixLength": 16,
     "IPv6Address": "N/A", "Gateway": "", "Dns": "", "DhcpEnabled": True,
     "WifiSignal": -1, "WifiStandard": "", "WifiBand": "", "WifiChannel": -1},
    {"InterfaceAlias": "Ethernet 3", "Description": "Old NIC",
     "Status": "Disabled", "MacAddress": "44-55-66", "LinkSpeed": "",
     "MediaType": "802.3", "HasProfile": False, "ProfileName": "",
     "NetworkCategory": -1, "IPv4Address": "N/A", "PrefixLength": -1,
     "IPv6Address": "N/A", "Gateway": "", "Dns": "", "DhcpEnabled": True,
     "WifiSignal": -1, "WifiStandard": "", "WifiBand": "", "WifiChannel": -1},
]

FIREWALL_STATE = "Domain=True\nPrivate=True\nPublic=True"


def install_mocks(readonly=False):
    """Remplace tout ce qui parle à Windows."""

    def fake_run_ps(cmd):
        if "Get-NetFirewallProfile" in cmd and "ForEach-Object" in cmd:
            return FIREWALL_STATE, ""
        if "Get-NetAdapter" in cmd or "$wifiBlocks" in cmd:
            return json.dumps(MOCK_IFACES), ""
        return "", ""

    ns.run_ps = fake_run_ps
    ns.run_ps_action = lambda cmd: (True, "")
    ns.run_cmd = lambda args: (True, "")
    ns.ping_ok = lambda host: True
    ns.dns_ok = lambda: True
    ns.log_event = lambda kind, msg: None      # pas de journal pendant un test

    class FakeWatcher:                          # pas de PowerShell qui tourne
        def __init__(self, cb): pass
        def start(self): pass
        def stop(self): pass
    ns.NetworkWatcher = FakeWatcher

    if readonly:
        # simule « l'utilisateur a refusé l'UAC »
        ns.sys.platform = "win32"
        ns.is_admin = lambda: False


def screenshot(path):
    """Capture l'écran. macOS : screencapture. Linux : ImageMagick import."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["screencapture", "-x", path], check=True)
        else:
            subprocess.run(["import", "-window", "root", path], check=True)
        print(f"capture : {path}")
    except Exception as e:
        print(f"capture impossible ({e}) — regarde la fenêtre directement")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readonly", action="store_true",
                    help="état « droits administrateur refusés »")
    ap.add_argument("--dialog", choices=["ip", "fw", "settings", "update"],
                    help="ouvre un dialogue après l'ouverture de la fenêtre")
    ap.add_argument("--shot", metavar="FICHIER.png",
                    help="capture puis quitte")
    ap.add_argument("--seconds", type=int, default=0,
                    help="ferme automatiquement après N secondes")
    args = ap.parse_args()

    install_mocks(readonly=args.readonly)

    app = ns.App()
    app.title("NetCatChanger — HARNAIS DE TEST (données simulées)")

    def open_dialog():
        if args.dialog == "ip":
            app._show_ip_dialog(MOCK_IFACES[0])
        elif args.dialog == "fw":
            app._show_fw_dialog()
        elif args.dialog == "settings":
            app._show_settings()
        elif args.dialog == "update":
            app._show_update_dialog("9.9.9", "https://example.com")

    if args.dialog:
        app.after(1500, open_dialog)

    if args.shot:
        delay = 2500 if not args.dialog else 3000
        def shoot():
            app.update_idletasks()
            screenshot(args.shot)
            app.after(300, lambda: os._exit(0))
        app.after(delay, shoot)
    elif args.seconds:
        app.after(args.seconds * 1000, lambda: os._exit(0))

    app.mainloop()


if __name__ == "__main__":
    main()
