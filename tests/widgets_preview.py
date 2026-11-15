"""Apercu des widgets de bureau Windows avec des donnees fictives, et capture d'ecran.
Lancement (Windows) : python tests/widgets_preview.py [dossier de sortie]
Sert au test automatique (GitHub Actions) : verifie que les widgets s'ouvrent et se dessinent."""
import datetime
import math
import os
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ha_core  # noqa: E402
from history import HistoryCache  # noqa: E402
from widgets_ui import WidgetManager  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
NOW = datetime.datetime.now(datetime.timezone.utc)


def series(fn, hours=24, n=160):
    return [(NOW - datetime.timedelta(hours=hours * (n - i) / n), fn(i / n * hours)) for i in range(n)]


class FakeApp:
    def __init__(self, light):
        self.root = tk.Tk()
        self.root.withdraw()
        self.cfg = dict(ha_core.DEFAULT_CONFIG)
        self.cfg["theme_mode"] = "light" if light else "dark"
        self.cfg["items"] = [{"entity_id": "sensor.consommation", "label": "Consommation"}]
        self.cfg["widgets"] = [
            {"id": "w1", "entities": ["sensor.consommation"], "style": "graph", "hours": 24, "size": "medium",
             "win_x": 40, "win_y": 40},
            {"id": "w2", "title": "Températures", "entities": ["sensor.temperature_exterieure",
                                                              "sensor.temperature_chambre"],
             "style": "graph", "hours": 24, "size": "medium", "win_x": 40, "win_y": 260},
            {"id": "w3", "entities": ["sensor.humidite_salle_de_bain"], "style": "value", "size": "small",
             "win_x": 380, "win_y": 40},
        ]
        self.light = light
        self.colors = ha_core.bar_colors(self.cfg, light)
        self.offline = False
        self.settings_win = None
        self.last_error = None
        self.ha = None
        self.last_states = {
            "sensor.consommation": {"state": "1240", "attributes": {"friendly_name": "Consommation",
                                                                    "unit_of_measurement": "W"}},
            "sensor.temperature_exterieure": {"state": "8.4", "attributes": {"friendly_name": "Extérieur",
                                                                             "unit_of_measurement": "°C"}},
            "sensor.temperature_chambre": {"state": "19.2", "attributes": {"friendly_name": "Chambre",
                                                                           "unit_of_measurement": "°C"}},
            "sensor.humidite_salle_de_bain": {"state": "62", "attributes": {"friendly_name": "Humidité salle de bain",
                                                                            "unit_of_measurement": "%"}},
        }
        self.history = HistoryCache(self)
        h = self.history
        h.series[("sensor.consommation", 24)] = series(
            lambda t: 380 + 1300 * (math.exp(-(t - 12.5) ** 2 / 2) + 1.4 * math.exp(-(t - 19.5) ** 2 / 3)))
        h.series[("sensor.temperature_exterieure", 24)] = series(lambda t: 7 + 4 * math.sin(t / 24 * 6.28 - 2.2))
        h.series[("sensor.temperature_chambre", 24)] = series(lambda t: 19 + 1.2 * math.sin(t / 24 * 6.28 - 2.8))
        h.series[("sensor.humidite_salle_de_bain", 24)] = series(lambda t: 55 + 8 * math.sin(t / 24 * 6.28))
        for k in list(h.series):
            h.fetched[k] = time.monotonic()

    def open_settings(self):
        pass


def main():
    ok = True
    for light in (False, True):
        app = FakeApp(light)
        ha_core.save_config = lambda cfg: None          # rien n'est ecrit
        import widgets_ui
        widgets_ui.save_config = lambda cfg: None
        mgr = WidgetManager(app)
        mgr.sync()
        app.root.update()
        time.sleep(1.5)
        app.root.update()
        n = len(mgr.widgets)
        drawn = all(len(dw.canvas.find_all()) > 5 for dw in mgr.widgets.values())
        print("%s : %d widgets, dessines : %s" % ("clair" if light else "sombre", n, drawn))
        ok = ok and n == 3 and drawn
        try:
            from PIL import ImageGrab
            ImageGrab.grab(bbox=(0, 0, 900, 560)).save(os.path.join(OUT, "widgets-windows-%s.png"
                                                                    % ("clair" if light else "sombre")))
        except Exception as e:
            print("capture impossible :", e)
        app.root.destroy()
    print("OK" if ok else "ECHEC")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
