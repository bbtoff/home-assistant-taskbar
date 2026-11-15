"""Test de fumee de la version Windows : lance le vrai programme (ha_taskbar.App) avec une configuration
de test et des etats fictifs, verifie la barre, le mini-graphique et les widgets, sans erreur Tk.
A lancer seulement sur une machine de test : ecrit config.json a cote du script.
Lancement (Windows) : python tests/app_smoke.py [dossier de sortie]"""
import datetime
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
OUT = sys.argv[1] if len(sys.argv) > 1 else "."

import ha_core  # noqa: E402

cfg = ha_core.copy.deepcopy(ha_core.DEFAULT_CONFIG)
cfg.update(ha_url="http://127.0.0.1:9", token="jeton-de-test", realtime=False, check_updates=False,
           notify_offline=False, ha_notifications=False, palette_hotkey="")
cfg["items"] = [{"entity_id": "light.salon", "label": "Salon"},
                {"entity_id": "sensor.consommation", "label": "Conso", "sparkline": True}]
cfg["widgets"] = [{"id": "w1", "entities": ["sensor.consommation"], "win_x": 200, "win_y": 200},
                  {"id": "w2", "entities": ["sensor.consommation"], "style": "value", "size": "small",
                   "win_x": 560, "win_y": 200}]
ha_core.save_config(cfg)

import ha_taskbar  # noqa: E402

errors = []
NOW = datetime.datetime.now(datetime.timezone.utc)
STATES = {
    "light.salon": {"entity_id": "light.salon", "state": "on",
                    "attributes": {"friendly_name": "Salon", "brightness": 178}},
    "sensor.consommation": {"entity_id": "sensor.consommation", "state": "1240",
                            "attributes": {"friendly_name": "Consommation", "unit_of_measurement": "W"}},
}


def main():
    app = ha_taskbar.App()
    app.root.report_callback_exception = lambda *a: errors.append(a)
    # historique fictif (pas de Home Assistant sur la machine de test)
    for h in (6, 24):
        n = 120
        app.history.series[("sensor.consommation", h)] = [
            (NOW - datetime.timedelta(hours=h * (n - i) / n), 600 + 500 * math.sin(i / 12)) for i in range(n)]
        app.history.fetched[("sensor.consommation", h)] = time.monotonic()

    def feed():
        app.q.put(("states", dict(STATES)))

    def check():
        ok = True
        spark = [it for it in app.items if it.entity_id == "sensor.consommation"]
        if not spark or spark[0].spark is None or not spark[0].spark.find_all():
            print("ECHEC mini-graphique absent")
            ok = False
        else:
            print("OK    mini-graphique dessine")
        n = len(app.widget_mgr.widgets) if app.widget_mgr else 0
        if n != 2:
            print("ECHEC widgets : %d au lieu de 2 (%s)" % (n, app.last_error))
            ok = False
        else:
            print("OK    2 widgets affiches")
        if errors:
            for e in errors:
                print("ECHEC erreur Tk :", e[0].__name__, e[1])
            ok = False
        else:
            print("OK    aucune erreur Tk")
        try:
            from PIL import ImageGrab
            ImageGrab.grab().save(os.path.join(OUT, "app-windows.png"))
        except Exception as ex:
            print("capture impossible :", ex)
        print("OK" if ok else "ECHEC")
        app.quit()
        os._exit(0 if ok else 1)
    app.root.after(1500, feed)
    app.root.after(3000, lambda: app.widget_mgr and app.widget_mgr.redraw_all())
    app.root.after(8000, check)
    app.root.mainloop()


if __name__ == "__main__":
    main()
