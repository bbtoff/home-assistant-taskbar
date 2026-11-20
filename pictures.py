"""
Images des entites (photo d'une personne, pochette du titre en cours, logo d'une mise a jour...) :
telechargees une fois en arriere-plan, reduites et decoupees (disque ou coins arrondis), puis gardees en
memoire pour la carte, le panneau et la barre.
"""
import queue
import threading
from collections import OrderedDict

CACHE_MAX = 80


class Pictures:
    def __init__(self, app):
        self.app = app
        self.cache = OrderedDict()        # (url, w, h, shape) -> PNG base64, ou None si illisible
        self.waiting = {}                 # meme cle -> fonctions a rappeler
        self.done = queue.Queue()
        self._pumping = False

    def get(self, url, w, h, shape, callback):
        """PNG base64 deja pret, sinon None ; callback(png ou None) sera appele plus tard (fil principal)."""
        if not url:
            return None
        key = (url, w, h, shape)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        if key in self.waiting:
            self.waiting[key].append(callback)
            return None
        self.waiting[key] = [callback]
        threading.Thread(target=self._fetch, args=(self.app.ha, key), daemon=True).start()
        if not self._pumping:
            self._pumping = True
            self.app.root.after(80, self._pump)
        return None

    def _fetch(self, ha, key):
        import imaging
        url, w, h, shape = key
        try:
            png, _w, _h = imaging.to_png(ha.picture(url), w, h, shape, radius=max(4, w // 10))
        except Exception:
            png = None
        self.done.put((key, png))

    def _pump(self):
        try:
            while True:
                key, png = self.done.get_nowait()
                self.cache[key] = png
                while len(self.cache) > CACHE_MAX:
                    self.cache.popitem(last=False)
                for cb in self.waiting.pop(key, []):
                    try:
                        cb(png)
                    except Exception:
                        pass
        except queue.Empty:
            pass
        if self.waiting:
            self.app.root.after(80, self._pump)
        else:
            self._pumping = False
