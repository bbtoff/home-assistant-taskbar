"""Fenetre "Mise a jour disponible" : notes de version, telechargement verifie, installation."""
import os
import re
import subprocess
import tempfile
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from ha_core import FROZEN, __version__, download_update, save_config


def plain_notes(md):
    """Notes de version Markdown -> texte simple lisible."""
    out = []
    for line in md.replace("\r\n", "\n").split("\n"):
        line = re.sub(r"^#+\s*", "", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"^\s*[-*]\s+", "• ", line)
        out.append(line)
    return "\n".join(out).strip()


class UpdateWindow:
    def __init__(self, app, info):
        self.app = app
        self.info = info
        self.cancel_flag = False
        self.busy = False
        win = self.win = tk.Toplevel(app.root)
        win.title("Mise à jour de HA Taskbar")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self.later)
        px = lambda v: int(v * win.winfo_fpixels("1i") / 96)   # noqa: E731
        f = ttk.Frame(win, padding=16)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Version %s disponible" % info["version"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(f, text="Tu as la version %s." % __version__, foreground="#5f5f5f").pack(anchor="w", pady=(2, 10))

        notes = tk.Text(f, height=12, width=64, wrap="word", relief="solid", borderwidth=1,
                        font=("Segoe UI", 9), padx=8, pady=6)
        notes.insert("1.0", plain_notes(info.get("notes", "")) or "(pas de notes de version)")
        notes.configure(state="disabled")
        notes.pack(fill="both", expand=True)

        self.status = ttk.Label(f, text="", foreground="#5f5f5f", wraplength=px(460), justify="left")
        self.status.pack(anchor="w", pady=(10, 0))
        self.bar = ttk.Progressbar(f, mode="determinate", maximum=100)

        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(12, 0))
        if FROZEN and info.get("asset_url"):
            self.b_install = ttk.Button(bf, text="Installer maintenant", command=self.install)
            hint = ("Le programme d'installation est téléchargé depuis GitHub et vérifié, puis HA Taskbar "
                    "se ferme, se met à jour et redémarre tout seul. Tes réglages sont conservés.")
        else:
            # Lance depuis les sources (ou version sans installateur) : on ouvre la page de la version
            self.b_install = ttk.Button(bf, text="Ouvrir la page de la version", command=self.open_page)
            hint = ("Tu utilises la version « sources » : récupère la nouvelle version sur GitHub "
                    "(git pull ou téléchargement), ou installe le programme d'installation.")
        self.status.configure(text=hint)
        self.b_install.pack(side="right")
        self.b_later = ttk.Button(bf, text="Plus tard", command=self.later)
        self.b_later.pack(side="right", padx=6)
        self.b_skip = ttk.Button(bf, text="Ignorer cette version", command=self.skip)
        self.b_skip.pack(side="left")

        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        win.geometry("+%d+%d" % ((win.winfo_screenwidth() - w) // 2, (win.winfo_screenheight() - h) // 3))
        win.focus_force()

    # ---------------- boutons
    def open_page(self):
        webbrowser.open(self.info.get("page") or "")
        self.close()

    def later(self):
        if self.busy:
            self.cancel_flag = True       # annule le telechargement en cours
            return
        self.close()

    def skip(self):
        self.app.cfg["skip_version"] = self.info["version"]
        try:
            save_config(self.app.cfg)
        except OSError:
            pass
        if self.app.settings_win is not None:
            self.app.settings_win.cfg["skip_version"] = self.info["version"]
            self.app.settings_win.saved["skip_version"] = self.info["version"]
        self.close()

    def close(self):
        if self.app.update_win is self:
            self.app.update_win = None
        self.win.destroy()

    # ---------------- installation
    def install(self):
        self.busy = True
        self.cancel_flag = False
        for b in (self.b_install, self.b_skip):
            b.configure(state="disabled")
        self.b_later.configure(text="Annuler")
        self.bar.pack(fill="x", pady=(6, 0), before=self.status)
        self.status.configure(text="Téléchargement…")
        dest = os.path.join(tempfile.gettempdir(), "HATaskbar-update")

        def progress(done, total):
            self.app.q.put(("update_progress", (done, total)))

        def run():
            try:
                path = download_update(self.info, dest, progress, lambda: self.cancel_flag)
                self.app.q.put(("update_ready", path))
            except Exception as e:
                self.app.q.put(("update_failed", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def on_progress(self, done, total):
        if total:
            self.bar.configure(value=100 * done / total)
            self.status.configure(text="Téléchargement… %.1f Mo sur %.1f Mo" % (done / 1e6, total / 1e6))

    def on_failed(self, msg):
        self.busy = False
        self.bar.pack_forget()
        for b in (self.b_install, self.b_skip):
            b.configure(state="normal")
        self.b_later.configure(text="Plus tard")
        if self.cancel_flag:
            self.close()
        else:
            self.status.configure(text="Échec : %s. Réessaie plus tard, ou télécharge la version "
                                       "depuis la page GitHub." % msg, foreground="#c42b1c")

    def on_ready(self, path):
        self.status.configure(text="Vérifié ✔ Installation : HA Taskbar va redémarrer…")
        self.win.update()
        try:
            # /SILENT : fenetre de progression sans question ; l'installateur ferme puis relance HA Taskbar
            subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], close_fds=True,
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0x8))
        except OSError as e:
            self.on_failed("impossible de lancer l'installation (%s)" % e)
            return
        self.app.root.after(300, self.app.root.destroy)
