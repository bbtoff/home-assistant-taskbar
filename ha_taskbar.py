"""
HA Taskbar - affiche des capteurs / boutons Home Assistant sur la barre des taches Windows 11.

Principe : une petite fenetre sans bordure, "toujours au premier plan", positionnee
sur une zone libre de la barre des taches (Windows 11 ne supporte plus les deskbands).

Aucune dependance externe : Python 3.8+ (tkinter + ctypes + urllib).
Lancement sans console :  pythonw ha_taskbar.py
Reglages : clic sur l'icone pres de l'horloge, ou clic droit sur la barre -> "Reglages..."
"""
import base64
import copy
import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk
import urllib.error
from ctypes import wintypes
from tkinter import font as tkfont

import anim_icons
import screens
from ha_core import (ACTIVE_STATES, ANIM_ICONS, BATTERIES, CONFIG_PATH, DEFAULT_CONFIG, ICON_FONTS, ICON_PATH, ICONS,
                     STATE_TEXT, WEATHER_TEXT, HomeAssistant, __version__, anim_active, bar_colors, bar_light,
                     battery_state, group_state, icon_key, in_quiet_hours, item_members, item_visible, system_light,
                     item_zone, latest_release, load_config, mix_color, needs_setup, parse_hotkey, parse_thresholds,
                     resolve_icon, resolve_service, save_config, threshold_color, update_available)

# --------------------------------------------------------------------------- Win32
# DPI : on travaille en pixels physiques pour coller exactement a la barre des taches
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.SetWindowPos.argtypes = [wintypes.HWND, ctypes.c_ssize_t, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]

WINEVENTPROC = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                  wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE, WINEVENTPROC,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]

HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_NOACTIVATE = 0x00000080, 0x00040000, 0x08000000
GA_ROOT = 2
MONITOR_DEFAULTTONEAREST = 2
ERROR_ALREADY_EXISTS = 183
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000


def tool_window(hwnd):
    """Pas de bouton dans la barre des taches, pas de vol du focus. A reappliquer apres certains
    reglages Tk (-transparentcolor remet le style etendu a zero)."""
    if hwnd:
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        want = (ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
        if want != ex:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, want)


def get_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def foreground_is_fullscreen(own_hwnds, taskbar=None):
    """True si l'app au premier plan est en plein ecran (jeu, video...) sur l'ecran de la barre."""
    fg = user32.GetForegroundWindow()
    if not fg or fg in own_hwnds:
        return False
    if class_name(fg) in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        return False
    r = get_rect(fg)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    hmon = user32.MonitorFromWindow(fg, MONITOR_DEFAULTTONEAREST)
    if taskbar and hmon != user32.MonitorFromWindow(taskbar, MONITOR_DEFAULTTONEAREST):
        return False      # plein ecran sur un autre ecran : la barre reste visible
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return False
    m = mi.rcMonitor
    return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom


LONG_PRESS_MS = 450      # appui long -> carte de controle
WHEEL_DELAY_MS = 350     # molette : on attend la fin des crans avant d'envoyer la commande
OFFLINE_AFTER = 2        # nombre d'echecs de suite avant de passer en "hors ligne"
RT_POLL_S = 60           # connexion temps reel active : simple verification complete chaque minute
PALETTE_HOTKEY_ID = 900  # identifiant du raccourci de la palette (les elements utilisent 1, 2, 3...)
AREAS_EVERY_S = 1800     # pieces de Home Assistant relues toutes les 30 min


UPDATE_FIRST_MS = 60 * 1000          # 1re recherche de mise a jour 1 min apres le lancement
UPDATE_EVERY_MS = 24 * 3600 * 1000   # puis une fois par jour


def anim_now():
    """Numero d'image courant des icones animees (commun a toute la barre)."""
    return int(time.monotonic() * 1000) // anim_icons.FRAME_MS


# --------------------------------------------------------------------------- UI
class Item:
    def __init__(self, app, parent, cfg):
        self.app = app
        self.cfg = cfg
        self.entity_id = cfg.get("entity_id", "")
        self.domain = self.entity_id.split(".", 1)[0]
        self.shown = None            # (icone, texte, couleur) actuellement affiches
        self.max_w = 0               # largeur max deja atteinte (la zone ne retrecit jamais)
        c = app.colors

        self.service = resolve_service(cfg)
        self.service_data = cfg.get("data") or {"entity_id": self.entity_id}
        self.members = item_members(cfg)
        self.is_group = len(self.members) > 1
        self.hold_until = 0.0        # molette : valeur en attente affichee, on ignore HA un instant
        self.rules = parse_thresholds(cfg.get("thresholds"))[0]    # couleurs selon la valeur
        self._flash_job = None

        cursor = "hand2"            # tout element ouvre au moins sa carte (appui long)
        fs = int(app.cfg.get("font_size", 9))
        font = app.cfg.get("font", "Segoe UI")
        stacked = app.cfg.get("layout", "stacked") == "stacked"
        label = cfg.get("label") or self.entity_id

        self.frame = tk.Frame(parent, bg=c["bg"], cursor=cursor, padx=6 if app.cfg.get("compact") else 8)
        self.frame.grid_rowconfigure(0, weight=1)      # contenu centre verticalement dans le rectangle
        self.zone = item_zone(cfg)
        self.icon = None
        self.anim_frames = None      # images de l'icone animee en cours (None = icone de police)
        self.anim_idx = -1
        if app.cfg.get("show_icons", True) and cfg.get("icon") != "none" and app.icon_font:
            ifont = tkfont.Font(self.frame, family=app.icon_font, size=fs + (7 if stacked else 3))
            self.icon_px = max(12, ifont.measure(ICONS["flame"][0]))   # taille des icones animees
            self.icon = tk.Label(self.frame, text="", bg=c["bg"], fg=c["fg"], cursor=cursor, font=ifont)
            self.icon.grid(row=0, column=0, padx=(0, 0 if app.cfg.get("compact") else 6))
        # petit badge (minuterie, sens de rotation, pourcentage...) en bas a droite de l'icone
        self.badge = tk.Label(self.frame, text="", bg=c["bg"], fg=c["on"], cursor=cursor,
                              font=(font, max(fs - 3, 6), "bold"), padx=0, pady=0, borderwidth=0)
        self.badge_text = ""
        self.txt = tk.Frame(self.frame, bg=c["bg"], cursor=cursor)
        # Barre compacte : icone seule (la valeur est dans l'infobulle) ; sans icone, on garde le texte
        self.compact = bool(app.cfg.get("compact")) and self.icon is not None
        if not self.compact:
            self.txt.grid(row=0, column=1, sticky="w")

        if stacked:
            self.title = tk.Label(self.txt, text=label, bg=c["bg"], fg=c["dim"],
                                  font=(font, max(fs - 1, 6)), cursor=cursor)
            self.value = tk.Label(self.txt, text="…", bg=c["bg"], fg=c["fg"],
                                  font=(font, fs + 1, "bold"), cursor=cursor)
            self.title.pack(anchor="w")
            self.value.pack(anchor="w")
        else:
            self.title = tk.Label(self.txt, text=label, bg=c["bg"], fg=c["dim"],
                                  font=(font, fs), cursor=cursor)
            self.value = tk.Label(self.txt, text="…", bg=c["bg"], fg=c["fg"],
                                  font=(font, fs, "bold"), cursor=cursor)
            self.title.pack(side="left")
            self.value.pack(side="left", padx=(4, 0))
        self.widgets = [w for w in (self.frame, self.icon, self.badge, self.txt, self.title, self.value)
                        if w is not None]

        for w in self.widgets:
            w.bind("<ButtonPress-1>", self.on_press)
            w.bind("<Control-ButtonPress-1>", lambda e: app.drag_start(self))
            w.bind("<B1-Motion>", app.drag_motion)
            w.bind("<ButtonRelease-1>", app.release)
            w.bind("<MouseWheel>", self.on_wheel)
            w.bind("<Button-2>", self.on_middle)
            w.bind("<Button-3>", lambda e: app.show_menu(e, self))
        self.grow()

    def grow(self):
        """Fige la largeur de la zone texte sur la plus grande valeur vue -> pas de redimensionnement."""
        if self.compact:
            return
        w = self.txt.winfo_reqwidth()
        if w > self.max_w:
            self.max_w = w
            self.frame.grid_columnconfigure(1, minsize=w)

    def set_bg(self, color):
        for w in self.widgets:
            w.configure(bg=color)

    def hoverable(self):
        return True

    def set_hover(self, on):
        self.set_bg(self.app.colors["hover" if on else "bg"])

    def contains_x(self, x_root):
        fx = self.frame.winfo_rootx()
        return fx <= x_root < fx + self.frame.winfo_width()

    def on_press(self, _e=None):
        self.app.press(self)

    def on_click(self, _e=None):
        """Appui court : action de l'element, ou sa carte s'il n'a pas d'action (capteur...)."""
        if not self.app.click_item(self.cfg):
            self.app.open_card(self)

    def on_middle(self, _e=None):
        self.app.middle_click(self)
        return "break"

    def on_wheel(self, e):
        self.app.wheel(self, 1 if e.delta > 0 else -1)

    def show_pending(self, text):
        """Valeur choisie a la molette, affichee tout de suite (avant la reponse de HA)."""
        self.hold_until = time.monotonic() + 2.0
        self.shown = None
        self.value.configure(text=text, fg=self.app.colors["on"])
        self.grow()

    def set_badge(self, text):
        text = text or ""
        if text == self.badge_text:
            return
        self.badge_text = text
        if not text:
            self.badge.place_forget()
            return
        self.badge.configure(text=text)
        if self.icon is not None:
            self.badge.place(in_=self.icon, relx=1.0, rely=1.0, x=4, y=2, anchor="se")
        else:
            self.badge.place(in_=self.txt, relx=1.0, rely=0.0, anchor="ne")
        self.badge.lift()

    def badge_for(self, st):
        """Texte du badge : minuterie en cours en priorite, sinon le badge choisi dans les reglages."""
        left = self.app.timer_left(self.entity_id)
        if left is not None:
            return "⏲%d" % max(1, round(left / 60.0))
        mode = self.cfg.get("badge") or ""
        if not mode or not st or st.get("state") in ("unavailable", "unknown"):
            return ""
        a = st.get("attributes", {})
        if mode == "direction":
            return {"forward": "↻", "reverse": "↺"}.get(a.get("direction"), "")
        if mode == "percentage":
            p = a.get("percentage")
            if p is None and a.get("brightness"):
                p = round(a["brightness"] * 100 / 255)
            return "%d" % p if p is not None and st.get("state") == "on" else ""
        if mode == "battery":
            b = a.get("battery_level", a.get("battery"))
            return "%s%%" % b if b is not None else ""
        v = a.get(mode)
        return "" if v is None else str(v)[:6]

    def refresh_from(self, states):
        if time.monotonic() < self.hold_until:
            return
        self.update(states.get(self.entity_id), states)

    def update(self, st, states=None):
        c = self.app.colors
        if self.entity_id == BATTERIES:          # resume des piles faibles
            st = battery_state(states if states is not None else self.app.last_states,
                               self.app.cfg.get("battery_low", 20))
            n = len(st["attributes"]["low"])
            fg = c["dim"] if self.app.offline else (c["error"] if n else c["fg"])
            self.set_badge("")
            self.show(resolve_icon(self.cfg, st), "%d" % n if n else "OK", fg, fg)
            return
        key = icon_key(self.cfg, st)
        anim = key if key in ANIM_ICONS else None
        self.set_badge(self.badge_for(st))
        if self.is_group and states is not None and not self.cfg.get("attribute"):
            gstate, on, total = group_state(self.cfg, states)
            if gstate is not None:
                fake = dict(st or {"entity_id": self.entity_id, "attributes": {}})
                fake["state"] = gstate
                fg = c["dim"] if gstate == "unavailable" or self.app.offline else (c["on"] if on else c["fg"])
                self.show(resolve_icon(self.cfg, fake), "%d/%d" % (on, total), fg, fg,
                          anim and (anim, bool(on) and not self.app.offline))
                return
        if st is None:
            self.show(resolve_icon(self.cfg, None), "?", c["error"], c["dim"], anim and (anim, False))
            return
        attrs = st.get("attributes", {})
        attr = self.cfg.get("attribute")
        raw = attrs.get(attr) if attr else st.get("state")
        unit = self.cfg.get("unit") or ("" if attr else attrs.get("unit_of_measurement", ""))

        text = str(raw)
        if self.cfg.get("decimals") is not None:
            try:
                text = "%.*f" % (int(self.cfg["decimals"]), float(raw))
            except (TypeError, ValueError):
                pass
        elif not attr:
            text = WEATHER_TEXT.get(text, text) if self.domain == "weather" else STATE_TEXT.get(text, text)

        if self.domain == "light" and st.get("state") == "on" and attrs.get("brightness") and not attr:
            text = "%d%%" % round(attrs["brightness"] * 100 / 255)
        if self.domain == "fan" and st.get("state") == "on" and attrs.get("percentage") and not attr:
            text = "%d%%" % attrs["percentage"]

        # Scenes / boutons : l'etat est la date du dernier declenchement -> on affiche l'action
        if not attr and st.get("state") not in ("unavailable", "unknown"):
            if self.domain == "scene":
                text = "Activer"
            elif self.domain in ("button", "input_button"):
                text = "Appuyer"
            elif self.domain == "script":
                text = "en cours" if st.get("state") == "on" else "Lancer"

        if unit:
            text = "%s %s" % (text, unit)

        state = st.get("state")
        active = state in ACTIVE_STATES and self.domain not in ("sensor",)
        if state in ("unavailable", "unknown") or self.app.offline:
            fg = icon_fg = c["dim"]
        elif active:
            fg = c["fg"] if attr else c["on"]
            icon_fg = c["on"]
        else:
            fg = icon_fg = c["fg"]
        if self.rules and state not in ("unavailable", "unknown") and not self.app.offline:
            col = threshold_color(self.rules, raw)
            if col:
                fg = icon_fg = col
        self.show(resolve_icon(self.cfg, st), text, fg, icon_fg,
                  anim and (anim, anim_active(self.cfg, st) and not self.app.offline))

    def show(self, glyph, text, fg, icon_fg, anim=None):
        new = (glyph, text, fg, icon_fg, anim)
        if new == self.shown:          # rien n'a change : on ne touche a rien (evite le scintillement)
            return
        old = self.shown
        self.shown = new
        if self._flash_job is not None:
            self.app.root.after_cancel(self._flash_job)
            self._flash_job = None
        self.value.configure(text=text, fg=fg)
        if self.icon is not None:
            if anim:
                key, on = anim
                self.anim_frames = self.app.anim_images(key, self.icon_px, on, icon_fg)
                self.anim_idx = -1
                self.icon.configure(text="")
                self.anim_tick(anim_now())
            else:
                self.anim_frames = None
                self.icon.configure(image="", text=glyph or "", fg=icon_fg)
        self.grow()
        if old is not None and old[1] != text and self.app.cfg.get("flash_changes", True) and not self.app.offline:
            self.flash(icon_fg if self.compact else fg)

    def flash(self, fg):
        """La valeur qui vient de changer brille un instant puis reprend sa couleur."""
        w = self.icon if self.compact else self.value
        if w is None or (self.compact and self.anim_frames is not None):
            return
        c = self.app.colors
        start = c["fg"] if str(fg).lower() == str(c["on"]).lower() else c["on"]
        steps = 14

        def step(i):
            self._flash_job = None
            try:
                w.configure(fg=mix_color(start, fg, (i / float(steps)) ** 1.5))
            except tk.TclError:
                return
            if i < steps:
                self._flash_job = self.app.root.after(90, lambda: step(i + 1))
        step(0)

    def anim_tick(self, n):
        fr = self.anim_frames
        if fr:
            i = n % len(fr)
            if i != self.anim_idx:
                self.anim_idx = i
                self.icon.configure(image=fr[i])


class Zone:
    """Une zone de la barre (gauche ou droite) : une fenetre sans bordure, toujours au premier plan,
    plus une fenetre "attrape-clics" en mode fond transparent."""

    def __init__(self, app, side, win):
        self.app = app
        self.side = side
        self.win = win
        self.hit = None
        self.hit_hwnd = None
        self.container = None
        self.items = []
        self.wanted = False      # la zone a quelque chose a afficher
        self.shown = True
        self.geom = None
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry("1x1+-32000+-32000")
        win.update_idletasks()
        self.hwnd = user32.GetAncestor(win.winfo_id(), GA_ROOT)
        tool_window(self.hwnd)
        win.deiconify()
        win.update_idletasks()
        win.bind("<Button-3>", app.show_menu)

    def style(self, cfg, colors):
        self.win.configure(bg=colors["bg"])
        try:
            self.win.attributes("-transparentcolor", colors["bg"] if cfg.get("transparent_bg") else "")
        except tk.TclError:
            pass
        self.setup_hit(bool(cfg.get("transparent_bg")))
        try:
            self.win.attributes("-alpha", max(0.2, min(1.0, float(cfg.get("opacity", 1.0)))))
        except (tk.TclError, ValueError):
            pass
        tool_window(self.hwnd)
        if self.container is not None:
            self.container.destroy()
        self.container = tk.Frame(self.win, bg=colors["bg"])
        # Remplit toute la fenetre (hauteur de la barre des taches) : chaque bouton est un rectangle plein
        self.container.pack(fill="both", expand=True)
        self.container.bind("<Button-3>", self.app.show_menu)
        self.items = []
        self.geom = None

    # ---------------- mode transparent : fenetre attrape-clics
    def setup_hit(self, enabled):
        """En mode transparent, Windows laisse passer les clics sur les pixels transparents.
        Une 2e fenetre quasi invisible (opacite ~1 %) placee juste dessous les recupere."""
        if not enabled:
            if self.hit is not None:
                self.hit.destroy()
                self.hit = self.hit_hwnd = None
            return
        if self.hit is not None:
            return
        app = self.app
        self.hit = tk.Toplevel(app.root)
        self.hit.overrideredirect(True)
        self.hit.configure(bg="black")
        self.hit.attributes("-topmost", True)
        self.hit.attributes("-alpha", 0.01)   # non nul -> Windows lui envoie bien les clics
        self.hit.update_idletasks()
        self.hit_hwnd = user32.GetAncestor(self.hit.winfo_id(), GA_ROOT)
        tool_window(self.hit_hwnd)
        self.hit.bind("<ButtonPress-1>", lambda e: app._hit_dispatch(e, "on_press"))
        self.hit.bind("<Control-ButtonPress-1>", lambda e: app._hit_drag(e))
        self.hit.bind("<B1-Motion>", app.drag_motion)
        self.hit.bind("<ButtonRelease-1>", app.release)
        self.hit.bind("<MouseWheel>", lambda e: app._hit_dispatch(e, "on_wheel"))
        self.hit.bind("<Button-2>", lambda e: app._hit_dispatch(e, "on_middle"))
        self.hit.bind("<Button-3>", lambda e: app.show_menu(e, app.item_at(e.x_root, e.y_root)))
        if not self.shown:
            self.hit.withdraw()
        self.geom = None          # force le placement au prochain tick

    def hwnds(self):
        return [h for h in (self.hwnd, self.hit_hwnd) if h]

    def show(self, on):
        if on == self.shown:
            return
        for w in (self.win, self.hit):
            if w is not None:
                w.deiconify() if on else w.withdraw()
        if on:
            for h in self.hwnds():
                tool_window(h)
        self.shown = on
        self.geom = None

    def contains(self, x, y):
        w = self.win
        rx, ry = w.winfo_rootx(), w.winfo_rooty()
        return self.shown and rx <= x < rx + w.winfo_width() and ry <= y < ry + w.winfo_height()

    def place(self, r, offset):
        h = r.bottom - r.top
        w = max(1, self.container.winfo_reqwidth())
        x = r.right - offset - w if self.side == "right" else r.left + offset
        geom = "%dx%d+%d+%d" % (w, h, x, r.top)
        if geom != self.geom:
            # Position appliquee via Win32 : Tk ignore parfois "wm geometry" quand plusieurs fenetres
            # sans bordure existent (zones + attrape-clics)
            for tkwin, hwnd in ((self.hit, self.hit_hwnd), (self.win, self.hwnd)):
                if tkwin is not None and hwnd:
                    tkwin.geometry("%dx%d" % (w, h))
                    user32.SetWindowPos(hwnd, HWND_TOPMOST, x, r.top, w, h, SWP_NOACTIVATE)
            self.geom = geom

    def raise_now(self):
        if self.shown:
            flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            if self.hit_hwnd:   # l'attrape-clics d'abord, la zone ensuite -> la zone reste au-dessus
                user32.SetWindowPos(self.hit_hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)


class App:
    def __init__(self):
        self.q = queue.Queue()
        self.wake = threading.Event()
        self.last_error = None
        self.last_states = {}
        self.hidden = False
        self.menu_open = False   # menu clic droit affiche : les zones ne se remettent pas devant
        self.settings_win = None
        self.hovered = None
        self.card = None         # carte de controle ouverte (appui long)
        self.anim_photos = {}    # images Tk des icones animees, par (icone, taille, etat, couleurs)
        self.update_info = None  # nouvelle version trouvee sur GitHub
        self.update_win = None
        self._update_report = None
        self._press_item = None
        self._press_job = None
        self.offline = False     # Home Assistant ne repond plus (valeurs grisees)
        self.fail_count = 0
        self.last_ok = None      # heure (time.time) de la derniere reponse de HA
        self.prev_states = None  # etats precedents (notifications sur changement)
        self.timers = {}         # arret programme : entity_id -> heure de fin (time.time)
        self.hotkey_map = {}     # id du raccourci -> config de l'element
        self.hotkey_errors = []
        self._wheel = {}         # molette : entity_id -> [valeur en attente, job after]
        self._vis_sig = None
        self.tray = None
        self.rt = None           # connexion temps reel (ha_ws.Realtime)
        self._rt_key = None
        self.rt_connected = False
        self.rt_detail = ""
        self.areas = {}          # entity_id -> piece (Home Assistant)
        self._areas_at = 0.0
        self._areas_busy = False
        self.palette = None      # palette de commandes ouverte
        self.drag = None         # Ctrl + glisser : element en cours de deplacement
        self._marker = None
        self._card_job = None
        self.notify_paused_until = 0.0

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("HA Taskbar")
        try:
            self.root.iconbitmap(default=ICON_PATH)   # icone de toutes les fenetres (reglages...)
        except tk.TclError:
            pass
        families = set(tkfont.families(self.root))
        self.icon_font = next((f for f in ICON_FONTS if f in families), None)

        self.items = []
        from tooltip_ui import Tooltip
        self.tip = Tooltip(self)
        # Deux zones : la fenetre principale a gauche, une 2e fenetre a droite. Les fenetres sont
        # affichees (hors ecran) avant d'y mettre quoi que ce soit : creer une Toplevel avant
        # l'affichage de la fenetre principale bloque le positionnement (bizarrerie Tk).
        left = Zone(self, "left", self.root)
        self.zones = [left, Zone(self, "right", tk.Toplevel(self.root))]
        self.main_zone = left
        try:
            cfg = load_config()
        except Exception as e:
            cfg = copy.deepcopy(DEFAULT_CONFIG)
            self.last_error = "config.json illisible : %s" % e
        self.apply_config(cfg)

        # Des qu'une fenetre (dont la barre des taches) passe au premier plan, on se remet au-dessus
        self._hook_cb = WINEVENTPROC(lambda *a: self.raise_now())
        self._hook = user32.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None,
                                            self._hook_cb, 0, 0, WINEVENT_OUTOFCONTEXT)

        # Icone dans la zone de notification : clic gauche -> reglages, clic droit -> menu
        try:
            import tray
            self.tray = tray.TrayIcon(ICON_PATH, "HA Taskbar " + __version__, self.open_settings,
                                      lambda x, y: self.popup_menu(x, y, from_tray=True), self.on_hotkey)
        except Exception:
            self.tray = None
        self.register_hotkeys()
        self.root.bind("<Destroy>", self._on_destroy, add="+")

        threading.Thread(target=self.poll_loop, daemon=True).start()
        self.tick()
        self.hover_loop()
        self.anim_loop()
        self.root.after(UPDATE_FIRST_MS, self.update_loop)
        if needs_setup(self.cfg) or not os.path.exists(CONFIG_PATH):
            self.root.after(300, self.open_settings)

    def _on_destroy(self, e):
        if e.widget is self.root and self.tray is not None:
            self.tray.remove()
            self.tray = None

    def quit(self):
        if self.rt is not None:
            self.rt.stop()
            self.rt = None
        if self.tray is not None:
            self.tray.remove()
            self.tray = None
        self.root.destroy()

    # ---------------- config
    def apply_config(self, cfg):
        """Applique une config (depuis le fichier ou en previsualisation depuis les reglages)."""
        self.cfg = cfg
        self.sys_light = system_light()
        self.light = bar_light(cfg)
        self.colors = bar_colors(cfg, self.light)
        self.ha = HomeAssistant(cfg["ha_url"], cfg["token"], cfg.get("verify_ssl", True))
        self.start_realtime()
        self.tip.hide()
        self.drag = None
        self._marker = None

        zones = {z.side: z for z in self.zones}
        for z in self.zones:
            z.style(cfg, self.colors)
        self.items = []
        self._vis_sig = self.visibility_sig(cfg)
        for it_cfg in cfg.get("items", []):
            if not item_visible(it_cfg):          # hors de sa plage horaire d'affichage
                continue
            z = zones[item_zone(it_cfg)]
            it = Item(self, z.container, it_cfg)
            it.frame.pack(side="left", fill="y")
            z.items.append(it)
            self.items.append(it)
        # Zone principale (message d'erreur "● HA", invite si la barre est vide) : la gauche si elle sert
        self.main_zone = zones["left"] if zones["left"].items or not self.items else zones["right"]
        for z in self.zones:
            z.wanted = bool(z.items) or z is self.main_zone

        font = (cfg.get("font", "Segoe UI"), int(cfg.get("font_size", 9)), "bold")
        self.status = tk.Label(self.main_zone.container, text="● HA", bg=self.colors["bg"],
                               fg=self.colors["error"], font=font)
        self.status.bind("<Button-3>", self.show_menu)
        self.status.bind("<Button-1>", lambda e: self.open_settings())

        if not self.items:
            hint = tk.Label(self.main_zone.container, text="HA Taskbar · clic droit → Réglages", bg=self.colors["bg"],
                            fg=self.colors["dim"], font=(cfg.get("font", "Segoe UI"), int(cfg.get("font_size", 9))))
            hint.pack(side="left", padx=8)
            hint.bind("<Button-3>", self.show_menu)
            hint.bind("<Button-1>", lambda e: self.open_settings())
        if self.last_states:
            for it in self.items:
                it.refresh_from(self.last_states)
        if self.last_error:
            self._show_status()
        self.hovered = None
        self.register_hotkeys()
        self.wake.set()

    def start_realtime(self):
        """(Re)lance la connexion temps reel si l'adresse, le jeton ou les options ont change."""
        cfg = self.cfg
        key = (cfg.get("ha_url"), cfg.get("token"), cfg.get("verify_ssl", True), bool(cfg.get("realtime", True)),
               bool(cfg.get("ha_notifications", True)))
        if key == self._rt_key:
            return
        self._rt_key = key
        if self.rt is not None:
            self.rt.stop()
            self.rt = None
        self.rt_connected, self.rt_detail = False, ""
        if key[3] and not needs_setup(cfg):
            from ha_ws import Realtime
            self.rt = Realtime(key[0], key[1], key[2], self.q, key[4])

    def state_for(self, item):
        if item.entity_id == BATTERIES:
            return battery_state(self.last_states, self.cfg.get("battery_low", 20))
        return self.last_states.get(item.entity_id)

    def on_state(self, eid, new):
        """Changement d'etat recu en temps reel."""
        if not self.last_states:
            return                     # pas encore d'etat complet : la lecture complete arrive
        old = self.last_states.get(eid)
        if new is None:
            self.last_states.pop(eid, None)
        else:
            self.last_states[eid] = new
        if old and new and not self.offline:
            self.check_notifications({eid: old}, {eid: new})
        battery = bool(new and new.get("attributes", {}).get("device_class") == "battery")
        for it in self.items:
            if eid in it.members or (battery and it.entity_id == BATTERIES):
                try:
                    it.refresh_from(self.last_states)
                except tk.TclError:
                    pass
        card = self.card
        if card is not None and self._card_job is None and (
                eid == card.eid or eid in card.members or any(e == eid for e, _f in card.extra_updaters)
                or (battery and card.eid == BATTERIES)):
            self._card_job = self.root.after(120, self._card_refresh)

    def _card_refresh(self):
        self._card_job = None
        if self.card is not None:
            self.card.refresh()

    def load_areas(self):
        """Pieces de Home Assistant (palette, choix des entites), lues dans un thread."""
        if self._areas_busy:
            return
        self._areas_busy = True
        self._areas_at = time.time()
        ha = self.ha

        def run():
            try:
                self.q.put(("areas", ha.areas()))
            except Exception:
                self.q.put(("areas", None))
        threading.Thread(target=run, daemon=True).start()

    # ---------------- modification de la liste des elements depuis la barre
    def item_index(self, item):
        return next((i for i, c in enumerate(self.cfg.get("items", [])) if c is item.cfg), None)

    def edit_items(self, fn, select=None):
        """fn(liste des elements) la modifie en place. Reglages ouverts : on modifie leur copie (apercu
        en direct, a enregistrer) ; sinon la config est enregistree tout de suite."""
        sw = self.settings_win
        if sw is not None and sw.win.winfo_exists():
            fn(sw.cfg["items"])
            sw.cur = None
            sw.refresh_tree()
            if select is not None:
                sw.select_item(select)
            else:
                sw.load_item_fields()
            sw.changed()
            return
        cfg = copy.deepcopy(self.cfg)
        fn(cfg["items"])
        try:
            save_config(cfg)
        except OSError as e:
            self.last_error = "config : %s" % e
        self.apply_config(cfg)

    def set_hidden(self, i, hidden):
        def fn(items):
            if 0 <= i < len(items):
                if hidden:
                    items[i]["hidden"] = True
                else:
                    items[i].pop("hidden", None)
        self.edit_items(fn)

    # ---------------- Ctrl + glisser : reordonner, changer de zone
    def drag_start(self, item):
        if item not in self.items:
            return "break"
        self._cancel_press()
        self.tip.hide()
        self.drag = {"item": item}
        for w in item.widgets:
            try:
                w.configure(cursor="fleur")
            except tk.TclError:
                pass
        item.set_bg(self.colors["hover"])
        return "break"

    def _hit_drag(self, e):
        it = self.item_at(e.x_root, e.y_root)
        if it is not None:
            self.drag_start(it)
        return "break"

    def drag_target(self):
        x, y = self.root.winfo_pointerxy()
        zone = next((z for z in self.zones if z.shown and z.contains(x, y)), None)
        if zone is None:
            tb = self.taskbar()
            if not tb:
                return None
            r = get_rect(tb)
            if not (r.top - 60 <= y <= r.bottom + 20 and r.left <= x <= r.right):
                return None            # relache loin de la barre : annule
            side = "left" if x < (r.left + r.right) / 2 else "right"
            zone = next(z for z in self.zones if z.side == side)
        idx = len(zone.items)
        for i, it in enumerate(zone.items):
            if x < it.frame.winfo_rootx() + it.frame.winfo_width() / 2:
                idx = i
                break
        return zone, idx

    def drag_motion(self, _e=None):
        if self.drag is None:
            return
        t = self.drag_target()
        m = self._marker
        if t is None or not t[0].shown or not t[0].items:
            if m is not None:
                m.place_forget()
            return
        zone, idx = t
        if m is None or m.master is not zone.container:
            if m is not None:
                m.destroy()
            m = self._marker = tk.Frame(zone.container, bg=self.colors["on"], width=3)
        x = zone.items[idx].frame.winfo_x() if idx < len(zone.items) else zone.container.winfo_width() - 3
        m.place(x=max(0, x - 1), y=0, relheight=1.0, width=3)
        m.lift()

    def drag_end(self):
        d, self.drag = self.drag, None
        if self._marker is not None:
            self._marker.destroy()
            self._marker = None
        item = d["item"]
        if item not in self.items:
            return
        for w in item.widgets:
            try:
                w.configure(cursor="hand2")
            except tk.TclError:
                pass
        item.set_hover(item is self.hovered)
        t = self.drag_target()
        src = self.item_index(item)
        if t is None or src is None:
            return
        zone, idx = t
        if zone.side == item.zone and item in zone.items and idx in (zone.items.index(item),
                                                                      zone.items.index(item) + 1):
            return                      # relache a sa place
        before = self.item_index(zone.items[idx]) if idx < len(zone.items) else None
        last = self.item_index(zone.items[-1]) if zone.items else None
        side = zone.side

        def fn(items):
            if not 0 <= src < len(items):
                return
            if before is not None:
                pos = before
            elif last is not None:
                pos = last + 1
            else:
                pos = len(items)
            moved = items.pop(src)
            if pos > src:
                pos -= 1
            items.insert(pos, moved)
            if side == "right":
                moved["zone"] = "right"
            else:
                moved.pop("zone", None)
        self.edit_items(fn)

    @staticmethod
    def visibility_sig(cfg):
        return tuple(item_visible(it) for it in cfg.get("items", []))

    # ---------------- actions
    def click_item(self, item_cfg):
        """Action du clic (ou du raccourci clavier). False si l'element n'a pas d'action."""
        members = item_members(item_cfg)
        if len(members) > 1 and not item_cfg.get("service") and not item_cfg.get("data"):
            # groupe : tout eteint si au moins un membre est allume, sinon tout allume
            _g, on, _n = group_state(item_cfg, self.last_states)
            self.call_service("homeassistant.turn_%s" % ("off" if on else "on"), {"entity_id": members})
            return True
        svc = resolve_service(item_cfg)
        if not svc:
            return False
        data = item_cfg.get("data") or {"entity_id": members if len(members) > 1 else item_cfg.get("entity_id", "")}
        self.call_service(svc, data)
        return True

    def middle_click(self, item):
        """Clic du milieu : action choisie dans les reglages (par defaut : ouvrir la carte)."""
        act = item.cfg.get("middle") or "@card"
        eid = item.entity_id
        a = (self.last_states.get(eid) or {}).get("attributes", {})
        if act == "@card":
            self.open_card(item)
        elif act == "@direction":
            self.call_service("fan.set_direction", {"entity_id": eid, "direction":
                                                    "forward" if a.get("direction") == "reverse" else "reverse"})
        elif act == "@preset":
            modes = a.get("preset_modes") or []
            if modes:
                cur = a.get("preset_mode")
                nxt = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else modes[0]
                self.call_service(item.domain + ".set_preset_mode", {"entity_id": eid, "preset_mode": nxt})
        elif act.startswith("@timer"):
            try:
                minutes = int(act[6:] or 30)
            except ValueError:
                minutes = 30
            if self.timer_left(eid) is not None:
                self.cancel_timer(eid)
            else:
                self.start_timer(eid, minutes)
        elif act == "@mute":
            self.call_service("media_player.volume_mute",
                              {"entity_id": eid, "is_volume_muted": not a.get("is_volume_muted")})
        elif act != "none":
            self.call_service(act, {"entity_id": item.members if item.is_group else eid})

    def wheel(self, item, d):
        """Molette sur un element : luminosite, vitesse, volume, position, consigne, valeur..."""
        eid, dom = item.entity_id, item.domain
        st = self.last_states.get(eid)
        if not st or st.get("state") in ("unavailable", "unknown"):
            return
        a = st.get("attributes", {})
        pend = self._wheel.get(eid)
        on = st.get("state") == "on"

        def num(v, default=None):
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        if dom == "light":
            if a.get("brightness") is None and not (set(a.get("supported_color_modes") or []) - {"onoff"}):
                return
            base = pend[0] if pend else ((num(a.get("brightness"), 0) * 100 / 255.0) if on else 0)
            v = max(0, min(100, round(base / 5.0) * 5 + 10 * d))
            if pend is None and not on and d < 0:
                return
            fmt = "%d%%" % v if v > 0 else "OFF"

            def send(v):
                if v <= 0:
                    self.call_service("light.turn_off", {"entity_id": eid})
                else:
                    self.call_service("light.turn_on", {"entity_id": eid, "brightness_pct": int(v)})
        elif dom == "fan":
            if "percentage" not in a:
                return
            step = num(a.get("percentage_step"), 10) or 10
            if step < 5:
                step = 10
            base = pend[0] if pend else (num(a.get("percentage"), 0) if on else 0)
            v = max(0, min(100, round((base + step * d) / step) * step))
            if pend is None and not on and d < 0:
                return
            fmt = "%d%%" % round(v) if v > 0 else "OFF"

            def send(v):
                if v <= 0:
                    self.call_service("fan.turn_off", {"entity_id": eid})
                else:
                    self.call_service("fan.set_percentage", {"entity_id": eid, "percentage": int(round(v))})
        elif dom == "media_player":
            if "volume_level" not in a:
                return
            base = pend[0] if pend else num(a.get("volume_level"), 0) * 100
            v = max(0, min(100, round(base / 5.0) * 5 + 5 * d))
            fmt = "%d%%" % v

            def send(v):
                self.call_service("media_player.volume_set", {"entity_id": eid, "volume_level": round(v / 100.0, 2)})
        elif dom == "cover":
            if a.get("current_position") is None:
                return
            base = pend[0] if pend else num(a.get("current_position"), 0)
            v = max(0, min(100, round(base / 10.0) * 10 + 10 * d))
            fmt = "%d%%" % v

            def send(v):
                self.call_service("cover.set_cover_position", {"entity_id": eid, "position": int(v)})
        elif dom in ("climate", "water_heater"):
            if a.get("temperature") is None:
                return
            step = num(a.get("target_temp_step"), 0.5) or 0.5
            lo, hi = num(a.get("min_temp"), 5), num(a.get("max_temp"), 35)
            base = pend[0] if pend else num(a.get("temperature"), 20)
            v = max(lo, min(hi, round((base + step * d) / step) * step))
            fmt = "→ %g°" % v

            def send(v):
                self.call_service(dom + ".set_temperature", {"entity_id": eid, "temperature": v})
        elif dom in ("input_number", "number"):
            step = num(a.get("step"), 1) or 1
            lo, hi = num(a.get("min"), 0), num(a.get("max"), 100)
            base = pend[0] if pend else num(st.get("state"), lo)
            v = max(lo, min(hi, round((base + step * d) / step) * step))
            fmt = "%g" % v

            def send(v):
                self.call_service(dom + ".set_value", {"entity_id": eid, "value": v})
        else:
            return
        if pend and pend[1] is not None:
            self.root.after_cancel(pend[1])

        def fire():
            p_ = self._wheel.pop(eid, None)
            if p_ is not None:
                send(p_[0])
        self._wheel[eid] = [v, self.root.after(WHEEL_DELAY_MS, fire)]
        item.show_pending(fmt)

    # ---------------- arret programme (minuterie locale)
    def start_timer(self, eid, minutes):
        self.timers[eid] = time.time() + minutes * 60
        self.refresh_badges()

    def cancel_timer(self, eid):
        self.timers.pop(eid, None)
        self.refresh_badges()

    def timer_left(self, eid):
        end = self.timers.get(eid)
        return None if end is None else max(0.0, end - time.time())

    def check_timers(self):
        now = time.time()
        for eid, end in list(self.timers.items()):
            if now >= end:
                del self.timers[eid]
                members = next((item_members(it) for it in self.cfg.get("items", [])
                                if it.get("entity_id") == eid and it.get("group")), [eid])
                if len(members) > 1:
                    self.call_service("homeassistant.turn_off", {"entity_id": members})
                else:
                    self.call_service("%s.turn_off" % eid.split(".", 1)[0], {"entity_id": eid})
                self.notify("Arrêt programmé", "%s : éteint." % self.friendly(eid))
        self.refresh_badges()

    def refresh_badges(self):
        for it in self.items:
            try:
                it.set_badge(it.badge_for(self.last_states.get(it.entity_id)))
            except tk.TclError:
                pass

    # ---------------- raccourcis clavier globaux
    def register_hotkeys(self):
        if self.tray is None:
            return
        self.tray.clear_hotkeys()
        self.hotkey_map, self.hotkey_errors = {}, []
        for i, it in enumerate(self.cfg.get("items", [])):
            hk = parse_hotkey(it.get("hotkey"))
            if not hk:
                continue
            hid = i + 1
            if self.tray.register_hotkey(hid, *hk):
                self.hotkey_map[hid] = it
            else:
                self.hotkey_errors.append(it.get("hotkey"))
        hk = parse_hotkey(self.cfg.get("palette_hotkey"))
        if hk and not self.tray.register_hotkey(PALETTE_HOTKEY_ID, *hk):
            self.hotkey_errors.append("%s (palette de commandes)" % self.cfg.get("palette_hotkey"))

    def on_hotkey(self, hid):
        if hid == PALETTE_HOTKEY_ID:
            self.open_palette()
            return
        it = self.hotkey_map.get(hid)
        if it is None:
            return
        if not self.click_item(it):
            item = next((x for x in self.items if x.cfg is it), None)
            if item is not None:
                self.open_card(item)

    def open_palette(self):
        if self.palette is not None and self.palette.alive:
            self.palette.close()          # 2e appui sur le raccourci : referme
            return
        from palette import Palette
        self.close_card()
        self.tip.hide()
        self.palette = Palette(self)

    # ---------------- notifications Windows
    def friendly(self, eid):
        st = self.last_states.get(eid) or {}
        return st.get("attributes", {}).get("friendly_name") or eid

    def notify(self, title, text, warning=False, force=False):
        """force : meme pendant une pause ou la plage sans notification (bouton Tester)."""
        if not force and (time.time() < self.notify_paused_until or in_quiet_hours(self.cfg)):
            return
        if self.tray is not None:
            try:
                self.tray.notify(title, text, warning)
            except Exception:
                pass

    def pause_notifications(self, seconds=None, until=None):
        self.notify_paused_until = until if until is not None else time.time() + seconds

    def check_notifications(self, old, new):
        for rule in self.cfg.get("notifications", []) or []:
            eid = rule.get("entity_id")
            if not eid or rule.get("enabled") is False:
                continue
            a, b = old.get(eid), new.get(eid)
            if not a or not b:
                continue
            sa, sb = a.get("state"), b.get("state")
            if sa == sb or sb in ("unavailable", "unknown") or sa in ("unavailable", "unknown"):
                continue
            want = (rule.get("to") or "").strip()
            if want and want not in (sb, STATE_TEXT.get(sb)):
                continue
            at = b.get("attributes", {})
            name = at.get("friendly_name") or eid
            state = ("%s %s" % (STATE_TEXT.get(sb, sb), at.get("unit_of_measurement", ""))).strip()
            text = (rule.get("message") or "").strip() or "{name} : {state}"
            try:
                text = text.format(name=name, state=state, old=STATE_TEXT.get(sa, sa))
            except (KeyError, IndexError, ValueError):
                pass
            self.notify("Home Assistant", text)

    def item_at(self, x_root, y_root=None):
        for z in self.zones:
            if y_root is not None and not z.contains(x_root, y_root):
                continue
            for it in z.items:
                if it.contains_x(x_root):
                    return it
        return None

    def _hit_dispatch(self, e, method):
        it = self.item_at(e.x_root, e.y_root)
        if it is not None:
            getattr(it, method)(e)
        elif method == "on_press" and (not self.items or self.status.winfo_ismapped()):
            self.open_settings()

    # ---------------- appui court / appui long
    def press(self, item):
        self.tip.hide()
        self._cancel_press()
        self._press_item = item
        self._press_job = self.root.after(LONG_PRESS_MS, self._long_press)

    def release(self, _e=None):
        if self.drag is not None:
            self.drag_end()
            return
        item = self._press_item
        if self._press_job is not None:       # relache avant le delai : appui court
            self._cancel_press()
            if item is not None and item in self.items:
                item.on_click()

    def _cancel_press(self):
        if self._press_job is not None:
            self.root.after_cancel(self._press_job)
        self._press_job = None
        self._press_item = None

    def _long_press(self):
        item = self._press_item
        self._press_job = None
        self._press_item = None
        if item is not None and item in self.items:
            self.open_card(item)

    # ---------------- carte de controle
    def anchor_for(self, item=None):
        """(centre x, haut de la barre des taches, bords gauche et droit de l'ecran) pour placer une fenetre
        au-dessus d'un element (ou au milieu de l'ecran)."""
        tb = self.taskbar()
        if not tb:
            return None
        r = get_rect(tb)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(user32.MonitorFromWindow(tb, MONITOR_DEFAULTTONEAREST), ctypes.byref(mi))
        work = mi.rcMonitor
        if item is not None:
            cx = item.frame.winfo_rootx() + item.frame.winfo_width() // 2
        else:
            cx = (work.left + work.right) // 2
        return cx, r.top, work.left, work.right

    def monitor_rect(self):
        """(gauche, haut, largeur, hauteur) de l'ecran de la barre."""
        tb = self.taskbar()
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if tb and user32.GetMonitorInfoW(user32.MonitorFromWindow(tb, MONITOR_DEFAULTTONEAREST), ctypes.byref(mi)):
            m = mi.rcMonitor
            return m.left, m.top, m.right - m.left, m.bottom - m.top
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def open_card(self, item):
        """Carte de controle d'un element de la barre, ou d'une config d'element (palette)."""
        from card_ui import Card
        self.close_card()
        self.tip.hide()
        is_item = isinstance(item, Item)
        a = self.anchor_for(item if is_item else None)
        if a is None:
            return
        cx, top, left, right = a
        self.card = Card(self, item.cfg if is_item else item, cx, top, left, right)

    def close_card(self):
        if self.card is not None:
            card, self.card = self.card, None
            card.destroy()

    def hover_loop(self):
        """Survol suivi par la position de la souris (fonctionne aussi sur les zones transparentes)."""
        try:
            x, y = self.root.winfo_pointerxy()
            it = self.item_at(x, y) if not self.hidden else None
            if it is not None and not it.hoverable():
                it = None
            if it is not self.hovered:
                if self.hovered is not None and self.hovered in self.items:
                    self.hovered.set_hover(False)
                if it is not None:
                    it.set_hover(True)
                self.hovered = it
                if self.drag is None and not self.menu_open:
                    self.tip.schedule(it)
        except tk.TclError:
            pass
        self.root.after(50, self.hover_loop)

    # ---------------- icones animees
    def anim_images(self, key, size, on, fg):
        """Images Tk d'une icone animee ; une seule (immobile) si eteinte ou animations desactivees."""
        moving = on and bool(self.cfg.get("anim_icons", True))
        ck = (key, size, on, moving, self.colors["on"], fg)
        if ck not in self.anim_photos:
            pngs = anim_icons.frames_png(key, size, on, self.colors["on"], fg)
            if not moving:
                pngs = pngs[:1]
            self.anim_photos[ck] = [tk.PhotoImage(master=self.root, data=base64.b64encode(p), format="png")
                                    for p in pngs]
        return self.anim_photos[ck]

    def anim_loop(self):
        if not self.hidden:
            n = anim_now()
            for it in self.items:
                if it.anim_frames is not None and len(it.anim_frames) > 1:
                    try:
                        it.anim_tick(n)
                    except tk.TclError:
                        pass
        self.root.after(anim_icons.FRAME_MS, self.anim_loop)

    # ---------------- mises a jour (GitHub)
    def update_loop(self):
        if self.cfg.get("check_updates", True):
            self.check_update()
        self.root.after(UPDATE_EVERY_MS, self.update_loop)

    def check_update(self, manual=False, report=None):
        """Interroge GitHub dans un thread. manual : demande explicite (on montre toujours le resultat).
        report(texte) : ou afficher le resultat (sinon une petite fenetre)."""
        self._update_report = report

        def run():
            try:
                self.q.put(("update", (latest_release(), manual)))
            except Exception as e:
                self.q.put(("update_error", (str(e), manual)))
        threading.Thread(target=run, daemon=True).start()

    def _report(self, text):
        if self._update_report:
            self._update_report(text)
        else:
            from tkinter import messagebox
            messagebox.showinfo("HA Taskbar", text)

    def on_update_msg(self, kind, payload):
        w = self.update_win
        if kind == "update":
            info, manual = payload
            if update_available(info):
                self.update_info = info
                if manual or info["version"] != self.cfg.get("skip_version"):
                    self.show_update()
                if manual:
                    self._report("Version %s disponible." % info["version"])
            elif manual:
                self._report("Tu as la dernière version (%s)." % __version__)
        elif kind == "update_error":
            msg, manual = payload
            if manual:
                self._report("Impossible de joindre GitHub : %s" % msg)
        elif w is not None:
            if kind == "update_progress":
                w.on_progress(*payload)
            elif kind == "update_ready":
                w.on_ready(payload)
            elif kind == "update_failed":
                w.on_failed(payload)

    def show_update(self):
        if not self.update_info:
            return
        if self.update_win is not None and self.update_win.win.winfo_exists():
            self.update_win.win.deiconify()
            self.update_win.win.lift()
            return
        from update_ui import UpdateWindow
        self.update_win = UpdateWindow(self, self.update_info)

    # ---------------- reseau (thread)
    def poll_loop(self):
        while True:
            ha = self.ha
            try:
                self.q.put(("states", ha.states()))
            except urllib.error.HTTPError as e:
                self.q.put(("error", "HTTP %s %s" % (e.code, "(jeton invalide ?)" if e.code == 401 else e.reason)))
            except Exception as e:
                self.q.put(("error", str(e)))
            try:
                interval = max(1.0, float(self.cfg.get("poll_interval", 5)))
            except (TypeError, ValueError):
                interval = 5.0
            if self.rt_connected:          # temps reel : les changements arrivent tout seuls
                interval = max(interval, RT_POLL_S)
            self.wake.wait(interval)
            self.wake.clear()

    def call_service(self, service, data):
        ha = self.ha

        def run():
            try:
                ha.call_service(service, data)
            except Exception as e:
                self.q.put(("error", "%s : %s" % (service, e)))
            time.sleep(0.4)
            self.wake.set()
        threading.Thread(target=run, daemon=True).start()

    # ---------------- boucle UI
    def set_tray_tip(self):
        if self.tray is not None:
            tip = "HA Taskbar %s" % __version__
            if self.offline:
                tip += " — Home Assistant hors ligne"
            elif self.rt_connected:
                tip += " — temps réel"
            self.tray.set_tip(tip)

    def _show_status(self):
        self.status.configure(text="● HA hors ligne" if self.offline else "● HA")
        if not self.status.winfo_ismapped():
            others = [w for w in self.main_zone.container.winfo_children() if w is not self.status]
            if others:
                self.status.pack(side="left", padx=6, before=others[0])
            else:
                self.status.pack(side="left", padx=6)

    def tick(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "rt_state":
                    self.on_state(*payload)
                    continue
                if kind == "states":
                    # un etat recu en temps reel pendant la lecture complete est plus recent : on le garde
                    for eid, cur in self.last_states.items():
                        new = payload.get(eid)
                        if new is not None and (cur.get("last_updated") or "") > (new.get("last_updated") or ""):
                            payload[eid] = cur
                    self.last_error = None
                    was_offline = self.offline
                    self.offline, self.fail_count, self.last_ok = False, 0, time.time()
                    if self.prev_states:
                        self.check_notifications(self.prev_states, payload)
                    self.prev_states = payload
                    self.last_states = payload
                    if self.status.winfo_ismapped():
                        self.status.pack_forget()
                    for it in self.items:
                        if was_offline:
                            it.shown = None
                        it.refresh_from(payload)
                    if self.card is not None:
                        self.card.refresh()
                    if was_offline:
                        self.set_tray_tip()
                        if self.cfg.get("notify_offline", True):
                            self.notify("Home Assistant", "Connexion rétablie.")
                    if not self.areas and time.time() - self._areas_at > 60:
                        self.load_areas()
                elif kind == "error":
                    self.last_error = payload
                    self.fail_count += 1
                    if not self.offline and self.fail_count >= OFFLINE_AFTER:
                        self.offline = True
                        for it in self.items:
                            it.shown = None
                            it.refresh_from(self.last_states)
                        self.set_tray_tip()
                        if self.cfg.get("notify_offline", True) and self.last_ok:
                            self.notify("Home Assistant ne répond plus", payload[:200], warning=True)
                    self._show_status()
                elif kind == "rt_status":
                    self.rt_connected, self.rt_detail = payload
                    self.wake.set()     # lecture complete tout de suite (resynchronisation ou retour a l'interrogation)
                    self.set_tray_tip()
                elif kind == "rt_notify":
                    if self.cfg.get("ha_notifications", True):
                        from update_ui import plain_notes
                        self.notify(payload[0] or "Home Assistant", plain_notes(payload[1])[:250])
                elif kind == "areas":
                    self._areas_busy = False
                    if payload is not None:
                        self.areas = payload
                else:
                    self.on_update_msg(kind, payload)
        except queue.Empty:
            pass
        # Theme clair / sombre de Windows : verifie toutes les ~2 s, bascule a la volee
        self._theme_tick = getattr(self, "_theme_tick", 0) + 1
        if self._theme_tick % 25 == 0:          # ~10 s : minuteries, plages horaires d'affichage
            self.check_timers()
            if self.last_ok and time.time() - self._areas_at > AREAS_EVERY_S:
                self.load_areas()
            if self.visibility_sig(self.cfg) != self._vis_sig:
                self.apply_config(self.cfg)
        if self._theme_tick % 5 == 0 and system_light() != self.sys_light:
            self.apply_config(self.cfg)
            if self.card is not None:
                self.close_card()
        self.reposition()
        self.root.after(400, self.tick)

    def raise_now(self):
        if self.menu_open:
            # Menu clic droit ouvert : c'est lui qui doit rester devant les zones
            menu = user32.FindWindowW("#32768", None)
            if menu:
                user32.SetWindowPos(menu, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            return
        if not self.hidden:
            for z in self.zones:
                z.raise_now()

    def own_hwnds(self):
        return [h for z in self.zones for h in z.hwnds()]

    def offset(self, side):
        key, default = ("offset_right", 300) if side == "right" else ("offset", 60)
        try:
            return int(self.cfg.get(key, default))
        except (TypeError, ValueError):
            return default

    def taskbar(self):
        """Barre des taches de l'ecran choisi dans les reglages (ecran principal par defaut)."""
        return screens.find_taskbar(self.cfg.get("monitor", ""))

    def reposition(self):
        tb = self.taskbar()
        if not tb:
            return
        self.hidden = bool(self.cfg.get("hide_on_fullscreen", True)
                           and foreground_is_fullscreen(self.own_hwnds(), tb))
        r = get_rect(tb)
        for z in self.zones:
            z.show(z.wanted and not self.hidden)
            if z.shown:
                z.place(r, self.offset(z.side))
        # La barre des taches repasse devant a chaque clic : on se remet au-dessus
        self.raise_now()

    # ---------------- menu clic droit
    def show_menu(self, e, item=None):
        self.popup_menu(e.x_root, e.y_root, item=item)
        return "break"

    def popup_menu(self, x, y, from_tray=False, item=None):
        self.tip.hide()
        m = tk.Menu(self.root, tearoff=0)
        i = self.item_index(item) if item is not None and item in self.items else None
        if i is not None:
            m.add_command(label=(item.cfg.get("label") or item.entity_id)[:50], state="disabled")
            m.add_command(label="Modifier cet élément…", command=lambda: self.open_settings(select=i))
            m.add_command(label="Ouvrir la carte", command=lambda: self.open_card(item))
            m.add_command(label="Masquer de la barre", command=lambda: self.set_hidden(i, True))
            m.add_command(label="Pour le déplacer : Ctrl + glisser", state="disabled")
            m.add_separator()
        if self.last_error:
            m.add_command(label="Erreur : " + self.last_error[:80], state="disabled")
            if self.last_ok:
                m.add_command(label="Dernière réponse de HA à %s" % time.strftime(
                    "%H:%M:%S", time.localtime(self.last_ok)), state="disabled")
            m.add_command(label="Réessayer maintenant", command=self.wake.set)
            m.add_separator()
        for hk in self.hotkey_errors:
            m.add_command(label="Raccourci déjà pris par une autre application : %s" % hk, state="disabled")
        if self.hotkey_errors:
            m.add_separator()
        if self.timers:
            for eid in list(self.timers):
                m.add_command(label="⏲  Annuler l'arrêt de %s (dans %d min)" % (
                    self.friendly(eid), max(1, round(self.timer_left(eid) / 60.0))),
                    command=lambda e=eid: self.cancel_timer(e))
            m.add_separator()
        if self.update_info:
            m.add_command(label="⬆  Mettre à jour vers la version %s…" % self.update_info["version"],
                          command=self.show_update)
            m.add_separator()
        hidden = [(n, it) for n, it in enumerate(self.cfg.get("items", [])) if it.get("hidden")]
        if hidden:
            sub = tk.Menu(m, tearoff=0)
            for n, it in hidden:
                sub.add_command(label=(it.get("label") or it.get("entity_id") or "?")[:50],
                                command=lambda n=n: self.set_hidden(n, False))
            m.add_cascade(label="Réafficher un élément masqué", menu=sub)
        hk = self.cfg.get("palette_hotkey")
        m.add_command(label="Palette de commandes" + ("   (%s)" % hk if parse_hotkey(hk) else ""),
                      command=self.open_palette)
        now = time.time()
        if self.notify_paused_until > now:
            m.add_command(label="Reprendre les notifications (suspendues jusqu'à %s)"
                          % time.strftime("%H:%M", time.localtime(self.notify_paused_until)),
                          command=lambda: self.pause_notifications(until=0.0))
        else:
            sub = tk.Menu(m, tearoff=0)
            sub.add_command(label="Pendant 1 heure", command=lambda: self.pause_notifications(3600))
            sub.add_command(label="Pendant 3 heures", command=lambda: self.pause_notifications(3 * 3600))
            lt = time.localtime(now + 86400)
            tomorrow = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 8, 0, 0, 0, 0, -1))
            sub.add_command(label="Jusqu'à demain 8 h", command=lambda: self.pause_notifications(until=tomorrow))
            m.add_cascade(label="Suspendre les notifications", menu=sub)
        m.add_separator()
        m.add_command(label="Réglages…", command=self.open_settings)
        m.add_command(label="Rafraîchir", command=self.wake.set)
        m.add_command(label="Recharger config.json", command=self.reload)
        m.add_command(label="Rechercher une mise à jour", command=lambda: self.check_update(manual=True))
        m.add_separator()
        m.add_command(label="Quitter", command=self.quit)
        self.menu_open = True
        try:
            user32.SetForegroundWindow(self.main_zone.hwnd)  # sinon le menu ne se ferme pas en cliquant ailleurs
            m.tk_popup(x, y)     # sous Windows : rend la main quand le menu se ferme
        finally:
            self.menu_open = False
            m.grab_release()

    def reload(self):
        try:
            self.apply_config(load_config())
        except Exception as e:
            self.last_error = "config : %s" % e
            self._show_status()

    def open_settings(self, select=None):
        """Ouvre les reglages ; select = index de l'element a selectionner (onglet Elements)."""
        sw = self.settings_win
        if sw is not None and sw.win.winfo_exists():
            sw.win.deiconify()
            sw.win.lift()
            sw.win.focus_force()
        else:
            from settings_ui import SettingsWindow
            sw = self.settings_win = SettingsWindow(self)
        if select is not None:
            sw.nb.select(1)
            sw.select_item(select)


def main():
    # Une seule instance a la fois
    kernel32.CreateMutexW(None, False, "Local\\HATaskbar_single_instance")
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        user32.MessageBoxW(None, "HA Taskbar est déjà lancé.\nClic sur l'icône près de l'horloge → Réglages.",
                           "HA Taskbar", 0x40)
        sys.exit(0)
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
    App().root.mainloop()


if __name__ == "__main__":
    main()
