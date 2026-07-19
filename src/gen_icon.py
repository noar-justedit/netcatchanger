"""
Generate app_icon.ico with proper multi-size BMP/PNG ICO format.
BMP for small sizes (<=48) for max Windows compatibility.
PNG for large sizes (>=64) for quality and size.
"""
import sys, io, struct, os

try:
    from PIL import Image, ImageDraw

    SVG_W = 800.0

    def p(x, y, S):
        return (x/SVG_W*S, y/SVG_W*S)

    def make_logo(out):
        S   = out * 8
        img = Image.new("RGBA", (S, S), (0,0,0,0))
        d   = ImageDraw.Draw(img)
        def pp(x, y): return p(x, y, S)
        lw  = max(2, int(67/SVG_W*S))
        rr  = max(4, int(142/SVG_W*S))
        cw  = (255, 255, 255, 255)
        a, b = pp(78.69, 60), pp(78.69+642.63, 60+284)
        d.rounded_rectangle([a[0],a[1],b[0],b[1]], radius=rr, outline=cw, width=lw)
        cx, cy = pp(570.33, 202)
        r = 70.99/SVG_W*S
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(89, 54, 216, 255))
        a2, b2 = pp(78.69, 456), pp(78.69+642.63, 456+284)
        d.rounded_rectangle([a2[0],a2[1],b2[0],b2[1]], radius=rr, outline=cw, width=lw)
        cx2, cy2 = pp(229.67, 598)
        d.ellipse([cx2-r, cy2-r, cx2+r, cy2+r], fill=(255, 0, 98, 255))
        return img.resize((out, out), Image.LANCZOS)

    def to_bmp(img):
        w, h = img.size
        bih = struct.pack('<IiiHHIIiiII', 40, w, h*2, 1, 32, 0, 0, 0, 0, 0, 0)
        pixels = img.tobytes('raw', 'BGRA')
        row_size = w * 4
        rows = [pixels[i*row_size:(i+1)*row_size] for i in range(h)]
        xor_mask = b''.join(reversed(rows))
        and_bytes = ((w + 31) // 32) * 4
        and_mask = b'\x00' * (and_bytes * h)
        return bih + xor_mask + and_mask

    def to_png(img):
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        return buf.getvalue()

    sizes  = [16, 24, 32, 48, 64, 128, 256]
    entries = []
    for s in sizes:
        pil = make_logo(s)
        raw = to_bmp(pil) if s <= 48 else to_png(pil)
        entries.append((s, raw))

    n = len(entries)
    header = struct.pack('<HHH', 0, 1, n)
    data_start = 6 + n * 16
    dirs = b''
    data = b''
    off  = data_start
    for (s, raw) in entries:
        w = 0 if s >= 256 else s
        dirs += struct.pack('<BBBBHHII', w, w, 0, 0, 1, 32, len(raw), off)
        data += raw
        off  += len(raw)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'app_icon.ico')
    with open(out_path, 'wb') as f:
        f.write(header + dirs + data)

    size_kb = os.path.getsize(out_path)
    print(f'[OK] {out_path}: {size_kb} bytes, {n} sizes: {sizes}')
    sys.exit(0)

except Exception as e:
    print(f'[SKIP] {e}')
    sys.exit(1)
