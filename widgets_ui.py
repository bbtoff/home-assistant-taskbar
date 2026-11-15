"""Widgets de bureau : graphique ou valeur en grand d'un ou plusieurs capteurs, poses sur le bureau
(sous les fenetres) ou toujours au premier plan. Deplacables a la souris, menu du clic droit.

Configuration (config.json, cle "widgets") :
  {"id", "entities": [...], "title", "style": "graph"|"value", "hours": 24|168|720,
   "size": "small"|"medium"|"large", "on_top", "hidden", "win_x", "win_y"}
(la version macOS utilise "x" / "y" pour sa propre position)."""
import copy
import ctypes
import datetime
import tkinter as tk
import uuid
from ctypes import wintypes

from card_ui import derive_palette, fnum
from ha_core import STATE_TEXT, card_light, card_palette, mix_color, save_config
from history import as_float

user32 = ctypes.windll.user32
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.SetWindowPos.argtypes = [wintypes.HWND, ctypes.c_ssize_t, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
HWND_BOTTOM = 1
SWP_FLAGS = 0x0001 | 0x0002 | 0x0010          # NOSIZE | NOMOVE | NOACTIVATE

SIZES = {"small": (220, 140, 110), "medium": (300, 185, 130), "large": (420, 250, 170)}   # l, h, h (valeur)
PERIODS = [("24 heures", 24), ("7 jours", 168), ("30 jours", 720)]
SERIES = ["accent", "#f7630c", "#16c60c", "#e3008c", "#b146c2", "#00b7c3"]


def period_label(h):
    return "24 h" if h <= 24 else "7 jours" if h <= 168 else "30 jours"


class DesktopWidget:
    def __init__(self, mgr, w, index):
        self.mgr = mgr
        self.app = mgr.app
        self.id = w["id"]
        self.w = w
        self.index = index
        self._drag = None
        root = self.app.root
        self.scale = root.winfo_fpixels("1i") / 96.0
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.canvas = tk.Canvas(self.win, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        for ev, fn in (("<ButtonPress-1>", self.on_press), ("<B1-Motion>", self.on_motion),
                       ("<ButtonRelease-1>", self.on_release), ("<Button-3>", self.on_menu),
                       ("<Double-Button-1>", lambda e: self.app.open_settings())):
            self.canvas.bind(ev, fn)
        self.apply(w, first=True)
        self.win.deiconify()
        self.win.update_idletasks()
        self._round_corners()
        self.to_bottom()
        self.redraw()

    def s(self, v):
        return int(round(v * self.scale))

    @property
    def hwnd(self):
        return user32.GetAncestor(self.win.winfo_id(), 2)

    def _round_corners(self):
        try:            # Windows 11 : coins arrondis (DWMWA_WINDOW_CORNER_PREFERENCE = DWMWCP_ROUND)
            pref = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(self.hwnd), 33, ctypes.byref(pref), 4)
        except Exception:
            pass

    def size(self):
        wi, hg, hv = SIZES.get(self.w.get("size"), SIZES["medium"])
        return self.s(wi), self.s(hv if self.w.get("style") == "value" else hg)

    def default_pos(self):
        W, H = self.size()
        sw = self.app.root.winfo_screenwidth()
        return sw - W - self.s(24), self.s(24) + self.index * (H + self.s(16))

    def apply(self, w, first=False):
        self.w = w
        W, H = self.size()
        x, y = w.get("win_x"), w.get("win_y")
        if x is None or y is None:
            x, y = self.default_pos()
        else:
            # garde le widget sur l'ecran (ecran debranche, resolution changee...)
            vx, vy = self.app.root.winfo_vrootx(), self.app.root.winfo_vrooty()
            vw = max(self.app.root.winfo_vrootwidth(), self.app.root.winfo_screenwidth())
            vh = max(self.app.root.winfo_vrootheight(), self.app.root.winfo_screenheight())
            if not (vx - W < x < vx + vw and vy <= y < vy + vh - self.s(20)):
                x, y = self.default_pos()
        self.win.geometry("%dx%d+%d+%d" % (W, H, int(x), int(y)))
        self.win.attributes("-topmost", bool(w.get("on_top")))
        if not first:
            self.to_bottom()
            self.redraw()

    def to_bottom(self):
        if not self.w.get("on_top"):
            try:
                user32.SetWindowPos(self.hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_FLAGS)
            except Exception:
                pass

    def destroy(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # ---------------- souris
    def on_press(self, e):
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def on_motion(self, e):
        if self._drag:
            self.win.geometry("+%d+%d" % (e.x_root - self._drag[0], e.y_root - self._drag[1]))

    def on_release(self, _e):
        if self._drag:
            self._drag = None
            x, y = self.win.winfo_x(), self.win.winfo_y()
            self.mgr.edit(self.id, lambda w: w.update(win_x=x, win_y=y), sync=False)
        self.to_bottom()

    def on_menu(self, e):
        self.mgr.menu(self, e.x_root, e.y_root)
        return "break"

    # ---------------- dessin
    def palette(self):
        app = self.app
        light = card_light(app.cfg, getattr(app, "light", False))
        base, _r = card_palette(app.cfg, app.colors, light)
        return derive_palette(base)

    def name(self, eid):
        for it in self.app.cfg.get("items", []):
            if it.get("entity_id") == eid and it.get("label"):
                return it["label"]
        st = self.app.last_states.get(eid) or {}
        return st.get("attributes", {}).get("friendly_name") or eid

    def value(self, eid):
        st = self.app.last_states.get(eid)
        if not st:
            return "?"
        a = st.get("attributes", {})
        v = as_float(st.get("state"))
        unit = a.get("unit_of_measurement") or ""
        if v is None:
            return STATE_TEXT.get(st.get("state"), st.get("state"))
        txt = fnum(v) if abs(v) >= 100 or v == int(v) else fnum(v, 1)
        return "%s %s" % (txt, unit) if unit else txt

    def color(self, i, c):
        k = SERIES[i % len(SERIES)]
        return c[k] if k in c else k

    def redraw(self):
        cv = self.canvas
        try:
            cv.delete("all")
        except tk.TclError:
            return
        w = self.w
        c = self.palette()
        W, H = self.size()
        cv.configure(bg=c["bg"], width=W, height=H)
        fam = self.app.cfg.get("font", "Segoe UI")
        ents = [e for e in w.get("entities", []) if e]
        if not ents:
            return
        single = len(ents) == 1
        value_style = w.get("style") == "value"
        hours = 24 if value_style else int(w.get("hours") or 24)
        pad = self.s(14)
        x0, x1 = pad, W - pad
        y = pad
        title = w.get("title") or (self.name(ents[0]) if single else "Capteurs")
        cv.create_text(x0, y, text=title[:40], anchor="nw", fill=c["fg"], font=(fam, 10, "bold"))
        if not value_style:
            cv.create_text(x1, y + self.s(2), text=period_label(hours), anchor="ne", fill=c["dim"], font=(fam, 8))
        if self.app.offline:
            cv.create_text(x1, y + self.s(16), text="hors ligne", anchor="ne", fill=c["dim"], font=(fam, 8))
        y += self.s(20)
        if single:
            big = 30 if value_style and w.get("size") == "large" else 24 if value_style else 17
            cv.create_text(x0, y, text=self.value(ents[0]), anchor="nw", fill=c["fg"], font=(fam, big))
            y += self.s(big * 1.6)
        else:
            for i, e in enumerate(ents[:6]):
                cv.create_oval(x0, y + self.s(5), x0 + self.s(7), y + self.s(12), fill=self.color(i, c), outline="")
                cv.create_text(x0 + self.s(12), y, text=self.name(e)[:28], anchor="nw", fill=c["fg"], font=(fam, 9))
                cv.create_text(x1, y, text=self.value(e), anchor="ne", fill=c["fg"], font=(fam, 9))
                y += self.s(17)
            y += self.s(4)
        stats_h = self.s(16) if single and not value_style and w.get("size") != "small" else 0
        top, bot = y, H - pad - stats_h
        series = []
        for i, e in enumerate(ents):
            self.app.history.request(e, hours)
            series.append((i, self.app.history.points(e, hours)))
        series = [(i, p) for i, p in series if len(p) >= 2]
        if bot - top < self.s(20):
            return
        if not series:
            if not value_style:
                cv.create_text((x0 + x1) // 2, (top + bot) // 2, text="Pas encore de valeurs numériques",
                               fill=c["dim"], font=(fam, 8))
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        t0 = now - datetime.timedelta(hours=hours)
        span = (now - t0).total_seconds()
        vals = [v for _i, p in series for _d, v in p]
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-9:
            hi, lo = hi + 1, lo - 1
        label_w = 0 if value_style else self.s(40)
        gx1 = x1 - label_w

        def tx(d):
            return x0 + max(0.0, min(1.0, (d - t0).total_seconds() / span)) * (gx1 - x0)

        def ty(v):
            return bot - (v - lo) / (hi - lo) * (bot - top)
        if not value_style:
            for f in (0.0, 0.5, 1.0):
                yy = top + f * (bot - top)
                cv.create_line(x0, yy, gx1, yy, fill=mix_color(c["bg"], c["fg"], 0.12))
            dec = 1 if hi - lo < 10 else 0
            cv.create_text(x1, top, text=fnum(hi, dec), anchor="ne", fill=c["dim"], font=(fam, 7))
            cv.create_text(x1, bot, text=fnum(lo, dec), anchor="se", fill=c["dim"], font=(fam, 7))
        for i, pts in series:
            xy = []
            for d, v in pts:
                xy += [tx(d), ty(v)]
            col = self.color(i, c)
            if len(series) == 1:
                cv.create_polygon([xy[0], bot] + xy + [xy[-2], bot], fill=mix_color(c["bg"], col, 0.18), outline="")
            cv.create_line(xy, fill=col, width=max(1, self.s(1.6)), smooth=False)
        if stats_h and series:
            p = [v for _d, v in series[0][1]]
            unit = ((self.app.last_states.get(ents[0]) or {}).get("attributes", {}).get("unit_of_measurement") or "")
            u = " " + unit if unit else ""
            yy = H - pad
            cv.create_text(x0, yy, text="min %s%s" % (fnum(min(p), 1), u), anchor="sw", fill=c["dim"], font=(fam, 7))
            cv.create_text((x0 + x1) // 2, yy, text="moy. %s%s" % (fnum(sum(p) / len(p), 1), u), anchor="s",
                           fill=c["dim"], font=(fam, 7))
            cv.create_text(x1, yy, text="max %s%s" % (fnum(max(p), 1), u), anchor="se", fill=c["dim"], font=(fam, 7))


class WidgetManager:
    def __init__(self, app):
        self.app = app
        self.widgets = {}
        self._job = None
        app.history.listeners.append(self.redraw_all)
        self._keep_bottom()

    def config(self):
        return self.app.cfg.setdefault("widgets", [])

    def sync(self):
        """Cree, met a jour ou ferme les fenetres d'apres la configuration."""
        ws = self.config()
        missing = [w for w in ws if not w.get("id")]
        for w in missing:
            w["id"] = str(uuid.uuid4())
        if missing:
            self._save()
        shown = [w for w in ws if not w.get("hidden") and w.get("entities")]
        ids = {w["id"] for w in shown}
        for wid in list(self.widgets):
            if wid not in ids:
                self.widgets.pop(wid).destroy()
        for i, w in enumerate(shown):
            dw = self.widgets.get(w["id"])
            if dw is None:
                try:
                    self.widgets[w["id"]] = DesktopWidget(self, w, i)
                except tk.TclError:
                    pass
            else:
                dw.index = i
                dw.apply(w)

    def redraw_all(self):
        for dw in self.widgets.values():
            dw.redraw()

    def on_state(self, eid):
        """Un capteur a change : on redessine les widgets concernes (au plus une fois par seconde)."""
        if self._job is None and any(eid in dw.w.get("entities", []) for dw in self.widgets.values()):
            self._job = self.app.root.after(1000, self._redraw_job)

    def _redraw_job(self):
        self._job = None
        self.redraw_all()

    def _keep_bottom(self):
        # Un clic ailleurs (bureau...) peut faire remonter un widget : on le renvoie sous les fenetres
        for dw in self.widgets.values():
            dw.to_bottom()
        self.app.root.after(5000, self._keep_bottom)

    def _save(self):
        try:
            save_config(self.app.cfg)
        except OSError as e:
            self.app.last_error = "config : %s" % e
        sw = self.app.settings_win
        if sw is not None and sw.win.winfo_exists():   # reglages ouverts : leur copie suit
            sw.cfg["widgets"] = copy.deepcopy(self.config())
            sw.saved["widgets"] = copy.deepcopy(self.config())

    def edit(self, wid, fn, sync=True):
        for w in self.config():
            if w.get("id") == wid:
                fn(w)
        self._save()
        if sync:
            self.sync()

    def add(self, entities):
        self.config().append({"id": str(uuid.uuid4()), "entities": list(entities), "style": "graph",
                              "hours": 24, "size": "medium"})
        self._save()
        self.sync()

    def remove(self, wid):
        self.app.cfg["widgets"] = [w for w in self.config() if w.get("id") != wid]
        self._save()
        self.sync()

    def set_all_hidden(self, hidden):
        for w in self.config():
            w["hidden"] = hidden
        self._save()
        self.sync()

    def title(self, w):
        ents = w.get("entities", [])
        if w.get("title"):
            return w["title"]
        if len(ents) == 1:
            st = self.app.last_states.get(ents[0]) or {}
            return st.get("attributes", {}).get("friendly_name") or ents[0]
        return "Capteurs (%d)" % len(ents)

    def numeric_entities(self):
        """Elements de la barre a valeur numerique (pour les ajouter a un widget)."""
        out = []
        for it in self.app.cfg.get("items", []):
            eid = it.get("entity_id", "")
            st = self.app.last_states.get(eid)
            if st and as_float(st.get("state")) is not None:
                out.append((eid, it.get("label") or st.get("attributes", {}).get("friendly_name") or eid))
        return out

    def menu(self, dw, x, y):
        w, wid = dw.w, dw.id
        m = tk.Menu(self.app.root, tearoff=0)
        keep = []                      # variables Tk des cases : a garder tant que le menu est ouvert

        def var(cls, v):
            x = cls(m, v)
            keep.append(x)
            return x
        m.add_command(label=self.title(w)[:50], state="disabled")
        m.add_separator()
        sub = tk.Menu(m, tearoff=0)
        for label, h in PERIODS:
            sub.add_radiobutton(label=label, value=h, variable=var(tk.IntVar, int(w.get("hours") or 24)),
                                command=lambda h=h: self.edit(wid, lambda w: w.update(hours=h)))
        m.add_cascade(label="Période", menu=sub)
        sub = tk.Menu(m, tearoff=0)
        for label, s in (("Petit", "small"), ("Moyen", "medium"), ("Grand", "large")):
            sub.add_radiobutton(label=label, value=s, variable=var(tk.StringVar, w.get("size") or "medium"),
                                command=lambda s=s: self.edit(wid, lambda w: w.update(size=s)))
        m.add_cascade(label="Taille", menu=sub)
        sub = tk.Menu(m, tearoff=0)
        for label, s in (("Graphique", "graph"), ("Valeur en grand", "value")):
            sub.add_radiobutton(label=label, value=s, variable=var(tk.StringVar, w.get("style") or "graph"),
                                command=lambda s=s: self.edit(wid, lambda w: w.update(style=s)))
        m.add_cascade(label="Affichage", menu=sub)
        m.add_checkbutton(label="Toujours au premier plan", variable=var(tk.BooleanVar, bool(w.get("on_top"))),
                          command=lambda: self.edit(wid, lambda w: w.update(on_top=not w.get("on_top"))))
        others = [(e, n) for e, n in self.numeric_entities() if e not in w.get("entities", [])]
        if others:
            sub = tk.Menu(m, tearoff=0)
            for e, n in others:
                sub.add_command(label=n[:50], command=lambda e=e: self.edit(
                    wid, lambda w: w.update(entities=w.get("entities", []) + [e])))
            m.add_cascade(label="Ajouter un capteur", menu=sub)
        if len(w.get("entities", [])) > 1:
            sub = tk.Menu(m, tearoff=0)
            for e in w.get("entities", []):
                sub.add_command(label=dw.name(e)[:50], command=lambda e=e: self.edit(
                    wid, lambda w: w.update(entities=[x for x in w.get("entities", []) if x != e])))
            m.add_cascade(label="Retirer un capteur", menu=sub)
        m.add_command(label="Remettre en haut à droite",
                      command=lambda: self.edit(wid, lambda w: (w.pop("win_x", None), w.pop("win_y", None))))
        m.add_separator()
        m.add_command(label="Masquer", command=lambda: self.edit(wid, lambda w: w.update(hidden=True)))
        m.add_command(label="Supprimer", command=lambda: self.remove(wid))
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()
