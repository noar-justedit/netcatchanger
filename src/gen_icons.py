"""
Regenerate src/icons.py — the pre-rendered PNG icons embedded in the app.

Source icons come from Lucide (https://lucide.dev), ISC licensed, taken
verbatim from the `lucide-static` npm package: only the stroke colour and the
raster size are applied here, the geometry is untouched.

This script is a DEVELOPMENT tool, not part of the build: the app ships the
generated src/icons.py and needs no SVG toolchain at runtime.

    pip install cairosvg
    npm install lucide-static
    python src/gen_icons.py path/to/node_modules/lucide-static/icons
"""
import base64
import io
import os
import re
import sys

import cairosvg

# Which Lucide icon backs which role in the UI
ICON_SOURCE = {
    "wifi":  "wifi.svg",          # wireless adapters
    "wired": "network.svg",       # wired adapters
    "fw_on":  "shield-check.svg", # firewall active
    "fw_off": "shield-off.svg",   # firewall disabled
}

# ingesto palette (see network_switcher.py)
COLORS = {
    "private": "#8b6ff0",
    "public":  "#f2555a",
    "domain":  "#35c98b",
    "muted":   "#8b909b",
}

SIZE_IFACE = 40
SIZE_FW    = 36


def render(svg_path, color, px):
    src = open(svg_path, encoding="utf-8").read()
    # Lucide uses stroke="currentColor"; give it the real colour.
    src = src.replace('stroke="currentColor"', f'stroke="{color}"')
    return cairosvg.svg2png(bytestring=src.encode("utf-8"),
                            output_width=px, output_height=px)


def main():
    icons_dir = sys.argv[1] if len(sys.argv) > 1 else "node_modules/lucide-static/icons"
    if not os.path.isdir(icons_dir):
        sys.exit(f"Lucide icons not found: {icons_dir}\n"
                 "Run:  npm install lucide-static")

    here = os.path.dirname(os.path.abspath(__file__))
    out = {}

    for role in ("wifi", "wired"):
        for name, color in COLORS.items():
            out[f"{role}_{name}"] = render(
                os.path.join(icons_dir, ICON_SOURCE[role]), color, SIZE_IFACE)
    out["fw_on"] = render(os.path.join(icons_dir, ICON_SOURCE["fw_on"]),
                          COLORS["domain"], SIZE_FW)
    out["fw_off"] = render(os.path.join(icons_dir, ICON_SOURCE["fw_off"]),
                           COLORS["public"], SIZE_FW)

    # The logo is NetCatChanger's own artwork, not a Lucide icon: keep the
    # existing entry byte for byte.
    sys.path.insert(0, here)
    from icons import ICONS as OLD
    logo_b64 = OLD["logo"]

    lines = [
        '# Pre-rendered icons -- base64 PNG, no PIL needed at runtime.',
        '#',
        '# Interface and firewall icons are Lucide icons (https://lucide.dev),',
        '# ISC licensed -- see LICENSE-lucide.txt. Only the stroke colour and',
        '# the raster size were changed; the artwork is unmodified.',
        '# The "logo" entry is NetCatChanger\'s own artwork (GPL v3, like the app).',
        '#',
        '# Regenerate with:  python src/gen_icons.py <lucide-static/icons>',
        'ICONS = {',
    ]
    for key in sorted(out) + ["logo"]:
        b64 = logo_b64 if key == "logo" else base64.b64encode(out[key]).decode()
        lines.append(f'    "{key}": "{b64}",')
    lines.append('}')

    target = os.path.join(here, "icons.py")
    with open(target, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    total = sum(len(v) for v in out.values())
    print(f"wrote {target}: {len(out) + 1} icons, {total // 1024} KB of PNG")


if __name__ == "__main__":
    main()
