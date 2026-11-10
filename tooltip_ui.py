"""Infobulle au survol d'un element de la barre : nom, valeur, derniere modification et mini-courbe
des 6 dernieres heures (ou frise allume / eteint)."""
import ctypes
import datetime
import queue
import threading
import time
import tkinter as tk
from ctypes import wintypes

from card_ui import ago, derive_palette, fnum
from ha_core import (ACTIVE_STATES, BATTERIES, STATE_TEXT, WEATHER_TEXT, card_light, card_palette, group_state)

user32 = ctypes.windll.user32
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.SetWindowPos.argtypes = [wintypes.HWND, ctypes.c_ssize_t, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]

DELAY_MS = 550           # survol avant affichage
HOURS = 6                # periode de la mini-courbe
CACHE_S = 120            # historique garde 2 min
NO_HISTORY = ("scene", "script", "button", "input_button", "weather")


class Tooltip:
    def __init__(self, app):
        self.app = app
        self.win = None
        self.item = None
        self.job = None
        self.cache = {}
        self.q = queue.Queue()
        self.chart = None
        self.key = None
        self._poll()

    # ---------------- cycle de vie
    def schedule(self, item):
        if item is self.item and (self.win is not None or self.job is not None):
            return
        self.hide()
        if item is None or not self.app.cfg.get("tooltips", True):
            return
        self.item = item
        self.job = self.app.root.after(DELAY_MS, self.show)

    def hide(self):
        if self.job is not None:
            self.app.root.after_cancel(self.job)
            self.job = None
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win = self.chart = self.key = None
        self.item = None

    def _poll(self):
        try:
            while True:
                key, pts = self.q.get_nowait()
                self.cache[key] = (time.monotonic(), pts)
                if key == self.key and self.chart is not None:
                    self._draw(pts)
        except queue.Empty:
            pass
        self.app.root.after(200, self._poll)

    # ---------------- contenu
    def show(self):
        self.job = None
        it = self.item
        app = self.app
        if it is None or it not in app.items or app.card is not None or app.hidden:
            return
        light = card_light(app.cfg, getattr(app, "light", False))
        base, _r = card_palette(app.cfg, app.colors, light)
        c = self.c = derive_palette(base)
        k = app.root.winfo_fpixels("1i") / 96.0
        s = self.s = lambda v: int(round(v * k))
        fam = app.cfg.get("font", "Segoe UI")
        st = app.state_for(it)

        win = self.win = tk.Toplevel(app.root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=c["border"])
        body = tk.Frame(win, bg=c["bg"], padx=s(12), pady=s(9))
        body.pack(padx=1, pady=1)
        a = (st or {}).get("attributes", {})
        name = it.cfg.get("card_title") or a.get("friendly_name") or it.cfg.get("label") or it.entity_id
        tk.Label(body, text=name, bg=c["bg"], fg=c["fg"], font=(fam, 9, "bold"), anchor="w", justify="left",
                 wraplength=s(260)).pack(anchor="w")
        tk.Label(body, text=self.value_text(it, st), bg=c["bg"], fg=c["accent"], font=(fam, 9), anchor="w",
                 justify="left", wraplength=s(260)).pack(anchor="w")

        if it.entity_id == BATTERIES:
            self.batteries(body, a.get("low") or [], fam)
        elif it.is_group:
            for eid in it.members:
                m = app.last_states.get(eid) or {}
                txt = "%s : %s" % (m.get("attributes", {}).get("friendly_name") or eid,
                                   STATE_TEXT.get(m.get("state"), m.get("state") or "?"))
                tk.Label(body, text=txt, bg=c["bg"], fg=c["dim"], font=(fam, 8), anchor="w").pack(anchor="w")
        elif st and it.domain not in NO_HISTORY:
            self.chart = tk.Canvas(body, width=s(220), height=s(46), bg=c["bg"], highlightthickness=0)
            self.chart.pack(anchor="w", pady=(s(6), 0))
            attr = it.cfg.get("attribute") or ("current_temperature" if it.domain in ("climate", "water_heater")
                                               else None)
            self.key = (it.entity_id, attr)
            hit = self.cache.get(self.key)
            if hit and time.monotonic() - hit[0] < CACHE_S:
                self._draw(hit[1])
            else:
                self.chart.create_text(s(110), s(23), text="…", fill=c["dim"], font=(fam, 8))
                threading.Thread(target=self._fetch, args=(app.ha, self.key), daemon=True).start()
        if st and st.get("last_changed"):
            tk.Label(body, text="Modifié " + ago(st["last_changed"]), bg=c["bg"], fg=c["dim"],
                     font=(fam, 8)).pack(anchor="w", pady=(s(4), 0))

        win.update_idletasks()
        hwnd = user32.GetAncestor(win.winfo_id(), 2)
        ex = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, (ex | 0x80 | 0x08000000) & ~0x40000)   # toolwindow, sans focus
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        anchor = app.anchor_for(it)
        if anchor is None:
            self.hide()
            return
        cx, top, xmin, xmax = anchor
        x = max(xmin + s(6), min(xmax - s(6) - w, cx - w // 2))
        y = top - h - s(8)
        win.geometry("%dx%d+%d+%d" % (w, h, x, y))
        win.deiconify()
        user32.SetWindowPos(hwnd, -1, x, y, w, h, 0x0010)      # HWND_TOPMOST, SWP_NOACTIVATE

    def value_text(self, it, st):
        if it.entity_id == BATTERIES:
            n = len((st or {}).get("attributes", {}).get("low") or [])
            return ("%d pile%s sous %s %%" % (n, "s" if n > 1 else "", fnum(self.app.cfg.get("battery_low", 20)))
                    if n else "Toutes les piles sont chargées")
        if it.is_group:
            _g, on, total = group_state(it.cfg, self.app.last_states)
            return "%d allumé%s sur %d" % (on, "s" if on > 1 else "", total)
        if st is None:
            return "Entité introuvable"
        txt = it.value.cget("text")
        if it.domain == "weather" and not it.cfg.get("attribute"):
            a = st.get("attributes", {})
            txt = WEATHER_TEXT.get(st.get("state"), txt)
            if a.get("temperature") is not None:
                txt += " · %s %s" % (fnum(a["temperature"]), a.get("temperature_unit", "°C"))
        if self.app.offline:
            txt += "  (Home Assistant hors ligne)"
        return txt

    def batteries(self, body, low, fam):
        c, s = self.c, self.s
        for eid, name, v in low[:8]:
            row = tk.Frame(body, bg=c["bg"])
            row.pack(fill="x")
            tk.Label(row, text=name, bg=c["bg"], fg=c["fg"], font=(fam, 8), anchor="w").pack(side="left")
            tk.Label(row, text="faible" if eid.startswith("binary_sensor.") else "%d %%" % v, bg=c["bg"], fg="#e5534b",
                     font=(fam, 8, "bold")).pack(side="right", padx=(s(12), 0))
        if len(low) > 8:
            tk.Label(body, text="… et %d autres" % (len(low) - 8), bg=c["bg"], fg=c["dim"],
                     font=(fam, 8)).pack(anchor="w")

    # ---------------- mini-courbe
    def _fetch(self, ha, key):
        eid, attr = key
        try:
            rows = ha.history(eid, HOURS, attributes=bool(attr))
            pts = [(t, (at.get(attr) if attr else stt)) for t, stt, at in rows]
        except Exception:
            pts = None
        self.q.put((key, pts))

    def _draw(self, pts):
        cv, c, s = self.chart, self.c, self.s
        try:
            cv.delete("all")
        except tk.TclError:
            return
        W, H = int(cv["width"]), int(cv["height"])
        fam = self.app.cfg.get("font", "Segoe UI")
        if not pts:
            cv.create_text(W // 2, H // 2, text="Pas d'historique", fill=c["dim"], font=(fam, 8))
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        t0 = now - datetime.timedelta(hours=HOURS)
        span = (now - t0).total_seconds()

        def tx(t):
            return max(0.0, min(1.0, (t - t0).total_seconds() / span))
        nums = []
        for t, v in pts:
            try:
                nums.append((t, float(v)))
            except (TypeError, ValueError):
                pass
        label_w = s(44)
        gw = W - label_w
        if len(nums) >= max(2, len(pts) // 2):
            lo, hi = min(v for _t, v in nums), max(v for _t, v in nums)
            if hi - lo < 1e-9:
                hi, lo = hi + 1, lo - 1
            top, bot = s(4), H - s(4)

            def ty(v):
                return bot - (v - lo) / (hi - lo) * (bot - top)
            xy = []
            for i, (t, v) in enumerate(nums):
                x = tx(t) * gw
                if i:
                    xy += [x, xy[-1]]          # palier : la valeur reste jusqu'au changement suivant
                xy += [x, ty(v)]
            xy += [gw, xy[-1]]
            fill = [xy[0], bot] + xy + [gw, bot]
            cv.create_polygon(fill, fill=self._tint(0.18), outline="")
            cv.create_line(xy, fill=c["accent"], width=max(1, s(1.5)))
            unit = (self.app.state_for(self.item) or {}).get("attributes", {}).get("unit_of_measurement", "")
            if self.item is not None and self.item.cfg.get("attribute"):
                unit = ""
            cv.create_text(W, top, text="%s %s" % (fnum(hi, 1 if hi - lo < 10 else 0), unit), anchor="ne",
                           fill=c["dim"], font=(fam, 7))
            cv.create_text(W, bot, text="%s %s" % (fnum(lo, 1 if hi - lo < 10 else 0), unit), anchor="se",
                           fill=c["dim"], font=(fam, 7))
        else:
            # etats (allume / eteint...) : frise coloree
            y0, y1 = s(16), H - s(16)
            for i, (t, v) in enumerate(pts):
                x0 = tx(t) * gw
                x1 = tx(pts[i + 1][0]) * gw if i + 1 < len(pts) else gw
                col = c["accent"] if v in ACTIVE_STATES else c["track"]
                cv.create_rectangle(x0, y0, max(x0 + 1, x1), y1, fill=col, outline="")
        cv.create_text(W, H // 2, text="%d h" % HOURS, anchor="e", fill=c["dim"], font=(fam, 7))

    def _tint(self, t):
        from ha_core import mix_color
        return mix_color(self.c["bg"], self.c["accent"], t)
