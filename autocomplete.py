"""
Autocompletion des entites : quand on tape dans un champ « Entite », une liste de suggestions s'ouvre
sous le champ (nom, piece, entity_id). Haut/Bas pour choisir, Entree ou Tab pour valider, Echap pour
fermer. Plusieurs mots : tous doivent se trouver dans le nom, la piece ou l'entity_id.
"""
import difflib
import tkinter as tk

from palette import fold

ROWS = 8


def search(entities, friendly, areas, text, limit=ROWS):
    """entity_id qui correspondent au texte, les meilleurs d'abord."""
    words = fold(text).split()
    if not words:
        return []
    out = []
    for eid in entities:
        name = fold(friendly(eid))
        area = fold(areas.get(eid, ""))
        e = eid.lower()
        hay = " ".join((e, name, area))
        if not all(w in hay for w in words):
            continue
        w0 = words[0]
        obj = e.split(".", 1)[-1]
        score = (0 if e.startswith(w0) or obj.startswith(w0) else
                 1 if name.startswith(w0) else
                 2 if any(p.startswith(w0) for p in name.split() + obj.split("_")) else 3)
        out.append((score, len(e), e, eid))
    out.sort()
    return [r[-1] for r in out[:limit]]


def closest(entities, eid):
    """Entite qui ressemble le plus a un entity_id inconnu (renommee dans Home Assistant...)."""
    if not eid or "." not in eid:
        return None
    domain, obj = eid.split(".", 1)
    same = [e for e in entities if e.startswith(domain + ".")]
    best = difflib.get_close_matches(eid, same, n=1, cutoff=0.6)
    if best:
        return best[0]
    # sinon : meme domaine et un mot en commun (camera.entree -> camera.porte_entree_fluent)
    parts = [p for p in obj.split("_") if len(p) >= 3]
    hits = [e for e in same if any(p in e for p in parts)]
    return hits[0] if len(hits) == 1 else None


class EntityAutocomplete:
    def __init__(self, widget, var, sw, on_pick=None):
        """widget : Entry/Combobox ; var : sa StringVar ; sw : fenetre des reglages (entities, friendly, areas, pal)."""
        self.w, self.var, self.sw, self.on_pick = widget, var, sw, on_pick
        self.pop = None
        self.rows = []
        self._packed = -1
        self.results = []
        self.sel = 0
        self.picking = False
        widget.bind("<KeyRelease>", self.on_key, add="+")
        widget.bind("<Down>", lambda e: self.move(1))
        widget.bind("<Up>", lambda e: self.move(-1))
        widget.bind("<Return>", self.on_enter, add="+")
        widget.bind("<Tab>", self.on_enter, add="+")
        widget.bind("<Escape>", self.on_escape, add="+")
        widget.bind("<FocusOut>", lambda e: widget.after(150, self.hide_if_unfocused), add="+")
        widget.bind("<Destroy>", lambda e: self.hide(), add="+")
        widget.bind("<Configure>", lambda e: self.place(), add="+")

    # ---------------------------------------------------------------- clavier
    def on_key(self, e):
        if e.keysym in ("Up", "Down", "Return", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L",
                        "Control_R", "Alt_L", "Alt_R", "Left", "Right", "Home", "End"):
            return
        text = self.var.get().strip()
        if not text or text in self.sw.entities:
            self.hide()
            return
        self.results = search(self.sw.entities, self.sw.friendly, getattr(self.sw, "areas", {}), text)
        self.sel = 0
        if self.results:
            self.show()
        else:
            self.hide()

    def move(self, d):
        if not self.visible():
            return None          # liste deroulante normale du champ
        self.sel = (self.sel + d) % len(self.results)
        self.paint()
        return "break"

    def on_enter(self, e):
        if not self.visible():
            return None
        self.pick(self.sel)
        return "break"

    def on_escape(self, e):
        if not self.visible():
            return None
        self.hide()
        return "break"

    # ---------------------------------------------------------------- liste
    def visible(self):
        return self.pop is not None and bool(self.results)

    def show(self):
        pal = self.sw.pal
        if self.pop is None:
            self.pop = tk.Toplevel(self.w)
            self.pop.withdraw()
            self.pop.overrideredirect(True)
            self.pop.attributes("-topmost", True)
            self.pop.configure(bg=pal["border"])
            self.box = tk.Frame(self.pop, bg=pal["field"])
            self.box.pack(fill="both", expand=True, padx=1, pady=1)
            self.rows = []
            for i in range(ROWS):
                r = tk.Frame(self.box, bg=pal["field"], cursor="hand2")
                nm = tk.Label(r, bg=pal["field"], fg=pal["fg"], anchor="w", font=("Segoe UI", 10))
                nm.pack(side="left", padx=(8, 0), pady=3)
                ar = tk.Label(r, bg=pal["field"], fg=pal["hint"], anchor="w", font=("Segoe UI", 9))
                ar.pack(side="left", padx=(8, 0))
                ei = tk.Label(r, bg=pal["field"], fg=pal["hint"], anchor="e", font=("Segoe UI", 9))
                ei.pack(side="right", padx=(12, 8))
                for wdg in (r, nm, ar, ei):
                    wdg.bind("<Button-1>", lambda e, i=i: self.pick(i))
                    wdg.bind("<Enter>", lambda e, i=i: self.hover(i))
                self.rows.append((r, nm, ar, ei))
        self.paint()
        self.place()
        self.pop.deiconify()
        self.pop.lift()

    def paint(self):
        pal = self.sw.pal
        areas = getattr(self.sw, "areas", {})
        for i, (r, nm, ar, ei) in enumerate(self.rows):
            if i >= len(self.results):
                r.pack_forget()
                continue
            eid = self.results[i]
            bg = pal["cell_sel"] if i == self.sel else pal["field"]
            for wdg in (r, nm, ar, ei):
                wdg.configure(bg=bg)
            nm.configure(text=(self.sw.friendly(eid) or eid)[:48])
            ar.configure(text=areas.get(eid, "")[:24])
            ei.configure(text=eid[:56])
        n = len(self.results)
        if n != getattr(self, "_packed", -1):       # repack dans l'ordre seulement si le nombre change
            for r, *_x in self.rows:
                r.pack_forget()
            for r, *_x in self.rows[:n]:
                r.pack(fill="x")
            self._packed = n

    def hover(self, i):
        if i != self.sel and i < len(self.results):
            self.sel = i
            self.paint()

    def place(self):
        if self.pop is None or not self.results:
            return
        try:
            self.pop.update_idletasks()
            x, y = self.w.winfo_rootx(), self.w.winfo_rooty() + self.w.winfo_height() + 2
            w = max(self.w.winfo_width(), self.pop.winfo_reqwidth())
            h = self.pop.winfo_reqheight()
            if y + h > self.w.winfo_screenheight():
                y = self.w.winfo_rooty() - h - 2
            self.pop.geometry("%dx%d+%d+%d" % (w, h, x, y))
        except tk.TclError:
            pass

    def pick(self, i):
        if i >= len(self.results):
            return
        eid = self.results[i]
        self.hide()
        self.var.set(eid)
        self.w.icursor("end")
        self.w.focus_set()
        if self.on_pick:
            self.on_pick(eid)

    def hide_if_unfocused(self):
        try:
            f = self.w.focus_get()
        except (tk.TclError, KeyError):
            f = None
        if f is not self.w:
            self.hide()

    def hide(self):
        self.results = []
        if self.pop is not None:
            try:
                self.pop.destroy()
            except tk.TclError:
                pass
        self.pop = None
        self.rows = []
        self._packed = -1
