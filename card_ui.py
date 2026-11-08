"""Carte de controle (appui long sur un element de la barre), dans l'esprit du "more-info" de Home Assistant :
interrupteur, luminosite, temperature de couleur, consigne de chauffage, modes, volets, media, historique 24 h...
"""
import ctypes
import datetime
import queue
import threading
import time
import urllib.parse
import webbrowser
import tkinter as tk
from ctypes import wintypes
from tkinter import font as tkfont

from ha_core import (ACTIVE_STATES, STATE_TEXT, card_light, card_palette, group_state, item_members, load_config,
                     parse_time, resolve_icon, resolve_service, save_config)

user32 = ctypes.windll.user32
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.SetWindowPos.argtypes = [wintypes.HWND, ctypes.c_ssize_t, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]

GA_ROOT, GWL_EXSTYLE = 2, -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x80, 0x40000
HWND_TOPMOST, SWP_NOACTIVATE = -1, 0x10

# Glyphes Segoe Fluent Icons / MDL2
G_PLUS, G_MINUS = "", ""
G_PLAY, G_PAUSE, G_PREV, G_NEXT, G_STOP = "", "", "", "", ""
G_UP, G_DOWN = "", ""
G_EDIT, G_CHECK = "", ""

G_MUTE, G_VOLUME, G_LOCATE = "", "", ""

TOGGLE_DOMAINS = {"light", "switch", "input_boolean", "fan", "automation", "siren", "humidifier"}
ACTION_DOMAINS = {"scene", "script", "button", "input_button"}
COLOR_MODES = {"hs", "rgb", "rgbw", "rgbww", "xy"}

HVAC_TEXT = {"off": "Arrêt", "heat": "Chauffage", "cool": "Clim", "heat_cool": "Auto", "auto": "Auto",
             "dry": "Déshum.", "fan_only": "Ventilation"}
HVAC_ACTION = {"heating": "Chauffe", "cooling": "Refroidit", "idle": "Au repos", "off": "Arrêt",
               "drying": "Déshumidifie", "fan": "Ventile", "preheating": "Préchauffe", "defrosting": "Dégivre"}
PRESET_TEXT = {"none": "Aucun", "eco": "Éco", "comfort": "Confort", "away": "Absent", "home": "Maison",
               "sleep": "Nuit", "boost": "Boost", "activity": "Activité", "frost_protection": "Hors-gel",
               "nature": "Naturel", "fresh": "Frais", "smart": "Auto", "custom": "Perso", "auto": "Auto",
               "normal": "Normal", "breeze": "Brise", "turbo": "Turbo", "silent": "Silence", "quiet": "Silence"}
# Ventilateur : features HA (FanEntityFeature) et sens de rotation
FAN_OSCILLATE, FAN_DIRECTION = 2, 4
FAN_DIRECTIONS = [("forward", "Été · normal"), ("reverse", "Hiver · inversé")]
# Arret programme (minuterie locale de HA Taskbar)
TIMER_DOMAINS = TOGGLE_DOMAINS | {"media_player", "climate"}
TIMER_CHOICES = [(15, "15 min"), (30, "30 min"), (60, "1 h"), (120, "2 h")]
# Periodes de l'historique (heures)
HISTORY_PERIODS = [(24, "24 h"), (168, "7 jours"), (720, "30 jours")]
# Ambiances integrees des lumieres : (nom, luminosite %, temperature K ou None)
LIGHT_SCENES_CT = [("Lecture", 100, 4500), ("Détente", 45, 2700), ("Veilleuse", 5, 2200)]
LIGHT_SCENES_DIM = [("Fort", 100, None), ("Moyen", 50, None), ("Veilleuse", 5, None)]
SELECT_TEXT = {"cancel": "Arrêt", "off": "Arrêt", "on": "Marche", "none": "Aucun"}
VACUUM_TEXT = {"cleaning": "Nettoie", "docked": "Sur sa base", "returning": "Retour à la base", "idle": "Inactif",
               "paused": "En pause", "error": "Erreur"}
# Entites du meme appareil affichees dans la carte (les autres domaines sont ignores)
SIBLING_DOMAINS = ("light", "switch", "fan", "select", "number", "sensor", "binary_sensor", "button",
                   "input_boolean", "cover", "lock", "siren")
MAX_SIBLINGS = 6
COVER_TEXT = {"open": "Ouvert", "closed": "Fermé", "opening": "Ouverture…", "closing": "Fermeture…"}
MEDIA_TEXT = {"playing": "Lecture", "paused": "Pause", "idle": "Inactif", "off": "Éteint", "on": "Allumé",
              "standby": "Veille", "buffering": "Chargement…"}
LOCK_TEXT = {"locked": "Verrouillé", "unlocked": "Déverrouillé", "locking": "Verrouillage…",
             "unlocking": "Déverrouillage…", "jammed": "Bloqué", "open": "Ouvert"}

SWATCHES = [(255, 59, 48), (255, 149, 0), (255, 214, 10), (52, 199, 89),
            (48, 200, 230), (10, 132, 255), (175, 82, 222), (255, 55, 145)]
CT_GRADIENT = ["#ff9b3d", "#ffc58a", "#fff1de", "#e6efff", "#c4d8ff"]


# --------------------------------------------------------------------------- utilitaires
def hex_rgb(c):
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def rgb_hex(t):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in t)


def mix(a, b, t):
    """Melange a -> b (t = 0..1)."""
    ra, rb = hex_rgb(a), hex_rgb(b)
    return rgb_hex([x + (y - x) * t for x, y in zip(ra, rb)])


def lum(c):
    r, g, b = hex_rgb(c)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def gradient_at(stops, t):
    t = max(0.0, min(1.0, t)) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    return mix(stops[i], stops[i + 1], t - i)


def fnum(v, dec=None):
    """Nombre a la francaise : 21,4 / 1250 / 12,84."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if dec is not None:
        s = "%.*f" % (int(dec), f)
    elif f.is_integer():
        s = "%d" % f
    else:
        s = ("%.2f" % f).rstrip("0").rstrip(".")
    return s.replace(".", ",")


def ago(iso):
    t = parse_time(iso)
    if t is None:
        return ""
    s = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
    if s < 60:
        return "à l'instant"
    if s < 3600:
        return "il y a %d min" % (s // 60)
    if s < 86400:
        return "il y a %d h" % (s // 3600)
    return "il y a %d j" % (s // 86400)


def derive_palette(base):
    """Complete les couleurs d'un theme : texte sur accent, survol de l'accent, piste des curseurs."""
    c = dict(base)
    dark = lum(c["bg"]) < 0.5
    c["accent_fg"] = "#000000" if lum(c["accent"]) > 0.55 else "#ffffff"
    c["accent_h"] = mix(c["accent"], "#ffffff" if dark else "#000000", 0.15)
    c["track"] = mix(c["bg"], c["fg"], 0.35)
    return c


def rrect(cv, x0, y0, x1, y1, r, **kw):
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
           x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(pts, smooth=True, splinesteps=12, **kw)


# --------------------------------------------------------------------------- widgets dessines
class Btn(tk.Canvas):
    """Bouton arrondi (texte et/ou glyphe). primary = couleur d'accent ; round_ = cercle."""

    def __init__(self, parent, card, text="", command=None, width=None, height=None, glyph=None,
                 primary=False, round_=False, glyph_size=11):
        self.card, self.text, self.glyph, self.primary, self.round = card, text, glyph, primary, round_
        self.command, self.hover, self.glyph_size = command, False, glyph_size
        h = height or card.s(32)
        if width is None:
            width = h if round_ else card.f_btn_m.measure(text) + card.s(28) + (card.s(22) if glyph else 0)
        self.w, self.h = int(width), int(h)
        super().__init__(parent, width=self.w, height=self.h, bg=card.c["bg"], highlightthickness=0, cursor="hand2")
        self.bind("<Enter>", lambda e: self._hov(True))
        self.bind("<Leave>", lambda e: self._hov(False))
        self.bind("<ButtonRelease-1>", self._release)
        self.draw()

    def _hov(self, on):
        self.hover = on
        self.draw()

    def _release(self, e):
        if 0 <= e.x < self.w and 0 <= e.y < self.h and self.command:
            self.command()

    def set(self, text=None, glyph=None, primary=None):
        if text is not None:
            self.text = text
        if glyph is not None:
            self.glyph = glyph
        if primary is not None:
            self.primary = primary
        self.draw()

    def draw(self):
        c, s = self.card.c, self.card.s
        self.delete("all")
        if self.primary:
            fill, fg = (c["accent_h"] if self.hover else c["accent"]), c["accent_fg"]
        else:
            fill, fg = (c["surface_h"] if self.hover else c["surface"]), c["fg"]
        if self.round:
            self.create_oval(1, 1, self.w - 1, self.h - 1, fill=fill, outline=fill)
        else:
            rrect(self, 1, 1, self.w - 1, self.h - 1, s(self.card.radius), fill=fill, outline=fill)
        gfont = (self.card.ifont, self.glyph_size)
        if self.glyph and self.text:
            gw = s(16) + s(8)
            tw = self.card.f_btn_m.measure(self.text)
            x = (self.w - gw - tw) / 2
            self.create_text(x + s(8), self.h / 2, text=self.glyph, font=gfont, fill=fg)
            self.create_text(x + gw, self.h / 2, text=self.text, font=self.card.f_btn, fill=fg, anchor="w")
        else:
            self.create_text(self.w / 2, self.h / 2, text=self.glyph or self.text,
                             font=gfont if self.glyph else self.card.f_btn, fill=fg)


class Toggle(tk.Canvas):
    """Interrupteur facon Windows 11."""

    def __init__(self, parent, card, command, key="toggle"):
        self.card, self.command, self.on, self.key = card, command, None, key
        self.w, self.h = card.s(44), card.s(22)
        super().__init__(parent, width=self.w, height=self.h, bg=card.c["bg"], highlightthickness=0, cursor="hand2")
        self.bind("<ButtonRelease-1>", self._click)
        self.set(False)

    def set(self, on, force=False):
        if on == self.on and not force:
            return
        self.on = on
        c, w, h = self.card.c, self.w, self.h
        self.delete("all")
        # pilule = 2 demi-cercles + rectangle (bords parfaitement ronds)
        fill = c["accent"] if on else c["dim"]
        self.create_oval(0, 0, h - 1, h - 1, fill=fill, outline=fill)
        self.create_oval(w - h, 0, w - 1, h - 1, fill=fill, outline=fill)
        self.create_rectangle(h / 2, 0, w - h / 2, h - 1, fill=fill, outline=fill)
        if not on:   # contour seul : on "creuse" l'interieur
            b = max(1, self.card.s(1))
            self.create_oval(b, b, h - 1 - b, h - 1 - b, fill=c["bg"], outline=c["bg"])
            self.create_oval(w - h + b, b, w - 1 - b, h - 1 - b, fill=c["bg"], outline=c["bg"])
            self.create_rectangle(h / 2, b, w - h / 2, h - 1 - b, fill=c["bg"], outline=c["bg"])
        r = h * (0.28 if on else 0.22)
        cx = w - h / 2 if on else h / 2
        col = c["accent_fg"] if on else c["dim"]
        self.create_oval(cx - r, (h - 1) / 2 - r, cx + r, (h - 1) / 2 + r, fill=col, outline=col)

    def _click(self, e):
        if 0 <= e.x < self.w and 0 <= e.y < self.h:
            self.set(not self.on)
            self.card.hold(self.key)
            self.command(self.on)


class Slider(tk.Frame):
    """Curseur avec libelle et valeur. commit(v) n'est appele qu'au relachement (pas de rafale d'appels)."""

    def __init__(self, parent, card, label, vmin, vmax, step, fmt, commit, key, wheel=None, gradient=None):
        c = card.c
        super().__init__(parent, bg=c["bg"])
        self.card, self.vmin, self.vmax, self.step = card, float(vmin), float(vmax), float(step)
        self.fmt, self.commit, self.key, self.gradient = fmt, commit, key, gradient
        self.wheel = wheel or step
        self.v, self.drag, self._wjob = None, False, None
        head = tk.Frame(self, bg=c["bg"])
        head.pack(fill="x")
        tk.Label(head, text=label, bg=c["bg"], fg=c["dim"], font=card.f_text).pack(side="left")
        self.lv = tk.Label(head, text="—", bg=c["bg"], fg=c["fg"], font=card.f_text_b)
        self.lv.pack(side="right")
        self.W, self.H = card.iw, card.s(26)
        self.cv = tk.Canvas(self, width=self.W, height=self.H, bg=c["bg"], highlightthickness=0, cursor="hand2")
        self.cv.pack()
        self.cv.bind("<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", lambda e: self._set(self._x2v(e.x)))
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<MouseWheel>", self._wheel)
        self._draw()

    def _x(self):
        pad = self.card.s(10)
        return pad, self.W - pad

    def _x2v(self, x):
        x0, x1 = self._x()
        f = max(0.0, min(1.0, (x - x0) / float(x1 - x0)))
        v = self.vmin + f * (self.vmax - self.vmin)
        v = round(v / self.step) * self.step
        return max(self.vmin, min(self.vmax, v))

    def _draw(self):
        c, s, cv = self.card.c, self.card.s, self.cv
        cv.delete("all")
        x0, x1 = self._x()
        yc = self.H / 2
        f = None if self.v is None else (self.v - self.vmin) / ((self.vmax - self.vmin) or 1)
        if self.gradient:
            n, th = 48, s(6)
            for i in range(n):
                xa = x0 + (x1 - x0) * i / n
                xb = x0 + (x1 - x0) * (i + 1) / n + 1
                cv.create_line(xa, yc, xb, yc, fill=gradient_at(self.gradient, (i + 0.5) / n), width=th)
            for x, col in ((x0, self.gradient[0]), (x1, self.gradient[-1])):
                cv.create_oval(x - th / 2, yc - th / 2, x + th / 2, yc + th / 2, fill=col, outline=col)
        else:
            th = s(4)
            cv.create_line(x0, yc, x1, yc, fill=c["track"], width=th, capstyle="round")
            if f is not None and f > 0:
                cv.create_line(x0, yc, x0 + (x1 - x0) * f, yc, fill=c["accent"], width=th, capstyle="round")
        xk = x0 + (x1 - x0) * (f or 0)
        R = s(9)
        cv.create_oval(xk - R, yc - R, xk + R, yc + R, fill=c["knob"], outline=c["border"])
        r = s(5) if f is not None else s(4)
        inner = c["dim"] if f is None else (gradient_at(self.gradient, f) if self.gradient else c["accent"])
        cv.create_oval(xk - r, yc - r, xk + r, yc + r, fill=inner, outline="")

    def _set(self, v):
        self.v = v
        self.lv.configure(text="—" if v is None else self.fmt(v))
        self._draw()

    def set(self, v):
        """Valeur venant de Home Assistant (ignoree pendant que l'utilisateur manipule le curseur)."""
        if self.drag or self.card.held(self.key) or v == self.v:
            return
        self._set(None if v is None else max(self.vmin, min(self.vmax, float(v))))

    def _press(self, e):
        self.drag = True
        self._set(self._x2v(e.x))

    def _release(self, _e):
        if not self.drag:
            return
        self.drag = False
        self.card.hold(self.key)
        self.commit(self.v)

    def _wheel(self, e):
        base = self.v if self.v is not None else self.vmin
        self._set(max(self.vmin, min(self.vmax, base + (self.wheel if e.delta > 0 else -self.wheel))))
        self.card.hold(self.key)
        if self._wjob:
            self.after_cancel(self._wjob)
        self._wjob = self.after(400, lambda: self.commit(self.v))


class Chips(tk.Frame):
    """Rangee de choix (modes, presets, sources...) sur plusieurs lignes si besoin."""

    def __init__(self, parent, card, options, command, key, on_right=None):
        c, s = card.c, card.s
        super().__init__(parent, bg=c["bg"])
        self.card, self.key, self.command, self.btns, self.sel = card, key, command, {}, None
        row, used = None, card.iw + 1
        for value, label in options:
            w = card.f_btn_m.measure(label) + s(24)
            if used + w > card.iw:
                row = tk.Frame(self, bg=c["bg"])
                row.pack(anchor="w", pady=(0, s(6)))
                used = 0
            b = Btn(row, card, label, command=lambda v=value: self._pick(v), width=w, height=s(28))
            b.pack(side="left", padx=(0, s(6)))
            if on_right is not None:
                b.bind("<Button-3>", lambda e, v=value: on_right(v))
            used += w + s(6)
            self.btns[value] = b

    def _pick(self, v):
        self.card.hold(self.key)
        self._select(v)
        self.command(v)

    def _select(self, v):
        self.sel = v
        for value, b in self.btns.items():
            b.set(primary=(value == v))

    def set(self, v):
        if not self.card.held(self.key) and v != self.sel:
            self._select(v)


class Swatches(tk.Canvas):
    def __init__(self, parent, card, colors, command):
        s = card.s
        self.card, self.colors, self.command = card, colors, command
        self.d = s(26)
        n = len(colors)
        self.gap = (card.iw - n * self.d) / max(1, n - 1)
        super().__init__(parent, width=card.iw, height=self.d + s(4), bg=card.c["bg"], highlightthickness=0,
                         cursor="hand2")
        for i, rgb in enumerate(colors):
            x = i * (self.d + self.gap)
            self.create_oval(x + 2, 2, x + self.d, self.d, fill=rgb_hex(rgb), outline=card.c["border"])
        self.bind("<ButtonRelease-1>", self._click)

    def _click(self, e):
        i = int(e.x // (self.d + self.gap))
        if 0 <= i < len(self.colors):
            self.command(self.colors[i])


class History(tk.Canvas):
    """Graphe 24 h : courbe pour une valeur numerique, frise colorée pour un etat (on/off...)."""

    def __init__(self, parent, card, unit=""):
        self.card, self.unit, self.hours = card, unit, 24
        self.W, self.H = card.iw, card.s(78)
        super().__init__(parent, width=self.W, height=self.H, bg=card.c["bg"], highlightthickness=0)
        self.series, self.segments = [], []
        self.message("Chargement de l'historique…")
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", self._leave)

    def message(self, text):
        self.delete("all")
        self.create_text(self.W / 2, self.H / 2, text=text, fill=self.card.c["dim"], font=self.card.f_small)

    @staticmethod
    def span_text(h):
        if h <= 48:
            return "%g h" % h
        return ("%g j" % round(h / 24.0, 1)).replace(".", ",")

    def _axis(self):
        c, f, y = self.card.c, self.card.f_small, self.H - 1
        self.create_text(0, y, text="−" + self.span_text(self.hours), fill=c["dim"], font=f, anchor="sw")
        self.create_text(self.W / 2, y, text="−" + self.span_text(self.hours / 2.0), fill=c["dim"], font=f,
                         anchor="s")
        self.create_text(self.W, y, text="maintenant", fill=c["dim"], font=f, anchor="se")

    def set_data(self, points, hours=24):
        """points = [(datetime UTC, valeur)]"""
        self.delete("all")
        self.hours = hours
        self.series, self.segments = [], []
        if not points:
            self.message("Pas d'historique sur " + self.span_text(hours))
            return
        self.now = datetime.datetime.now(datetime.timezone.utc)
        self.t0 = self.now - datetime.timedelta(hours=hours)
        nums = []
        for t, v in points:
            try:
                nums.append((t, float(v)))
            except (TypeError, ValueError):
                pass
        if nums and len(nums) >= 0.6 * len(points):
            self._line(nums)
        else:
            self._timeline(points)
        self._axis()

    def _tx(self, t):
        f = (t - self.t0).total_seconds() / (self.hours * 3600.0)
        return max(0.0, min(1.0, f)) * (self.W - 1)

    def _line(self, nums):
        c, s = self.card.c, self.card.s
        nums.sort(key=lambda p: p[0])
        nums.append((self.now, nums[-1][1]))
        # une valeur par colonne de pixels (moyenne) -> trace leger meme avec beaucoup de points
        cols = {}
        for t, v in nums:
            x = int(self._tx(t))
            cols.setdefault(x, []).append((t, v))
        pts = [(x, sum(v for _, v in g) / len(g), g[-1][0]) for x, g in sorted(cols.items())]
        vals = [v for _, v, _ in pts]
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-9:
            lo, hi = lo - 1, hi + 1
        top, bot = s(20), self.H - s(16)

        def ty(v):
            return bot - (v - lo) / (hi - lo) * (bot - top)
        xy = [(x, ty(v)) for x, v, _ in pts]
        if len(xy) == 1:
            xy.append((self.W - 1, xy[0][1]))
        poly = [xy[0][0], bot] + [k for p in xy for k in p] + [xy[-1][0], bot]
        self.create_polygon(poly, fill=mix(c["bg"], c["accent"], 0.22), outline="")
        self.create_line(*[k for p in xy for k in p], fill=c["accent"], width=s(2), joinstyle="round")
        u = (" " + self.unit) if self.unit else ""
        # moyenne ponderee par la duree de chaque valeur
        tot = wsum = 0.0
        for (ta, va), (tb, _vb) in zip(nums, nums[1:]):
            dt = (tb - max(ta, self.t0)).total_seconds()
            if dt > 0:
                tot += dt
                wsum += va * dt
        avg = wsum / tot if tot else sum(vals) / len(vals)
        self.create_text(0, 0, text="min %s  ·  moy. %s  ·  max %s%s" % (
            fnum(round(min(v for _, v in nums), 2)), fnum(round(avg, 2)), fnum(round(max(v for _, v in nums), 2)), u),
            fill=c["dim"], font=self.card.f_small, anchor="nw", tags="mm")
        self.series = [(x, ty(v), v, t) for x, v, t in pts]

    def _timeline(self, points):
        c, s = self.card.c, self.card.s
        points = sorted(points, key=lambda p: p[0])
        y0, y1 = s(18), self.H - s(20)
        for i, (t, v) in enumerate(points):
            t_end = points[i + 1][0] if i + 1 < len(points) else self.now
            xa, xb = self._tx(t), self._tx(t_end)
            if xb - xa < 0.5:
                continue
            if v in ACTIVE_STATES:
                col = c["accent"]
            elif v in ("unavailable", "unknown", None):
                col = mix(c["bg"], c["dim"], 0.35)
            else:
                col = c["surface_h"]
            self.create_rectangle(xa, y0, xb, y1, fill=col, outline="")
            self.segments.append((xa, xb, v, t, t_end))

    def _leave(self, _e=None):
        self.delete("hover")
        self.itemconfigure("mm", state="normal")

    def _motion(self, e):
        self.delete("hover")
        c, s, f = self.card.c, self.card.s, self.card.f_small
        if self.series:
            self.itemconfigure("mm", state="hidden")
            x, y, v, t = min(self.series, key=lambda p: abs(p[0] - e.x))
            self.create_line(x, s(18), x, self.H - s(16), fill=c["dim"], dash=(2, 2), tags="hover")
            r = s(3)
            self.create_oval(x - r, y - r, x + r, y + r, fill=c["accent"], outline=c["bg"], tags="hover")
            txt = "%s%s · %s" % (fnum(round(v, 2)), (" " + self.unit) if self.unit else "",
                                 t.astimezone().strftime("%H:%M" if self.hours <= 24 else "%d/%m %H:%M"))
        else:
            seg = next((p for p in self.segments if p[0] <= e.x <= p[1]), None)
            if seg is None:
                return
            tf = "%H:%M" if self.hours <= 24 else "%d/%m %H:%M"
            txt = "%s · %s → %s" % (STATE_TEXT.get(seg[2], seg[2]), seg[3].astimezone().strftime(tf),
                                    seg[4].astimezone().strftime(tf))
        tid = self.create_text(self.W, 0, text=txt, fill=c["fg"], font=f, anchor="ne", tags="hover")
        bb = self.bbox(tid)
        bg = self.create_rectangle(bb[0] - s(4), bb[1], bb[2], bb[3], fill=c["bg"], outline="", tags="hover")
        self.tag_lower(bg, tid)


# --------------------------------------------------------------------------- la carte
class Card:
    WIDTH = 296   # largeur utile a 96 dpi

    def __init__(self, app, item_cfg, cx, bottom, xmin, xmax):
        self.app, self.cfg = app, dict(item_cfg)
        self.item_ref = item_cfg          # l'element de la config (pour enregistrer le titre)
        self.eid = self.cfg.get("entity_id", "")
        self.domain = self.eid.split(".", 1)[0]
        self.root = app.root
        self.anchor = (cx, bottom, xmin, xmax)
        self.alive, self.holds, self.updaters = True, {}, []
        self.extra_updaters = []          # (entity_id, fonction) : membres du groupe, entites de l'appareil
        self.members = item_members(self.cfg)
        self.is_group = len(self.members) > 1
        self.hist_hours = 24
        self.q = queue.Queue()
        self.k = self.root.winfo_fpixels("1i") / 96.0
        self.iw = self.s(self.WIDTH)
        self._palette()
        self._fonts()

        win = self.win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.0)
        win.configure(bg=self.c["border"])
        self.body = tk.Frame(win, bg=self.c["bg"], padx=self.s(18), pady=self.s(16))
        self.body.pack(padx=1, pady=1, fill="both", expand=True)

        st = self.state()
        self._build(st)
        self.refresh()

        win.update_idletasks()
        self.hwnd = user32.GetAncestor(win.winfo_id(), GA_ROOT)
        ex = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
        try:   # coins arrondis Windows 11
            pref = ctypes.c_int(1 if self.radius <= 3 else 2)    # 1 = angles droits, 2 = arrondis
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(self.hwnd), 33, ctypes.byref(pref), 4)
        except Exception:
            pass
        self.size = None
        self._place()
        win.bind("<Escape>", lambda e: self.close())
        user32.SetForegroundWindow(self.hwnd)
        win.focus_force()
        self._was_fg = False
        self._mouse = self._mouse_down()
        self._fade(1)
        self._loop()
        if self.want_history:
            threading.Thread(target=self._fetch_history, args=(app.ha, 24), daemon=True).start()
        if not self.is_group and self.domain not in ("scene", "script", "automation", "person", "zone", "sun"):
            threading.Thread(target=self._fetch_device, args=(app.ha,), daemon=True).start()
        self._tick_1s()

    # ---------------- bases
    def s(self, v):
        return int(round(v * self.k))

    def _palette(self):
        light = card_light(self.app.cfg, getattr(self.app, "light", False))
        base, radius = card_palette(self.app.cfg, self.app.colors, light)
        self.c, self.radius = derive_palette(base), radius

    def _fonts(self):
        fam = self.app.cfg.get("font", "Segoe UI")
        fams = set(tkfont.families(self.root))
        semi = "Segoe UI Semibold" if fam == "Segoe UI" and "Segoe UI Semibold" in fams else None
        light = "Segoe UI Light" if fam == "Segoe UI" and "Segoe UI Light" in fams else fam
        self.f_title = (semi, 12) if semi else (fam, 12, "bold")
        self.f_text = (fam, 9)
        self.f_text_b = (semi, 9) if semi else (fam, 9, "bold")
        self.f_small = (fam, 8)
        self.f_btn = (fam, 9)
        self.f_big = (light, 30)
        self.f_btn_m = tkfont.Font(root=self.root, font=self.f_btn)
        self.ifont = self.app.icon_font or fam

    def state(self):
        return self.app.last_states.get(self.eid)

    def call(self, service, **data):
        data["entity_id"] = self.eid
        self.app.call_service(service, data)

    def hold(self, key, sec=3.0):
        """Apres une action, on ignore les valeurs venant de HA quelques secondes (pas de retour en arriere)."""
        self.holds[key] = time.monotonic() + sec

    def held(self, key):
        return self.holds.get(key, 0) > time.monotonic()

    def section(self, title=None, top=14):
        f = tk.Frame(self.body, bg=self.c["bg"])
        f.pack(fill="x", pady=(self.s(top), 0))
        if title:
            tk.Label(f, text=title, bg=self.c["bg"], fg=self.c["dim"], font=self.f_text).pack(anchor="w",
                                                                                             pady=(0, self.s(4)))
        return f

    # ---------------- construction
    def _build(self, st):
        c, s = self.c, self.s
        a = (st or {}).get("attributes", {})
        self.default_name = a.get("friendly_name") or self.cfg.get("label") or self.eid
        name = self.cfg.get("card_title") or self.default_name

        hdr = tk.Frame(self.body, bg=c["bg"])
        hdr.pack(fill="x")
        hdr.grid_columnconfigure(1, weight=1)
        self.h_icon = tk.Label(hdr, text="", bg=c["bg"], fg=c["fg"], font=(self.ifont, 20))
        self.h_icon.grid(row=0, column=0, rowspan=2, padx=(0, s(12)))
        # titre + crayon pour le renommer
        self.h_title = tk.Frame(hdr, bg=c["bg"])
        self.h_title.grid(row=0, column=1, sticky="w")
        self.h_name = tk.Label(self.h_title, text=name, bg=c["bg"], fg=c["fg"], font=self.f_title, anchor="w",
                               justify="left", wraplength=self.iw - s(140))
        self.h_name.pack(side="left")
        self.h_edit = tk.Label(self.h_title, text=G_EDIT, bg=c["bg"], fg=c["dim"], font=(self.ifont, 10),
                               cursor="hand2")
        self.h_edit.pack(side="left", padx=(s(8), 0))
        self.h_edit.bind("<Enter>", lambda e: self.h_edit.configure(fg=c["fg"]))
        self.h_edit.bind("<Leave>", lambda e: self.h_edit.configure(fg=c["dim"]))
        self.h_edit.bind("<Button-1>", lambda e: self.edit_title())
        self.h_name.bind("<Double-Button-1>", lambda e: self.edit_title())
        self.editing = None
        self.h_sub = tk.Label(hdr, text="", bg=c["bg"], fg=c["dim"], font=self.f_text, anchor="w")
        self.h_sub.grid(row=1, column=1, sticky="w")
        self.tog = None
        if self.is_group:
            self.tog = Toggle(hdr, self, lambda on: self.app.call_service(
                "homeassistant.turn_%s" % ("on" if on else "off"), {"entity_id": self.members}))
            self.tog.grid(row=0, column=2, rowspan=2, sticky="e")
        elif self.domain in TOGGLE_DOMAINS:
            self.tog = Toggle(hdr, self, lambda on: self.call("%s.turn_%s" % (self.domain, "on" if on else "off")))
            self.tog.grid(row=0, column=2, rowspan=2, sticky="e")

        if self.is_group:
            sec = self.section("Membres du groupe")
            for eid in self.members:
                self._entity_row(sec, eid)
        else:
            builder = getattr(self, "_b_" + self.domain, None)
            if builder is not None:
                builder(a)
            elif self.domain not in TOGGLE_DOMAINS:
                self._b_value(a)

        if self.domain in TIMER_DOMAINS or self.is_group:
            self._b_timer()
        # entites du meme appareil (remplie quand Home Assistant a repondu)
        self.dev_sec = tk.Frame(self.body, bg=c["bg"])
        self.dev_sec.pack(fill="x")

        self.want_history = self.domain not in ACTION_DOMAINS and not self.is_group
        if self.want_history:
            sec = self.section(top=16)
            hrow = tk.Frame(sec, bg=c["bg"])
            hrow.pack(fill="x", pady=(0, s(4)))
            tk.Label(hrow, text="Historique", bg=c["bg"], fg=c["dim"], font=self.f_text).pack(side="left")
            self.hist_btns = {}
            for h, t in reversed(HISTORY_PERIODS):
                lb = tk.Label(hrow, text=t, bg=c["bg"], fg=c["fg"] if h == 24 else c["dim"],
                              font=self.f_text_b if h == 24 else self.f_small, cursor="hand2")
                lb.pack(side="right", padx=(s(8), 0))
                lb.bind("<Button-1>", lambda e, h=h: self._set_period(h))
                self.hist_btns[h] = lb
            unit = self.cfg.get("unit") or ("°C" if self.domain == "climate" else a.get("unit_of_measurement", ""))
            self.chart = History(sec, self, unit)
            self.chart.pack()

        tk.Frame(self.body, bg=c["border"], height=1).pack(fill="x", pady=(s(14), s(10)))
        foot = tk.Frame(self.body, bg=c["bg"])
        foot.pack(fill="x")
        self.f_ago = tk.Label(foot, text="", bg=c["bg"], fg=c["dim"], font=self.f_small)
        self.f_ago.pack(side="left")
        link = tk.Label(foot, text="Ouvrir dans Home Assistant  ↗", bg=c["bg"], fg=c["dim"], font=self.f_small,
                        cursor="hand2")
        link.pack(side="right")
        link.bind("<Enter>", lambda e: link.configure(fg=c["fg"]))
        link.bind("<Leave>", lambda e: link.configure(fg=c["dim"]))
        link.bind("<Button-1>", lambda e: self._open_ha())

    # -- arret programme
    def _b_timer(self):
        sec = self.section("Arrêt programmé")
        eid = self.eid
        info = tk.Label(sec, text="", bg=self.c["bg"], fg=self.c["accent"], font=self.f_text_b, anchor="w")

        def pick(m):
            if m == 0:
                self.app.cancel_timer(eid)
            else:
                self.app.start_timer(eid, m)
            upd()
        ch = Chips(sec, self, TIMER_CHOICES + [(0, "Annuler")], pick, "timer")
        ch.pack(anchor="w")

        def upd(_st=None):
            left = self.app.timer_left(eid)
            if left is None:
                info.pack_forget()
                if ch.sel is not None:
                    ch._select(None)
            else:
                m = int(left // 60) + 1
                info.configure(text="S'éteint dans %s (à %s)" % (
                    "%d h %02d" % divmod(m, 60) if m >= 60 else "%d min" % m,
                    time.strftime("%H:%M", time.localtime(time.time() + left))))
                if not info.winfo_ismapped():
                    info.pack(anchor="w", pady=(self.s(2), 0))
        self.updaters.append(upd)
        self.timer_upd = upd

    # -- une ligne "nom + commande" (membres d'un groupe, entites du meme appareil)
    def short_name(self, eid, st):
        name = (st or {}).get("attributes", {}).get("friendly_name") or eid
        if self.is_group:
            return name
        base = self.default_name
        if base and name.lower().startswith(base.lower()) and len(name) > len(base) + 1:
            name = name[len(base):].strip(" -·:")
            name = name[:1].upper() + name[1:]
        elif base and name.lower() == base.lower():
            name = {"light": "Lumière", "fan": "Ventilateur", "switch": "Prise / interrupteur",
                    "sensor": "Capteur", "select": "Choix"}.get(eid.split(".", 1)[0], name)
        return name

    def _entity_row(self, parent, eid):
        c, s = self.c, self.s
        st = self.app.last_states.get(eid)
        if st is None:
            return False
        d = eid.split(".", 1)[0]
        a = st.get("attributes", {})
        call = self.app.call_service
        box = tk.Frame(parent, bg=c["bg"])
        box.pack(fill="x", pady=(0, s(6)))
        row = tk.Frame(box, bg=c["bg"])
        row.pack(fill="x")
        tk.Label(row, text=self.short_name(eid, st), bg=c["bg"], fg=c["fg"], font=self.f_text, anchor="w",
                 wraplength=self.iw - s(110), justify="left").pack(side="left")
        key = "row:" + eid
        if d in ("light", "switch", "fan", "input_boolean", "siren", "automation", "humidifier"):
            tg = Toggle(row, self, lambda on: call("%s.turn_%s" % (d, "on" if on else "off"), {"entity_id": eid}),
                        key=key)
            tg.pack(side="right")
            sl = None
            if d == "light" and ((set(a.get("supported_color_modes") or []) - {"onoff"}) or a.get("brightness")):
                sl = Slider(box, self, "Luminosité", 1, 100, 1, lambda v: "%d %%" % v,
                            lambda v: call("light.turn_on", {"entity_id": eid, "brightness_pct": int(v)}),
                            key + ":bri", wheel=5)
                sl.pack(fill="x")

            def upd(st, tg=tg, sl=sl):
                if not self.held(key):
                    tg.set(st.get("state") == "on")
                if sl is not None:
                    b = st.get("attributes", {}).get("brightness")
                    sl.set(round(b * 100 / 255) if st.get("state") == "on" and b else None)
        elif d == "select":
            opts = a.get("options") or []
            ch = Chips(box, self, [(o, SELECT_TEXT.get(o, o)) for o in opts],
                       lambda o: call("select.select_option", {"entity_id": eid, "option": o}), key)
            ch.pack(anchor="w", pady=(s(4), 0))

            def upd(st, ch=ch):
                ch.set(st.get("state"))
        elif d == "number":
            lo, hi = float(a.get("min", 0)), float(a.get("max", 100))
            step = float(a.get("step", 1))
            unit = a.get("unit_of_measurement", "")
            sl = Slider(box, self, "", lo, hi, step, lambda v: "%s%s" % (fnum(v), (" " + unit) if unit else ""),
                        lambda v: call("number.set_value", {"entity_id": eid, "value": v}), key, wheel=step)
            sl.pack(fill="x")

            def upd(st, sl=sl):
                try:
                    sl.set(float(st.get("state")))
                except (TypeError, ValueError):
                    sl.set(None)
        elif d == "button":
            Btn(row, self, "Appuyer", height=s(26), command=lambda: call("button.press", {"entity_id": eid})).pack(
                side="right")

            def upd(st):
                pass
        elif d in ("cover", "lock"):
            svc = {"cover": (("open_cover", "Ouvrir"), ("close_cover", "Fermer")),
                   "lock": (("lock", "Verrouiller"), ("unlock", "Ouvrir"))}[d]
            for sv, t in reversed(svc):
                Btn(row, self, t, height=s(26), command=lambda sv=sv: call("%s.%s" % (d, sv), {"entity_id": eid})
                    ).pack(side="right", padx=(s(4), 0))
            val = None

            def upd(st):
                pass
        else:   # capteurs : valeur a droite
            val = tk.Label(row, text="", bg=c["bg"], fg=c["fg"], font=self.f_text_b)
            val.pack(side="right")

            def upd(st, val=val):
                at = st.get("attributes", {})
                raw = st.get("state")
                try:
                    float(raw)
                    txt = fnum(raw)
                except (TypeError, ValueError):
                    txt = STATE_TEXT.get(raw, raw)
                u = at.get("unit_of_measurement", "")
                val.configure(text=("%s %s" % (txt, u)).strip())
        self.extra_updaters.append((eid, upd))
        try:
            upd(st)
        except Exception:
            pass
        return True

    def _fetch_device(self, ha):
        try:
            self.q.put(("device", ha.device_entities(self.eid)))
        except Exception:
            pass

    def _build_device(self, eids):
        states = self.app.last_states
        shown = [e for e in eids if e.split(".", 1)[0] in SIBLING_DOMAINS and e in states
                 and states[e].get("state") != "unavailable"][:MAX_SIBLINGS]
        # les minuteurs de l'appareil d'abord, puis lumieres, puis le reste
        order = {"select": 0, "light": 1}
        shown.sort(key=lambda e: order.get(e.split(".", 1)[0], 2))
        if not shown:
            return
        tk.Label(self.dev_sec, text="Sur le même appareil", bg=self.c["bg"], fg=self.c["dim"],
                 font=self.f_text).pack(anchor="w", pady=(self.s(14), self.s(4)))
        for e in shown:
            self._entity_row(self.dev_sec, e)

    # -- valeur en grand (capteurs, personnes, meteo...)
    def _b_value(self, a):
        sec = self.section(top=12)
        row = tk.Frame(sec, bg=self.c["bg"])
        row.pack(anchor="w")
        big = tk.Label(row, text="", bg=self.c["bg"], fg=self.c["fg"], font=self.f_big)
        big.pack(side="left")
        unit = tk.Label(row, text="", bg=self.c["bg"], fg=self.c["dim"], font=self.f_title)
        unit.pack(side="left", anchor="s", pady=(0, self.s(9)), padx=(self.s(4), 0))
        attr = self.cfg.get("attribute")

        def upd(st):
            at = st.get("attributes", {})
            raw = at.get(attr) if attr else st.get("state")
            u = self.cfg.get("unit") or ("" if attr else at.get("unit_of_measurement", ""))
            try:
                float(raw)
                txt = fnum(raw, self.cfg.get("decimals"))
            except (TypeError, ValueError):
                txt = STATE_TEXT.get(raw, raw)
                txt = txt[:1].upper() + txt[1:] if isinstance(txt, str) else str(txt)
            big.configure(text=txt)
            unit.configure(text=u)
        self.updaters.append(upd)

    # -- lumiere
    def _b_light(self, a):
        modes = set(a.get("supported_color_modes") or [])
        if (modes - {"onoff"}) or a.get("brightness") is not None:
            sec = self.section()
            bri = Slider(sec, self, "Luminosité", 1, 100, 1, lambda v: "%d %%" % v,
                         lambda v: self.call("light.turn_on", brightness_pct=int(v)), "bri", wheel=5)
            bri.pack(fill="x")

            def upd(st):
                b = st.get("attributes", {}).get("brightness")
                bri.set(round(b * 100 / 255) if st.get("state") == "on" and b else None)
            self.updaters.append(upd)
        if "color_temp" in modes:
            kmin = int(a.get("min_color_temp_kelvin") or 2000)
            kmax = int(a.get("max_color_temp_kelvin") or 6500)
            sec = self.section()
            ct = Slider(sec, self, "Température du blanc", kmin, kmax, 50, lambda v: "%d K" % v,
                        lambda v: self.call("light.turn_on", color_temp_kelvin=int(v)), "ct", wheel=250,
                        gradient=CT_GRADIENT)
            ct.pack(fill="x")

            def upd_ct(st):
                at = st.get("attributes", {})
                ct.set(at.get("color_temp_kelvin") if st.get("state") == "on" else None)
            self.updaters.append(upd_ct)
        if modes & COLOR_MODES:
            sec = self.section("Couleur")
            Swatches(sec, self, SWATCHES, lambda rgb: self.call("light.turn_on", rgb_color=list(rgb))).pack()
        if (modes - {"onoff"}) or a.get("brightness") is not None:
            self.fav_sec = self.section("Ambiances")
            self.fav_has_ct = "color_temp" in modes
            self.fav_has_rgb = bool(modes & COLOR_MODES)
            self._fill_favorites()

    def _fill_favorites(self):
        """Ambiances integrees + favoris memorises (clic droit sur un favori : le supprimer)."""
        sec = self.fav_sec
        for w in list(sec.winfo_children())[1:]:
            w.destroy()
        builtin = LIGHT_SCENES_CT if self.fav_has_ct else LIGHT_SCENES_DIM
        opts = [("b%d" % i, n) for i, (n, _b, _k) in enumerate(builtin)]
        favs = list(self.cfg.get("favorites") or [])
        opts += [("f%d" % i, "★ " + (f.get("name") or str(i + 1))) for i, f in enumerate(favs)]
        opts.append(("save", "+ Mémoriser"))

        def pick(v):
            if v == "save":
                self._save_favorite()
                return
            if v.startswith("b"):
                _n, bri, k = builtin[int(v[1:])]
                data = {"brightness_pct": bri}
                if k:
                    data["color_temp_kelvin"] = k
            else:
                f = favs[int(v[1:])]
                data = {k: f[k] for k in ("brightness_pct", "color_temp_kelvin", "rgb_color") if f.get(k) is not None}
            self.call("light.turn_on", **data)

        def right(v):
            if v.startswith("f"):
                i = int(v[1:])
                self.save_item(lambda it: it.__setitem__("favorites",
                                                         [f for j, f in enumerate(it.get("favorites") or []) if j != i]))
                self._fill_favorites()
        Chips(sec, self, opts, pick, "fav", on_right=right).pack(anchor="w")
        if favs:
            tk.Label(sec, text="Clic droit sur un ★ pour le supprimer.", bg=self.c["bg"], fg=self.c["dim"],
                     font=self.f_small).pack(anchor="w")

    def _save_favorite(self):
        st = self.state() or {}
        a = st.get("attributes", {})
        if st.get("state") != "on" or not a.get("brightness"):
            self.h_sub.configure(text="Allume la lumière avant de mémoriser")
            return
        fav = {"brightness_pct": max(1, round(a["brightness"] * 100 / 255))}
        if a.get("color_mode") == "color_temp" and a.get("color_temp_kelvin"):
            fav["color_temp_kelvin"] = int(a["color_temp_kelvin"])
        elif a.get("rgb_color") and a.get("color_mode") not in ("brightness", "onoff", "white"):
            fav["rgb_color"] = list(a["rgb_color"])
        n = len(self.cfg.get("favorites") or []) + 1
        fav["name"] = "%d %%" % fav["brightness_pct"] + (" · %d K" % fav["color_temp_kelvin"]
                                                        if "color_temp_kelvin" in fav else "")
        if n > 8:
            self.h_sub.configure(text="8 favoris au maximum")
            return
        self.save_item(lambda it: it.__setitem__("favorites", list(it.get("favorites") or []) + [dict(fav)]))
        self._fill_favorites()

    # -- thermostat
    def _b_climate(self, a):
        c, s = self.c, self.s
        unit = self.cfg.get("unit") if self.cfg.get("unit") in ("°C", "°F") else "°C"
        step = float(a.get("target_temp_step") or 0.5)
        tmin, tmax = float(a.get("min_temp") or 5), float(a.get("max_temp") or 35)
        self._pending, self._tjob = None, None
        if "temperature" in a:
            sec = self.section(top=16)
            row = tk.Frame(sec, bg=c["bg"])
            row.pack(fill="x")
            row.grid_columnconfigure(1, weight=1)
            mid = tk.Frame(row, bg=c["bg"])
            mid.grid(row=0, column=1)
            big = tk.Label(mid, text="—", bg=c["bg"], fg=c["fg"], font=self.f_big)
            big.pack()
            tk.Label(mid, text="Consigne", bg=c["bg"], fg=c["dim"], font=self.f_text).pack()

            def show(v):
                big.configure(text="—" if v is None else "%s %s" % (fnum(v, 1), unit))

            def send():
                self._tjob = None
                self.call("climate.set_temperature", temperature=self._pending)

            def bump(d):
                cur = self.state() or {}
                base = self._pending
                if base is None:
                    at = cur.get("attributes", {})
                    base = at.get("temperature") or at.get("current_temperature") or 20
                v = max(tmin, min(tmax, round((float(base) + d * step) / step) * step))
                self._pending = v
                show(v)
                self.hold("tgt", 4)
                if self._tjob:
                    self.root.after_cancel(self._tjob)
                self._tjob = self.root.after(700, send)

            Btn(row, self, glyph=G_MINUS, round_=True, height=s(40), command=lambda: bump(-1)).grid(row=0, column=0)
            Btn(row, self, glyph=G_PLUS, round_=True, height=s(40), command=lambda: bump(1)).grid(row=0, column=2)
            mid.bind("<MouseWheel>", lambda e: bump(1 if e.delta > 0 else -1))
            big.bind("<MouseWheel>", lambda e: bump(1 if e.delta > 0 else -1))

            def upd(st):
                if not self.held("tgt"):
                    self._pending = None
                    show(st.get("attributes", {}).get("temperature"))
            self.updaters.append(upd)
        info = tk.Label(self.section(top=10), text="", bg=c["bg"], fg=c["dim"], font=self.f_text, anchor="w")
        info.pack(anchor="w")

        def upd_info(st):
            at = st.get("attributes", {})
            parts = []
            if at.get("current_humidity") is not None:
                parts.append("Humidité %s %%" % fnum(at["current_humidity"], 0))
            w = self.outdoor()
            if w:
                parts.append("Extérieur %s" % w)
            info.configure(text="  ·  ".join(parts))
        self.updaters.append(upd_info)
        modes = a.get("hvac_modes") or []
        if modes:
            sec = self.section("Mode")
            ch = Chips(sec, self, [(m, HVAC_TEXT.get(m, m)) for m in modes],
                       lambda m: self.call("climate.set_hvac_mode", hvac_mode=m), "hvac")
            ch.pack(anchor="w")
            self.updaters.append(lambda st: ch.set(st.get("state")))
        presets = a.get("preset_modes") or []
        if presets:
            sec = self.section("Préréglage")
            pc = Chips(sec, self, [(p, PRESET_TEXT.get(p, p.capitalize())) for p in presets],
                       lambda p: self.call("climate.set_preset_mode", preset_mode=p), "preset")
            pc.pack(anchor="w")
            self.updaters.append(lambda st: pc.set(st.get("attributes", {}).get("preset_mode")))

    def outdoor(self):
        """Temperature exterieure : capteur choisi dans les reglages ("outdoor"), sinon la 1re meteo."""
        states = self.app.last_states
        eid = self.cfg.get("outdoor")
        if eid and eid in states:
            st = states[eid]
            u = st.get("attributes", {}).get("unit_of_measurement", "°C")
            try:
                return "%s %s" % (fnum(float(st.get("state")), 1), u)
            except (TypeError, ValueError):
                return None
        for e, st in states.items():
            if e.startswith("weather.") and st.get("attributes", {}).get("temperature") is not None:
                at = st["attributes"]
                return "%s %s" % (fnum(at["temperature"], 1), at.get("temperature_unit", "°C"))
        return None

    # -- volet
    def _b_cover(self, a):
        s = self.s
        sec = self.section()
        row = tk.Frame(sec, bg=self.c["bg"])
        row.pack(fill="x")
        w = (self.iw - 2 * s(8)) // 3
        for i, (g, t, svc) in enumerate(((G_UP, "Ouvrir", "open_cover"), (G_STOP, "Stop", "stop_cover"),
                                         (G_DOWN, "Fermer", "close_cover"))):
            Btn(row, self, t, glyph=g, width=w, command=lambda sv=svc: self.call("cover." + sv)).pack(
                side="left", padx=(0 if i == 0 else s(8), 0))
        if a.get("current_position") is not None:
            sec = self.section()
            pos = Slider(sec, self, "Position", 0, 100, 1, lambda v: "%d %%" % v,
                         lambda v: self.call("cover.set_cover_position", position=int(v)), "pos", wheel=10)
            pos.pack(fill="x")
            self.updaters.append(lambda st: pos.set(st.get("attributes", {}).get("current_position")))
            favs = self.cfg.get("cover_positions") or [25, 50, 75]
            pc = Chips(sec, self, [(int(v), "%d %%" % int(v)) for v in favs],
                       lambda v: self.call("cover.set_cover_position", position=v), "posfav")
            pc.pack(anchor="w", pady=(self.s(6), 0))
            self.updaters.append(lambda st: pc.set(st.get("attributes", {}).get("current_position")))
        if a.get("current_tilt_position") is not None:
            sec = self.section()
            tilt = Slider(sec, self, "Inclinaison", 0, 100, 1, lambda v: "%d %%" % v,
                          lambda v: self.call("cover.set_cover_tilt_position", tilt_position=int(v)), "tilt", wheel=10)
            tilt.pack(fill="x")
            self.updaters.append(lambda st: tilt.set(st.get("attributes", {}).get("current_tilt_position")))

    # -- ventilateur
    def _b_fan(self, a):
        step = float(a.get("percentage_step") or 1)
        n = int(round(100.0 / step)) if step > 0 else 0
        if "percentage" in a and 2 <= n <= 10:
            # peu de vitesses (souvent 3 a 6) : des boutons 1, 2, 3... plutot qu'un curseur
            sec = self.section("Vitesse")
            sc = Chips(sec, self, [(i, str(i)) for i in range(1, n + 1)],
                       lambda i: self.call("fan.set_percentage", percentage=min(100, int(round(i * step)))), "pct")
            sc.pack(anchor="w")
            self.updaters.append(lambda st: sc.set(int(round((st.get("attributes", {}).get("percentage") or 0) / step))
                                                   if st.get("state") == "on" else None))
        elif "percentage" in a:
            sec = self.section()
            sp = Slider(sec, self, "Vitesse", 0, 100, float(a.get("percentage_step") or 1), lambda v: "%d %%" % v,
                        lambda v: self.call("fan.set_percentage", percentage=int(round(v))), "pct", wheel=10)
            sp.pack(fill="x")
            self.updaters.append(lambda st: sp.set(st.get("attributes", {}).get("percentage")
                                                   if st.get("state") == "on" else None))
        presets = a.get("preset_modes") or []
        if presets:
            sec = self.section("Mode")
            pc = Chips(sec, self, [(p, PRESET_TEXT.get(p, p.capitalize())) for p in presets],
                       lambda p: self.call("fan.set_preset_mode", preset_mode=p), "preset")
            pc.pack(anchor="w")
            self.updaters.append(lambda st: pc.set(st.get("attributes", {}).get("preset_mode")))
        feats = int(a.get("supported_features") or 0)
        if feats & FAN_DIRECTION or "direction" in a:
            sec = self.section("Sens de rotation")
            dc = Chips(sec, self, FAN_DIRECTIONS,
                       lambda d: self.call("fan.set_direction", direction=d), "dir")
            dc.pack(anchor="w")
            self.updaters.append(lambda st: dc.set(st.get("attributes", {}).get("direction")))
        if feats & FAN_OSCILLATE or "oscillating" in a:
            sec = self.section("Oscillation")
            oc = Chips(sec, self, [(True, "Activée"), (False, "Désactivée")],
                       lambda o: self.call("fan.oscillate", oscillating=o), "osc")
            oc.pack(anchor="w")
            self.updaters.append(lambda st: oc.set(st.get("attributes", {}).get("oscillating")))

    # -- lecteur multimedia
    def _b_media_player(self, a):
        c, s = self.c, self.s
        sec = self.section(top=12)
        title = tk.Label(sec, text="", bg=c["bg"], fg=c["fg"], font=self.f_text_b, anchor="w",
                         wraplength=self.iw, justify="left")
        title.pack(anchor="w")
        artist = tk.Label(sec, text="", bg=c["bg"], fg=c["dim"], font=self.f_text, anchor="w")
        artist.pack(anchor="w")
        row = tk.Frame(sec, bg=c["bg"])
        row.pack(pady=(s(10), 0))
        Btn(row, self, glyph=G_PREV, round_=True, height=s(38),
            command=lambda: self.call("media_player.media_previous_track")).pack(side="left", padx=s(8))
        pp = Btn(row, self, glyph=G_PLAY, round_=True, height=s(46), primary=True, glyph_size=14,
                 command=lambda: self.call("media_player.media_play_pause"))
        pp.pack(side="left", padx=s(8))
        Btn(row, self, glyph=G_NEXT, round_=True, height=s(38),
            command=lambda: self.call("media_player.media_next_track")).pack(side="left", padx=s(8))
        mute = None
        if "is_volume_muted" in a:
            mute = Btn(row, self, glyph=G_VOLUME, round_=True, height=s(38),
                       command=lambda: self.call("media_player.volume_mute",
                                                 is_volume_muted=not (self.state() or {}).get(
                                                     "attributes", {}).get("is_volume_muted")))
            mute.pack(side="left", padx=s(8))
        # progression du morceau
        prog = tk.Canvas(sec, width=self.iw, height=s(22), bg=c["bg"], highlightthickness=0)
        self._media_prog = prog
        vol = None
        if "volume_level" in a:
            sec2 = self.section()
            vol = Slider(sec2, self, "Volume", 0, 100, 1, lambda v: "%d %%" % v,
                         lambda v: self.call("media_player.volume_set", volume_level=round(v / 100.0, 2)), "vol",
                         wheel=5)
            vol.pack(fill="x")
        sources = (a.get("source_list") or [])[:10]
        src = None
        if sources:
            sec3 = self.section("Source")
            src = Chips(sec3, self, [(x, x) for x in sources],
                        lambda x: self.call("media_player.select_source", source=x), "src")
            src.pack(anchor="w")

        def upd(st):
            at = st.get("attributes", {})
            title.configure(text=at.get("media_title") or "")
            artist.configure(text=at.get("media_artist") or at.get("app_name") or "")
            pp.set(glyph=G_PAUSE if st.get("state") == "playing" else G_PLAY)
            if mute is not None:
                mute.set(glyph=G_MUTE if at.get("is_volume_muted") else G_VOLUME,
                         primary=bool(at.get("is_volume_muted")))
            self._draw_progress(st)
            if vol is not None:
                v = at.get("volume_level")
                vol.set(None if v is None else round(v * 100))
            if src is not None:
                src.set(at.get("source"))
        self.updaters.append(upd)

    def _draw_progress(self, st):
        cv = getattr(self, "_media_prog", None)
        if cv is None:
            return
        at = st.get("attributes", {})
        dur, pos = at.get("media_duration"), at.get("media_position")
        if not dur or pos is None:
            if cv.winfo_ismapped():
                cv.pack_forget()
            return
        if not cv.winfo_ismapped():
            cv.pack(pady=(self.s(8), 0))
        if st.get("state") == "playing":
            t = parse_time(at.get("media_position_updated_at"))
            if t is not None:
                pos += (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
        pos = max(0, min(float(dur), float(pos)))
        c, s = self.c, self.s
        cv.delete("all")
        y = s(5)
        cv.create_line(0, y, self.iw, y, fill=c["track"], width=s(3), capstyle="round")
        cv.create_line(0, y, self.iw * pos / float(dur), y, fill=c["accent"], width=s(3), capstyle="round")

        def mmss(v):
            v = int(v)
            return "%d:%02d:%02d" % (v // 3600, v // 60 % 60, v % 60) if v >= 3600 else "%d:%02d" % (v // 60, v % 60)
        cv.create_text(0, s(20), text=mmss(pos), fill=c["dim"], font=self.f_small, anchor="sw")
        cv.create_text(self.iw, s(20), text=mmss(dur), fill=c["dim"], font=self.f_small, anchor="se")

    def _tick_1s(self):
        """Rafraichissements lents : progression du morceau, compte a rebours de l'arret programme."""
        if not self.alive:
            return
        st = self.state()
        if st:
            try:
                self._draw_progress(st)
            except tk.TclError:
                pass
        upd = getattr(self, "timer_upd", None)
        if upd is not None:
            upd()
        self.root.after(1000, self._tick_1s)

    # -- serrure
    def _b_lock(self, a):
        sec = self.section()
        b = Btn(sec, self, "Verrouiller", width=self.iw, height=self.s(36), primary=True)
        b.pack()

        def upd(st):
            locked = st.get("state") == "locked"
            b.set(text="Déverrouiller" if locked else "Verrouiller")
            b.command = lambda: self.call("lock.unlock" if locked else "lock.lock")
        self.updaters.append(upd)

    # -- aspirateur
    def _b_vacuum(self, a):
        s = self.s
        sec = self.section()
        row = tk.Frame(sec, bg=self.c["bg"])
        row.pack(fill="x")
        w = (self.iw - 3 * s(8) - s(32)) // 3
        for i, (t, svc) in enumerate((("Démarrer", "start"), ("Pause", "pause"), ("Base", "return_to_base"))):
            Btn(row, self, t, width=w, command=lambda sv=svc: self.call("vacuum." + sv)).pack(
                side="left", padx=(0 if i == 0 else s(8), 0))
        Btn(row, self, glyph=G_LOCATE, round_=True, height=s(32), command=lambda: self.call("vacuum.locate")).pack(
            side="left", padx=(s(8), 0))
        bat = None
        if a.get("battery_level") is not None:
            sec2 = self.section()
            head = tk.Frame(sec2, bg=self.c["bg"])
            head.pack(fill="x")
            tk.Label(head, text="Batterie", bg=self.c["bg"], fg=self.c["dim"], font=self.f_text).pack(side="left")
            bat_lv = tk.Label(head, text="", bg=self.c["bg"], fg=self.c["fg"], font=self.f_text_b)
            bat_lv.pack(side="right")
            bat_cv = tk.Canvas(sec2, width=self.iw, height=s(12), bg=self.c["bg"], highlightthickness=0)
            bat_cv.pack(pady=(s(4), 0))

            def draw_bat(v):
                c = self.c
                bat_cv.delete("all")
                y = s(6)
                bat_cv.create_line(s(4), y, self.iw - s(4), y, fill=c["track"], width=s(6), capstyle="round")
                if v:
                    col = c["accent"] if v > 20 else "#e5534b"
                    bat_cv.create_line(s(4), y, s(4) + (self.iw - s(8)) * min(100, v) / 100.0, y, fill=col,
                                       width=s(6), capstyle="round")
                bat_lv.configure(text="%d %%" % v if v is not None else "—")
            bat = draw_bat
        speeds = a.get("fan_speed_list") or []
        fs = None
        if speeds:
            sec3 = self.section("Puissance d'aspiration")
            fs = Chips(sec3, self, [(x, x.capitalize()) for x in speeds],
                       lambda x: self.call("vacuum.set_fan_speed", fan_speed=x), "fanspeed")
            fs.pack(anchor="w")

        def upd(st):
            at = st.get("attributes", {})
            if bat is not None:
                bat(at.get("battery_level"))
            if fs is not None:
                fs.set(at.get("fan_speed"))
        self.updaters.append(upd)

    # -- nombres / listes
    def _b_input_number(self, a, domain="input_number"):
        lo, hi = float(a.get("min", 0)), float(a.get("max", 100))
        step = float(a.get("step", 1))
        unit = a.get("unit_of_measurement", "")
        sec = self.section()
        sl = Slider(sec, self, "Valeur", lo, hi, step,
                    lambda v: "%s%s" % (fnum(v), (" " + unit) if unit else ""),
                    lambda v: self.call(domain + ".set_value", value=v), "num", wheel=step)
        sl.pack(fill="x")

        def upd(st):
            try:
                sl.set(float(st.get("state")))
            except (TypeError, ValueError):
                sl.set(None)
        self.updaters.append(upd)

    def _b_number(self, a):
        self._b_input_number(a, "number")

    def _b_input_select(self, a, domain="input_select"):
        opts = a.get("options") or []
        sec = self.section("Choix")
        ch = Chips(sec, self, [(o, o) for o in opts],
                   lambda o: self.call(domain + ".select_option", option=o), "opt")
        ch.pack(anchor="w")
        self.updaters.append(lambda st: ch.set(st.get("state")))

    def _b_select(self, a):
        self._b_input_select(a, "select")

    # -- actions (scene, script, bouton)
    def _action(self, text):
        svc = resolve_service(self.cfg)
        sec = self.section()
        Btn(sec, self, text, width=self.iw, height=self.s(36), primary=True,
            command=lambda: (self.app.call_service(svc, self.cfg.get("data") or {"entity_id": self.eid}),
                             self.close())).pack()

    def _b_scene(self, a):
        self._action("Activer la scène")

    def _b_script(self, a):
        self._action("Lancer le script")

    def _b_button(self, a):
        self._action("Appuyer")

    def _b_input_button(self, a):
        self._action("Appuyer")

    # ---------------- mise a jour
    def subtitle(self, st):
        s, a, d = st.get("state"), st.get("attributes", {}), self.domain
        if self.is_group:
            _g, on, total = group_state(self.cfg, self.app.last_states)
            return "Groupe · %d allumé%s sur %d" % (on, "s" if on > 1 else "", total)
        if s == "unavailable":
            return "Indisponible"
        if s == "unknown":
            return "État inconnu"
        if d == "light":
            if s != "on":
                return "Éteinte"
            b = a.get("brightness")
            return "Allumée · %d %%" % round(b * 100 / 255) if b else "Allumée"
        if d in ("switch", "input_boolean", "automation", "siren", "humidifier"):
            return "Allumé" if s == "on" else "Éteint"
        if d == "fan":
            p = a.get("percentage")
            txt = ("Allumé · %d %%" % p if p else "Allumé") if s == "on" else "Éteint"
            if s == "on" and a.get("direction"):
                txt += " · " + ("hiver" if a["direction"] == "reverse" else "été")
            return txt
        if d == "vacuum":
            txt = VACUUM_TEXT.get(s, STATE_TEXT.get(s, s))
            if a.get("battery_level") is not None:
                txt += " · batterie %d %%" % a["battery_level"]
            return txt
        if d in ("climate", "water_heater"):
            parts = [HVAC_ACTION.get(a.get("hvac_action"), HVAC_TEXT.get(s, s))]
            if a.get("current_temperature") is not None:
                parts.append("%s °C actuellement" % fnum(a["current_temperature"], 1))
            return " · ".join(parts)
        if d == "cover":
            p = a.get("current_position")
            t = COVER_TEXT.get(s, s)
            return "%s · %d %%" % (t, p) if p is not None else t
        if d == "media_player":
            return MEDIA_TEXT.get(s, s)
        if d == "lock":
            return LOCK_TEXT.get(s, s)
        if d == "scene":
            return "Scène · activée " + ago(s) if parse_time(s) else "Scène"
        if d == "script":
            return "En cours" if s == "on" else "Script"
        if d in ("button", "input_button"):
            return "Dernier appui " + ago(s) if parse_time(s) else "Bouton"
        if d in ("sensor", "binary_sensor", "weather", "sun", "person", "device_tracker"):
            return {"binary_sensor": "Détecteur", "weather": "Météo", "sun": "Soleil", "person": "Personne",
                    "device_tracker": "Localisation"}.get(d, "Capteur")
        return STATE_TEXT.get(s, s)

    def refresh(self):
        if not self.alive:
            return
        st = self.state()
        if st is None:
            self.h_sub.configure(text="Entité introuvable")
            return
        s, a = st.get("state"), st.get("attributes", {})
        active = s in ACTIVE_STATES and self.domain not in ("sensor",)
        icon_fg = self.c["accent"] if active else self.c["fg"]
        if self.domain == "light" and s == "on" and a.get("rgb_color") and a.get("color_mode") not in (
                "color_temp", "brightness", "onoff", "white"):
            icon_fg = rgb_hex(a["rgb_color"])
        self.h_icon.configure(text=resolve_icon(self.cfg, st) or "", fg=icon_fg)
        self.h_sub.configure(text=self.subtitle(st))
        if self.tog is not None and not self.held("toggle"):
            if self.is_group:
                self.tog.set(group_state(self.cfg, self.app.last_states)[1] > 0)
            else:
                self.tog.set(s == "on")
        for f in self.updaters:
            try:
                f(st)
            except Exception:
                pass
        for eid, f in self.extra_updaters:
            est = self.app.last_states.get(eid)
            if est is not None:
                try:
                    f(est)
                except Exception:
                    pass
        self.f_ago.configure(text="Modifié " + ago(st.get("last_changed")) if st.get("last_changed") else "")

    # ---------------- titre modifiable
    def edit_title(self):
        if self.editing is not None:
            return
        c, s = self.c, self.s
        self.h_name.pack_forget()
        self.h_edit.pack_forget()
        var = tk.StringVar(value=self.h_name.cget("text"))
        e = tk.Entry(self.h_title, textvariable=var, font=self.f_title, width=17, relief="flat",
                     bg=c["surface"], fg=c["fg"], insertbackground=c["fg"], selectbackground=c["accent"],
                     selectforeground=c["accent_fg"], highlightthickness=1, highlightbackground=c["border"],
                     highlightcolor=c["accent"])
        e.pack(side="left")
        ok = tk.Label(self.h_title, text=G_CHECK, bg=c["bg"], fg=c["accent"], font=(self.ifont, 11), cursor="hand2")
        ok.pack(side="left", padx=(s(6), 0))
        self.editing = (e, ok, var)
        e.bind("<Return>", lambda ev: self._end_edit(True))
        e.bind("<KP_Enter>", lambda ev: self._end_edit(True))
        e.bind("<Escape>", lambda ev: (self._end_edit(False), "break")[1])   # Echap annule sans fermer la carte
        ok.bind("<Button-1>", lambda ev: self._end_edit(True))
        user32.SetForegroundWindow(self.hwnd)
        e.focus_force()
        e.select_range(0, "end")
        e.icursor("end")

    def _end_edit(self, save):
        if self.editing is None:
            return
        e, ok, var = self.editing
        self.editing = None
        text = var.get().strip()
        if save:
            title = text if text and text != self.default_name else None
            self.save_title(title)
        try:
            e.destroy()
            ok.destroy()
            self.h_name.configure(text=self.cfg.get("card_title") or self.default_name)
            self.h_name.pack(side="left")
            self.h_edit.pack(side="left", padx=(self.s(8), 0))
        except tk.TclError:
            pass

    def save_title(self, title):
        """Enregistre le titre (None = nom de Home Assistant) dans l'element de la config, sur disque aussi."""
        def put(it):
            if title:
                it["card_title"] = title
            else:
                it.pop("card_title", None)
        self.save_item(put)

    def save_item(self, put):
        """Applique put(element) a l'element : copie de la carte, config en memoire, disque, reglages ouverts."""
        put(self.cfg)
        put(self.item_ref)
        idx = next((i for i, it in enumerate(self.app.cfg.get("items", [])) if it is self.item_ref), None)

        def find(items):
            if idx is not None and idx < len(items) and items[idx].get("entity_id") == self.eid:
                return items[idx]
            return next((it for it in items if it.get("entity_id") == self.eid), None)
        try:
            disk = load_config()
            target = find(disk.get("items", []))
            if target is not None:
                put(target)
                save_config(disk)
        except Exception:
            pass
        sw = getattr(self.app, "settings_win", None)     # reglages ouverts : on les tient a jour
        if sw is not None:
            try:
                for conf in (sw.cfg, sw.saved):
                    target = find(conf.get("items", []))
                    if target is not None:
                        put(target)
                if sw.cur is not None:
                    sw.load_item_fields()
            except Exception:
                pass

    # ---------------- historique
    def _fetch_history(self, ha, hours):
        attr = self.cfg.get("attribute") or ("current_temperature" if self.domain in ("climate", "water_heater")
                                              else None)
        try:
            rows = ha.history(self.eid, hours, attributes=bool(attr))
            pts = [(t, (at.get(attr) if attr else st)) for t, st, at in rows]
            self.q.put(("hist", (pts, hours)))
        except Exception as e:
            self.q.put(("hist_err", (str(e), hours)))

    def _set_period(self, h):
        if h == self.hist_hours:
            return
        self.hist_hours = h
        for k, lb in self.hist_btns.items():
            lb.configure(fg=self.c["fg"] if k == h else self.c["dim"], font=self.f_text_b if k == h else self.f_small)
        self.chart.message("Chargement de l'historique…")
        threading.Thread(target=self._fetch_history, args=(self.app.ha, h), daemon=True).start()

    # ---------------- fenetre
    def _place(self):
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        if (w, h) == self.size:
            return
        self.size = (w, h)
        cx, bottom, xmin, xmax = self.anchor
        x = max(xmin + self.s(8), min(xmax - self.s(8) - w, cx - w // 2))
        y = bottom - self.s(12) - h
        self.win.geometry("%dx%d" % (w, h))
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE)

    def _fade(self, step):
        if not self.alive:
            return
        a = min(1.0, step / 6.0)
        self.win.attributes("-alpha", a)
        if a < 1.0:
            self.root.after(15, lambda: self._fade(step + 1))

    @staticmethod
    def _mouse_down():
        return bool(user32.GetAsyncKeyState(0x01) & 0x8000 or user32.GetAsyncKeyState(0x02) & 0x8000)

    def _loop(self):
        if not self.alive:
            return
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "hist":
                    if data[1] == self.hist_hours:
                        self.chart.set_data(*data)
                elif kind == "device":
                    self._build_device(data)
                elif data[1] == self.hist_hours:
                    self.chart.message("Historique indisponible")
        except queue.Empty:
            pass
        self._place()
        # Fermeture : clic en dehors de la carte, ou une autre fenetre passe au premier plan
        fg = user32.GetForegroundWindow()
        if fg == self.hwnd:
            self._was_fg = True
        elif self._was_fg and fg:
            self.close()
            return
        down = self._mouse_down()
        if down and not self._mouse:
            x, y = self.root.winfo_pointerxy()
            wx, wy = self.win.winfo_rootx(), self.win.winfo_rooty()
            if not (wx <= x < wx + self.win.winfo_width() and wy <= y < wy + self.win.winfo_height()):
                self.close()
                return
        self._mouse = down
        self.root.after(50, self._loop)

    def _open_ha(self):
        url = (self.app.cfg.get("ha_url") or "").rstrip("/")
        if url:
            webbrowser.open("%s/history?entity_id=%s" % (url, urllib.parse.quote(self.eid)))
        self.close()

    def close(self):
        self.app.close_card()

    def destroy(self):
        if self.editing is not None:      # fermee pendant la saisie : on garde ce qui a ete tape
            self._end_edit(True)
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass
