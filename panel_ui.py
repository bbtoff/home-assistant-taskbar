"""
Panneau : un seul bouton sur la barre des taches ouvre une liste verticale d'elements, juste au-dessus,
dans l'esprit des Parametres rapides de Windows 11 et du Centre de controle du Mac.
Les elements dont la zone est "panel" y sont ranges, par piece, dans des cartes arrondies.
Clic = action, curseur ou molette = reglage, appui long = carte de controle, clic droit = options.
"""
import ctypes
import threading
import time
import tkinter as tk
from ctypes import wintypes
from tkinter import font as tkfont

from card_ui import TOGGLE_DOMAINS, Btn, Card, Toggle, ago, derive_palette, fnum, mix, rrect, G_MINUS, G_PLUS
from ha_core import (ACTIVE_STATES, BATTERIES, CAMERA_DOMAINS, ICONS, card_light, card_palette, item_members,
                     parse_thresholds, picture_of)
from i18n import _
from palette import fold

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

LONG_PRESS_MS = 450
COL_MIN = 320            # largeur mini d'une colonne : panneau plus large = plusieurs colonnes
MIN_W, MAX_W = 300, 1800
DRAG_PX = 8              # deplacement qui transforme un appui en glisser (reordonner)
CAMERA_S = 3.0           # apercu d'une camera dans le panneau : une image toutes les 3 s
ERROR = "#e5534b"
OK = "#3fb950"


class _Display:
    """Ce que la barre afficherait pour un element (icone, texte, couleurs), sans widget : on reutilise
    Item.update avec un objet qui recoit le resultat."""

    def __init__(self, app, cfg):
        self.app, self.cfg = app, cfg
        self.entity_id = self.eid = cfg.get("entity_id", "")
        self.domain = self.entity_id.split(".", 1)[0]
        self.members = item_members(cfg)
        self.is_group = len(self.members) > 1
        self.rules = parse_thresholds(cfg.get("thresholds"))[0]
        self.out = None

    def set_badge(self, _t):
        pass

    def badge_for(self, _st):
        return ""

    def show(self, glyph, text, fg, icon_fg, anim=None):
        self.out = (glyph, text, fg, icon_fg)

    def compute(self, item_cls, states):
        self.out = None
        item_cls.update(self, states.get(self.entity_id), states)
        return self.out

    def subtitle(self, st):
        """Meme phrase que sous le titre de la carte (« Allumée · 70 % », « Chauffe · 19,5 °C »...)."""
        try:
            return Card.subtitle(self, st)
        except Exception:
            return ""


class _Proxy:
    """Ce qu'attend App.wheel() : entity_id, domain, show_pending()."""

    def __init__(self, panel, row):
        self.panel, self.row = panel, row
        self.entity_id = row["cfg"].get("entity_id", "")
        self.domain = self.entity_id.split(".", 1)[0]

    def show_pending(self, text):
        self.row["hold"] = time.monotonic() + 2.0
        self.row["val"].configure(text=text, fg=self.panel.c["accent"])


class _Skin:
    """Les widgets de card_ui (interrupteur, boutons) dessines sur le fond des cartes du panneau."""

    def __init__(self, panel, bg, surface):
        self._p = panel
        self.c = dict(panel.c, bg=bg, surface=surface)

    def __getattr__(self, name):
        return getattr(self._p, name)


class _Box:
    """Cadre aux coins arrondis (Tk ne sait pas arrondir un Frame) : un Canvas dessine le fond arrondi,
    le contenu (self.inner) est pose dessus, en retrait."""

    def __init__(self, parent, panel, color, pad=None, radius=None):
        self.panel = panel
        self.color = color
        self.pad = panel.s(5) if pad is None else pad
        self.radius = panel.s(10) if radius is None else radius
        self.cv = tk.Canvas(parent, bg=panel.c["bg"], highlightthickness=0, bd=0, height=10)
        self.inner = tk.Frame(self.cv, bg=color)
        self._win = self.cv.create_window(self.pad, self.pad, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self._redraw())
        self.cv.bind("<Configure>", lambda e: self._redraw())

    def _redraw(self):
        w = self.cv.winfo_width()
        if w <= 1:
            w = int(self.cv["width"]) if int(self.cv["width"]) > 1 else self.panel.iw
        h = self.inner.winfo_reqheight() + 2 * self.pad
        self.cv.itemconfigure(self._win, width=w - 2 * self.pad)
        if int(self.cv["height"]) != h:
            self.cv.configure(height=h)
        self.cv.delete("bg")
        rrect(self.cv, 0, 0, w - 1, h - 1, self.radius, fill=self.color, outline=self.color, tags="bg")
        self.cv.tag_lower("bg")


class _Bar:
    """Curseur fin (luminosite, vitesse, volume, position), envoye au relachement."""

    def __init__(self, parent, panel, skin, commit, key):
        s = panel.s
        self.panel, self.skin, self.commit, self.key = panel, skin, commit, key
        self.h = s(18)
        self.cv = tk.Canvas(parent, height=self.h, bg=skin.c["bg"], highlightthickness=0, bd=0, cursor="hand2")
        self.value = None
        self.cv.bind("<ButtonPress-1>", self._drag)
        self.cv.bind("<B1-Motion>", self._drag)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<Configure>", lambda e: self.draw())

    def _x2v(self, x):
        w = max(1, self.cv.winfo_width() - self.h)
        return max(1, min(100, round((x - self.h / 2) / w * 100)))

    def _drag(self, e):
        self.value = self._x2v(e.x)
        self.panel.hold(self.key, 4.0)
        self.draw()
        return "break"

    def _release(self, e):
        self.value = self._x2v(e.x)
        self.panel.hold(self.key, 4.0)
        self.draw()
        self.commit(self.value)
        return "break"

    def set(self, v):
        if self.panel.held(self.key):
            return
        if v != self.value:
            self.value = v
            self.draw()

    def draw(self):
        cv, c, s = self.cv, self.skin.c, self.panel.s
        cv.delete("all")
        w = cv.winfo_width()
        if w <= 1:
            return
        y, r = self.h / 2, self.h / 2
        x0, x1 = r, w - r
        cv.create_line(x0, y, x1, y, fill=mix(c["bg"], c["fg"], 0.22), width=s(4), capstyle="round")
        if self.value:
            xv = x0 + (x1 - x0) * self.value / 100.0
            cv.create_line(x0, y, xv, y, fill=c["accent"], width=s(4), capstyle="round")
            kr = s(7)
            cv.create_oval(xv - kr, y - kr, xv + kr, y + kr, fill=c["knob"], outline=c["border"])
            cv.create_oval(xv - s(3), y - s(3), xv + s(3), y + s(3), fill=c["accent"], outline="")


class Panel:
    WIDTH = 360

    def __init__(self, app, button, cfgs, fade=True):
        self.app, self.button = app, button
        self.cfgs = cfgs
        self.alive = True
        self.holds = {}
        self.rows = []
        self.sections = []
        self.k = app.root.winfo_fpixels("1i") / 96.0
        self.iw = self.s(self._cfg_num("panel_width", self.WIDTH, MIN_W, MAX_W))
        ph = self.app.cfg.get("panel_height")
        self.h_cap = self.s(self._cfg_num("panel_height", 400, 140, 4000)) if ph else None   # hauteur de la liste
        self._rs = None          # redimensionnement en cours
        self._drag = None        # element ou piece en cours de deplacement
        self._target = None
        self.ind = None
        light = card_light(app.cfg, getattr(app, "light", False))
        base, self.radius = card_palette(app.cfg, app.colors, light)
        self.c = c = derive_palette(base)
        self.card_c = mix(c["bg"], c["fg"], 0.06)        # fond des cartes de section
        self.line_c = mix(c["bg"], c["fg"], 0.12)        # separateurs
        self.chip_off = mix(c["bg"], c["fg"], 0.14)      # pastille d'une icone eteinte
        self.skin = _Skin(self, self.card_c, mix(c["bg"], c["fg"], 0.16))
        self._fonts()
        self._press = None
        self._job = None
        self._menu_open = False

        win = self.win = tk.Toplevel(app.root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=c["border"])
        body = tk.Frame(win, bg=c["bg"], padx=self.s(14), pady=self.s(14))
        body.pack(padx=1, pady=1, fill="both", expand=True)
        self.body = body
        s = self.s
        # bords du panneau : tirer pour l'agrandir (haut, gauche, droite et coins du haut)
        body.bind("<Motion>", self._edge_cursor)
        body.bind("<Leave>", lambda e: self._rs is None and body.configure(cursor=""))
        body.bind("<ButtonPress-1>", self._rs_start)
        body.bind("<B1-Motion>", self._rs_move)
        body.bind("<ButtonRelease-1>", self._rs_end)
        body.bind("<Double-Button-1>", self._rs_reset)

        # en-tete : titre, etat de la connexion, reglages
        head = tk.Frame(body, bg=c["bg"])
        head.pack(fill="x")
        tcol = tk.Frame(head, bg=c["bg"])
        tcol.pack(side="left")
        tk.Label(tcol, text=app.cfg.get("panel_title") or _("Maison"), bg=c["bg"], fg=c["fg"],
                 font=self.f_head).pack(anchor="w")
        srow = tk.Frame(tcol, bg=c["bg"])
        srow.pack(anchor="w")
        self.dot = tk.Label(srow, text="●", bg=c["bg"], fg=OK, font=self.f_small)
        self.dot.pack(side="left")
        self.status = tk.Label(srow, text="", bg=c["bg"], fg=c["dim"], font=self.f_small)
        self.status.pack(side="left", padx=(s(4), 0))
        gear = Btn(head, self, glyph=ICONS["gear"][0], round_=True, height=s(30),
                   command=lambda: (self.close(), app.open_settings()))
        gear.pack(side="right")
        self.opac_btn = Btn(head, self, glyph="", round_=True, height=s(30), command=self.toggle_opacity)
        self.opac_btn.pack(side="right", padx=(0, s(6)))
        self.head = head
        self.opac_box = None

        # recherche
        sb = _Box(body, self, self.card_c, pad=s(7), radius=s(8))
        sb.cv.configure(width=self.iw)
        sb.cv.pack(fill="x", pady=(s(12), s(4)))
        self.sb = sb
        tk.Label(sb.inner, text="", bg=self.card_c, fg=c["dim"], font=(self.ifont, 10)).pack(
            side="left", padx=(s(4), 0))
        self.v_find = tk.StringVar()
        self.entry = tk.Entry(sb.inner, textvariable=self.v_find, relief="flat", bd=0, bg=self.card_c, fg=c["fg"],
                              insertbackground=c["fg"], font=self.f_text)
        self.entry.pack(side="left", fill="x", expand=True, padx=(s(8), 0))
        self.v_find.trace_add("write", lambda *a: self.filter())

        # liste (defile si elle est trop haute)
        self.canvas = tk.Canvas(body, bg=c["bg"], highlightthickness=0, bd=0, width=self.iw, height=10)
        self.canvas.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=c["bg"])
        self._cwin = self.canvas.create_window(0, 0, window=self.inner, anchor="nw", width=self.iw)
        self._build(cfgs)

        # pied
        foot = tk.Frame(body, bg=c["bg"])
        foot.pack(fill="x", pady=(s(10), 0))
        for text, side, cmd in ((_("Réglages"), "left", lambda: (self.close(), app.open_settings())),
                                (_("Ouvrir dans Home Assistant  ↗"), "right", self._open_ha)):
            lb = tk.Label(foot, text=text, bg=c["bg"], fg=c["dim"], font=self.f_small, cursor="hand2")
            lb.pack(side=side)
            lb.bind("<Button-1>", lambda e, cmd=cmd: cmd())
            lb.bind("<Enter>", lambda e, lb=lb: lb.configure(fg=c["fg"]))
            lb.bind("<Leave>", lambda e, lb=lb: lb.configure(fg=c["dim"]))

        self.refresh()
        win.update_idletasks()
        self.hwnd = user32.GetAncestor(win.winfo_id(), 2)
        ex = user32.GetWindowLongW(self.hwnd, -20)
        user32.SetWindowLongW(self.hwnd, -20, (ex | 0x80) & ~0x40000)       # pas de bouton dans la barre
        try:                                                                 # coins arrondis Windows 11
            pref = ctypes.c_int(1 if self.radius <= 3 else 2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(self.hwnd), 33, ctypes.byref(pref), 4)
        except Exception:
            pass
        self.place()
        win.attributes("-alpha", 0.0 if fade else self.opacity())
        win.deiconify()
        if fade:
            self._fade(1)
        user32.SetForegroundWindow(self.hwnd)
        win.focus_force()
        self.entry.focus_set()
        win.bind("<Escape>", lambda e: self.close())
        win.bind("<MouseWheel>", self._scroll)
        self._was_fg = False
        self._mouse = self._mouse_down()
        if hasattr(app, "history"):
            app.history.listeners.append(self.draw_sparks)
        self._loop()

    # ---------------- bases (memes noms que la carte : les widgets de card_ui s'en servent)
    def s(self, v):
        return int(round(v * self.k))

    def _fonts(self):
        app = self.app
        fam = app.cfg.get("font", "Segoe UI")
        fams = set(tkfont.families(app.root))
        semi = "Segoe UI Semibold" if fam == "Segoe UI" and "Segoe UI Semibold" in fams else None
        self.f_head = (semi, 14) if semi else (fam, 14, "bold")
        self.f_title = (semi, 12) if semi else (fam, 12, "bold")
        self.f_text = (fam, 10)
        self.f_text_b = (semi, 10) if semi else (fam, 10, "bold")
        self.f_small = (fam, 8)
        self.f_section = (semi, 9) if semi else (fam, 9, "bold")
        self.f_btn = (fam, 9)
        self.f_btn_m = tkfont.Font(root=app.root, font=self.f_btn)
        self.ifont = app.icon_font or fam

    def _cfg_num(self, key, default, lo, hi):
        try:
            return max(lo, min(hi, int(self.app.cfg.get(key) or default)))
        except (TypeError, ValueError):
            return default

    def hold(self, key, sec=3.0):
        self.holds[key] = time.monotonic() + sec

    def held(self, key):
        return self.holds.get(key, 0) > time.monotonic()

    # ---------------- construction
    def _build(self, cfgs):
        app, c, s = self.app, self.c, self.s
        areas = getattr(app, "areas", {}) or {}
        groups, order = {}, []
        for cfg in cfgs:
            area = ""
            if app.cfg.get("panel_by_area", True) and areas:
                area = areas.get(cfg.get("entity_id", ""), "") or _("Autres")
            if area not in groups:
                groups[area] = []
                order.append(area)
            groups[area].append(cfg)
        if order == [_("Autres")]:            # aucune piece connue : pas de titre de section
            groups = {"": groups[order[0]]}
            order = [""]
        elif _("Autres") in order:            # les elements sans piece a la fin
            order.remove(_("Autres"))
            order.append(_("Autres"))
        # colonnes : autant que la largeur le permet
        gap = s(12)
        n = self.ncols = max(1, min(6, (self.iw + gap) // (s(COL_MIN) + gap)))
        self.col_w = (self.iw - (n - 1) * gap) // n
        for i in range(8):
            self.inner.columnconfigure(i, weight=0, uniform="")
        cols = []
        for i in range(n):
            f = tk.Frame(self.inner, bg=c["bg"])
            f.grid(row=0, column=i, sticky="new", padx=(0 if i == 0 else gap, 0))
            self.inner.columnconfigure(i, weight=1, uniform="col")
            cols.append(f)
        self.empty = tk.Label(self.inner, text="", bg=c["bg"], fg=c["dim"], font=self.f_text)

        def est(cfg):                       # hauteur estimee d'une ligne (pour equilibrer les colonnes)
            dom = cfg.get("entity_id", "").split(".", 1)[0]
            h = s(50)
            if dom in ("light", "fan", "cover", "media_player"):
                h += s(26)
            if dom in CAMERA_DOMAINS:
                h += int(self.col_w * 0.5625) + s(10)
            return h
        # blocs : une piece = un bloc ; une seule piece sur plusieurs colonnes = decoupee
        blocks = []
        if len(order) == 1 and n > 1:
            lst = groups[order[0]]
            total = sum(est(x) for x in lst)
            chunk, acc = [], 0
            for x in lst:
                if chunk and acc + est(x) / 2 > total / n * (len(blocks) + 1) and len(blocks) < n - 1:
                    blocks.append((order[0], chunk, not blocks))
                    chunk = []
                chunk.append(x)
                acc += est(x)
            blocks.append((order[0], chunk, not blocks))
            place = list(range(len(blocks)))
        else:
            blocks = [(area, groups[area], True) for area in order]
            heights = [0] * n
            place = []
            for area, lst, _h in blocks:
                k = heights.index(min(heights))
                place.append(k)
                heights[k] += sum(est(x) for x in lst) + (s(32) if area else 0)
        for (area, lst, with_head), k in zip(blocks, place):
            col = cols[k]
            head = None
            if area and with_head:
                head = tk.Label(col, text=area[:1].upper() + area[1:], bg=c["bg"], fg=c["dim"],
                                font=self.f_section, anchor="w", cursor="fleur")
                head.pack(fill="x", padx=s(4), pady=(s(10), s(4)))
            box = _Box(col, self, self.card_c, pad=s(4))
            box.cv.pack(fill="x", pady=(0 if head is not None else s(8), 0))
            rows = []
            for i, cfg in enumerate(lst):
                r = self._row(box.inner, cfg, first=(i == 0))
                r["area"] = area
                rows.append(r)
            sec = (head, rows, box)
            self.sections.append(sec)
            if head is not None:
                head.bind("<ButtonPress-1>", lambda e, sec=sec: self._sec_down(sec, e))
                head.bind("<B1-Motion>", lambda e, sec=sec: self._drag_motion(("sec", sec), e))
                head.bind("<ButtonRelease-1>", lambda e: self._drop())
                head.bind("<MouseWheel>", self._scroll)

    def rebuild(self):
        """Reconstruit la liste (nouvel ordre, nouveau nombre de colonnes)."""
        if not self.alive:
            return
        top = self.canvas.yview()[0]
        for row in self.rows:
            row["dead"] = True
        for w in self.inner.winfo_children():
            w.destroy()
        self.ind = None
        self.rows, self.sections = [], []
        self._build(self.cfgs)
        self.filter()
        self.refresh()
        self.canvas.yview_moveto(top)

    def _row(self, parent, cfg, first=False):
        app, c, s = self.app, self.c, self.s
        bg = self.card_c
        eid = cfg.get("entity_id", "")
        dom = eid.split(".", 1)[0]
        box = tk.Frame(parent, bg=bg)
        box.pack(fill="x")
        if not first:                                   # separateur, en retrait apres la pastille
            tk.Frame(box, bg=self.line_c, height=1).pack(fill="x", padx=(s(54), s(10)))
        r = tk.Frame(box, bg=bg, cursor="hand2", padx=s(10), pady=s(7))
        r.pack(fill="x")
        chip = tk.Canvas(r, width=s(34), height=s(34), bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        chip.pack(side="left")
        txt = tk.Frame(r, bg=bg, cursor="hand2")
        txt.pack(side="left", fill="x", expand=True, padx=(s(10), 0))
        st = app.last_states.get(eid) or {}
        label = cfg.get("label") or st.get("attributes", {}).get("friendly_name") or eid
        nm = tk.Label(txt, text=label, bg=bg, fg=c["fg"], font=self.f_text_b, anchor="w", cursor="hand2")
        nm.pack(anchor="w", fill="x")
        sub = tk.Label(txt, text="", bg=bg, fg=c["dim"], font=self.f_small, anchor="w", cursor="hand2")
        sub.pack(anchor="w", fill="x")
        row = {"cfg": cfg, "box": box, "frame": r, "chip": chip, "name": nm, "sub": sub, "label": label,
               "hold": 0.0, "disp": _Display(app, cfg), "tog": None, "spark": None, "cam": None, "cam_img": None,
               "cam_err": None, "bar": None, "bar_kind": None, "dom": dom}
        members = item_members(cfg)
        if dom in TOGGLE_DOMAINS or len(members) > 1:
            row["tog"] = Toggle(r, self.skin, lambda on, cfg=cfg: self._toggle(cfg, on), key="t:" + eid)
            row["tog"].pack(side="right", padx=(s(8), 0))
        elif dom in ("climate", "water_heater"):
            for d, g in ((1, G_PLUS), (-1, G_MINUS)):
                Btn(r, self.skin, glyph=g, round_=True, height=s(26),
                    command=lambda d=d, row=row: app.wheel(_Proxy(self, row), d)).pack(side="right", padx=(s(4), 0))
        val = tk.Label(r, text="", bg=bg, fg=c["fg"], font=self.f_title, cursor="hand2")
        val.pack(side="right")
        row["val"] = val
        widgets = [r, chip, txt, nm, sub, val]
        if cfg.get("sparkline"):
            sp = tk.Canvas(r, width=s(54), height=s(22), bg=bg, highlightthickness=0, bd=0, cursor="hand2")
            sp.pack(side="right", padx=(0, s(10)))
            row["spark"] = sp
            widgets.append(sp)
            if hasattr(app, "history"):
                app.history.request(eid, 6)
        # curseur sous la ligne : luminosite, vitesse, position, volume
        kind = {"light": "brightness", "fan": "percentage", "cover": "position",
                "media_player": "volume"}.get(dom) if len(members) == 1 else None
        if kind:
            holder = tk.Frame(box, bg=bg)
            row["bar_holder"] = holder
            row["bar"] = _Bar(holder, self, self.skin, lambda v, row=row: self._commit_bar(row, v), "b:" + eid)
            row["bar"].cv.pack(fill="x", padx=(s(54), s(12)), pady=(0, s(8)))
            row["bar_kind"] = kind
        if dom in CAMERA_DOMAINS:
            cam = tk.Label(box, text=_("Chargement de l'image…"), bg=mix(bg, c["fg"], 0.08), fg=c["dim"],
                           font=self.f_small, height=5, cursor="hand2")
            cam.pack(fill="x", padx=s(10), pady=(0, s(10)))
            row["cam"] = cam
            widgets.append(cam)
            threading.Thread(target=self._fetch_cam, args=(app.ha, eid, row), daemon=True).start()
        row["widgets"] = widgets
        for w in widgets:
            w.bind("<ButtonPress-1>", lambda e, row=row: self._down(row, e))
            w.bind("<B1-Motion>", lambda e, row=row: self._drag_motion(("row", row), e))
            w.bind("<ButtonRelease-1>", lambda e, row=row: self._up(row))
            w.bind("<MouseWheel>", lambda e, row=row: self._wheel(row, e))
            w.bind("<Enter>", lambda e, row=row: self._hover(row, True))
            w.bind("<Leave>", lambda e, row=row: self._hover(row, False))
            w.bind("<Button-3>", lambda e, row=row: self._menu(row, e))
        self.rows.append(row)
        return row

    # ---------------- valeurs
    def refresh(self):
        if not self.alive:
            return
        Item = self.app.item_class          # pas d'import de ha_taskbar : il tourne deja comme programme principal
        app, c = self.app, self.c
        bar = app.colors
        states = app.last_states

        def tr(col):
            col = str(col).lower()
            if col == str(bar["on"]).lower():
                return c["accent"]
            if col == str(bar["dim"]).lower():
                return c["dim"]
            if col == str(bar["error"]).lower():
                return ERROR
            if col == str(bar["fg"]).lower():
                return c["fg"]
            return col
        active = 0
        for row in self.rows:
            cfg = row["cfg"]
            eid = cfg.get("entity_id", "")
            st = states.get(eid)
            try:
                out = row["disp"].compute(Item, states)
            except Exception:
                out = None
            if not out:
                continue
            glyph, text, fg, icon_fg = out
            members = item_members(cfg)
            on = any((states.get(m) or {}).get("state") in ACTIVE_STATES for m in members) \
                and row["dom"] not in ("sensor", "binary_sensor", "weather", "camera", "image")
            if on:
                active += 1
            unavailable = st is not None and st.get("state") in ("unavailable", "unknown") and eid != BATTERIES
            self._chip(row, glyph, on, tr(icon_fg), unavailable, picture_of(st) if len(members) == 1 else None)
            # sous-titre : la phrase de la carte (etat detaille)
            if eid == BATTERIES:
                sub = (_("%s pile(s) faible(s)") % text) if text.isdigit() and text != "0" else _("Piles chargées")
            elif st is None:
                sub = _("Entité introuvable")
            elif row["dom"] in ("sensor", "binary_sensor", "input_number", "number") and st.get("last_changed")                     and not unavailable:
                sub = _("Modifié ") + ago(st["last_changed"])
            else:
                sub = row["disp"].subtitle(st)
                at = st.get("attributes", {})
                if row["dom"] == "media_player" and at.get("media_title") and st.get("state") in ("playing", "paused"):
                    sub = " · ".join(x for x in (at.get("media_title"), at.get("media_artist")) if x)
            if row["cam_err"]:
                row["sub"].configure(text=row["cam_err"], fg=ERROR)
            else:
                row["sub"].configure(text=sub, fg=ERROR if unavailable else c["dim"])
            # valeur a droite : pour un interrupteur ou un appareil, le sous-titre suffit
            show = text
            if row["tog"] is not None or row["dom"] in ("light", "fan", "switch", "cover", "media_player",
                                                         "camera", "image", "weather", "vacuum", "lock"):
                show = ""
            if row["dom"] in ("climate", "water_heater"):
                t = (st or {}).get("attributes", {}).get("temperature")
                show = ("%s°" % fnum(t, 1)) if t is not None else ""
            if eid == BATTERIES:
                show = ""
            if time.monotonic() >= row["hold"]:
                col = tr(fg)
                row["val"].configure(text=show, fg=c["fg"] if col == c["dim"] else col)
            tog = row["tog"]
            if tog is not None and not self.held(tog.key):
                tog.set(any((states.get(m) or {}).get("state") == "on" for m in members))
            self._update_bar(row, st)
        if app.offline:
            self.dot.configure(fg=ERROR)
            self.status.configure(text=_("Home Assistant hors ligne"))
        else:
            live = bool(getattr(app, "rt_connected", False))
            self.dot.configure(fg=OK if live else c["dim"])
            text = _("En direct") if live else _("Connecté")
            if active:
                text += " · " + _("%d allumé(s)") % active
            self.status.configure(text=text)
        self.draw_sparks()
        self.place()

    def _chip(self, row, glyph, on, color, unavailable, picture=None):
        cv, s, c = row["chip"], self.s, self.c
        d = s(34)
        if picture:                                   # photo d'une personne, pochette du titre en cours...
            shape = "circle" if row["dom"] in ("person", "device_tracker") else "rounded"

            def show(png, u=picture):
                if not self.alive or row.get("dead") or not png or row.get("pic_url") != u:
                    return
                try:
                    row["pic"] = tk.PhotoImage(master=self.app.root, data=png)
                except tk.TclError:
                    return
                cv.delete("all")
                cv.create_image(d / 2, d / 2, image=row["pic"])
            if row.get("pic_url") != picture or row.get("pic") is None:
                row["pic_url"], row["pic"] = picture, None
                png = self.app.pictures.get(picture, d, d, shape, show)
                if png:
                    show(png)
                    return
            else:
                return                                # l'image est deja affichee
        else:
            row["pic_url"] = row["pic"] = None
        cv.delete("all")
        if on:
            fill, fg = c["accent"], c["accent_fg"]
        else:
            fill = self.chip_off
            fg = c["dim"] if unavailable else (color if color not in (c["fg"], c["dim"]) else c["fg"])
        cv.create_oval(1, 1, d - 1, d - 1, fill=fill, outline=fill)
        cv.create_text(d / 2, d / 2 + 1, text=glyph or "", fill=fg, font=(self.ifont, 13))

    def _update_bar(self, row, st):
        bar = row["bar"]
        if bar is None:
            return
        a = (st or {}).get("attributes", {})
        state = (st or {}).get("state")
        kind = row["bar_kind"]
        v = None
        if kind == "brightness" and state == "on" and a.get("brightness") is not None:
            v = round(a["brightness"] * 100 / 255)
        elif kind == "percentage" and state == "on" and a.get("percentage"):
            v = a["percentage"]
        elif kind == "position" and a.get("current_position") is not None:
            v = a["current_position"]
        elif kind == "volume" and a.get("volume_level") is not None and state not in ("off", "standby"):
            v = round(a["volume_level"] * 100)
        holder = row["bar_holder"]
        if v is None and not self.held(bar.key):
            if holder.winfo_ismapped():
                holder.pack_forget()
            return
        if not holder.winfo_ismapped():
            holder.pack(fill="x", after=row["frame"])
        bar.set(v)

    def _commit_bar(self, row, v):
        eid = row["cfg"].get("entity_id", "")
        kind = row["bar_kind"]
        call = self.app.call_service
        if kind == "brightness":
            call("light.turn_on", {"entity_id": eid, "brightness_pct": int(v)})
        elif kind == "percentage":
            call("fan.set_percentage", {"entity_id": eid, "percentage": int(v)})
        elif kind == "position":
            call("cover.set_cover_position", {"entity_id": eid, "position": int(v)})
        elif kind == "volume":
            call("media_player.volume_set", {"entity_id": eid, "volume_level": round(v / 100.0, 2)})

    def schedule_refresh(self):
        if self._job is None and self.alive:
            self._job = self.app.root.after(150, self._do_refresh)

    def _do_refresh(self):
        self._job = None
        self.refresh()

    def draw_sparks(self):
        hist = getattr(self.app, "history", None)
        if hist is None or not self.alive:
            return
        for row in self.rows:
            cv = row["spark"]
            if cv is None:
                continue
            vals = hist.values(row["cfg"].get("entity_id", ""), 6)
            cv.delete("all")
            if len(vals) < 2:
                continue
            w, h = int(cv["width"]), int(cv["height"])
            lo, hi = min(vals), max(vals)
            span = (hi - lo) or 1.0
            pts = []
            for i, v in enumerate(vals):
                pts += [i * (w - 2) / (len(vals) - 1) + 1, h - 3 - (v - lo) / span * (h - 6)]
            cv.create_line(pts, fill=self.c["accent"], width=max(1, self.s(1.5)), smooth=True)

    # ---------------- camera
    def _fetch_cam(self, ha, eid, row):
        import imaging
        import urllib.error
        while self.alive and not row.get("dead"):
            w = self.col_w - self.s(28)
            try:
                png, _w, _h = imaging.to_png(ha.camera_image(eid), w, int(w * 0.5625))
                if row.get("dead"):
                    return
                self.app.root.after(0, lambda png=png: self._show_cam(row, png))
                delay = CAMERA_S
            except urllib.error.HTTPError as e:
                msg = _("Caméra indisponible dans Home Assistant") if e.code in (404, 500, 503) \
                    else _("Image indisponible : %s") % e.code
                self.app.root.after(0, lambda msg=msg: self._cam_error(row, msg))
                delay = 15.0
            except Exception as e:
                msg = _("Image indisponible : %s") % str(getattr(e, "reason", e))[:60]
                self.app.root.after(0, lambda msg=msg: self._cam_error(row, msg))
                delay = 8.0
            end = time.monotonic() + delay
            while self.alive and not row.get("dead") and time.monotonic() < end:
                time.sleep(0.1)

    def _show_cam(self, row, png):
        if not self.alive or row.get("dead"):
            return
        try:
            img = tk.PhotoImage(master=self.app.root, data=png)
            row["cam_img"] = img
            row["cam_err"] = None
            row["cam"].configure(image=img, text="", height=img.height(), width=img.width())
            self.schedule_refresh()
        except tk.TclError:
            pass

    def _cam_error(self, row, msg):
        if not self.alive or row.get("dead"):
            return
        row["cam_err"] = msg
        if row["cam_img"] is None:
            row["cam"].configure(text=msg)
        row["sub"].configure(text=msg, fg=ERROR)

    # ---------------- actions
    def _toggle(self, cfg, on):
        members = item_members(cfg)
        if len(members) > 1:
            self.app.call_service("homeassistant.turn_%s" % ("on" if on else "off"), {"entity_id": members})
        else:
            eid = cfg.get("entity_id", "")
            self.app.call_service("%s.turn_%s" % (eid.split(".", 1)[0], "on" if on else "off"), {"entity_id": eid})

    def _down(self, row, e=None):
        self._cancel_press()
        self._press_xy = (e.x_root, e.y_root) if e is not None else None
        self._press = (row, self.app.root.after(LONG_PRESS_MS, lambda: self._long(row)))

    def _cancel_press(self):
        if self._press is not None:
            self.app.root.after_cancel(self._press[1])
        self._press = None

    def _up(self, row):
        if self._drag is not None:
            self._drop()
            return
        if self._press is None or self._press[0] is not row:
            return
        self._cancel_press()
        cfg = row["cfg"]
        if cfg.get("entity_id") == BATTERIES or row["dom"] in CAMERA_DOMAINS or not self.app.click_item(cfg):
            self._card(row)

    def _long(self, row):
        self._press = None
        self._card(row)

    def _card(self, row):
        cfg = row["cfg"]
        self.close()
        self.app.open_card(cfg, near=self.button)

    def _wheel(self, row, e):
        d = 1 if e.delta > 0 else -1
        before = dict(self.app._wheel)
        self.app.wheel(_Proxy(self, row), d)
        if self.app._wheel == before:
            self._scroll(e)              # rien a regler sur cette ligne : on fait defiler la liste
        return "break"

    def _scroll(self, e):
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        return "break"

    def _hover(self, row, on):
        row["name"].configure(fg=self.c["accent"] if on else self.c["fg"])

    def _menu(self, row, e):
        app = self.app
        cfg = row["cfg"]
        i = next((n for n, it in enumerate(app.cfg.get("items", [])) if it is cfg), None)
        m = tk.Menu(app.root, tearoff=0)
        m.add_command(label=row["label"][:50], state="disabled")
        m.add_command(label=_("Ouvrir la carte"), command=lambda: self._card(row))
        if i is not None:
            m.add_command(label=_("Modifier cet élément…"), command=lambda: (self.close(), app.open_settings(select=i)))
            m.add_separator()
            m.add_command(label=_("Mettre sur la barre (zone gauche)"),
                          command=lambda: (self.close(), app.set_zone(i, "left")))
            m.add_command(label=_("Mettre sur la barre (zone droite)"),
                          command=lambda: (self.close(), app.set_zone(i, "right")))
        if app.cfg.get("panel_width") or app.cfg.get("panel_height"):
            m.add_separator()
            m.add_command(label=_("Taille du panneau par défaut"), command=self.reset_size)
        self._menu_open = True
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            self._menu_open = False
            m.grab_release()

    # ---------------- recherche
    def filter(self):
        words = fold(self.v_find.get()).split()
        shown = 0
        for head, rows, box in self.sections:
            if head is not None:
                head.pack_forget()
            box.cv.pack_forget()
            vis = []
            for row in rows:
                ok = all(w in fold(row["label"] + " " + row["cfg"].get("entity_id", "")) for w in words)
                row["box"].pack_forget()
                if ok:
                    vis.append(row)
            if not vis:
                continue
            if head is not None:
                head.pack(fill="x", padx=self.s(4), pady=(self.s(10), self.s(4)))
            box.cv.pack(fill="x", pady=(0 if head is not None else self.s(8), 0))
            for row in vis:
                row["box"].pack(fill="x")
            shown += len(vis)
        if not shown:
            self.empty.configure(text=_("Aucun élément ne correspond.") if words else _("Le panneau est vide."))
            self.empty.grid(row=1, column=0, columnspan=self.ncols, pady=self.s(16))
        else:
            self.empty.grid_forget()
        self.place()

    # ---------------- fenetre
    def place(self):
        if not self.alive:
            return
        app = self.app
        self.win.update_idletasks()
        anchor = app.anchor_for(self.button if self.button in app.items else None)
        if anchor is None:
            return
        cx, top, xmin, xmax = anchor
        mx, my, mw, mh = app.monitor_rect()
        others = self.win.winfo_reqheight() - int(self.canvas["height"])
        cap = int(mh * 0.75) - others if self.h_cap is None else min(self.h_cap, mh - others - self.s(40))
        list_h = min(self.inner.winfo_reqheight(), max(self.s(140), cap))
        if int(self.canvas["height"]) != list_h:
            self.canvas.configure(height=list_h)
            self.win.update_idletasks()
        self.canvas.configure(scrollregion=(0, 0, self.iw, self.inner.winfo_reqheight()))
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        x = self._x_for(w, anchor)
        y = top - self.s(12) - h
        geo = (x, y, w, h)
        if geo != getattr(self, "_geo", None):
            self._geo = geo
            self.win.geometry("%dx%d+%d+%d" % (w, h, x, y))
            if getattr(self, "hwnd", None):
                user32.SetWindowPos(self.hwnd, -1, x, y, w, h, 0x0010)

    def _x_for(self, w, anchor):
        cx, _top, xmin, xmax = anchor
        return max(xmin + self.s(8), min(xmax - self.s(8) - w, cx - w // 2))

    # ---------------- taille : tirer les bords
    def _edge(self, e):
        pad = self.s(14)
        w = self.body.winfo_width()
        t = e.y < pad
        l, r = e.x < pad, e.x > w - pad
        return ("t" if t else "") + ("l" if l else "r" if r else "")

    def _edge_cursor(self, e):
        if self._rs is not None:
            return
        cur = {"t": "sb_v_double_arrow", "l": "sb_h_double_arrow", "r": "sb_h_double_arrow",
               "tl": "size_nw_se", "tr": "size_ne_sw"}.get(self._edge(e), "")
        if str(self.body.cget("cursor")) != cur:
            self.body.configure(cursor=cur)

    def _rs_start(self, e):
        edge = self._edge(e)
        self._rs = edge or None

    def _rs_move(self, e):
        if not self._rs:
            return
        app = self.app
        anchor = app.anchor_for(self.button if self.button in app.items else None)
        if anchor is None:
            return
        mx, my, mw, mh = app.monitor_rect()
        x_m, y_m = e.x_root, e.y_root
        chrome = self.win.winfo_reqwidth() - self.iw          # marges du panneau autour de la liste
        if "l" in self._rs or "r" in self._rs:
            lo, hi = self.s(MIN_W), min(self.s(MAX_W), mw - self.s(24) - chrome)
            left = "l" in self._rs
            while lo < hi:                                      # largeur qui met le bord sous la souris
                mid = (lo + hi) // 2
                x = self._x_for(mid + chrome, anchor)
                edge = x if left else x + mid + chrome
                if (edge > x_m) if left else (edge < x_m):
                    lo = mid + 1
                else:
                    hi = mid
            self.set_width(lo)
        if "t" in self._rs:
            others = self.win.winfo_reqheight() - int(self.canvas["height"])
            self.h_cap = max(self.s(140), anchor[1] - self.s(12) - y_m - others)
        self.place()

    def set_width(self, w):
        if w == self.iw:
            return
        self.iw = w
        self.canvas.configure(width=w)
        self.canvas.itemconfigure(self._cwin, width=w)
        self.sb.cv.configure(width=w)
        if self.opac_box is not None:
            self.opac_box.cv.configure(width=w)
        gap = self.s(12)
        n = max(1, min(6, (w + gap) // (self.s(COL_MIN) + gap)))
        if n != self.ncols:
            self.rebuild()
        else:
            self.col_w = (w - (n - 1) * gap) // n

    def _rs_end(self, e):
        if not self._rs:
            return
        edge, self._rs = self._rs, None
        kv = {"panel_width": round(self.iw / self.k)}
        if "t" in edge:
            kv["panel_height"] = round(self.h_cap / self.k)
        self._save_cfg(kv)

    def _rs_reset(self, e):
        """Double-clic sur un bord : taille par defaut."""
        if not self._edge(e):
            return
        self._rs = None
        self.h_cap = None
        self.set_width(self.s(self.WIDTH))
        self.place()
        self._save_cfg({"panel_width": None, "panel_height": None})

    def reset_size(self):
        self.h_cap = None
        self.set_width(self.s(self.WIDTH))
        self.place()
        self._save_cfg({"panel_width": None, "panel_height": None})

    def _save_cfg(self, kv):
        """Enregistre des reglages du panneau (None = retire la cle), y compris dans les Reglages ouverts."""
        import ha_core

        def put(cfg):
            for k, v in kv.items():
                if v is None:
                    cfg.pop(k, None)
                else:
                    cfg[k] = v
        put(self.app.cfg)
        sw = getattr(self.app, "settings_win", None)
        if sw is not None and getattr(sw, "cfg", None) is not None:
            put(sw.cfg)
        try:
            cfg = ha_core.load_config()
            put(cfg)
            ha_core.save_config(cfg)
        except OSError:
            pass

    # ---------------- reordonner : glisser un element ou le titre d'une piece
    def _sec_down(self, sec, e):
        self._cancel_press()
        self._press_xy = (e.x_root, e.y_root)
        self._drag = None

    def _drag_motion(self, what, e):
        s = self.s
        if self._drag is None:
            xy = getattr(self, "_press_xy", None)
            if xy is None or (abs(e.x_root - xy[0]) < s(DRAG_PX) and abs(e.y_root - xy[1]) < s(DRAG_PX)):
                return
            if what[0] == "row" and (self._press is None or self._press[0] is not what[1]):
                return
            self._cancel_press()
            self._drag = what
            self._target = None
            if what[0] == "row":
                what[1]["name"].configure(fg=self.c["accent"])
            else:
                what[1][0].configure(fg=self.c["accent"])
        # defilement automatique pres des bords de la liste
        cy = self.canvas.winfo_rooty()
        if e.y_root < cy + s(24):
            self.canvas.yview_scroll(-1, "units")
        elif e.y_root > cy + self.canvas.winfo_height() - s(24):
            self.canvas.yview_scroll(1, "units")
        self._find_target(e.x_root, e.y_root)
        return "break"

    @staticmethod
    def _rect(w):
        return w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height()

    def _find_target(self, x, y):
        kind, src = self._drag
        best = None
        if kind == "row":
            for r in self.rows:
                if r.get("area") != src.get("area") or not r["box"].winfo_ismapped():
                    continue
                rx, ry, rw, rh = self._rect(r["box"])
                if rx <= x < rx + rw and ry - 2 <= y < ry + rh + 2:
                    best = (r, y < ry + rh / 2, r["box"])
                    break
        else:
            for sec in self.sections:
                head, rows, box = sec
                if head is None or not head.winfo_ismapped():
                    continue
                hx, hy, hw, _hh = self._rect(head)
                bx, by, bw, bh = self._rect(box.cv)
                if hx <= x < hx + hw and hy <= y < by + bh:
                    best = (sec, y < (hy + by + bh) / 2, None)
                    break
        if best is None:
            return
        self._target = best[:2]
        # trait de couleur a l'endroit ou l'element sera pose
        if kind == "row":
            ref = best[2]
            top = ref.winfo_rooty() if best[1] else ref.winfo_rooty() + ref.winfo_height()
            left, width = ref.winfo_rootx(), ref.winfo_width()
        else:
            head, _rows, box = best[0]
            top = head.winfo_rooty() if best[1] else box.cv.winfo_rooty() + box.cv.winfo_height()
            left, width = box.cv.winfo_rootx(), box.cv.winfo_width()
        if self.ind is None:
            self.ind = tk.Frame(self.inner, bg=self.c["accent"], height=self.s(3))
        self.ind.place(x=left - self.inner.winfo_rootx(), y=top - self.inner.winfo_rooty() - self.s(1),
                       width=width, height=self.s(3))
        self.ind.lift()

    def _drop(self):
        drag, target = self._drag, self._target
        self._drag = self._target = None
        self._press_xy = None
        if self.ind is not None:
            self.ind.place_forget()
        if drag is None:
            return
        kind, src = drag
        if kind == "row":
            src["name"].configure(fg=self.c["fg"])
        elif src[0] is not None:
            src[0].configure(fg=self.c["dim"])
        if target is None:
            return
        obj, before = target
        if kind == "row":
            moving = [src["cfg"]]
            anchor = obj["cfg"]
        else:
            if obj is src:
                return
            moving = [r["cfg"] for sec in self.sections if sec[0] is not None and sec[0].cget("text") == src[0].cget("text")
                      for r in sec[1]]
            same = [r["cfg"] for sec in self.sections if sec[0] is not None and sec[0].cget("text") == obj[0].cget("text")
                    for r in sec[1]]
            if not same:
                return
            anchor = same[0] if before else same[-1]
        if any(anchor is m for m in moving):
            return
        self._move(moving, anchor, before)

    def _move(self, moving, anchor, before):
        """Deplace des elements (memes objets que app.cfg["items"]) avant ou apres un autre, et enregistre."""
        app = self.app
        items = app.cfg.get("items", [])

        def idx(cfg):
            return next((i for i, it in enumerate(items) if it is cfg), None)
        mi = [idx(m) for m in moving]
        ai = idx(anchor)
        if ai is None or None in mi:
            return
        rest = [i for i in range(len(items)) if i not in mi]
        pos = rest.index(ai) + (0 if before else 1)
        perm = rest[:pos] + mi + rest[pos:]
        if perm == list(range(len(items))):
            return
        sw = getattr(app, "settings_win", None)
        if sw is not None and sw.win.winfo_exists():
            # Reglages ouverts : on passe par eux (apercu, a enregistrer), puis on rouvre le panneau
            btn = self.button
            app.edit_items(lambda its: its.__setitem__(slice(None), [its[i] for i in perm]))
            if app.panel_win is None or not app.panel_win.alive:
                from panel_ui import Panel as _P
                app.panel_win = _P(app, app.panel_btn or btn, app.panel_items, fade=False)
            return
        items[:] = [items[i] for i in perm]
        order = {id(it): n for n, it in enumerate(items)}
        app.panel_items.sort(key=lambda c: order.get(id(c), 0))
        import copy
        import ha_core
        try:
            cfg = ha_core.load_config()
            fi = cfg.get("items", [])
            if len(fi) == len(perm):
                cfg["items"] = [fi[i] for i in perm]
            else:
                cfg["items"] = copy.deepcopy(items)
            ha_core.save_config(cfg)
        except OSError:
            pass
        self.cfgs = app.panel_items
        self.rebuild()

    # ---------------- opacite reglable depuis le panneau
    def opacity(self):
        try:
            return max(0.5, min(1.0, float(self.app.cfg.get("panel_opacity", 1.0))))
        except (TypeError, ValueError):
            return 1.0

    def toggle_opacity(self):
        """Affiche ou cache le curseur d'opacite sous l'en-tete."""
        s, c = self.s, self.c
        if self.opac_box is not None:
            self.opac_box.cv.destroy()
            self.opac_box = None
            self.place()
            return
        box = self.opac_box = _Box(self.head.master, self, self.card_c, pad=s(8), radius=s(8))
        box.cv.configure(width=self.iw)
        box.cv.pack(fill="x", pady=(s(10), 0), after=self.head)
        tk.Label(box.inner, text=_("Opacité"), bg=self.card_c, fg=c["fg"], font=self.f_small).pack(
            side="left", padx=(s(4), s(8)))
        pct = tk.Label(box.inner, text="", width=5, anchor="e", bg=self.card_c, fg=c["dim"], font=self.f_small)
        pct.pack(side="right", padx=(s(4), s(2)))
        panel = self

        class OpacityBar(_Bar):
            def show(self):
                pct.configure(text="%d %%" % round(panel._v2op(self.value) * 100))

            def _drag(self, e):
                r = _Bar._drag(self, e)
                panel.win.attributes("-alpha", panel._v2op(self.value))
                self.show()
                return r

        bar = OpacityBar(box.inner, self, self.skin, self._save_opacity, "opacity")
        bar.cv.pack(side="left", fill="x", expand=True)
        bar.value = max(1, min(100, round(1 + (self.opacity() - 0.5) / 0.5 * 99)))
        bar.show()
        bar.draw()
        self.place()

    @staticmethod
    def _v2op(v):
        return round(0.5 + (max(1, min(100, v)) - 1) / 99.0 * 0.5, 2)

    def _save_opacity(self, v):
        """Enregistre l'opacite. Si les Reglages sont ouverts, on passe par eux (rien d'autre n'est enregistre)."""
        op = self._v2op(v)
        self.win.attributes("-alpha", op)
        self.app.cfg["panel_opacity"] = op
        sw = getattr(self.app, "settings_win", None)
        if sw is not None and getattr(sw, "v_popac", None) is not None:
            try:
                sw.v_popac.set(op)
                return
            except tk.TclError:
                pass
        self._save_cfg({"panel_opacity": op})

    def _fade(self, step):
        if not self.alive:
            return
        target = self.opacity()
        a = min(target, target * step / 6.0)
        self.win.attributes("-alpha", a)
        if a < target:
            self.app.root.after(15, lambda: self._fade(step + 1))

    @staticmethod
    def _mouse_down():
        return bool(user32.GetAsyncKeyState(0x01) & 0x8000 or user32.GetAsyncKeyState(0x02) & 0x8000)

    def _loop(self):
        if not self.alive:
            return
        if not self._menu_open:
            fg = user32.GetForegroundWindow()
            if fg == self.hwnd:
                self._was_fg = True
            elif self._was_fg and fg:
                self.close()
                return
            down = self._mouse_down()
            if down and not self._mouse:
                x, y = self.app.root.winfo_pointerxy()
                wx, wy = self.win.winfo_rootx(), self.win.winfo_rooty()
                if not (wx <= x < wx + self.win.winfo_width() and wy <= y < wy + self.win.winfo_height()):
                    self.close()
                    return
            self._mouse = down
        self.app.root.after(50, self._loop)

    def _open_ha(self):
        import webbrowser
        url = (self.app.cfg.get("ha_url") or "").rstrip("/")
        self.close()
        if url:
            webbrowser.open(url)

    def close(self):
        if not self.alive:
            return
        self.alive = False
        self._cancel_press()
        hist = getattr(self.app, "history", None)
        if hist is not None and self.draw_sparks in hist.listeners:
            hist.listeners.remove(self.draw_sparks)
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if self.app.panel_win is self:
            self.app.panel_win = None
            self.app._panel_closed_at = time.monotonic()
