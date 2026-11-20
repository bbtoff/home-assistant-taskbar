"""
Apparence "Windows 11" des fenetres (reglages, mise a jour) : theme Sun Valley (sv_ttk, licence MIT,
fourni dans le dossier sv_ttk/), clair ou sombre selon Windows, et navigation laterale.
"""
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

import sv_ttk
from ha_core import system_light

# Couleurs des elements dessines a la main (le reste vient du theme)
PALETTES = {
    "dark": {"bg": "#1c1c1c", "nav": "#202020", "card": "#2b2b2b", "field": "#2b2b2b", "border": "#3d3d3d",
             "fg": "#fafafa", "hint": "#a6a6a6", "ok": "#6ccb5f", "err": "#ff99a4", "accent": "#57c8ff",
             "hover": "#2d2d2d", "selected": "#2d2d2d", "cell_sel": "#1f3d5c", "icon_on": "#ffc83d"},
    "light": {"bg": "#fafafa", "nav": "#f0f0f0", "card": "#ffffff", "field": "#ffffff", "border": "#d9d9d9",
              "fg": "#1c1c1c", "hint": "#5f5f5f", "ok": "#0f7b0f", "err": "#c42b1c", "accent": "#005fb8",
              "hover": "#e5e5e5", "selected": "#e5e5e5", "cell_sel": "#cce4f7", "icon_on": "#b86e00"},
}
_FONTS = {"SunValleyCaptionFont": 12, "SunValleyBodyFont": 14, "SunValleyBodyStrongFont": 14,
          "SunValleyBodyLargeFont": 18, "SunValleySubtitleFont": 20, "SunValleyTitleFont": 28}


def apply(root):
    """Applique le theme (clair/sombre comme Windows) et renvoie la palette."""
    mode = "light" if system_light() else "dark"
    if getattr(root, "_ui_mode", None) == "fallback":
        mode = "light"
    elif getattr(root, "_ui_mode", None) != mode:
        try:
            sv_ttk.set_theme(mode, root)
            root._ui_mode = mode
        except Exception:
            # Theme introuvable ou illisible : on garde l'apparence Windows classique plutot que d'echouer
            try:
                ttk.Style(root).theme_use("vista")
            except tk.TclError:
                pass
            root._ui_mode = "fallback"
            mode = "light"
        # Les polices du theme sont en pixels fixes : on suit le zoom de l'ecran (125 %, 150 %...)
        scale = root.winfo_fpixels("1i") / 96.0
        for name, px in _FONTS.items():
            try:
                tkfont.nametofont(name, root).configure(size=-round(px * scale))
            except tk.TclError:
                pass
    pal = PALETTES[mode]
    st = ttk.Style(root)
    st.configure("Hint.TLabel", foreground=pal["hint"], font="SunValleyCaptionFont")
    st.configure("Ok.TLabel", foreground=pal["ok"], font="SunValleyCaptionFont")
    st.configure("Err.TLabel", foreground=pal["err"], font="SunValleyCaptionFont")
    st.configure("Title.TLabel", font="SunValleySubtitleFont")
    st.configure("Strong.TLabel", font="SunValleyBodyStrongFont")
    st.configure("Empty.TLabel", background=pal["field"], foreground=pal["hint"])
    return pal


def dark_title_bar(win, dark):
    """Barre de titre Windows sombre ou claire, assortie au theme (Windows 10 2004+ / 11)."""
    try:
        import ctypes
        win.update_idletasks()
        hwnd = int(win.wm_frame(), 16)
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):          # DWMWA_USE_IMMERSIVE_DARK_MODE (et ancien numero)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


class SideNav(ttk.Frame):
    """Remplace un ttk.Notebook : menu a gauche avec icones (comme les Parametres de Windows 11),
    titre de la page en haut. Meme utilisation : les pages sont creees avec ce widget pour parent,
    puis add(page, text=...) ; select(i) affiche une page."""

    def __init__(self, win, pal, icon_font, title, subtitle, px):
        super().__init__(win, padding=(px(28), px(20), px(28), px(8)))
        self.pal, self.icon_font, self.px = pal, icon_font, px
        self.pages, self.rows = [], []
        self.current = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.title = ttk.Label(self, text="", style="Title.TLabel")
        self.title.grid(row=0, column=0, sticky="w", pady=(0, px(14)))

        side = self.side = tk.Frame(win, bg=pal["nav"], width=px(230))
        side.grid_propagate(False)
        side.columnconfigure(0, weight=1)
        head = self.head = tk.Frame(side, bg=pal["nav"])
        head.grid(row=0, column=0, sticky="ew", padx=px(16), pady=(px(18), px(22)))
        tk.Label(head, text=title, bg=pal["nav"], fg=pal["fg"], font="SunValleyBodyStrongFont").pack(anchor="w")
        tk.Label(head, text=subtitle, bg=pal["nav"], fg=pal["hint"], font="SunValleyCaptionFont").pack(anchor="w")

    def add(self, page, text, icon=""):
        i = len(self.pages)
        page.grid(row=1, column=0, sticky="nsew")
        self.pages.append((page, text))
        pal, px = self.pal, self.px
        row = tk.Frame(self.side, bg=pal["nav"], cursor="hand2")
        row.grid(row=i + 1, column=0, sticky="ew", padx=px(8), pady=1)
        bar = tk.Frame(row, bg=pal["nav"], width=px(3), height=px(16))      # repere de la page active
        bar.pack(side="left", padx=(0, px(10)))
        ic = tk.Label(row, text=icon, bg=pal["nav"], fg=pal["fg"], cursor="hand2",
                      font=(self.icon_font, 12) if self.icon_font else None)
        ic.pack(side="left", padx=(0, px(12)))
        lb = tk.Label(row, text=text, bg=pal["nav"], fg=pal["fg"], cursor="hand2", font="SunValleyBodyFont",
                      pady=px(8))
        lb.pack(side="left")
        widgets = (row, ic, lb)
        for w in widgets:
            w.bind("<Button-1>", lambda e, k=i: self.select(k))
            w.bind("<Enter>", lambda e, k=i: self._paint(k, hover=True))
            w.bind("<Leave>", lambda e, k=i: self._paint(k))
        self.rows.append((widgets, bar))
        if self.current is None:
            self.select(0)

    def _paint(self, k, hover=False):
        widgets, bar = self.rows[k]
        on = k == self.current
        bg = self.pal["selected"] if on else self.pal["hover"] if hover else self.pal["nav"]
        for w in widgets:
            w.configure(bg=bg)
        bar.configure(bg=self.pal["accent"] if on else bg)

    def select(self, k):
        if not 0 <= k < len(self.pages):
            return
        self.current = k
        page, text = self.pages[k]
        page.tkraise()
        self.title.configure(text=text)
        for i in range(len(self.rows)):
            self._paint(i)


class ScrollFrame:
    """Cadre qui defile a la molette quand son contenu est plus haut que la place disponible.
    Utilisation : sf = ScrollFrame(parent, pal) ; construire le contenu dans sf.inner ; placer sf.outer."""

    def __init__(self, parent, pal, padding=0):
        self.outer = ttk.Frame(parent)
        self.outer.columnconfigure(0, weight=1)
        self.outer.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self.outer, highlightthickness=0, borderwidth=0, bg=pal["bg"])
        self.bar = ttk.Scrollbar(self.outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.inner = ttk.Frame(self.canvas, padding=padding)
        self.inner._scrollframe = self
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self._update())
        self.canvas.bind("<Configure>", lambda e: (self.canvas.itemconfigure(self._win, width=e.width),
                                                   self._update()))
        # molette : liee a la fenetre (etiquette commune a tous ses widgets), disparait avec elle
        self.outer.winfo_toplevel().bind("<MouseWheel>", self._wheel, add="+")

    def _update(self):
        self.canvas.configure(scrollregion=(0, 0, self.inner.winfo_reqwidth(), self.inner.winfo_reqheight()))
        need = self.inner.winfo_reqheight() > self.canvas.winfo_height() > 1
        if need and not self.bar.winfo_ismapped():
            self.bar.grid(row=0, column=1, sticky="ns")
        elif not need and self.bar.winfo_ismapped():
            self.bar.grid_remove()
            self.canvas.yview_moveto(0)

    def _wheel(self, e):
        try:
            if not self.canvas.winfo_ismapped() or not self.bar.winfo_ismapped():
                return
            w = e.widget if isinstance(e.widget, tk.Misc) else None
            if w is None or w.winfo_class() in ("Treeview", "Listbox", "Text", "TSpinbox", "TCombobox"):
                return
            x, y = self.canvas.winfo_pointerxy()
            cx, cy = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
            if cx <= x < cx + self.canvas.winfo_width() and cy <= y < cy + self.canvas.winfo_height():
                self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        except (tk.TclError, KeyError):
            pass


def scroll_into_view(widget):
    """Fait defiler le ScrollFrame qui contient `widget` pour le montrer."""
    w = widget
    while w is not None:
        sf = getattr(w, "_scrollframe", None)
        if sf is not None:
            try:
                sf.inner.update_idletasks()
                y = widget.winfo_rooty() - sf.inner.winfo_rooty()
                h = max(1, sf.inner.winfo_reqheight())
                sf.canvas.yview_moveto(max(0.0, (y - 40) / float(h)))
            except tk.TclError:
                pass
            return
        w = w.master
