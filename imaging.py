"""
Decodage d'images (JPEG, PNG, GIF, BMP...) avec GDI+, la bibliotheque graphique de Windows, sans
dependance externe : Tk ne lit pas le JPEG tout seul. L'image est reduite a la taille voulue puis
re-encodee en PNG, que Tk sait afficher (tk.PhotoImage(data=...)).
"""
import base64
import ctypes
import struct
import threading
import zlib
from ctypes import POINTER, byref, c_void_p, wintypes

_lock = threading.Lock()
_token = None
PixelFormat32bppARGB = 0x26200A


class _StartupInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", ctypes.c_uint32), ("DebugEventCallback", c_void_p),
                ("SuppressBackgroundThread", wintypes.BOOL), ("SuppressExternalCodecs", wintypes.BOOL)]


class _Rect(ctypes.Structure):
    _fields_ = [("X", ctypes.c_int), ("Y", ctypes.c_int), ("Width", ctypes.c_int), ("Height", ctypes.c_int)]


class _BitmapData(ctypes.Structure):
    _fields_ = [("Width", ctypes.c_uint), ("Height", ctypes.c_uint), ("Stride", ctypes.c_int),
                ("PixelFormat", ctypes.c_int), ("Scan0", c_void_p), ("Reserved", ctypes.c_size_t)]


def _gdiplus():
    global _token
    gp = ctypes.windll.gdiplus
    if _token is None:
        tok = ctypes.c_size_t()
        si = _StartupInput(1, None, False, False)
        if gp.GdiplusStartup(byref(tok), byref(si), None) != 0:
            raise OSError("GDI+ indisponible")
        _token = tok
    return gp


def _png(width, height, pix, alpha=False):
    """Pixels RGB ou RGBA (bytes) -> fichier PNG."""
    stride = width * (4 if alpha else 3)
    raw = b"".join(b"\x00" + pix[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6 if alpha else 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _mask(w, h, shape, radius):
    """Opacite (0-255) de chaque pixel pour un disque ("circle") ou un rectangle aux coins arrondis
    ("rounded"), avec un bord adouci."""
    out = bytearray(w * h)
    corner = None if shape == "circle" else max(1.0, float(radius))
    for y in range(h):
        cy = y + 0.5
        for x in range(w):
            cx = x + 0.5
            if corner is None:
                dx, dy, rr = cx - w / 2.0, cy - h / 2.0, min(w, h) / 2.0
            else:
                dx = max(0.0, abs(cx - w / 2.0) - (w / 2.0 - corner))
                dy = max(0.0, abs(cy - h / 2.0) - (h / 2.0 - corner))
                rr = corner
                if not dx and not dy:
                    out[y * w + x] = 255
                    continue
            a = rr + 0.5 - (dx * dx + dy * dy) ** 0.5
            out[y * w + x] = 255 if a >= 1 else (0 if a <= 0 else int(a * 255))
    return out


def to_png(data, max_w, max_h, shape=None, radius=8):
    """Image (bytes, tout format lu par Windows) -> (PNG en base64, largeur, hauteur), reduite pour tenir
    dans max_w x max_h en gardant ses proportions. shape="circle" : recadree en carre puis en disque
    (photo d'une personne) ; "rounded" : coins arrondis (pochette). Leve OSError si l'image est illisible."""
    shlwapi = ctypes.windll.shlwapi
    shlwapi.SHCreateMemStream.restype = c_void_p
    shlwapi.SHCreateMemStream.argtypes = [ctypes.c_char_p, ctypes.c_uint]
    with _lock:
        gp = _gdiplus()
        stream = shlwapi.SHCreateMemStream(data, len(data))
        if not stream:
            raise OSError("memoire insuffisante")
        src, dst, g = c_void_p(), c_void_p(), c_void_p()
        try:
            if gp.GdipCreateBitmapFromStream(c_void_p(stream), byref(src)) != 0:
                raise OSError("image illisible")
            w, h = ctypes.c_uint(), ctypes.c_uint()
            gp.GdipGetImageWidth(src, byref(w))
            gp.GdipGetImageHeight(src, byref(h))
            if not w.value or not h.value:
                raise OSError("image vide")
            sx, sy, sw, sh = 0, 0, w.value, h.value
            if shape == "circle":                          # carre central, a la taille demandee
                side = min(w.value, h.value)
                sx, sy, sw, sh = (w.value - side) // 2, (h.value - side) // 2, side, side
                tw = th = max(1, min(max_w, max_h))
            else:
                k = min(max_w / float(w.value), max_h / float(h.value))
                if not shape:
                    k = min(1.0, k)                        # une capture n'est jamais agrandie
                tw, th = max(1, int(w.value * k)), max(1, int(h.value * k))
            if gp.GdipCreateBitmapFromScan0(tw, th, 0, PixelFormat32bppARGB, None, byref(dst)) != 0:
                raise OSError("memoire insuffisante")
            gp.GdipGetImageGraphicsContext(dst, byref(g))
            gp.GdipSetInterpolationMode(g, 7)              # bicubique haute qualite
            gp.GdipSetPixelOffsetMode(g, 4)                # pas de liseré sur les bords
            gp.GdipDrawImageRectRectI(g, src, 0, 0, tw, th, sx, sy, sw, sh, 2, None, None, None)
            rect = _Rect(0, 0, tw, th)
            bd = _BitmapData()
            if gp.GdipBitmapLockBits(dst, byref(rect), 1, PixelFormat32bppARGB, byref(bd)) != 0:
                raise OSError("lecture des pixels impossible")
            try:
                buf = ctypes.string_at(bd.Scan0, bd.Stride * th)
            finally:
                gp.GdipBitmapUnlockBits(dst, byref(bd))
        finally:
            if g:
                gp.GdipDeleteGraphics(g)
            for im in (dst, src):
                if im:
                    gp.GdipDisposeImage(im)
            # IStream::Release
            vt = ctypes.cast(c_void_p(stream), POINTER(POINTER(c_void_p)))[0]
            ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(vt[2])(c_void_p(stream))
    if shape:                                              # BGRA -> RGBA, opacite du masque
        mask = _mask(tw, th, shape, radius)
        rgba = bytearray(tw * th * 4)
        for y in range(th):
            row = buf[y * bd.Stride:y * bd.Stride + tw * 4]
            o = y * tw * 4
            rgba[o:o + tw * 4:4] = row[2::4]
            rgba[o + 1:o + tw * 4:4] = row[1::4]
            rgba[o + 2:o + tw * 4:4] = row[0::4]
            rgba[o + 3:o + tw * 4:4] = mask[y * tw:(y + 1) * tw]
        return base64.b64encode(_png(tw, th, bytes(rgba), alpha=True)), tw, th
    # BGRA (lignes de `Stride` octets) -> RGB
    rgb = bytearray(tw * th * 3)
    for y in range(th):
        row = buf[y * bd.Stride:y * bd.Stride + tw * 4]
        o = y * tw * 3
        rgb[o:o + tw * 3:3] = row[2::4]
        rgb[o + 1:o + tw * 3:3] = row[1::4]
        rgb[o + 2:o + tw * 3:3] = row[0::4]
    return base64.b64encode(_png(tw, th, bytes(rgb))), tw, th
