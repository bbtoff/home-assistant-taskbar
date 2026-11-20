"""
Fenetre camera : quand une notification a une camera (Reglages -> Notifications), par exemple quand on
sonne, une petite fenetre s'ouvre en bas a droite avec l'image en direct. Elle ne prend pas le clavier,
se ferme toute seule apres un moment, et un clic sur l'image ouvre la carte de la camera.
"""
import ctypes
import queue
import threading
import time
import tkinter as tk
from ctypes import wintypes

from card_ui import derive_palette
from ha_core import ICONS, card_light, card_palette
from i18n import _

user32 = ctypes.windll.user32
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]

REFRESH_S = 1.0          # une image par seconde
WIDTH = 440
ERROR = "#e5534b"


class CameraPopup:
    def __init__(self, app, camera, text, seconds=60):
        self.app, self.camera = app, camera
        self.alive = True
        self.q = queue.Queue()
        self.img = None
        k = app.root.winfo_fpixels("1i") / 96.0
        self.s = s = lambda v: int(round(v * k))
        light = card_light(app.cfg, getattr(app, "light", False))
        base, self.radius = card_palette(app.cfg, app.colors, light)
        c = self.c = derive_palette(base)
        fam = app.cfg.get("font", "Segoe UI")
        ifont = app.icon_font or fam
        self.iw = s(WIDTH)

        win = self.win = tk.Toplevel(app.root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=c["border"])
        body = tk.Frame(win, bg=c["bg"], padx=s(12), pady=s(10))
        body.pack(padx=1, pady=1, fill="both", expand=True)

        head = tk.Frame(body, bg=c["bg"])
        head.pack(fill="x")
        tk.Label(head, text=ICONS["bell"][0], bg=c["bg"], fg=c["accent"], font=(ifont, 13)).pack(side="left")
        self.title = tk.Label(head, text="", bg=c["bg"], fg=c["fg"], font=(fam, 10, "bold"), anchor="w",
                              justify="left", wraplength=self.iw - s(70))
        self.title.pack(side="left", padx=(s(8), 0), fill="x", expand=True)
        x = tk.Label(head, text="✕", bg=c["bg"], fg=c["dim"], font=(fam, 11), cursor="hand2")
        x.pack(side="right")
        x.bind("<Button-1>", lambda e: self.close())
        x.bind("<Enter>", lambda e: x.configure(fg=c["fg"]))
        x.bind("<Leave>", lambda e: x.configure(fg=c["dim"]))

        self.view = tk.Label(body, text=_("Chargement de l'image…"), bg=c["surface"], fg=c["dim"],
                             font=(fam, 9), cursor="hand2", width=1, height=1)
        self.view.pack(fill="x", pady=(s(8), 0), ipady=s(70))
        self.view.bind("<Button-1>", lambda e: self.open_card())

        foot = tk.Frame(body, bg=c["bg"])
        foot.pack(fill="x", pady=(s(8), 0))
        st = app.last_states.get(camera) or {}
        tk.Label(foot, text=st.get("attributes", {}).get("friendly_name") or camera, bg=c["bg"], fg=c["dim"],
                 font=(fam, 8)).pack(side="left")
        self.left = tk.Label(foot, text="", bg=c["bg"], fg=c["dim"], font=(fam, 8))
        self.left.pack(side="right")
        keep = tk.Label(foot, text=_("Garder ouverte"), bg=c["bg"], fg=c["dim"], font=(fam, 8), cursor="hand2")
        keep.pack(side="right", padx=(0, s(12)))
        keep.bind("<Button-1>", lambda e: self.keep())
        keep.bind("<Enter>", lambda e: keep.configure(fg=c["fg"]))
        keep.bind("<Leave>", lambda e: keep.configure(fg=c["dim"]))
        self.keep_lb = keep

        win.update_idletasks()
        self.hwnd = user32.GetAncestor(win.winfo_id(), 2)
        ex = user32.GetWindowLongW(self.hwnd, -20)
        # fenetre outil, sans bouton dans la barre, qui ne prend pas le clavier a l'application en cours
        user32.SetWindowLongW(self.hwnd, -20, (ex | 0x80 | 0x08000000) & ~0x40000)
        try:
            pref = ctypes.c_int(1 if self.radius <= 3 else 2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(self.hwnd), 33, ctypes.byref(pref), 4)
        except Exception:
            pass
        self.ring(text, seconds)
        threading.Thread(target=self._fetch, args=(app.ha,), daemon=True).start()
        self._loop()

    def ring(self, text, seconds=60):
        """Nouvelle sonnerie (fenetre deja ouverte ou non) : texte et delai de fermeture remis a jour."""
        self.title.configure(text=text)
        self.until = time.monotonic() + max(10, seconds) if seconds else None
        self.place()
        self.win.deiconify()
        self.win.attributes("-topmost", True)

    def keep(self):
        self.until = None
        self.left.configure(text="")
        self.keep_lb.pack_forget()

    def place(self):
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        a = self.app.anchor_for(None)
        if a is None:
            mx, my, mw, mh = self.app.monitor_rect()
            x, y = mx + mw - w - self.s(16), my + mh - h - self.s(64)
        else:
            _cx, top, _xmin, xmax = a
            x, y = xmax - w - self.s(16), top - h - self.s(16)
        self.win.geometry("%dx%d+%d+%d" % (w, h, x, y))

    def _fetch(self, ha):
        import imaging
        while self.alive:
            try:
                png, _w, _h = imaging.to_png(ha.camera_image(self.camera), self.iw, int(self.iw * 0.75))
                self.q.put(("img", png))
                delay = REFRESH_S
            except Exception as e:
                code = getattr(e, "code", None)
                self.q.put(("err", _("Caméra indisponible dans Home Assistant") if code in (404, 500, 503)
                            else str(getattr(e, "reason", e))))
                delay = 5.0
            end = time.monotonic() + delay
            while self.alive and time.monotonic() < end:
                time.sleep(0.1)

    def _loop(self):
        if not self.alive:
            return
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "img":
                    try:
                        img = tk.PhotoImage(master=self.app.root, data=payload)
                    except tk.TclError:
                        continue
                    first = self.img is None
                    self.img = img
                    self.view.configure(image=img, text="", width=img.width(), height=img.height())
                    if first:
                        self.view.pack_configure(ipady=0)
                        self.place()
                elif self.img is None:
                    self.view.configure(text=payload, fg=ERROR)
        except queue.Empty:
            pass
        if self.until is not None:
            left = self.until - time.monotonic()
            if left <= 0:
                self.close()
                return
            self.left.configure(text=_("se ferme dans %d s") % int(left + 0.99))
        self.app.root.after(200, self._loop)

    def open_card(self):
        self.close()
        self.app.open_card({"entity_id": self.camera})

    def close(self):
        if not self.alive:
            return
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if getattr(self.app, "cam_popup", None) is self:
            self.app.cam_popup = None
