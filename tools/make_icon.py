"""Genere assets/ha_taskbar.ico (sans dependance : dessin vectoriel simple + PNG/ICO ecrits a la main).

Usage :  python tools/make_icon.py
"""
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "ha_taskbar.ico")
SIZES = (16, 20, 24, 32, 40, 48, 64, 256)

BLUE = (0x41, 0xBD, 0xF5)
WHITE = (0xFF, 0xFF, 0xFF)
DARK = (0x20, 0x20, 0x20)
YELLOW = (0xFF, 0xC8, 0x3D)


def in_rrect(x, y, x0, y0, x1, y1, r):
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def in_tri(x, y, ax, ay, bx, by, cx, cy):
    def s(px, py, qx, qy, rx, ry):
        return (px - rx) * (qy - ry) - (qx - rx) * (py - ry)
    d1, d2, d3 = s(x, y, ax, ay, bx, by), s(x, y, bx, by, cx, cy), s(x, y, cx, cy, ax, ay)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def color_at(x, y):
    """Couleur (r, g, b) ou None (transparent) au point (x, y) dans [0,1]^2."""
    if not in_rrect(x, y, 0.03, 0.03, 0.97, 0.97, 0.2):
        return None
    if y >= 0.78:                                   # barre des taches
        if in_rrect(x, y, 0.13, 0.835, 0.40, 0.915, 0.04):
            return YELLOW                           # "bouton" allume
        return DARK
    house = in_tri(x, y, 0.5, 0.13, 0.13, 0.46, 0.87, 0.46) or (0.24 <= x <= 0.76 and 0.44 <= y <= 0.70)
    door = 0.43 <= x <= 0.57 and 0.53 <= y <= 0.70
    if house and not door:
        return WHITE
    return BLUE


def render(size, ss=4):
    rows = []
    for py in range(size):
        row = bytearray([0])                        # filtre PNG "None"
        for px in range(size):
            r = g = b = a = 0
            for sy in range(ss):
                for sx in range(ss):
                    c = color_at((px + (sx + 0.5) / ss) / size, (py + (sy + 0.5) / ss) / size)
                    if c:
                        r += c[0]; g += c[1]; b += c[2]; a += 1
            if a:
                row += bytes((r // a, g // a, b // a, 255 * a // (ss * ss)))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return png(size, b"".join(rows))


def png(size, raw):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def main():
    images = [(s, render(s, 8 if s <= 48 else 4)) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, data = b"", b""
    for s, img in images:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), offset + len(data))
        data += img
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(header + entries + data)
    with open(os.path.join(os.path.dirname(OUT), "ha_taskbar.png"), "wb") as f:
        f.write(dict(images)[256])
    print("ecrit :", OUT)


if __name__ == "__main__":
    main()
