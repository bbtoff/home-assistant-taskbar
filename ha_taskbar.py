"""
HA Taskbar - affiche des capteurs / boutons Home Assistant sur la barre des taches Windows 11.

Principe : une petite fenetre sans bordure, "toujours au premier plan", positionnee
sur une zone libre de la barre des taches (Windows 11 ne supporte plus les deskbands).

Aucune dependance externe : Python 3.8+ (tkinter + ctypes + urllib).
Lancement sans console :  pythonw ha_taskbar.py
Reglages : clic droit sur la barre -> "Reglages..."
"""
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

from ha_core import (ACTIVE_STATES, CONFIG_PATH, DEFAULT_CONFIG, ICON_FONTS, ICON_PATH, STATE_TEXT, HomeAssistant,
                     bar_colors, bar_light, system_light, item_zone, load_config, needs_setup,
                     resolve_icon, resolve_service, save_config)

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


def get_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def foreground_is_fullscreen(own_hwnds):
    """True si l'app au premier plan est en plein ecran (jeu, video...)."""
    fg = user32.GetForegroundWindow()
    if not fg or fg in own_hwnds:
        return False
    if class_name(fg) in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        return False
    r = get_rect(fg)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(user32.MonitorFromWindow(fg, MONITOR_DEFAULTTONEAREST), ctypes.byref(mi)):
        return False
    m = mi.rcMonitor
    return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom


LONG_PRESS_MS = 450      # appui long -> carte de controle


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

        cursor = "hand2"            # tout element ouvre au moins sa carte (appui long)
        fs = int(app.cfg.get("font_size", 9))
        font = app.cfg.get("font", "Segoe UI")
        stacked = app.cfg.get("layout", "stacked") == "stacked"
        label = cfg.get("label") or self.entity_id

        self.frame = tk.Frame(parent, bg=c["bg"], cursor=cursor, padx=8)
        self.frame.grid_rowconfigure(0, weight=1)      # contenu centre verticalement dans le rectangle
        self.zone = item_zone(cfg)
        self.icon = None
        if app.cfg.get("show_icons", True) and cfg.get("icon") != "none" and app.icon_font:
            self.icon = tk.Label(self.frame, text="", bg=c["bg"], fg=c["fg"], cursor=cursor,
                                 font=(app.icon_font, fs + (7 if stacked else 3)))
            self.icon.grid(row=0, column=0, padx=(0, 6))
        self.txt = tk.Frame(self.frame, bg=c["bg"], cursor=cursor)
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
        self.widgets = [w for w in (self.frame, self.icon, self.txt, self.title, self.value) if w is not None]

        for w in self.widgets:
            w.bind("<ButtonPress-1>", self.on_press)
            w.bind("<ButtonRelease-1>", lambda e: app.release())
            w.bind("<MouseWheel>", self.on_wheel)
            w.bind("<Button-3>", app.show_menu)
        self.grow()

    def grow(self):
        """Fige la largeur de la zone texte sur la plus grande valeur vue -> pas de redimensionnement."""
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
        if self.service:
            self.app.call_service(self.service, self.service_data)
        else:
            self.app.open_card(self)

    def on_wheel(self, e):
        # Molette sur une lumiere = luminosite +/- 10 %
        if self.domain == "light":
            step = 10 if e.delta > 0 else -10
            self.app.call_service("light.turn_on", {"entity_id": self.entity_id, "brightness_step_pct": step})

    def update(self, st):
        c = self.app.colors
        if st is None:
            self.show(resolve_icon(self.cfg, None), "?", c["error"], c["dim"])
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
            text = STATE_TEXT.get(text, text)

        if self.domain == "light" and st.get("state") == "on" and attrs.get("brightness") and not attr:
            text = "%d%%" % round(attrs["brightness"] * 100 / 255)

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
        if state in ("unavailable", "unknown"):
            fg = icon_fg = c["dim"]
        elif active:
            fg = c["fg"] if attr else c["on"]
            icon_fg = c["on"]
        else:
            fg = icon_fg = c["fg"]
        self.show(resolve_icon(self.cfg, st), text, fg, icon_fg)

    def show(self, glyph, text, fg, icon_fg):
        new = (glyph, text, fg, icon_fg)
        if new == self.shown:          # rien n'a change : on ne touche a rien (evite le scintillement)
            return
        self.shown = new
        self.value.configure(text=text, fg=fg)
        if self.icon is not None:
            self.icon.configure(text=glyph or "", fg=icon_fg)
        self.grow()


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
        ex = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW)
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
        ex = user32.GetWindowLongW(self.hit_hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(self.hit_hwnd, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW)
        self.hit.bind("<ButtonPress-1>", lambda e: app._hit_dispatch(e, "on_press"))
        self.hit.bind("<ButtonRelease-1>", lambda e: app.release())
        self.hit.bind("<MouseWheel>", lambda e: app._hit_dispatch(e, "on_wheel"))
        self.hit.bind("<Button-3>", app.show_menu)
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
        self._press_item = None
        self._press_job = None

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

        threading.Thread(target=self.poll_loop, daemon=True).start()
        self.tick()
        self.hover_loop()
        if needs_setup(self.cfg) or not os.path.exists(CONFIG_PATH):
            self.root.after(300, self.open_settings)

    # ---------------- config
    def apply_config(self, cfg):
        """Applique une config (depuis le fichier ou en previsualisation depuis les reglages)."""
        self.cfg = cfg
        self.sys_light = system_light()
        self.light = bar_light(cfg)
        self.colors = bar_colors(cfg, self.light)
        self.ha = HomeAssistant(cfg["ha_url"], cfg["token"], cfg.get("verify_ssl", True))

        zones = {z.side: z for z in self.zones}
        for z in self.zones:
            z.style(cfg, self.colors)
        self.items = []
        for it_cfg in cfg.get("items", []):
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
                it.update(self.last_states.get(it.entity_id))
        if self.last_error:
            self._show_status()
        self.hovered = None
        self.wake.set()

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
        self._cancel_press()
        self._press_item = item
        self._press_job = self.root.after(LONG_PRESS_MS, self._long_press)

    def release(self):
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
    def open_card(self, item):
        from card_ui import Card
        self.close_card()
        tb = user32.FindWindowW("Shell_TrayWnd", None)
        if not tb:
            return
        r = get_rect(tb)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(user32.MonitorFromWindow(tb, MONITOR_DEFAULTTONEAREST), ctypes.byref(mi))
        work = mi.rcMonitor
        cx = item.frame.winfo_rootx() + item.frame.winfo_width() // 2
        self.card = Card(self, item.cfg, cx, r.top, work.left, work.right)

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
        except tk.TclError:
            pass
        self.root.after(50, self.hover_loop)

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
    def _show_status(self):
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
                if kind == "states":
                    self.last_error = None
                    self.last_states = payload
                    if self.status.winfo_ismapped():
                        self.status.pack_forget()
                    for it in self.items:
                        it.update(payload.get(it.entity_id))
                    if self.card is not None:
                        self.card.refresh()
                else:
                    self.last_error = payload
                    self._show_status()
        except queue.Empty:
            pass
        # Theme clair / sombre de Windows : verifie toutes les ~2 s, bascule a la volee
        self._theme_tick = getattr(self, "_theme_tick", 0) + 1
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

    def reposition(self):
        tb = user32.FindWindowW("Shell_TrayWnd", None)
        if not tb:
            return
        self.hidden = bool(self.cfg.get("hide_on_fullscreen", True) and foreground_is_fullscreen(self.own_hwnds()))
        r = get_rect(tb)
        for z in self.zones:
            z.show(z.wanted and not self.hidden)
            if z.shown:
                z.place(r, self.offset(z.side))
        # La barre des taches repasse devant a chaque clic : on se remet au-dessus
        self.raise_now()

    # ---------------- menu clic droit
    def show_menu(self, e):
        m = tk.Menu(self.root, tearoff=0)
        if self.last_error:
            m.add_command(label="Erreur : " + self.last_error[:80], state="disabled")
            m.add_separator()
        m.add_command(label="Réglages…", command=self.open_settings)
        m.add_command(label="Rafraîchir", command=self.wake.set)
        m.add_command(label="Recharger config.json", command=self.reload)
        m.add_separator()
        m.add_command(label="Quitter", command=self.root.destroy)
        self.menu_open = True
        try:
            user32.SetForegroundWindow(self.main_zone.hwnd)  # sinon le menu ne se ferme pas en cliquant ailleurs
            m.tk_popup(e.x_root, e.y_root)     # sous Windows : rend la main quand le menu se ferme
        finally:
            self.menu_open = False
            m.grab_release()
        return "break"

    def reload(self):
        try:
            self.apply_config(load_config())
        except Exception as e:
            self.last_error = "config : %s" % e
            self._show_status()

    def open_settings(self):
        if self.settings_win is not None and self.settings_win.win.winfo_exists():
            self.settings_win.win.deiconify()
            self.settings_win.win.lift()
            self.settings_win.win.focus_force()
            return
        from settings_ui import SettingsWindow
        self.settings_win = SettingsWindow(self)


def main():
    # Une seule instance a la fois
    kernel32.CreateMutexW(None, False, "Local\\HATaskbar_single_instance")
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        user32.MessageBoxW(None, "HA Taskbar est déjà lancé.\nClic droit sur la barre → Réglages.",
                           "HA Taskbar", 0x40)
        sys.exit(0)
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
    App().root.mainloop()


if __name__ == "__main__":
    main()
