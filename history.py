"""Historique des capteurs pour les mini-graphiques de la barre et les widgets de bureau.

Chaque serie (entite + periode) est lue dans un thread, gardee en memoire et relue toutes les
5 minutes tant qu'elle sert. La valeur actuelle est ajoutee en direct a la fin de la courbe."""
import datetime
import queue
import threading
import time

REFRESH_S = 300          # relecture d'une serie utilisee
FORGET_S = 900           # une serie qui ne sert plus n'est plus relue
MAX_POINTS = 240


def downsample(pts, max_points=MAX_POINTS):
    """[(datetime, valeur)] -> au plus max_points points (moyenne par tranche de temps)."""
    if len(pts) <= max_points:
        return pts
    t0, t1 = pts[0][0].timestamp(), pts[-1][0].timestamp()
    span = (t1 - t0) or 1.0
    buckets = [[0.0, 0, 0.0] for _ in range(max_points)]
    for d, v in pts:
        t = d.timestamp()
        b = buckets[min(max_points - 1, int((t - t0) / span * max_points))]
        b[0] += v
        b[1] += 1
        b[2] += t
    tz = pts[0][0].tzinfo
    return [(datetime.datetime.fromtimestamp(b[2] / b[1], tz), b[0] / b[1]) for b in buckets if b[1]]


def as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class HistoryCache:
    def __init__(self, app):
        self.app = app
        self.series = {}         # (entite, heures) -> [(datetime, valeur)]
        self.fetched = {}        # (entite, heures) -> time.monotonic()
        self.used = {}
        self.busy = set()
        self.q = queue.Queue()
        self.listeners = []      # fonctions appelees quand une serie arrive
        self._poll()

    def points(self, eid, hours):
        """Serie numerique, avec la valeur actuelle a la fin."""
        key = (eid, int(hours))
        self.used[key] = time.monotonic()
        pts = list(self.series.get(key, []))
        st = self.app.last_states.get(eid)
        v = as_float(st.get("state")) if st else None
        if v is not None:
            now = datetime.datetime.now(datetime.timezone.utc)
            if pts and (now - pts[-1][0]).total_seconds() < 30:
                pts[-1] = (now, v)
            else:
                pts.append((now, v))
        return pts

    def values(self, eid, hours):
        return [v for _d, v in self.points(eid, hours)]

    def request(self, eid, hours):
        """Lit la serie si elle manque ou date de plus de 5 minutes."""
        key = (eid, int(hours))
        self.used[key] = time.monotonic()
        if key in self.busy:
            return
        t = self.fetched.get(key)
        if t is not None and time.monotonic() - t < REFRESH_S:
            return
        ha = getattr(self.app, "ha", None)
        if ha is None or not getattr(ha, "token", ""):
            return
        self.busy.add(key)

        def run():
            try:
                raw = ha.history(eid, hours)
                pts = [(d, as_float(s)) for d, s, _a in raw]
                pts = downsample([(d, v) for d, v in pts if v is not None])
            except Exception:
                pts = None
            self.q.put((key, pts))
        threading.Thread(target=run, daemon=True).start()

    def reset(self):
        self.series.clear()
        self.fetched.clear()

    def _poll(self):
        changed = False
        try:
            while True:
                key, pts = self.q.get_nowait()
                self.busy.discard(key)
                self.fetched[key] = time.monotonic()
                if pts is not None:
                    self.series[key] = pts
                    changed = True
        except queue.Empty:
            pass
        if changed:
            for fn in list(self.listeners):
                try:
                    fn()
                except Exception:
                    pass
        # Relecture des series encore utilisees
        now = time.monotonic()
        for key, used in list(self.used.items()):
            if now - used < FORGET_S:
                t = self.fetched.get(key)
                if t is None or now - t >= REFRESH_S:
                    self.request(*key)
        try:
            self.app.root.after(500, self._poll)
        except Exception:
            pass
