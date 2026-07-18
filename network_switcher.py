"""
NetCatChanger 2.0.1  -  by Just Edit  -  www.just-edit.fr
Windows Network Profile Manager + Firewall Control
"""
import tkinter as tk
from tkinter import messagebox
import subprocess, json, threading, sys, ctypes, webbrowser, base64, re, time
from concurrent.futures import ThreadPoolExecutor

try:
    from icons import ICONS
except ImportError:
    ICONS = {}

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
def is_admin():
    try:    return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

def run_as_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1)

# ---------------------------------------------------------------------------
# PowerShell -- hidden, no console flash
# ---------------------------------------------------------------------------
def run_ps(cmd):
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive",
         "-WindowStyle", "Hidden", "-Command", cmd],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        creationflags=CREATE_NO_WINDOW)
    return r.stdout.strip(), r.stderr.strip()

# ---------------------------------------------------------------------------
# Single batched PS call -- all interface data in one shot
# ---------------------------------------------------------------------------
_BATCH_SCRIPT = r"""
$result = @()
$profiles = Get-NetConnectionProfile -ErrorAction SilentlyContinue
if (-not $profiles) { Write-Output '[]'; exit }
if ($profiles -isnot [array]) { $profiles = @($profiles) }

$adapters = @{}
try {
    Get-NetAdapter -ErrorAction SilentlyContinue |
        ForEach-Object { $adapters[$_.Name] = $_ }
} catch {}

$allIPs = @{}
try {
    Get-NetIPAddress -ErrorAction SilentlyContinue |
        Where-Object { $_.AddressFamily -eq 'IPv4' -or $_.AddressFamily -eq 'IPv6' } |
        ForEach-Object {
            if (-not $allIPs.ContainsKey($_.InterfaceAlias)) {
                $allIPs[$_.InterfaceAlias] = @()
            }
            $allIPs[$_.InterfaceAlias] += $_
        }
} catch {}

$wifiBlocks = @{}
try {
    $netshOut = netsh wlan show interfaces 2>$null
    $cur = $null
    foreach ($line in $netshOut) {
        if ($line -match '^\s+Name\s+:\s+(.+)$') {
            $cur = $matches[1].Trim()
            $wifiBlocks[$cur] = @{ Signal=-1; RadioType=''; Band=''; Channel=-1 }
        }
        if ($cur) {
            if ($line -match '^\s+Signal\s+:\s+(\d+)%')       { $wifiBlocks[$cur].Signal    = [int]$matches[1] }
            if ($line -match '^\s+Radio type\s+:\s+(.+)$')    { $wifiBlocks[$cur].RadioType = $matches[1].Trim() }
            if ($line -match '^\s+Band\s+:\s+(.+)$')          { $wifiBlocks[$cur].Band      = $matches[1].Trim() }
            if ($line -match '^\s+Channel\s+:\s+(\d+)')       { $wifiBlocks[$cur].Channel   = [int]$matches[1] }
        }
    }
} catch {}

foreach ($p in $profiles) {
    $a = $p.InterfaceAlias
    $obj = [ordered]@{
        InterfaceAlias  = $a
        Name            = $p.Name
        NetworkCategory = [int]$p.NetworkCategory
        IPv4Address     = 'N/A'
        IPv6Address     = 'N/A'
        LinkSpeed       = ''
        MediaType       = ''
        WifiSignal      = -1
        WifiStandard    = ''
        WifiBand        = ''
        WifiChannel     = -1
    }
    if ($allIPs.ContainsKey($a)) {
        $v4 = $allIPs[$a] | Where-Object { $_.AddressFamily -eq 'IPv4' } |
              Select-Object -First 1 -ExpandProperty IPAddress
        $v6 = $allIPs[$a] | Where-Object { $_.AddressFamily -eq 'IPv6' -and
              $_.PrefixOrigin -ne 'WellKnown' } |
              Select-Object -First 1 -ExpandProperty IPAddress
        if ($v4) { $obj.IPv4Address = $v4 }
        if ($v6) { $obj.IPv6Address = $v6 }
    }
    if ($adapters.ContainsKey($a)) {
        $ad = $adapters[$a]
        $obj.LinkSpeed = "$($ad.LinkSpeed)"
        $obj.MediaType = "$($ad.MediaType)"
    }
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
        return [data] if isinstance(data, dict) else data
    except:
        return []

def get_firewall_state():
    out, _ = run_ps(
        "Get-NetFirewallProfile -All | Select-Object -ExpandProperty Enabled")
    if not out:
        return None, None
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    on = sum(1 for l in lines if l.lower() == "true")
    return on, len(lines)

def set_network_profile(alias, category):
    _, err = run_ps(
        f'Set-NetConnectionProfile -InterfaceAlias "{alias}" -NetworkCategory {category}')
    return err == ""

def set_firewall_state(enable):
    val = "True" if enable else "False"
    _, err = run_ps(f"Set-NetFirewallProfile -All -Enabled {val}")
    return err == ""

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
def detect_iface_type(alias, media_type=""):
    kws = ["wi-fi", "wifi", "wireless", "wlan", "802.11", "wi fi", "airport"]
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
    b = band_str.lower()
    if "6" in b and "ghz" in b: return "6 GHz"
    if "5" in b and "ghz" in b: return "5 GHz"
    if "2.4" in b:               return "2.4 GHz"
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
    except:
        return speed_str.strip()

def signal_color(pct):
    if pct >= 70: return DOMAIN
    if pct >= 40: return WARN
    return PUBLIC

# ---------------------------------------------------------------------------
# Background network watcher -- polls every 3s, negligible CPU
# ---------------------------------------------------------------------------
class NetworkWatcher:
    def __init__(self, callback):
        self._cb      = callback
        self._running = False

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _loop(self):
        last = None
        while self._running:
            try:
                out, _ = run_ps(
                    "Get-NetConnectionProfile -ErrorAction SilentlyContinue | "
                    "Select-Object InterfaceAlias,NetworkCategory | "
                    "ConvertTo-Json -Compress")
                h = hash(out)
                if last is not None and h != last:
                    self._cb()
                last = h
            except:
                pass
            time.sleep(3)

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
    except:
        _icon_cache[key] = None
        return None

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
BG      = "#0c0a14"
CARD    = "#120f1e"
BORDER  = "#2a2244"
TEXT    = "#eae6ff"
MUTED   = "#6b5f8a"
PRIVATE = "#5936d8"
PUBLIC  = "#e8414a"
DOMAIN  = "#22c55e"
ACCENT  = "#7c5ce8"
HOVER   = "#1c1730"
WARN    = "#f59e0b"

PROFILE_MAP = {
    "Private":             {"label": "Private", "color": PRIVATE, "icon_key": "private"},
    "Public":              {"label": "Public",  "color": PUBLIC,  "icon_key": "public"},
    "DomainAuthenticated": {"label": "Domain",  "color": DOMAIN,  "icon_key": "domain"},
}
TOGGLE_STEPS = 10

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NetCatChanger 2.0.1")
        self.geometry("840x680")
        self.minsize(700, 520)
        self.configure(bg=BG)
        self.resizable(True, True)
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"840x680+{(sw-840)//2}+{(sh-680)//2}")

        self._fw_enabled   = None
        self._fw_animating = False
        self._loading      = False

        self._build_ui()
        self._load_all()

        self._watcher = NetworkWatcher(self._on_net_change)
        self._watcher.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._watcher.stop()
        self.destroy()

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

    def _set_toggle_frame(self, target_on, step=None):
        key = ("toggle_on" if target_on else "toggle_off") if step is None \
              else f"{'tog_on' if target_on else 'tog_off'}_{step}"
        img = self._icon(key)
        if img:
            self._fw_toggle.config(image=img)
            self._fw_toggle._img = img

    # -----------------------------------------------------------------------
    # Build UI
    # -----------------------------------------------------------------------
    def _build_ui(self):

        # FOOTER -- packed first so it stays at bottom
        tk.Frame(self, bg=PRIVATE, height=1).pack(side="bottom", fill="x")
        footer = tk.Frame(self, bg=CARD)
        footer.pack(side="bottom", fill="x")
        fi = tk.Frame(footer, bg=CARD, pady=9)
        fi.pack(fill="x", padx=22)

        by = tk.Frame(fi, bg=CARD)
        by.pack(side="left")
        tk.Label(by, text="by ", font=("Segoe UI",8),
                 fg=MUTED, bg=CARD).pack(side="left")
        je = tk.Label(by, text="Just Edit",
                      font=("Segoe UI",8,"bold underline"),
                      fg=PRIVATE, bg=CARD, cursor="hand2")
        je.pack(side="left")
        je.bind("<Button-1>", lambda e: webbrowser.open("https://www.just-edit.fr"))
        je.bind("<Enter>",    lambda e: je.config(fg=ACCENT))
        je.bind("<Leave>",    lambda e: je.config(fg=PRIVATE))
        tk.Label(fi, text="  -  Requires administrator rights",
                 font=("Segoe UI",8), fg=MUTED, bg=CARD).pack(side="left")

        self._refresh_btn = tk.Button(
            fi, text="Refresh",
            font=("Segoe UI",9,"bold"), fg=TEXT, bg=HOVER,
            activeforeground=TEXT, activebackground=BORDER,
            relief="flat", bd=0, cursor="hand2", padx=14, pady=5,
            command=self._load_all)
        self._refresh_btn.pack(side="right")
        self._refresh_btn.bind("<Enter>", lambda e: self._refresh_btn.config(bg=BORDER))
        self._refresh_btn.bind("<Leave>", lambda e: self._refresh_btn.config(bg=HOVER))

        # HEADER
        header = tk.Frame(self, bg=BG)
        header.pack(side="top", fill="x")

        top = tk.Frame(header, bg=BG)
        top.pack(fill="x", padx=26, pady=(20,4))

        left = tk.Frame(top, bg=BG)
        left.pack(side="left")

        logo_lbl = tk.Label(left, bg=BG, bd=0)
        logo_lbl.pack(side="left", padx=(0,14))
        self._set_img(logo_lbl, self._icon("logo"),
                      fallback="N", font=("Arial",18,"bold"), fg=PRIVATE)

        tc = tk.Frame(left, bg=BG)
        tc.pack(side="left")
        tk.Label(tc, text="NetCatChanger 2.0.1",
                 font=("Segoe UI",17,"bold"), fg=TEXT, bg=BG).pack(anchor="w")
        tk.Label(tc, text="Windows Network Profile Manager",
                 font=("Segoe UI",8), fg=MUTED, bg=BG).pack(anchor="w")

        self._status_lbl = tk.Label(top, text="  Loading...",
                                    font=("Segoe UI",8), fg=MUTED, bg=BG)
        self._status_lbl.pack(side="right", anchor="n", pady=(6,0))

        # Legend chips
        leg = tk.Frame(header, bg=BG)
        leg.pack(fill="x", padx=26, pady=(2,0))
        for info in PROFILE_MAP.values():
            c = tk.Frame(leg, bg=info["color"], padx=1, pady=1)
            c.pack(side="left", padx=(0,8))
            tk.Label(c, text=f"  {info['label']}  ",
                     font=("Segoe UI",8,"bold"), fg="white",
                     bg=info["color"]).pack()

        tk.Frame(self, bg=PRIVATE, height=2).pack(side="top", fill="x", pady=(10,0))

        # FIREWALL BANNER
        fw_b = tk.Frame(self, bg=CARD)
        fw_b.pack(side="top", fill="x")
        fwi = tk.Frame(fw_b, bg=CARD, padx=26, pady=12)
        fwi.pack(fill="x")

        self._fw_icon_lbl = tk.Label(fwi, bg=CARD, bd=0)
        self._fw_icon_lbl.pack(side="left", padx=(0,14))

        fw_txt = tk.Frame(fwi, bg=CARD)
        fw_txt.pack(side="left", fill="x", expand=True)
        tk.Label(fw_txt, text="Windows Firewall",
                 font=("Segoe UI",10,"bold"), fg=TEXT, bg=CARD).pack(anchor="w")
        self._fw_sub = tk.Label(fw_txt, text="Checking...",
                                font=("Segoe UI",8), fg=MUTED, bg=CARD)
        self._fw_sub.pack(anchor="w")

        rfw = tk.Frame(fwi, bg=CARD)
        rfw.pack(side="right")
        self._fw_state_lbl = tk.Label(rfw, text="--",
                                      font=("Segoe UI",9,"bold"),
                                      fg=MUTED, bg=CARD, width=5, anchor="e")
        self._fw_state_lbl.pack(side="left", padx=(0,12))

        self._fw_toggle = tk.Label(rfw, bg=CARD, bd=0, cursor="hand2")
        self._fw_toggle.pack(side="left")
        self._fw_toggle.bind("<Button-1>", self._on_fw_click)
        self._set_toggle_frame(False)

        tk.Frame(self, bg=BORDER, height=1).pack(side="top", fill="x")

        # SCROLLABLE CARD LIST
        outer = tk.Frame(self, bg=BG)
        outer.pack(side="top", fill="both", expand=True, padx=26, pady=16)

        scv = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        sb  = tk.Scrollbar(outer, orient="vertical", command=scv.yview,
                           bg=CARD, troughcolor=BG, activebackground=BORDER,
                           relief="flat", bd=0, width=5)
        scv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        scv.pack(side="left", fill="both", expand=True)

        self._list_frame = tk.Frame(scv, bg=BG)
        win = scv.create_window((0,0), window=self._list_frame, anchor="nw")
        self._list_frame.bind("<Configure>",
            lambda e: scv.configure(scrollregion=scv.bbox("all")))
        scv.bind("<Configure>",
            lambda e: scv.itemconfig(win, width=e.width))
        scv.bind_all("<MouseWheel>",
            lambda e: scv.yview_scroll(-1*(e.delta//120), "units"))

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
                ifaces          = f_ifaces.result()
                fw_on, fw_total = f_firewall.result()
            self.after(0, lambda: self._render_all(ifaces, fw_on, fw_total))

        threading.Thread(target=fetch, daemon=True).start()

    def _render_all(self, ifaces, fw_on, fw_total):
        self._render_profiles(ifaces)
        self._update_fw_ui(fw_on, fw_total)
        self._refresh_btn.config(state="normal")
        self._loading = False

    # -----------------------------------------------------------------------
    # Render profile cards
    # -----------------------------------------------------------------------
    def _render_profiles(self, profiles):
        for w in self._list_frame.winfo_children():
            w.destroy()

        if not profiles:
            tk.Label(self._list_frame,
                     text="No network interface found.\n\n"
                          "Make sure the app is running as administrator.",
                     font=("Segoe UI",11), fg=MUTED, bg=BG,
                     justify="center").pack(pady=60)
            self._set_status("error")
            return

        for p in profiles:
            self._make_card(self._list_frame, p).pack(fill="x", pady=(0,10))
        self._set_status("ok")

    # -----------------------------------------------------------------------
    # Card builder
    # -----------------------------------------------------------------------
    def _make_card(self, parent, p):
        cat = p.get("NetworkCategory", 0)
        if isinstance(cat, int):
            cat = {0:"Public", 1:"Private", 2:"DomainAuthenticated"}.get(cat, "Public")

        info  = PROFILE_MAP.get(cat, PROFILE_MAP["Public"])
        alias = p.get("InterfaceAlias", "Unknown")
        name  = p.get("Name", alias)
        v4    = p.get("IPv4Address", "N/A")
        v6    = p.get("IPv6Address", "N/A")
        media = p.get("MediaType", "")
        itype = detect_iface_type(alias, media)
        color = info["color"]
        ikey  = info["icon_key"]

        signal   = int(p.get("WifiSignal", -1))
        standard = parse_wifi_standard(p.get("WifiStandard", ""))
        band     = parse_wifi_band(p.get("WifiBand", ""), int(p.get("WifiChannel", -1)))
        link_spd = parse_link_speed(p.get("LinkSpeed", ""))

        outer = tk.Frame(parent, bg=color, padx=1, pady=1)
        card  = tk.Frame(outer, bg=CARD, padx=16, pady=12)
        card.pack(fill="both", expand=True)

        # col 0: icon | col 1: name+details | col 2: IPs | col 3: pill+btn

        # -- Icon --
        ico = tk.Label(card, bg=CARD, bd=0)
        ico.grid(row=0, column=0, rowspan=4, padx=(0,16), sticky="nw", pady=(2,0))
        icon_key = f"{'wifi' if itype=='wifi' else 'wired'}_{ikey}"
        self._set_img(ico, self._icon(icon_key),
                      fallback="W" if itype=="wifi" else "E",
                      font=("Arial",18,"bold"), fg=color)

        # -- Name --
        tk.Label(card, text=alias,
                 font=("Segoe UI",12,"bold"), fg=TEXT, bg=CARD,
                 anchor="w").grid(row=0, column=1, sticky="w")

        sub = name if name != alias else ("Wi-Fi" if itype=="wifi" else "Ethernet")
        tk.Label(card, text=sub,
                 font=("Segoe UI",8), fg=MUTED, bg=CARD,
                 anchor="w").grid(row=1, column=1, sticky="w")

        # -- Extra info: wifi standard+band OR ethernet speed --
        extra_parts = []
        if itype == "wifi":
            if standard: extra_parts.append(standard)
            if band:     extra_parts.append(band)
        else:
            if link_spd: extra_parts.append(link_spd)

        if extra_parts:
            tk.Label(card, text="  ".join(extra_parts),
                     font=("Segoe UI",8,"bold"), fg=color, bg=CARD,
                     anchor="w").grid(row=2, column=1, sticky="w")

        # -- WiFi signal bar --
        if itype == "wifi" and signal >= 0:
            sig_frame = tk.Frame(card, bg=CARD)
            sig_frame.grid(row=3, column=1, sticky="w", pady=(4,0))
            sig_col = signal_color(signal)
            tk.Label(sig_frame, text=f"Signal  {signal}%",
                     font=("Segoe UI",8), fg=sig_col, bg=CARD).pack(side="left", padx=(0,8))
            bar_w, bar_h = 100, 7
            bar = tk.Canvas(sig_frame, width=bar_w, height=bar_h,
                            bg=BORDER, highlightthickness=0, bd=0)
            bar.pack(side="left")
            fill_w = int(bar_w * signal / 100)
            if fill_w > 0:
                bar.create_rectangle(0, 0, fill_w, bar_h,
                                     fill=sig_col, outline="")

        # -- IPs --
        ipf = tk.Frame(card, bg=CARD)
        ipf.grid(row=0, column=2, rowspan=4, padx=(18,0), sticky="e")
        self._ip_row(ipf, "IPv4", v4,
                     DOMAIN if v4 != "N/A" else MUTED).pack(anchor="e", pady=2)
        self._ip_row(ipf, "IPv6", v6,
                     ACCENT if v6 != "N/A" else MUTED).pack(anchor="e", pady=2)

        # -- Profile pill + switch button --
        right = tk.Frame(card, bg=CARD)
        right.grid(row=0, column=3, rowspan=4, padx=(16,0), sticky="ne")

        pill = tk.Frame(right, bg=color, padx=1, pady=1)
        pill.pack(anchor="e")
        tk.Label(pill, text=f"  {info['label']}  ",
                 font=("Segoe UI",9,"bold"), fg="white", bg=color).pack()

        if cat in ("Private", "Public"):
            tgt     = "Public" if cat == "Private" else "Private"
            tgt_inf = PROFILE_MAP[tgt]
            btn = tk.Button(right, text=f"> {tgt_inf['label']}",
                font=("Segoe UI",8,"bold"), fg=tgt_inf["color"], bg=BG,
                activeforeground=TEXT, activebackground=HOVER,
                relief="flat", bd=0, cursor="hand2", padx=10, pady=4,
                command=lambda a=alias, t=tgt: self._switch_profile(a, t))
            btn.pack(anchor="e", pady=(6,0))
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=HOVER))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=BG))
        elif cat == "DomainAuthenticated":
            tk.Label(right, text="Managed by IT",
                     font=("Segoe UI",8), fg=MUTED, bg=CARD).pack(anchor="e", pady=(6,0))

        card.columnconfigure(2, weight=1)
        return outer

    def _ip_row(self, parent, label, value, col):
        row = tk.Frame(parent, bg=CARD)
        tk.Label(row, text=f"{label} : ",
                 font=("Segoe UI",8), fg=MUTED, bg=CARD).pack(side="left")
        tk.Label(row, text=value,
                 font=("Courier New",8,"bold"), fg=col, bg=CARD).pack(side="left")
        return row

    # -----------------------------------------------------------------------
    # Profile switching
    # -----------------------------------------------------------------------
    def _switch_profile(self, alias, target):
        if not messagebox.askyesno("Confirm",
                f"Switch '{alias}' to {target} profile?", parent=self):
            return
        self._set_status("loading")
        def do():
            ok = set_network_profile(alias, target)
            self.after(0, lambda: self._on_switch_done(ok, alias))
        threading.Thread(target=do, daemon=True).start()

    def _on_switch_done(self, ok, alias):
        if ok:
            self._load_all()
        else:
            messagebox.showerror("Error",
                f"Could not change profile for '{alias}'.\n\n"
                "Make sure the app is running as administrator.", parent=self)
            self._set_status("error")
            self._refresh_btn.config(state="normal")
            self._loading = False

    # -----------------------------------------------------------------------
    # Firewall
    # -----------------------------------------------------------------------
    def _update_fw_ui(self, on, total):
        if on is None:
            self._fw_sub.config(text="Status unknown", fg=MUTED)
            self._fw_state_lbl.config(text="?", fg=MUTED)
            self._fw_enabled = None
            self._set_img(self._fw_icon_lbl, self._icon("fw_off"),
                          "?", ("Segoe UI",16), PUBLIC)
            self._set_toggle_frame(False)
            return

        self._fw_enabled = (on > 0)

        if on == total and total > 0:
            color, sub, lbl = DOMAIN, \
                f"Active  -  {total} profile{'s' if total>1 else ''} protected", "ON"
        elif on == 0:
            color, sub, lbl = PUBLIC, \
                "Disabled  -  Your system is not protected", "OFF"
        else:
            color, sub, lbl = WARN, \
                f"Partially active ({on}/{total} profiles)", f"{on}/{total}"

        self._fw_sub.config(text=sub, fg=color)
        self._fw_state_lbl.config(text=lbl, fg=color)
        fw_key = "fw_on" if on > 0 else "fw_off"
        self._set_img(self._fw_icon_lbl, self._icon(fw_key),
                      "O" if on > 0 else "X", ("Segoe UI",16), color)
        self._set_toggle_frame(on > 0)

    def _on_fw_click(self, _=None):
        if self._fw_animating:
            return
        self._fw_animating = True
        target = not self._fw_enabled if self._fw_enabled is not None else True
        self._animate_fw(0, target)

    def _animate_fw(self, step, target):
        if step > TOGGLE_STEPS:
            self._fw_animating = False
            self._fw_state_lbl.config(text="...", fg=MUTED)
            def do():
                ok = set_firewall_state(target)
                self.after(0, lambda: self._on_fw_done(ok))
            threading.Thread(target=do, daemon=True).start()
            return
        self._set_toggle_frame(target, step=step)
        self.after(20, lambda: self._animate_fw(step+1, target))

    def _on_fw_done(self, ok):
        self._fw_animating = False
        if not ok:
            messagebox.showerror("Error",
                "Could not change firewall state.\n\n"
                "Make sure the app is running as administrator.", parent=self)
        def fetch():
            on, total = get_firewall_state()
            self.after(0, lambda: self._update_fw_ui(on, total))
        threading.Thread(target=fetch, daemon=True).start()

    # -----------------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------------
    def _set_status(self, state):
        d = {"ok":      (DOMAIN, "  Ready"),
             "loading": (ACCENT, "  Loading..."),
             "error":   (PUBLIC, "  Error")}
        col, txt = d.get(state, d["error"])
        self._status_lbl.config(fg=col, text=txt)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if sys.platform == "win32" and not is_admin():
        if messagebox.askyesno(
            "Administrator rights required",
            "NetCatChanger 2.0.1 requires administrator rights "
            "to manage network profiles and the firewall.\n\n"
            "Restart as administrator?"):
            run_as_admin()
        sys.exit(0)

    App().mainloop()
