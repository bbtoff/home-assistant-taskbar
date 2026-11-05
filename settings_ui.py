"""Fenetre de reglages de HA Taskbar (ouverte par clic droit -> Reglages...)."""
import base64
import copy
import json
import os
import queue
import re
import subprocess
import threading
import time
import tkinter as tk
import urllib.error
from tkinter import colorchooser, messagebox, ttk
from tkinter import font as tkfont

import anim_icons
import ui_theme
from ha_core import (__version__, ANIM_ICONS, CARD_THEMES, CARD_THEMES_PATH, DARK_COLORS, ICON_FONTS, ICONS, LIGHT_COLORS,
                     PLACEHOLDER_TOKEN, HomeAssistant, auto_icon, bar_colors, bar_light, card_light, card_palette,
                     card_themes, default_service, get_startup, resolve_icon, resolve_service, save_config,
                     set_startup, system_light, item_zone)

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
COLOR_NAMES = [("bg", "Fond"), ("fg", "Valeurs"), ("dim", "Libellés"), ("on", "Actif / allumé"),
               ("hover", "Survol"), ("error", "Erreur")]
AUTO = "(auto)"
NO_ACTION = "(aucune)"
STATE_ATTR = "(état)"
NEW_LABEL = "Nouvel élément"
ZONE_TEXT = {"left": "Gauche", "right": "Droite"}
ALL_DOMAINS = "(tous les types)"
DOMAIN_NAMES = {
    "sensor": "Capteurs", "binary_sensor": "Capteurs binaires", "light": "Lumières", "switch": "Interrupteurs",
    "climate": "Thermostats", "cover": "Volets", "fan": "Ventilateurs", "lock": "Serrures",
    "media_player": "Lecteurs multimédia", "scene": "Scènes", "script": "Scripts", "automation": "Automatisations",
    "button": "Boutons", "input_button": "Boutons (helpers)", "input_boolean": "Interrupteurs (helpers)",
    "input_number": "Nombres (helpers)", "number": "Nombres", "select": "Sélecteurs", "person": "Personnes",
    "device_tracker": "Localisation", "weather": "Météo", "camera": "Caméras", "update": "Mises à jour",
    "sun": "Soleil", "zone": "Zones", "vacuum": "Aspirateurs", "alarm_control_panel": "Alarmes",
}


def domain_label(d, n):
    return "%s (%s) — %d" % (DOMAIN_NAMES.get(d, d), d, n) if d in DOMAIN_NAMES else "%s — %d" % (d, n)


class IconPicker:
    """Petite fenetre de choix d'icone pour l'element selectionne."""
    COLS = 12

    def __init__(self, sw):
        self.sw = sw
        it = sw.cfg["items"][sw.cur]
        current = it.get("icon") or "auto"
        auto_key = auto_icon(it.get("entity_id", ""), sw.entities.get(it.get("entity_id", "")))
        font = (getattr(sw.app, "icon_font", None) or "Segoe Fluent Icons", 18)

        pal = sw.pal
        top = self.top = tk.Toplevel(sw.win)
        top.title("Choisir une icône")
        top.transient(sw.win)
        top.resizable(False, False)
        top.configure(bg=pal["bg"])
        ui_theme.dark_title_bar(top, pal is ui_theme.PALETTES["dark"])
        f = ttk.Frame(top, padding=16)
        f.pack(fill="both", expand=True)

        bf = ttk.Frame(f)
        bf.grid(row=0, column=0, columnspan=self.COLS, sticky="w", pady=(0, 10))
        ttk.Button(bf, text="Automatique (%s)" % ICONS.get(auto_key, ("", auto_key))[1],
                   command=lambda: self.choose("auto")).pack(side="left")
        ttk.Button(bf, text="Aucune icône", command=lambda: self.choose("none")).pack(side="left", padx=6)

        self.name = ttk.Label(f, text="Icône actuelle : %s" % (
            "automatique" if current == "auto" else "aucune" if current == "none"
            else ANIM_ICONS[current][1] if current in ANIM_ICONS
            else ICONS.get(current, ("", current))[1]), style="Hint.TLabel")
        for i, (key, (glyph, label)) in enumerate(ICONS.items()):
            r, c = divmod(i, self.COLS)
            sel = key == current
            cell = tk.Label(f, text=glyph, font=font, width=2, cursor="hand2", fg=pal["fg"],
                            bg=pal["cell_sel"] if sel else pal["card"], relief="flat", borderwidth=0,
                            highlightthickness=1, highlightbackground=pal["accent"] if sel else pal["border"])
            cell.grid(row=r + 1, column=c, padx=2, pady=2, ipadx=4, ipady=2)
            cell.bind("<Button-1>", lambda e, k=key: self.choose(k))
            cell.bind("<Enter>", lambda e, l=label, w=cell: (self.name.configure(text=l),
                                                              w.configure(bg=pal["hover"])))
            cell.bind("<Leave>", lambda e, w=cell, s=sel: w.configure(bg=pal["cell_sel"] if s else pal["card"]))
        rows = (len(ICONS) + self.COLS - 1) // self.COLS

        # Icones animees : apercu "allume" qui bouge, comme sur la barre
        ttk.Label(f, text="Icônes animées : immobiles quand l'élément est éteint, elles bougent doucement "
                          "quand il est allumé (un thermostat : seulement quand il chauffe).",
                  style="Hint.TLabel", wraplength=sw.px(440), justify="left").grid(
            row=rows + 1, column=0, columnspan=self.COLS, sticky="w", pady=(10, 4))
        px = max(16, tkfont.Font(top, family=font[0], size=font[1]).measure(ICONS["flame"][0]))
        self.anim_cells = []
        self.anim_px = px
        blank = self.blank = tk.PhotoImage(master=top, width=px, height=px)
        arows = (len(ANIM_ICONS) + self.COLS - 1) // self.COLS
        for i, (key, (_fb, label, _n)) in enumerate(ANIM_ICONS.items()):
            sel = key == current
            cell = tk.Label(f, image=blank, cursor="hand2", width=px + 8, height=px + 4,
                            bg=pal["cell_sel"] if sel else pal["card"], relief="flat", borderwidth=0,
                            highlightthickness=1, highlightbackground=pal["accent"] if sel else pal["border"])
            r_, c_ = divmod(i, self.COLS)
            cell.grid(row=rows + 2 + r_, column=c_, padx=2, pady=2, ipadx=4, ipady=2)
            cell.bind("<Button-1>", lambda e, k=key: self.choose(k))
            cell.bind("<Enter>", lambda e, l=label, w=cell: (self.name.configure(text=l),
                                                              w.configure(bg=pal["hover"])))
            cell.bind("<Leave>", lambda e, w=cell, s=sel: w.configure(bg=pal["cell_sel"] if s else pal["card"]))
            self.anim_cells.append([cell, [], key])
        self.name.grid(row=rows + 2 + arows, column=0, columnspan=self.COLS, sticky="w", pady=(10, 0))
        self.top.after(10, self.load_next)       # images preparees une par une : la fenetre s'ouvre tout de suite
        self.animate()
        top.grab_set()
        top.focus_force()

    def load_next(self):
        if not self.top.winfo_exists():
            return
        pal = self.sw.pal
        for entry in self.anim_cells:
            if not entry[1]:
                entry[1] = [tk.PhotoImage(master=self.top, data=base64.b64encode(png), format="png")
                            for png in anim_icons.frames_png(entry[2], self.anim_px, True, pal["icon_on"], pal["fg"])]
                self.top.after(5, self.load_next)
                return

    def animate(self):
        if not self.top.winfo_exists():
            return
        n = int(time.monotonic() * 1000) // anim_icons.FRAME_MS
        for cell, imgs, _k in self.anim_cells:
            if imgs:
                cell.configure(image=imgs[n % len(imgs)])
        self.top.after(anim_icons.FRAME_MS, self.animate)

    def choose(self, key):
        self.sw.v_icon.set(key)
        self.top.destroy()


class EntityPicker:
    """Fenetre pour parcourir toutes les entites HA et les ajouter a la barre."""

    def __init__(self, sw):
        self.sw = sw
        self.job = None
        self.domain_map = {}
        top = self.top = tk.Toplevel(sw.win)
        top.title("Ajouter des entités Home Assistant")
        top.transient(sw.win)
        top.geometry("%dx%d" % (sw.px(900), sw.px(620)))
        top.minsize(sw.px(640), sw.px(440))
        top.configure(bg=sw.pal["bg"])
        ui_theme.dark_title_bar(top, sw.pal is ui_theme.PALETTES["dark"])

        f = ttk.Frame(top, padding=14)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        f.rowconfigure(1, weight=1)

        ttk.Label(f, text="Rechercher").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.v_search = tk.StringVar()
        e = ttk.Entry(f, textvariable=self.v_search)
        e.grid(row=0, column=1, sticky="ew")
        self.v_domain = tk.StringVar(value=ALL_DOMAINS)
        self.cb_domain = ttk.Combobox(f, textvariable=self.v_domain, state="readonly", width=34)
        self.cb_domain.grid(row=0, column=2, padx=(8, 0))
        self.v_search.trace_add("write", lambda *a: self.schedule())
        self.cb_domain.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        tf = ttk.Frame(f)
        tf.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(tf, columns=("name", "entity", "state"), show="headings", selectmode="extended")
        for col, title, w in (("name", "Nom", 280), ("entity", "Entité", 300), ("state", "État", 140)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=sw.px(w), minwidth=sw.px(60))
        self.tree.tag_configure("added", foreground="#8a8a8a")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", self.add_selected)
        self.tree.bind("<Return>", self.add_selected)

        bf = ttk.Frame(f)
        bf.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.info = ttk.Label(bf, text="", style="Hint.TLabel")
        self.info.pack(side="left")
        ttk.Button(bf, text="Fermer", command=top.destroy).pack(side="right")
        ttk.Button(bf, text="Ajouter la sélection à la barre", command=self.add_selected).pack(side="right", padx=6)
        ttk.Label(f, text="Double-clic pour ajouter. Ctrl ou Maj + clic pour en sélectionner plusieurs. "
                          "Les entités déjà sur la barre sont grisées (✔).",
                  style="Hint.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self.refresh()
        e.focus_set()

    def schedule(self):
        if self.job:
            self.top.after_cancel(self.job)
        self.job = self.top.after(200, self.refresh)

    def refresh(self):
        self.job = None
        if not self.top.winfo_exists():
            return
        ents = self.sw.entities
        counts = {}
        for eid in ents:
            d = eid.split(".", 1)[0]
            counts[d] = counts.get(d, 0) + 1
        self.domain_map = {domain_label(d, n): d for d, n in sorted(counts.items(), key=lambda x: -x[1])}
        self.cb_domain["values"] = [ALL_DOMAINS] + list(self.domain_map)
        if self.v_domain.get() not in self.domain_map:
            self.v_domain.set(ALL_DOMAINS)
        dom = self.domain_map.get(self.v_domain.get())

        words = self.v_search.get().lower().split()
        added = {it.get("entity_id") for it in self.sw.cfg["items"]}
        rows = []
        for eid, st in ents.items():
            if dom and not eid.startswith(dom + "."):
                continue
            name = st.get("attributes", {}).get("friendly_name", "") or ""
            hay = (eid + " " + name).lower()
            if any(w not in hay for w in words):
                continue
            unit = st.get("attributes", {}).get("unit_of_measurement", "")
            rows.append(((name or eid).lower(), eid, name, ("%s %s" % (st.get("state", ""), unit)).strip()))
        rows.sort()

        self.tree.delete(*self.tree.get_children())
        for _k, eid, name, state in rows:
            mark = eid in added
            self.tree.insert("", "end", iid=eid, values=(("✔ " if mark else "") + (name or eid), eid, state),
                             tags=("added",) if mark else ())
        if not ents:
            self.info.configure(text="Aucune entité chargée — vérifie l'onglet Connexion puis « Tester la connexion ».")
        else:
            self.info.configure(text="%d entité(s) affichée(s) sur %d" % (len(rows), len(ents)))

    def add_selected(self, _e=None):
        sel = self.tree.selection()
        for eid in sel:
            self.sw.add_entity(eid)
        if sel:
            self.refresh()
            self.info.configure(text="✔ %d entité(s) ajoutée(s) à la barre" % len(sel))
        return "break"


class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.saved = copy.deepcopy(app.cfg)          # ce qui est sur le disque
        self.cfg = copy.deepcopy(app.cfg)            # ce qu'on edite
        if self.cfg.get("token") == PLACEHOLDER_TOKEN:
            self.cfg["token"] = ""
        self.entities = dict(app.last_states)        # entity_id -> etat HA
        self.services = {}                           # domaine -> [services]
        self.q = queue.Queue()
        self.dirty = False
        self.loading = False                         # bloque les callbacks pendant le remplissage
        self.cur = None                              # index de l'element selectionne
        self.preview_job = None
        self.data_ok = True
        self.picker = None
        self.first_ok = True

        win = self.win = tk.Toplevel(app.root)
        self.s = win.winfo_fpixels("1i") / 96.0      # facteur d'echelle DPI
        win.title("HA Taskbar %s — Réglages" % __version__)
        win.geometry("%dx%d" % (self.px(1180), self.px(860)))
        win.minsize(self.px(1080), self.px(780))
        win.protocol("WM_DELETE_WINDOW", self.on_close)

        # Theme Windows 11 (clair ou sombre comme Windows)
        self.pal = ui_theme.apply(app.root)
        win.configure(bg=self.pal["bg"])
        ui_theme.dark_title_bar(win, self.pal is ui_theme.PALETTES["dark"])
        ttk.Style(win).configure("Treeview", rowheight=self.px(30))

        win.columnconfigure(1, weight=1)
        win.rowconfigure(0, weight=1)
        self.nb = ui_theme.SideNav(win, self.pal, getattr(app, "icon_font", None), "HA Taskbar",
                                   "Version %s" % __version__, self.px)
        self.nb.side.grid(row=0, column=0, rowspan=2, sticky="ns")
        self.nb.grid(row=0, column=1, sticky="nsew")
        self.build_connection()
        self.build_items()
        self.build_appearance()

        bar = ttk.Frame(win, padding=(self.px(28), self.px(10), self.px(28), self.px(18)))
        bar.grid(row=1, column=1, sticky="ew")
        self.status = ttk.Label(bar, text="", style="Hint.TLabel")
        self.status.pack(side="left")
        ttk.Button(bar, text="Appliquer", command=self.apply).pack(side="right")
        ttk.Button(bar, text="Annuler", command=self.cancel).pack(side="right", padx=8)
        ttk.Button(bar, text="OK", style="Accent.TButton", width=10, command=self.ok).pack(side="right")

        self.win.after(150, self.poll_queue)
        if self.cfg.get("token"):
            self.test_connection()
            if self.cfg["items"]:
                self.nb.select(1)
        win.lift()
        win.focus_force()

    # ------------------------------------------------------------------ outils
    def px(self, n):
        return int(n * self.s)

    def hint(self, parent, text, wrap=520, **grid):
        lbl = ttk.Label(parent, text=text, style="Hint.TLabel", wraplength=self.px(wrap), justify="left")
        lbl.grid(**grid)
        return lbl

    def track(self, var, setter):
        """Relie une variable Tk a la config : chaque modif met a jour self.cfg + previsualisation."""
        def cb(*_):
            if self.loading:
                return
            try:
                setter(var.get())
            except (ValueError, TypeError, tk.TclError):
                return
            self.changed()
        var.trace_add("write", cb)
        return var

    def key(self, name, conv=lambda v: v):
        def setter(v):
            self.cfg[name] = conv(v)
        return setter

    def changed(self):
        self.dirty = True
        self.status.configure(text="Modifications non enregistrées (aperçu en direct sur la barre)")
        if self.preview_job:
            self.win.after_cancel(self.preview_job)
        self.preview_job = self.win.after(350, self.preview)

    def preview(self):
        self.preview_job = None
        self.app.apply_config(copy.deepcopy(self.cfg))

    def friendly(self, eid):
        st = self.entities.get(eid)
        return st.get("attributes", {}).get("friendly_name", "") if st else ""

    # ------------------------------------------------------------------ onglet Connexion
    def build_connection(self):
        f = ttk.Frame(self.nb, padding=0)
        self.nb.add(f, text="Connexion", icon="")
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text="Adresse de Home Assistant").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.v_url = self.track(tk.StringVar(value=self.cfg["ha_url"]), self.key("ha_url", str.strip))
        ttk.Entry(f, textvariable=self.v_url).grid(row=0, column=1, columnspan=2, sticky="ew")
        self.hint(f, "Exemple : http://homeassistant.local:8123 ou http://192.168.1.10:8123",
                  row=1, column=1, columnspan=2, sticky="w", pady=(2, 12))

        ttk.Label(f, text="Jeton d'accès").grid(row=2, column=0, sticky="w", padx=(0, 12))
        self.v_token = self.track(tk.StringVar(value=self.cfg["token"]), self.key("token", str.strip))
        self.token_entry = ttk.Entry(f, textvariable=self.v_token, show="•")
        self.token_entry.grid(row=2, column=1, sticky="ew")
        self.v_show = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Afficher", variable=self.v_show,
                        command=lambda: self.token_entry.configure(show="" if self.v_show.get() else "•")
                        ).grid(row=2, column=2, padx=(8, 0))
        self.hint(f, "Dans Home Assistant : clique sur ton profil (en bas à gauche) → onglet « Sécurité » → "
                     "« Jetons d'accès longue durée » → « Créer un jeton », puis colle-le ici.",
                  row=3, column=1, columnspan=2, sticky="w", pady=(2, 12))

        self.v_verify = self.track(tk.BooleanVar(value=self.cfg.get("verify_ssl", True)), self.key("verify_ssl"))
        ttk.Checkbutton(f, text="Vérifier le certificat HTTPS (décocher pour un certificat auto-signé)",
                        variable=self.v_verify).grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(f, text="Rafraîchissement").grid(row=5, column=0, sticky="w", padx=(0, 12))
        rf = ttk.Frame(f)
        rf.grid(row=5, column=1, sticky="w")
        self.v_poll = self.track(tk.StringVar(value=str(self.cfg.get("poll_interval", 5))),
                                 self.key("poll_interval", lambda v: max(1, int(v))))
        ttk.Spinbox(rf, from_=1, to=300, width=6, textvariable=self.v_poll).pack(side="left")
        ttk.Label(rf, text="secondes").pack(side="left", padx=6)

        tf = ttk.Frame(f)
        tf.grid(row=6, column=1, columnspan=2, sticky="w", pady=(20, 0))
        ttk.Button(tf, text="Tester la connexion", command=self.test_connection).pack(side="left")
        self.conn_label = ttk.Label(tf, text="", style="Hint.TLabel")
        self.conn_label.pack(side="left", padx=10)

        ttk.Separator(f).grid(row=7, column=0, columnspan=3, sticky="ew", pady=20)
        self.v_startup = tk.BooleanVar(value=get_startup())
        self.track(self.v_startup, lambda v: None)
        ttk.Checkbutton(f, text="Lancer HA Taskbar au démarrage de Windows",
                        variable=self.v_startup).grid(row=8, column=1, columnspan=2, sticky="w")

        # --- mises a jour
        self.v_updates = self.track(tk.BooleanVar(value=self.cfg.get("check_updates", True)),
                                    self.key("check_updates"))
        ttk.Checkbutton(f, text="Rechercher les mises à jour sur GitHub (au démarrage, puis une fois par jour)",
                        variable=self.v_updates).grid(row=9, column=1, columnspan=2, sticky="w", pady=(6, 0))
        uf = ttk.Frame(f)
        uf.grid(row=10, column=1, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(uf, text="Rechercher maintenant", command=self.check_update_now).pack(side="left")
        self.update_label = ttk.Label(uf, text="Version installée : %s" % __version__, style="Hint.TLabel")
        self.update_label.pack(side="left", padx=10)

    def check_update_now(self):
        self.update_label.configure(text="Recherche…", style="Hint.TLabel")

        def report(text):
            if self.win.winfo_exists():
                self.update_label.configure(text=text, style="Hint.TLabel")
        self.app.check_update(manual=True, report=report)

    def test_connection(self):
        ha = HomeAssistant(self.cfg["ha_url"], self.cfg["token"], self.cfg.get("verify_ssl", True))
        self.conn_label.configure(text="Connexion…", style="Hint.TLabel")

        def run():
            try:
                conf = ha.config()
                states = ha.states()
                services = ha.services()
                self.q.put(("ok", conf, states, services))
            except urllib.error.HTTPError as e:
                self.q.put(("err", "Jeton refusé (HTTP 401)" if e.code == 401 else "Erreur HTTP %s" % e.code))
            except Exception as e:
                self.q.put(("err", "Connexion impossible : %s" % getattr(e, "reason", e)))
        threading.Thread(target=run, daemon=True).start()

    def poll_queue(self):
        if not self.win.winfo_exists():
            return
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "ok":
                    _, conf, states, services = msg
                    self.entities, self.services = states, services
                    self.conn_label.configure(
                        text="✔ Connecté à « %s » (version %s) — %d entités"
                             % (conf.get("location_name", "Home Assistant"), conf.get("version", "?"), len(states)),
                        style="Ok.TLabel")
                    self.update_item_choices()
                    self.update_item_hints()
                    if self.picker is not None and self.picker.top.winfo_exists():
                        self.picker.refresh()
                    if self.first_ok and not self.cfg["items"]:
                        self.nb.select(1)       # premiere connexion : on va directement aux elements
                    self.first_ok = False
                else:
                    self.conn_label.configure(text="✖ " + msg[1], style="Err.TLabel")
        except queue.Empty:
            pass
        self.win.after(150, self.poll_queue)

    # ------------------------------------------------------------------ onglet Elements
    def build_items(self):
        f = ttk.Frame(self.nb, padding=0)
        self.nb.add(f, text="Éléments", icon="")
        f.columnconfigure(0, weight=1, minsize=self.px(420))
        f.columnconfigure(1, weight=1)
        f.rowconfigure(0, weight=1)

        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(left, columns=("label", "entity", "action", "zone"), show="headings",
                                 selectmode="browse")
        for col, title, w in (("label", "Libellé", 95), ("entity", "Entité", 140), ("action", "Clic", 100),
                              ("zone", "Zone", 60)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=self.px(w), minwidth=self.px(50))
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.empty_label = ttk.Label(left, style="Empty.TLabel", justify="center", anchor="center",
                                     text="La barre est vide.\n\nClique sur « Ajouter des entités… »\n"
                                          "pour choisir parmi tes entités Home Assistant.")

        ttk.Button(left, text="➕  Ajouter des entités…", command=self.open_picker).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        btns = ttk.Frame(left)
        btns.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        for text, cmd, w in (("Ajouter vide", self.add_item, None), ("Dupliquer", self.dup_item, None),
                             ("Supprimer", self.del_item, None), ("▲", lambda: self.move_item(-1), 3),
                             ("▼", lambda: self.move_item(1), 3)):
            ttk.Button(btns, text=text, command=cmd, width=w).pack(side="left", padx=(0, 6))

        right = ttk.LabelFrame(f, text="Élément sélectionné", padding=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)
        self.v_eid, self.v_label, self.v_attr = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.v_unit, self.v_dec, self.v_service = tk.StringVar(), tk.StringVar(), tk.StringVar()

        def row(r, text):
            ttk.Label(right, text=text).grid(row=r, column=0, sticky="nw", padx=(0, 10), pady=(4, 0))

        row(0, "Entité")
        self.cb_eid = ttk.Combobox(right, textvariable=self.v_eid, postcommand=self.filter_entities)
        self.cb_eid.grid(row=0, column=1, sticky="ew", pady=(4, 0))
        self.cb_eid.bind("<KeyRelease>", self.filter_entities)
        self.eid_info = self.hint(right, "", row=1, column=1, sticky="w")

        row(2, "Libellé")
        lf = ttk.Frame(right)
        lf.grid(row=2, column=1, sticky="ew", pady=(4, 0))
        self.e_label = ttk.Entry(lf, textvariable=self.v_label)
        self.e_label.pack(side="left", fill="x", expand=True)
        ttk.Label(lf, text="  Icône").pack(side="left")
        self.v_icon = tk.StringVar(value="auto")
        self.icon_preview = tk.Label(lf, text="", width=2,
                                     font=(getattr(self.app, "icon_font", None) or "Segoe Fluent Icons", 14),
                                     relief="flat", borderwidth=0, bg=self.pal["field"], fg=self.pal["fg"],
                                     highlightthickness=1, highlightbackground=self.pal["border"], cursor="hand2")
        self.icon_preview.pack(side="left", padx=(6, 4))
        self.icon_preview.bind("<Button-1>", lambda e: self.open_icon_picker())
        self.b_icon = ttk.Button(lf, text="Changer…", command=self.open_icon_picker)
        self.b_icon.pack(side="left")

        row(3, "Valeur affichée")
        self.cb_attr = ttk.Combobox(right, textvariable=self.v_attr)
        self.cb_attr.grid(row=3, column=1, sticky="ew", pady=(4, 0))
        self.hint(right, "« (état) » = l'état de l'entité, sinon un de ses attributs.", row=4, column=1, sticky="w")

        row(5, "Unité")
        uf = ttk.Frame(right)
        uf.grid(row=5, column=1, sticky="ew", pady=(4, 0))
        self.e_unit = ttk.Entry(uf, textvariable=self.v_unit, width=8)
        self.e_unit.pack(side="left")
        ttk.Label(uf, text="  Décimales").pack(side="left")
        self.cb_dec = ttk.Combobox(uf, textvariable=self.v_dec, width=7, values=[AUTO, "0", "1", "2", "3"])
        self.cb_dec.pack(side="left", padx=(6, 0))
        self.hint(right, "Unité vide = celle fournie par Home Assistant.", row=6, column=1, sticky="w")

        row(7, "Action au clic")
        self.cb_service = ttk.Combobox(right, textvariable=self.v_service)
        self.cb_service.grid(row=7, column=1, sticky="ew", pady=(4, 0))
        self.svc_info = self.hint(right, "", row=8, column=1, sticky="w")

        row(9, "Données (JSON)")
        self.t_data = tk.Text(right, height=4, font=("Consolas", 10), wrap="word", relief="flat", borderwidth=0,
                              bg=self.pal["field"], fg=self.pal["fg"], insertbackground=self.pal["fg"],
                              highlightthickness=1, highlightbackground=self.pal["border"],
                              highlightcolor=self.pal["accent"], padx=6, pady=4)
        self.t_data.grid(row=9, column=1, sticky="ew", pady=(4, 0))
        self.data_info = self.hint(right, "Optionnel. Vide = {\"entity_id\": \"<l'entité>\"}",
                                   row=10, column=1, sticky="w")

        row(11, "Titre de la carte")
        self.v_ctitle = tk.StringVar()
        self.e_ctitle = ttk.Entry(right, textvariable=self.v_ctitle)
        self.e_ctitle.grid(row=11, column=1, sticky="ew", pady=(4, 0))
        self.hint(right, "Vide = nom de l'entité dans Home Assistant. Aussi modifiable avec le crayon ✎ "
                         "de la carte (appui long).", wrap=360, row=12, column=1, sticky="w")

        row(13, "Zone")
        self.v_zone = tk.StringVar(value="left")
        zf = ttk.Frame(right)
        zf.grid(row=13, column=1, sticky="w", pady=(4, 0))
        self.rb_zones = [ttk.Radiobutton(zf, text=t, value=v, variable=self.v_zone)
                         for t, v in (("Gauche", "left"), ("Droite", "right"))]
        for rb in self.rb_zones:
            rb.pack(side="left", padx=(0, 12))
        self.hint(right, "Côté de la barre des tâches où s'affiche l'élément. Les décalages se règlent "
                         "dans l'onglet Apparence.", wrap=360, row=14, column=1, sticky="w")

        for v in (self.v_eid, self.v_label, self.v_attr, self.v_unit, self.v_dec, self.v_service, self.v_icon,
                  self.v_ctitle, self.v_zone):
            v.trace_add("write", self.on_item_field)
        self.t_data.bind("<KeyRelease>", self.on_item_field)
        self.item_widgets = [self.cb_eid, self.e_label, self.cb_attr, self.e_unit, self.cb_dec,
                             self.cb_service, self.t_data, self.b_icon, self.e_ctitle] + self.rb_zones

        self.refresh_tree()
        if self.cfg["items"]:
            self.select_item(0)
        else:
            self.load_item_fields()

    def entity_list(self, text=""):
        t = text.lower().strip()
        if t in self.entities:      # entite deja choisie : on montre tout
            t = ""
        out = []
        for eid in sorted(self.entities):
            if not t or t in eid.lower() or t in self.friendly(eid).lower():
                out.append(eid)
        return out[:500]

    def filter_entities(self, e=None):
        if e is not None and e.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        self.cb_eid["values"] = self.entity_list(self.v_eid.get())

    def action_text(self, it):
        svc = resolve_service(it)
        return svc if svc else "—"

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, it in enumerate(self.cfg["items"]):
            self.tree.insert("", "end", iid=str(i),
                             values=(it.get("label", ""), it.get("entity_id", ""), self.action_text(it),
                                     ZONE_TEXT[item_zone(it)]))
        if self.cfg["items"]:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(in_=self.tree, relx=0.5, rely=0.4, anchor="center")

    def open_picker(self):
        if self.picker is not None and self.picker.top.winfo_exists():
            self.picker.top.lift()
            self.picker.top.focus_force()
            return
        self.picker = EntityPicker(self)

    def open_icon_picker(self):
        if self.cur is None:
            return
        IconPicker(self)

    def add_entity(self, eid):
        self.cfg["items"].append({"entity_id": eid, "label": self.friendly(eid) or eid})
        self.refresh_tree()
        self.select_item(len(self.cfg["items"]) - 1)
        self.changed()

    def refresh_tree_row(self, i):
        it = self.cfg["items"][i]
        self.tree.item(str(i), values=(it.get("label", ""), it.get("entity_id", ""), self.action_text(it),
                                     ZONE_TEXT[item_zone(it)]))

    def select_item(self, i):
        if 0 <= i < len(self.cfg["items"]):
            self.tree.selection_set(str(i))
            self.tree.see(str(i))
            self.cur = i
        else:
            self.cur = None
        self.load_item_fields()

    def on_select(self, _e=None):
        sel = self.tree.selection()
        new = int(sel[0]) if sel else None
        if new != self.cur:
            self.cur = new
            self.load_item_fields()

    def load_item_fields(self):
        it = self.cfg["items"][self.cur] if self.cur is not None else {}
        self.loading = True
        self.v_eid.set(it.get("entity_id", ""))
        self.v_label.set(it.get("label", ""))
        self.v_ctitle.set(it.get("card_title", ""))
        self.v_zone.set(item_zone(it))
        self.v_icon.set(it.get("icon") or "auto")
        self.v_attr.set(it.get("attribute") or STATE_ATTR)
        self.v_unit.set(it.get("unit", ""))
        self.v_dec.set(AUTO if it.get("decimals") is None else str(it["decimals"]))
        svc = it.get("service")
        self.v_service.set(NO_ACTION if svc == "none" else (svc or AUTO))
        self.t_data.configure(state="normal")
        self.t_data.delete("1.0", "end")
        if it.get("data"):
            self.t_data.insert("1.0", json.dumps(it["data"], ensure_ascii=False))
        self.loading = False
        state = "normal" if self.cur is not None else "disabled"
        for w in self.item_widgets:
            w.configure(state=state)
        self.data_ok = True
        self.data_info.configure(text="Optionnel. Vide = {\"entity_id\": \"<l'entité>\"}", style="Hint.TLabel")
        self.update_item_choices()
        self.update_item_hints()

    def update_item_choices(self):
        eid = self.v_eid.get().strip()
        st = self.entities.get(eid, {})
        self.cb_attr["values"] = [STATE_ATTR] + sorted(st.get("attributes", {}))
        domain = eid.split(".", 1)[0] if eid else ""
        svcs = ["%s.%s" % (domain, s) for s in self.services.get(domain, [])]
        svcs += ["homeassistant.%s" % s for s in self.services.get("homeassistant", [])
                 if s in ("toggle", "turn_on", "turn_off")]
        self.cb_service["values"] = [AUTO, NO_ACTION] + svcs

    def update_item_hints(self):
        if self.cur is None:
            self.eid_info.configure(text="Sélectionne un élément ou clique sur « Ajouter des entités… ».",
                                    style="Hint.TLabel")
            self.svc_info.configure(text="")
            self.icon_preview.configure(text="")
            return
        it = self.cfg["items"][self.cur]
        eid = it.get("entity_id", "")
        st = self.entities.get(eid)
        self.icon_preview.configure(text=resolve_icon(it, st) or "")
        if st:
            unit = st.get("attributes", {}).get("unit_of_measurement", "")
            self.eid_info.configure(text="%s — état actuel : %s %s" % (self.friendly(eid) or eid, st.get("state"), unit),
                                    style="Hint.TLabel")
        elif not self.entities:
            self.eid_info.configure(text="Teste la connexion (onglet Connexion) pour avoir la liste des entités.",
                                    style="Hint.TLabel")
        elif eid:
            self.eid_info.configure(text="Entité inconnue dans Home Assistant.", style="Err.TLabel")
        else:
            self.eid_info.configure(text="Tape quelques lettres puis ouvre la liste.", style="Hint.TLabel")

        if it.get("service") in (None, ""):
            d = default_service(eid)
            self.svc_info.configure(text="Auto : %s" % d if d else "Auto : aucune action (affichage seul)")
        else:
            self.svc_info.configure(text="")

    def on_item_field(self, *_):
        if self.loading or self.cur is None:
            return
        it = self.cfg["items"][self.cur]
        old_eid = it.get("entity_id", "")
        eid = self.v_eid.get().strip()
        it["entity_id"] = eid
        it["label"] = self.v_label.get()
        ctitle = self.v_ctitle.get().strip()
        if ctitle:
            it["card_title"] = ctitle
        else:
            it.pop("card_title", None)
        if self.v_zone.get() == "right":
            it["zone"] = "right"
        else:
            it.pop("zone", None)
        icon = self.v_icon.get()
        if icon in ("", "auto"):
            it.pop("icon", None)
        else:
            it["icon"] = icon

        attr = self.v_attr.get().strip()
        if attr in ("", STATE_ATTR):
            it.pop("attribute", None)
        else:
            it["attribute"] = attr

        unit = self.v_unit.get().strip()
        if unit:
            it["unit"] = unit
        else:
            it.pop("unit", None)

        dec = self.v_dec.get().strip()
        if dec in ("", AUTO):
            it.pop("decimals", None)
        else:
            try:
                it["decimals"] = max(0, int(dec))
            except ValueError:
                pass

        svc = self.v_service.get().strip()
        if svc in ("", AUTO):
            it.pop("service", None)
        elif svc == NO_ACTION:
            it["service"] = "none"
        else:
            it["service"] = svc

        raw = self.t_data.get("1.0", "end").strip()
        if not raw:
            it.pop("data", None)
            self.data_ok = True
            self.data_info.configure(text="Optionnel. Vide = {\"entity_id\": \"<l'entité>\"}", style="Hint.TLabel")
        else:
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError
                it["data"] = parsed
                self.data_ok = True
                self.data_info.configure(text="JSON valide ✔", style="Ok.TLabel")
            except ValueError:
                self.data_ok = False
                self.data_info.configure(text="JSON invalide (ex : {\"entity_id\": \"light.salon\"})",
                                         style="Err.TLabel")

        if eid != old_eid:
            # Libelle automatique depuis le nom de l'entite si l'utilisateur ne l'a pas personnalise
            fn = self.friendly(eid)
            if fn and it["label"] in ("", NEW_LABEL, self.friendly(old_eid)):
                self.loading = True
                self.v_label.set(fn)
                self.loading = False
                it["label"] = fn
            self.update_item_choices()
        self.update_item_hints()
        self.refresh_tree_row(self.cur)
        self.changed()

    def add_item(self):
        self.cfg["items"].append({"entity_id": "", "label": NEW_LABEL})
        self.refresh_tree()
        self.select_item(len(self.cfg["items"]) - 1)
        self.cb_eid.focus_set()
        self.changed()

    def dup_item(self):
        if self.cur is None:
            return
        self.cfg["items"].insert(self.cur + 1, copy.deepcopy(self.cfg["items"][self.cur]))
        self.refresh_tree()
        self.select_item(self.cur + 1)
        self.changed()

    def del_item(self):
        if self.cur is None:
            return
        del self.cfg["items"][self.cur]
        i = min(self.cur, len(self.cfg["items"]) - 1)
        self.cur = None
        self.refresh_tree()
        self.select_item(i)
        self.changed()

    def move_item(self, d):
        i = self.cur
        if i is None or not 0 <= i + d < len(self.cfg["items"]):
            return
        items = self.cfg["items"]
        items[i], items[i + d] = items[i + d], items[i]
        self.refresh_tree()
        self.select_item(i + d)
        self.changed()

    # ------------------------------------------------------------------ onglet Apparence
    def build_appearance(self):
        f = ttk.Frame(self.nb, padding=0)
        self.nb.add(f, text="Apparence", icon="")
        f.columnconfigure(0, weight=3)
        f.columnconfigure(1, weight=2)

        # --- position
        pos = ttk.LabelFrame(f, text="Position sur la barre des tâches", padding=10)
        pos.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        pos.columnconfigure(0, weight=1)
        maxoff = max(400, self.win.winfo_screenwidth() - 50)

        def offset_slider(row, text, key, default):
            ttk.Label(pos, text=text).grid(row=row, column=0, sticky="w", pady=(10 if row else 0, 2))
            of = ttk.Frame(pos)
            of.grid(row=row + 1, column=0, sticky="ew")
            of.columnconfigure(0, weight=1)
            var = tk.IntVar(value=int(self.cfg.get(key, default)))
            scale = ttk.Scale(of, from_=0, to=maxoff, orient="horizontal",
                              command=lambda v: var.set(int(float(v))))
            scale.set(var.get())
            scale.grid(row=0, column=0, sticky="ew")
            ttk.Spinbox(of, from_=0, to=maxoff, width=6, textvariable=var).grid(row=0, column=1, padx=(8, 0))

            def set_offset(v):
                v = int(v)
                self.cfg[key] = v
                if int(float(scale.get())) != v:
                    scale.set(v)
            self.track(var, set_offset)
            return var

        self.v_offset = offset_slider(0, "Zone gauche : décalage depuis le bord gauche (pixels)", "offset", 60)
        self.v_offset_right = offset_slider(
            2, "Zone droite : décalage depuis le bord droit (pixels, avant les icônes de notification)",
            "offset_right", 300)
        self.hint(pos, "Chaque élément choisit sa zone dans l'onglet Éléments. Une zone sans élément "
                       "n'apparaît pas. Fais glisser : la barre se déplace en direct.",
                  row=4, column=0, sticky="w", pady=(2, 0))

        # --- texte
        look = ttk.LabelFrame(f, text="Texte et affichage", padding=10)
        look.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(10, 0))
        look.columnconfigure(1, weight=1)
        self.v_layout = self.track(tk.StringVar(value=self.cfg.get("layout", "stacked")), self.key("layout"))
        ttk.Radiobutton(look, text="Libellé au-dessus de la valeur", value="stacked",
                        variable=self.v_layout).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(look, text="Libellé et valeur sur une ligne", value="inline",
                        variable=self.v_layout).grid(row=1, column=0, columnspan=2, sticky="w")

        ttk.Label(look, text="Police").grid(row=2, column=0, sticky="w", pady=(10, 0), padx=(0, 10))
        ff = ttk.Frame(look)
        ff.grid(row=2, column=1, sticky="ew", pady=(10, 0))
        families = sorted({f_ for f_ in tkfont.families(self.win) if not f_.startswith("@")})
        self.v_font = self.track(tk.StringVar(value=self.cfg.get("font", "Segoe UI")), self.key("font"))
        ttk.Combobox(ff, textvariable=self.v_font, values=families, width=22).pack(side="left", fill="x", expand=True)
        self.v_fsize = self.track(tk.StringVar(value=str(self.cfg.get("font_size", 9))),
                                  self.key("font_size", lambda v: min(30, max(5, int(v)))))
        ttk.Spinbox(ff, from_=5, to=30, width=4, textvariable=self.v_fsize).pack(side="left", padx=(6, 0))

        ttk.Label(look, text="Opacité").grid(row=3, column=0, sticky="w", pady=(10, 0), padx=(0, 10))
        opf = ttk.Frame(look)
        opf.grid(row=3, column=1, sticky="ew", pady=(10, 0))
        self.op_label = ttk.Label(opf, width=5)
        self.v_opacity = tk.DoubleVar(value=float(self.cfg.get("opacity", 1.0)))

        def set_opacity(v):
            v = round(float(v), 2)
            self.cfg["opacity"] = v
            self.op_label.configure(text="%d %%" % round(v * 100))
        ttk.Scale(opf, from_=0.3, to=1.0, orient="horizontal", variable=self.v_opacity).pack(
            side="left", fill="x", expand=True)
        self.op_label.pack(side="left", padx=(6, 0))
        set_opacity(self.v_opacity.get())
        self.track(self.v_opacity, set_opacity)

        self.v_transp = self.track(tk.BooleanVar(value=self.cfg.get("transparent_bg", False)),
                                   self.key("transparent_bg"))
        ttk.Checkbutton(look, text="Fond transparent", variable=self.v_transp).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.v_hidefs = self.track(tk.BooleanVar(value=self.cfg.get("hide_on_fullscreen", True)),
                                   self.key("hide_on_fullscreen"))
        ttk.Checkbutton(look, text="Masquer quand une application est en plein écran",
                        variable=self.v_hidefs).grid(row=5, column=0, columnspan=2, sticky="w")
        self.v_icons = self.track(tk.BooleanVar(value=self.cfg.get("show_icons", True)), self.key("show_icons"))
        ttk.Checkbutton(look, text="Afficher les icônes", variable=self.v_icons).grid(
            row=6, column=0, columnspan=2, sticky="w")
        self.v_anim = self.track(tk.BooleanVar(value=self.cfg.get("anim_icons", True)), self.key("anim_icons"))
        ttk.Checkbutton(look, text="Animer les icônes animées (mouvement lent et discret)",
                        variable=self.v_anim).grid(row=7, column=0, columnspan=2, sticky="w")

        # --- theme et couleurs de la barre
        col = ttk.LabelFrame(f, text="Thème et couleurs de la barre", padding=10)
        col.grid(row=0, column=1, rowspan=2, sticky="nsew")
        col.columnconfigure(2, weight=1)
        self.v_tmode = self.track(tk.StringVar(value=self.cfg.get("theme_mode", "system")), self.set_theme_mode)
        for r, (val, txt) in enumerate((("system", "Suivre Windows (clair / sombre)"),
                                        ("dark", "Toujours sombre"), ("light", "Toujours clair"))):
            ttk.Radiobutton(col, text=txt, value=val, variable=self.v_tmode).grid(
                row=r, column=0, columnspan=3, sticky="w")
        self.hint(col, "Windows est actuellement en mode %s." % ("clair" if system_light() else "sombre"),
                  wrap=300, row=3, column=0, columnspan=3, sticky="w", pady=(2, 8))

        ttk.Label(col, text="Couleurs à modifier :").grid(row=4, column=0, columnspan=3, sticky="w")
        sf = ttk.Frame(col)
        sf.grid(row=5, column=0, columnspan=3, sticky="w", pady=(2, 6))
        self.edit_set = "colors_light" if bar_light(self.cfg) else "colors"
        self.v_set = tk.StringVar(value=self.edit_set)
        ttk.Radiobutton(sf, text="Mode sombre", value="colors", variable=self.v_set,
                        command=self.switch_color_set).pack(side="left")
        ttk.Radiobutton(sf, text="Mode clair", value="colors_light", variable=self.v_set,
                        command=self.switch_color_set).pack(side="left", padx=(12, 0))

        self.v_colors, self.swatches = {}, {}
        for r, (k, name) in enumerate(COLOR_NAMES, start=6):
            ttk.Label(col, text=name).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 10))
            val = self.cfg[self.edit_set][k]
            sw = tk.Label(col, width=4, bg=val, relief="solid", borderwidth=1, cursor="hand2")
            sw.grid(row=r, column=1, pady=2)
            sw.bind("<Button-1>", lambda e, k=k: self.pick_color(k))
            self.swatches[k] = sw
            v = tk.StringVar(value=val)
            ttk.Entry(col, textvariable=v, width=9).grid(row=r, column=2, padx=(8, 0), pady=2, sticky="w")
            self.v_colors[k] = v
            self.track(v, lambda val, k=k: self.set_color(k, val))
        r = 6 + len(COLOR_NAMES)
        ttk.Button(col, text="Couleurs par défaut", command=self.reset_colors).grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.hint(col, "Clique sur une pastille pour choisir une couleur. Le fond doit être proche de la "
                       "couleur de ta barre des tâches.", wrap=300, row=r + 1, column=0, columnspan=3,
                  sticky="w", pady=(6, 0))

        # --- carte de controle (appui long)
        cf = ttk.LabelFrame(f, text="Carte de contrôle (appui long)", padding=10)
        cf.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        cf.columnconfigure(1, weight=1)
        self.themes = card_themes()
        ttk.Label(cf, text="Thème").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.cb_theme = ttk.Combobox(cf, state="readonly", width=34)
        self.cb_theme.grid(row=0, column=1, sticky="w")
        self.cb_theme.bind("<<ComboboxSelected>>", self.on_card_theme)
        self.fill_themes()

        ttk.Label(cf, text="Couleurs").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0))
        self.card_modes = [("bar", "Comme la barre"),
                           ("dark", "Toujours sombre"), ("light", "Toujours clair")]
        self.cb_cmode = ttk.Combobox(cf, state="readonly", width=34, values=[t for _, t in self.card_modes])
        cur = self.cfg.get("card_mode", "bar")
        self.cb_cmode.current(next((i for i, (k, _) in enumerate(self.card_modes) if k == cur), 0))
        self.cb_cmode.grid(row=1, column=1, sticky="w", pady=(8, 0))
        self.cb_cmode.bind("<<ComboboxSelected>>", self.on_card_mode)

        bf = ttk.Frame(cf)
        bf.grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Button(bf, text="Ouvrir la carte sur la barre", command=self.try_card).pack(side="left")
        ttk.Button(bf, text="Thèmes personnalisés…", command=self.edit_themes).pack(side="left", padx=6)
        ttk.Button(bf, text="↻", width=3, command=self.reload_themes).pack(side="left")
        self.hint(cf, "« Thèmes personnalisés… » ouvre le fichier card_themes.json : copie un thème, change ses "
                      "couleurs, enregistre puis clique sur ↻.", wrap=420, row=3, column=0, columnspan=2,
                  sticky="w", pady=(8, 0))

        self.card_cv = tk.Canvas(cf, width=self.px(300), height=self.px(140), highlightthickness=0,
                                 bg=ttk.Style().lookup("TFrame", "background") or "#f0f0f0")
        self.card_cv.grid(row=0, column=2, rowspan=4, sticky="e", padx=(10, 0))
        self.draw_card_preview()

    # -- couleurs de la barre
    def set_theme_mode(self, v):
        self.cfg["theme_mode"] = v
        if v in ("dark", "light"):      # on edite directement le jeu de couleurs affiche
            self.v_set.set("colors_light" if v == "light" else "colors")
            self.switch_color_set()
        self.draw_card_preview()

    def switch_color_set(self):
        self.edit_set = self.v_set.get()
        self.loading = True
        try:
            for k, v in self.v_colors.items():
                val = self.cfg[self.edit_set][k]
                v.set(val)
                self.swatches[k].configure(bg=val)
        finally:
            self.loading = False

    def set_color(self, k, val):
        val = val.strip()
        if not HEX_RE.match(val):
            raise ValueError(val)
        self.cfg[self.edit_set][k] = val
        self.swatches[k].configure(bg=val)
        self.draw_card_preview()

    def pick_color(self, k):
        _rgb, hx = colorchooser.askcolor(color=self.cfg[self.edit_set][k], parent=self.win,
                                         title=dict(COLOR_NAMES)[k])
        if hx:
            self.v_colors[k].set(hx)

    def reset_colors(self):
        for k, v in (LIGHT_COLORS if self.edit_set == "colors_light" else DARK_COLORS).items():
            self.v_colors[k].set(v)

    # -- carte
    def fill_themes(self):
        self.theme_keys = list(self.themes)
        self.cb_theme.configure(values=[self.themes[k]["name"] for k in self.theme_keys])
        cur = self.cfg.get("card_theme", "barre")
        self.cb_theme.current(self.theme_keys.index(cur) if cur in self.theme_keys else 0)

    def on_card_theme(self, _e=None):
        self.cfg["card_theme"] = self.theme_keys[self.cb_theme.current()]
        self.draw_card_preview()
        self.changed()

    def on_card_mode(self, _e=None):
        self.cfg["card_mode"] = self.card_modes[self.cb_cmode.current()][0]
        self.draw_card_preview()
        self.changed()

    def reload_themes(self):
        self.themes = card_themes()
        self.fill_themes()
        self.draw_card_preview()
        self.app.close_card()

    def edit_themes(self):
        """Cree card_themes.json (avec un exemple) s'il n'existe pas, puis l'ouvre dans le Bloc-notes."""
        if not os.path.exists(CARD_THEMES_PATH):
            ex = copy.deepcopy(CARD_THEMES["ocean"])
            ex["name"] = "Mon thème"
            try:
                os.makedirs(os.path.dirname(CARD_THEMES_PATH), exist_ok=True)
                with open(CARD_THEMES_PATH, "w", encoding="utf-8") as fh:
                    json.dump({"mon_theme": ex}, fh, indent=2, ensure_ascii=False)
            except OSError as e:
                messagebox.showerror("HA Taskbar", "Impossible de créer %s : %s" % (CARD_THEMES_PATH, e),
                                     parent=self.win)
                return
            self.reload_themes()
        subprocess.Popen(["notepad.exe", CARD_THEMES_PATH])

    def try_card(self):
        """Ouvre la vraie carte du premier element avec le theme en cours d'edition."""
        if self.preview_job:
            self.win.after_cancel(self.preview_job)
            self.preview()
        if self.app.items:
            self.app.open_card(self.app.items[0])
        else:
            messagebox.showinfo("HA Taskbar", "Ajoute d'abord un élément dans l'onglet Éléments.", parent=self.win)

    def draw_card_preview(self):
        """Mini carte dessinee avec les couleurs du theme choisi."""
        from card_ui import derive_palette, rrect
        cv, p = self.card_cv, self.px
        light = card_light(self.cfg, bar_light(self.cfg))
        base, radius = card_palette(self.cfg, bar_colors(self.cfg), light, self.themes)
        c = derive_palette(base)
        r = p(radius)
        cv.delete("all")
        W, H = int(cv["width"]), int(cv["height"])
        rrect(cv, 1, 1, W - 2, H - 2, p(8), fill=c["bg"], outline=c["border"])
        fam = self.cfg.get("font", "Segoe UI")
        icon_font = next((x for x in ICON_FONTS if x in tkfont.families(self.win)), None)
        if icon_font:
            cv.create_text(p(26), p(28), text=ICONS["lightbulb"][0], font=(icon_font, 15), fill=c["accent"])
        cv.create_text(p(48), p(20), text="Lumière salon", font=(fam, 10, "bold"), fill=c["fg"], anchor="w")
        cv.create_text(p(48), p(38), text="Allumée · 70 %", font=(fam, 8), fill=c["dim"], anchor="w")
        # interrupteur
        tw, th, tx, ty = p(36), p(18), W - p(52), p(20)
        cv.create_oval(tx, ty, tx + th, ty + th, fill=c["accent"], outline=c["accent"])
        cv.create_oval(tx + tw - th, ty, tx + tw, ty + th, fill=c["accent"], outline=c["accent"])
        cv.create_rectangle(tx + th / 2, ty, tx + tw - th / 2, ty + th, fill=c["accent"], outline=c["accent"])
        kr = th * 0.28
        cv.create_oval(tx + tw - th / 2 - kr, ty + th / 2 - kr, tx + tw - th / 2 + kr, ty + th / 2 + kr,
                       fill=c["accent_fg"], outline=c["accent_fg"])
        # curseur
        y, x0, x1 = p(68), p(18), W - p(18)
        xm = x0 + (x1 - x0) * 0.7
        cv.create_line(x0, y, x1, y, fill=c["track"], width=p(4), capstyle="round")
        cv.create_line(x0, y, xm, y, fill=c["accent"], width=p(4), capstyle="round")
        cv.create_oval(xm - p(8), y - p(8), xm + p(8), y + p(8), fill=c["knob"], outline=c["border"])
        cv.create_oval(xm - p(4), y - p(4), xm + p(4), y + p(4), fill=c["accent"], outline="")
        # choix
        x = p(18)
        for txt, sel in (("Éco", False), ("Confort", True), ("Absent", False)):
            w_ = p(16) + tkfont.Font(font=(fam, 8)).measure(txt)
            fill = c["accent"] if sel else c["surface"]
            rrect(cv, x, p(94), x + w_, p(120), r, fill=fill, outline=fill)
            cv.create_text(x + w_ / 2, p(107), text=txt, font=(fam, 8), fill=c["accent_fg"] if sel else c["fg"])
            x += w_ + p(6)

    # ------------------------------------------------------------------ enregistrement
    def validate(self):
        for i, it in enumerate(self.cfg["items"]):
            if not it.get("entity_id"):
                self.nb.select(1)
                self.select_item(i)
                messagebox.showerror("HA Taskbar", "L'élément n°%d n'a pas d'entité." % (i + 1), parent=self.win)
                return False
        if not self.data_ok:
            self.nb.select(1)
            messagebox.showerror("HA Taskbar", "Le champ « Données (JSON) » est invalide.", parent=self.win)
            return False
        return True

    def apply(self):
        if not self.validate():
            return False
        save_config(self.cfg)
        try:
            set_startup(self.v_startup.get())
        except OSError as e:
            messagebox.showwarning("HA Taskbar", "Impossible de régler le démarrage auto : %s" % e, parent=self.win)
        self.saved = copy.deepcopy(self.cfg)
        self.dirty = False
        if self.preview_job:
            self.win.after_cancel(self.preview_job)
            self.preview_job = None
        self.app.apply_config(copy.deepcopy(self.cfg))
        self.status.configure(text="✔ Enregistré")
        return True

    def ok(self):
        if self.apply():
            self.close()

    def cancel(self):
        self.app.apply_config(copy.deepcopy(self.saved))
        self.close()

    def close(self):
        if self.preview_job:
            self.win.after_cancel(self.preview_job)
        self.win.destroy()
        self.app.settings_win = None

    def on_close(self):
        if not self.dirty:
            self.close()
            return
        r = messagebox.askyesnocancel("HA Taskbar", "Enregistrer les modifications ?", parent=self.win)
        if r is None:
            return
        if r:
            self.ok()
        else:
            self.cancel()
