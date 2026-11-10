"""Palette de commandes (raccourci global, Ctrl+Alt+Espace par defaut) : recherche parmi toutes les
entites de Home Assistant, Entree pour l'action, fleches gauche / droite ou molette pour regler."""
import ctypes
import tkinter as tk
import unicodedata
from ctypes import wintypes

from card_ui import derive_palette, fnum
from ha_core import (ACTIVE_STATES, STATE_TEXT, WEATHER_TEXT, card_light, card_palette, resolve_icon,
                     resolve_service)

user32 = ctypes.windll.user32
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]

ROWS = 8
# Domaines sans interet dans la palette
SKIP_DOMAINS = {"persistent_notification", "zone", "conversation", "tts", "stt", "event", "image", "tag",
                "update", "assist_satellite", "wake_word", "todo", "calendar", "ai_task"}
CONTROL_DOMAINS = {"light", "switch", "fan", "cover", "climate", "media_player", "scene", "script", "lock",
                   "input_boolean", "button", "input_button", "vacuum", "automation", "humidifier",
                   "water_heater", "siren", "number", "input_number", "select", "input_select"}


def fold(text):
    """Minuscules sans accents (recherche « eclairage » = « Éclairage »)."""
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(ch for ch in t if not unicodedata.combining(ch))


def state_text(eid, st):
    s = st.get("state")
    a = st.get("attributes", {})
    d = eid.split(".", 1)[0]
    if s in ("unavailable", "unknown"):
        return STATE_TEXT.get(s, s)
    if d == "light" and s == "on" and a.get("brightness"):
        return "%d %%" % round(a["brightness"] * 100 / 255)
    if d == "fan" and s == "on" and a.get("percentage"):
        return "%d %%" % a["percentage"]
    if d == "cover" and a.get("current_position") is not None:
        return "%d %%" % a["current_position"]
    if d in ("climate", "water_heater") and a.get("temperature") is not None:
        cur = a.get("current_temperature")
        return ("%s° → %s°" % (fnum(cur, 1), fnum(a["temperature"]))) if cur is not None else "→ %s°" % fnum(
            a["temperature"])
    if d == "media_player" and a.get("volume_level") is not None and s not in ("off", "standby"):
        return "%s · %d %%" % (STATE_TEXT.get(s, s), round(a["volume_level"] * 100))
    if d == "weather":
        return WEATHER_TEXT.get(s, s)
    if d in ("scene", "button", "input_button"):
        return ""
    if d == "script":
        return "en cours" if s == "on" else ""
    try:
        float(s)
        unit = a.get("unit_of_measurement", "")
        return ("%s %s" % (fnum(s), unit)).strip()
    except (TypeError, ValueError):
        return STATE_TEXT.get(s, s)


class _Row:
    """Ce que attend App.wheel() : entity_id, domain, show_pending()."""

    def __init__(self, palette, eid):
        self.palette, self.entity_id = palette, eid
        self.domain = eid.split(".", 1)[0]

    def show_pending(self, text):
        self.palette.pending[self.entity_id] = text
        self.palette.render()


class Palette:
    def __init__(self, app):
        self.app = app
        self.results = []
        self.sel = 0
        self.pending = {}
        self.alive = True
        light = card_light(app.cfg, getattr(app, "light", False))
        base, _r = card_palette(app.cfg, app.colors, light)
        c = self.c = derive_palette(base)
        k = app.root.winfo_fpixels("1i") / 96.0
        s = self.s = lambda v: int(round(v * k))
        fam = app.cfg.get("font", "Segoe UI")
        ifont = app.icon_font or fam
        self.on_bar = {it.get("entity_id"): it for it in app.cfg.get("items", [])}

        win = self.win = tk.Toplevel(app.root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=c["border"])
        body = tk.Frame(win, bg=c["bg"], padx=s(10), pady=s(10))
        body.pack(padx=1, pady=1, fill="both", expand=True)

        top = tk.Frame(body, bg=c["surface"], padx=s(10), pady=s(6))
        top.pack(fill="x")
        tk.Label(top, text="", bg=c["surface"], fg=c["dim"], font=(ifont, 12)).pack(side="left")
        self.v = tk.StringVar()
        self.entry = tk.Entry(top, textvariable=self.v, font=(fam, 13), relief="flat", bd=0, bg=c["surface"],
                              fg=c["fg"], insertbackground=c["fg"], width=40)
        self.entry.pack(side="left", fill="x", expand=True, padx=(s(10), 0))
        self.rows = []
        for i in range(ROWS):
            r = tk.Frame(body, bg=c["bg"], padx=s(8), pady=s(5), cursor="hand2")
            r.pack(fill="x", pady=(s(4) if i == 0 else 0, 0))
            ic = tk.Label(r, text="", width=2, bg=c["bg"], fg=c["fg"], font=(ifont, 12))
            ic.pack(side="left")
            nm = tk.Label(r, text="", bg=c["bg"], fg=c["fg"], font=(fam, 10), anchor="w")
            nm.pack(side="left", padx=(s(8), 0))
            ar = tk.Label(r, text="", bg=c["bg"], fg=c["dim"], font=(fam, 8), anchor="w")
            ar.pack(side="left", padx=(s(8), 0))
            val = tk.Label(r, text="", bg=c["bg"], fg=c["dim"], font=(fam, 10), anchor="e")
            val.pack(side="right")
            ws = (r, ic, nm, ar, val)
            for w in ws:
                w.bind("<Button-1>", lambda e, i=i: self.click(i))
                w.bind("<MouseWheel>", lambda e, i=i: self.wheel(i, e))
                w.bind("<Motion>", lambda e, i=i: self.hover(i))
            self.rows.append(ws)
        self.empty = tk.Label(body, text="", bg=c["bg"], fg=c["dim"], font=(fam, 9))
        tk.Label(body, text="Entrée : action   ·   ← → ou molette : régler   ·   Tab : carte   ·   Échap : fermer",
                 bg=c["bg"], fg=c["dim"], font=(fam, 8)).pack(anchor="w", pady=(s(8), 0), side="bottom")

        e = self.entry
        e.bind("<Down>", lambda ev: self.move(1))
        e.bind("<Up>", lambda ev: self.move(-1))
        e.bind("<Next>", lambda ev: self.move(ROWS))
        e.bind("<Prior>", lambda ev: self.move(-ROWS))
        e.bind("<Return>", lambda ev: self.act())
        e.bind("<KP_Enter>", lambda ev: self.act())
        e.bind("<Tab>", lambda ev: self.card())
        e.bind("<Left>", lambda ev: self.adjust(-1))
        e.bind("<Right>", lambda ev: self.adjust(1))
        e.bind("<Escape>", lambda ev: self.close())
        win.bind("<MouseWheel>", lambda ev: self.wheel(self.sel, ev))
        self.v.trace_add("write", lambda *a: self.search())
        self.search()

        win.update_idletasks()
        self.hwnd = user32.GetAncestor(win.winfo_id(), 2)
        ex = user32.GetWindowLongW(self.hwnd, -20)
        user32.SetWindowLongW(self.hwnd, -20, (ex | 0x80) & ~0x40000)
        w = s(620)
        h = win.winfo_reqheight()
        mx, my, mw, mh = app.monitor_rect()
        win.geometry("%dx%d+%d+%d" % (w, h, mx + (mw - w) // 2, my + mh // 4))
        win.deiconify()
        win.lift()
        user32.SetForegroundWindow(self.hwnd)
        win.focus_force()
        e.focus_set()
        self._was_fg = False
        self._loop()

    # ---------------- recherche
    def search(self):
        words = fold(self.v.get()).split()
        states = self.app.last_states
        areas = getattr(self.app, "areas", {}) or {}
        out = []
        for eid, st in states.items():
            d = eid.split(".", 1)[0]
            if d in SKIP_DOMAINS:
                continue
            name = st.get("attributes", {}).get("friendly_name") or eid
            area = areas.get(eid, "")
            hay = fold("%s %s %s" % (name, eid, area))
            if words and any(w not in hay for w in words):
                continue
            fn = fold(name)
            score = 0
            if eid in self.on_bar:
                score += 4
            if d in CONTROL_DOMAINS:
                score += 2
            if words and fn.startswith(words[0]):
                score += 3
            elif words and (" " + words[0]) in (" " + fn):
                score += 1
            if st.get("state") == "unavailable":
                score -= 3
            out.append((-score, fn, eid, name, area))
        out.sort()
        self.results = [(eid, name, area) for _s, _f, eid, name, area in out[:ROWS]]
        self.total = len(out)
        self.sel = 0
        self.render()

    def render(self):
        if not self.alive:
            return
        c = self.c
        states = self.app.last_states
        for i, (r, ic, nm, ar, val) in enumerate(self.rows):
            if i < len(self.results):
                eid, name, area = self.results[i]
                st = states.get(eid) or {}
                bg = c["surface"] if i == self.sel else c["bg"]
                cfg = self.on_bar.get(eid) or {"entity_id": eid}
                on = st.get("state") in ACTIVE_STATES and not eid.startswith("sensor.")
                for w in (r, ic, nm, ar, val):
                    w.configure(bg=bg)
                ic.configure(text=resolve_icon(cfg, st) or "", fg=c["accent"] if on else c["fg"])
                nm.configure(text=name[:48])
                ar.configure(text=area)
                pend = self.pending.get(eid)
                val.configure(text=pend if pend is not None else state_text(eid, st),
                              fg=c["accent"] if (on or pend is not None) else c["dim"])
                if not r.winfo_ismapped():
                    r.pack(fill="x")
            elif r.winfo_ismapped():
                r.pack_forget()
        if not self.results:
            self.empty.configure(text="Aucune entité ne correspond." if self.app.last_states
                                 else "Home Assistant n'a pas encore répondu.")
            if not self.empty.winfo_ismapped():
                self.empty.pack(pady=self.s(10))
        elif self.empty.winfo_ismapped():
            self.empty.pack_forget()

    # ---------------- actions
    def move(self, d):
        if self.results:
            self.sel = max(0, min(len(self.results) - 1, self.sel + d))
            self.render()
        return "break"

    def hover(self, i):
        if i != self.sel and i < len(self.results):
            self.sel = i
            self.render()

    def current(self):
        if 0 <= self.sel < len(self.results):
            eid = self.results[self.sel][0]
            return eid, self.on_bar.get(eid) or {"entity_id": eid}
        return None, None

    def act(self):
        eid, cfg = self.current()
        if eid is None:
            return "break"
        if eid.split(".", 1)[0] in ("climate", "water_heater", "number", "input_number", "select",
                                    "input_select", "weather", "sensor", "binary_sensor") \
                or not resolve_service(cfg):
            return self.card()
        self.close()
        self.app.click_item(cfg)
        return "break"

    def card(self):
        eid, cfg = self.current()
        if eid is not None:
            self.close()
            self.app.open_card(cfg)
        return "break"

    def adjust(self, d):
        eid, _cfg = self.current()
        if eid is not None:
            self.app.wheel(_Row(self, eid), d)
        return "break"

    def click(self, i):
        self.sel = i
        self.act()

    def wheel(self, i, e):
        if i < len(self.results):
            self.sel = i
            self.adjust(1 if e.delta > 0 else -1)
        return "break"

    # ---------------- fenetre
    def _loop(self):
        if not self.alive:
            return
        fg = user32.GetForegroundWindow()
        if fg == self.hwnd:
            self._was_fg = True
        elif self._was_fg and fg:
            self.close()
            return
        # valeurs a jour (et fin des valeurs "en attente" de la molette)
        if self.pending and not self.app._wheel:
            self.pending.clear()
        self.render()
        self.win.after(250, self._loop)

    def close(self):
        if not self.alive:
            return
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if self.app.palette is self:
            self.app.palette = None

