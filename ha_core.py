"""Partie commune : configuration, client Home Assistant, demarrage auto."""
import copy
import datetime
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

from anim_icons import ANIM_ICONS

__version__ = "1.3.0"

HERE = os.path.dirname(os.path.abspath(__file__))
# Version installee (exe PyInstaller) : la config va dans %APPDATA%\HATaskbar,
# le dossier du programme n'etant pas fait pour etre modifie.
# Depuis les sources : config.json a cote du script, comme avant.
FROZEN = getattr(sys, "frozen", False)
RESOURCE_DIR = getattr(sys, "_MEIPASS", HERE)
if FROZEN:
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "HATaskbar")
else:
    CONFIG_DIR = HERE
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
ICON_PATH = os.path.join(RESOURCE_DIR, "assets", "ha_taskbar.ico")
PLACEHOLDER_TOKEN = "COLLE_ICI_TON_JETON_LONGUE_DUREE"

DARK_COLORS = {"bg": "#202020", "fg": "#ffffff", "dim": "#9a9a9a", "on": "#ffc83d",
               "hover": "#2f2f2f", "error": "#ff6b6b"}
LIGHT_COLORS = {"bg": "#eeeeee", "fg": "#000000", "dim": "#5f5f5f", "on": "#b86e00",
                "hover": "#dcdcdc", "error": "#c42b1c"}

DEFAULT_CONFIG = {
    "ha_url": "http://homeassistant.local:8123",
    "token": "",
    "verify_ssl": True,
    "poll_interval": 5,
    "offset": 60,                    # zone gauche : decalage depuis le bord gauche (pixels)
    "offset_right": 300,             # zone droite : decalage depuis le bord droit (avant les icones)
    "layout": "stacked",
    "font": "Segoe UI",
    "font_size": 9,
    "opacity": 1.0,
    "transparent_bg": True,
    "hide_on_fullscreen": True,
    "show_icons": True,
    "anim_icons": True,              # icones animees (flamme, ventilateur...) quand l'element est actif
    "check_updates": True,           # cherche une nouvelle version sur GitHub (au demarrage puis 1 fois/jour)
    "skip_version": "",              # version que l'utilisateur a choisi d'ignorer
    "theme_mode": "system",          # barre : "system" (suit Windows), "dark" ou "light"
    "colors": dict(DARK_COLORS),     # couleurs de la barre en mode sombre
    "colors_light": dict(LIGHT_COLORS),   # ... et en mode clair
    "card_theme": "barre",           # theme de la carte d'appui long (cle de card_themes())
    "card_mode": "bar",              # carte : "bar" (comme la barre), "dark" ou "light"
    "items": [],
}


def load_config():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        cfg.update(data)
        cfg["colors"] = dict(DARK_COLORS, **data.get("colors", {}))
        cfg["colors_light"] = dict(LIGHT_COLORS, **data.get("colors_light", {}))
        migrate_zones(cfg, data)
    return cfg


def migrate_zones(cfg, data):
    """Anciennes configs (une seule zone, "anchor" gauche/droite) -> zones gauche et droite."""
    anchor = cfg.pop("anchor", "left")
    if "offset_right" in data or anchor != "right":
        return
    cfg["offset_right"] = data.get("offset", DEFAULT_CONFIG["offset_right"])
    cfg["offset"] = DEFAULT_CONFIG["offset"]
    for it in cfg.get("items", []):
        it.setdefault("zone", "right")


def item_zone(it):
    return "right" if it.get("zone") == "right" else "left"


# --------------------------------------------------------------------------- themes clair / sombre
def system_light():
    """True si Windows est en mode clair (barre des taches / menus)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "SystemUsesLightTheme")[0])
    except OSError:
        return False


def bar_light(cfg):
    mode = cfg.get("theme_mode", "system")
    return system_light() if mode == "system" else mode == "light"


def bar_colors(cfg, light=None):
    if light is None:
        light = bar_light(cfg)
    return dict(cfg["colors_light"] if light else cfg["colors"])


def card_light(cfg, bar_is_light):
    mode = cfg.get("card_mode", "bar")
    return bar_is_light if mode == "bar" else mode == "light"


def windows_accent(light):
    """Couleur d'accentuation de Windows (variante adaptee au mode clair / sombre)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent") as k:
            pal = winreg.QueryValueEx(k, "AccentPalette")[0]
        i = 4 if light else 1          # 1 = "Light 2" (sur fond sombre), 4 = "Dark 1" (sur fond clair)
        return "#%02x%02x%02x" % (pal[i * 4], pal[i * 4 + 1], pal[i * 4 + 2])
    except (OSError, IndexError, TypeError):
        return "#0078d4"


# --------------------------------------------------------------------------- themes de la carte
# Chaque theme a une variante "dark" et "light". "accent" peut valoir "bar" (couleur « actif » de la
# barre) ou "system" (couleur d'accentuation de Windows). "radius" = arrondi des boutons (px a 96 dpi).
# Des themes perso peuvent etre ajoutes dans card_themes.json (meme dossier que config.json).
_NEUTRAL_DARK = {"bg": "#2b2b2b", "surface": "#383838", "surface_h": "#444444", "border": "#4a4a4a",
                 "fg": "#ffffff", "dim": "#a8a8a8", "knob": "#454545", "accent": "bar"}
_NEUTRAL_LIGHT = {"bg": "#fbfbfb", "surface": "#ececec", "surface_h": "#e0e0e0", "border": "#d4d4d4",
                  "fg": "#1b1b1b", "dim": "#616161", "knob": "#ffffff", "accent": "bar"}
CARD_THEMES = {
    "barre": {"name": "Comme la barre (défaut)", "radius": 6,
              "dark": dict(_NEUTRAL_DARK), "light": dict(_NEUTRAL_LIGHT)},
    "windows": {"name": "Windows 11 (couleur d'accentuation)", "radius": 6,
                "dark": dict(_NEUTRAL_DARK, accent="system"), "light": dict(_NEUTRAL_LIGHT, accent="system")},
    "ha": {"name": "Home Assistant", "radius": 14,
           "dark": {"bg": "#1c1c1c", "surface": "#2b2b2b", "surface_h": "#363636", "border": "#3a3a3a",
                    "fg": "#e1e1e1", "dim": "#9b9b9b", "knob": "#2b2b2b", "accent": "#03a9f4"},
           "light": {"bg": "#ffffff", "surface": "#f0f0f0", "surface_h": "#e4e4e4", "border": "#e0e0e0",
                     "fg": "#212121", "dim": "#727272", "knob": "#ffffff", "accent": "#039be5"}},
    "ocean": {"name": "Océan", "radius": 8,
              "dark": {"bg": "#0f1e2b", "surface": "#17304a", "surface_h": "#1f3d5c", "border": "#24486b",
                       "fg": "#e6f1ff", "dim": "#8aa4bf", "knob": "#17304a", "accent": "#2ec4b6"},
              "light": {"bg": "#f2f8fc", "surface": "#dcebf5", "surface_h": "#cde1ef", "border": "#c2d8e8",
                        "fg": "#0f2a3f", "dim": "#4f6b82", "knob": "#ffffff", "accent": "#0f8b8d"}},
    "foret": {"name": "Forêt", "radius": 8,
              "dark": {"bg": "#17201a", "surface": "#223026", "surface_h": "#2b3d30", "border": "#33473a",
                       "fg": "#eef5ee", "dim": "#93a896", "knob": "#223026", "accent": "#8bc34a"},
              "light": {"bg": "#f5f8f1", "surface": "#e3ecda", "surface_h": "#d6e3ca", "border": "#cddbbf",
                        "fg": "#1f2d1f", "dim": "#5b6e58", "knob": "#ffffff", "accent": "#4c8c2b"}},
    "crepuscule": {"name": "Crépuscule", "radius": 10,
                   "dark": {"bg": "#1e1729", "surface": "#2c2140", "surface_h": "#382a52", "border": "#3f305c",
                            "fg": "#f3eefe", "dim": "#a99cc2", "knob": "#2c2140", "accent": "#ff8a5c"},
                   "light": {"bg": "#fbf6ff", "surface": "#efe4fa", "surface_h": "#e4d4f5", "border": "#dccbf0",
                             "fg": "#2a1d3d", "dim": "#6d5a85", "knob": "#ffffff", "accent": "#c2185b"}},
    "contraste": {"name": "Contraste élevé", "radius": 2,
                  "dark": {"bg": "#000000", "surface": "#1a1a1a", "surface_h": "#333333", "border": "#ffffff",
                           "fg": "#ffffff", "dim": "#d0d0d0", "knob": "#000000", "accent": "#ffff00"},
                  "light": {"bg": "#ffffff", "surface": "#f0f0f0", "surface_h": "#dddddd", "border": "#000000",
                            "fg": "#000000", "dim": "#333333", "knob": "#ffffff", "accent": "#0000cc"}},
}
CARD_THEMES_PATH = os.path.join(CONFIG_DIR, "card_themes.json")
CARD_KEYS = ("bg", "surface", "surface_h", "border", "fg", "dim", "knob", "accent")


def card_themes():
    """Themes integres + themes perso de card_themes.json (les erreurs du fichier sont ignorees)."""
    themes = copy.deepcopy(CARD_THEMES)
    try:
        with open(CARD_THEMES_PATH, encoding="utf-8") as f:
            user = json.load(f)
        for key, t in user.items():
            if isinstance(t, dict) and isinstance(t.get("dark"), dict) and isinstance(t.get("light"), dict):
                themes[key] = {"name": t.get("name") or key, "radius": t.get("radius", 6),
                               "dark": dict(_NEUTRAL_DARK, **t["dark"]),
                               "light": dict(_NEUTRAL_LIGHT, **t["light"])}
    except (OSError, ValueError, AttributeError):
        pass
    return themes


def card_palette(cfg, bar_cols, light, themes=None):
    """Couleurs de base de la carte + arrondi, d'apres le theme et le mode choisis."""
    themes = themes or card_themes()
    t = themes.get(cfg.get("card_theme", "barre")) or themes["barre"]
    p = dict(t["light" if light else "dark"])
    if p.get("accent") == "bar":
        p["accent"] = bar_cols.get("on", "#ffc83d")
    elif p.get("accent") == "system":
        p["accent"] = windows_accent(light)
    try:
        radius = max(0, int(t.get("radius", 6)))
    except (TypeError, ValueError):
        radius = 6
    return p, radius


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_PATH)


def needs_setup(cfg):
    return not cfg.get("token") or cfg.get("token") == PLACEHOLDER_TOKEN


# --------------------------------------------------------------------------- etats
ACTIVE_STATES = {"on", "open", "opening", "playing", "home", "unlocked", "heat", "cool", "heat_cool", "auto"}
STATE_TEXT = {"on": "ON", "off": "OFF", "unavailable": "indispo", "unknown": "?",
              "open": "ouvert", "closed": "fermé", "playing": "lecture", "paused": "pause",
              "idle": "inactif", "home": "présent", "not_home": "absent",
              "locked": "fermé", "unlocked": "ouvert"}


# --------------------------------------------------------------------------- actions
# Action par defaut au clic selon le domaine de l'entite
DEFAULT_ACTIONS = {
    "light": "toggle", "switch": "toggle", "input_boolean": "toggle", "fan": "toggle",
    "cover": "toggle", "automation": "toggle", "media_player": "media_play_pause",
    "script": "turn_on", "scene": "turn_on",
    "button": "press", "input_button": "press",
}


def default_service(entity_id):
    domain = entity_id.split(".", 1)[0]
    if domain in DEFAULT_ACTIONS:
        return "%s.%s" % (domain, DEFAULT_ACTIONS[domain])
    return None


def resolve_service(item):
    """Service appele au clic, ou None si l'element n'est pas cliquable."""
    svc = item.get("service")
    if svc == "none":
        return None
    return svc or default_service(item.get("entity_id", ""))


# --------------------------------------------------------------------------- icones
# Glyphes de la police Windows 11 "Segoe Fluent Icons" (repli : "Segoe MDL2 Assets")
ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
ICONS = {
    "lightbulb": ("", "Ampoule"),
    "lightbulb2": ("", "Ampoule (contour)"),
    "toggle": ("", "Interrupteur (suit l'état)"),
    "power": ("", "Marche / arrêt"),
    "tap": ("", "Bouton / appui"),
    "thermometer": ("", "Thermomètre"),
    "flame": ("", "Flamme / chauffage"),
    "drop": ("", "Goutte / humidité"),
    "bolt": ("", "Éclair / énergie"),
    "battery": ("", "Batterie"),
    "sun": ("", "Soleil / luminosité"),
    "moon": ("", "Lune / nuit"),
    "cloud": ("", "Nuage / météo"),
    "wind": ("", "Vent / ventilateur"),
    "home": ("", "Maison"),
    "home_filled": ("", "Maison (plein)"),
    "window": ("", "Fenêtre / volet"),
    "lock": ("", "Cadenas (suit l'état)"),
    "shield": ("", "Bouclier / alarme"),
    "bell": ("", "Cloche"),
    "warning": ("", "Alerte"),
    "speaker": ("", "Haut-parleur"),
    "music": ("", "Musique"),
    "play": ("", "Lecture"),
    "pause": ("", "Pause"),
    "tv": ("", "Écran / TV"),
    "video": ("", "Caméra"),
    "camera": ("", "Appareil photo"),
    "person": ("", "Personne"),
    "people": ("", "Personnes"),
    "car": ("", "Voiture"),
    "wifi": ("", "Wi-Fi"),
    "gear": ("", "Engrenage"),
    "gears": ("", "Automatisation"),
    "code": ("", "Script"),
    "palette": ("", "Scène"),
    "clock": ("", "Horloge"),
    "timer": ("", "Minuteur"),
    "pulse": ("", "Capteur / activité"),
    "heart": ("", "Cœur"),
    "star": ("", "Étoile"),
    "flag": ("", "Drapeau"),
    "location": ("", "Position"),
    "refresh": ("", "Actualiser"),
    "game": ("", "Console / jeux"),
    "laptop": ("", "Ordinateur portable"),
    "desktop": ("", "Ordinateur"),
    "phone": ("", "Téléphone"),
    "headphones": ("", "Casque audio"),
    "mic": ("", "Micro"),
    "mute": ("", "Son coupé"),
    "stop": ("", "Stop"),
    "prev": ("", "Précédent"),
    "next": ("", "Suivant"),
    "photo": ("", "Photo / cadre"),
    "eye": ("", "Œil / surveillance"),
    "fingerprint": ("", "Empreinte"),
    "key": ("", "Clé"),
    "bell_off": ("", "Sonnerie coupée"),
    "check": ("", "Validé"),
    "person_filled": ("", "Personne (plein)"),
    "sunrise": ("", "Lever du soleil"),
    "sunset": ("", "Coucher du soleil"),
    "snow": ("", "Flocon / froid"),
    "health": ("", "Santé"),
    "smile": ("", "Humeur"),
    "like": ("", "J'aime"),
    "mail": ("", "Courrier"),
    "message": ("", "Message"),
    "calendar": ("", "Calendrier"),
    "history": ("", "Historique"),
    "cart": ("", "Courses"),
    "bag": ("", "Achats"),
    "trash": ("", "Poubelle"),
    "work": ("", "Travail"),
    "school": ("", "École"),
    "building": ("", "Bâtiment"),
    "globe": ("", "Internet / monde"),
    "map": ("", "Carte"),
    "plane": ("", "Avion / voyage"),
    "bus": ("", "Bus"),
    "train": ("", "Train"),
    "bluetooth": ("", "Bluetooth"),
    "antenna": ("", "Antenne / signal"),
    "chip": ("", "Processeur"),
    "chart": ("", "Tendance"),
    "pie": ("", "Statistiques"),
    "wrench": ("", "Outils / entretien"),
    "puzzle": ("", "Extension"),
}
# Variantes selon l'etat
TOGGLE_OFF = ""
UNLOCKED = ""


def auto_icon(entity_id, st):
    """Icone par defaut selon le domaine / device_class / unite de l'entite."""
    d = entity_id.split(".", 1)[0]
    attrs = (st or {}).get("attributes", {})
    dc = attrs.get("device_class", "") or ""
    unit = attrs.get("unit_of_measurement", "") or ""
    by_domain = {
        "light": "lightbulb", "switch": "toggle", "input_boolean": "toggle", "fan": "wind",
        "climate": "flame", "water_heater": "flame", "cover": "window", "lock": "lock",
        "media_player": "music", "scene": "palette", "script": "code", "automation": "gears",
        "button": "tap", "input_button": "tap", "person": "person", "device_tracker": "person",
        "weather": "cloud", "camera": "video", "sun": "sun", "alarm_control_panel": "shield",
        "vacuum": "home", "update": "refresh", "timer": "timer", "siren": "bell",
    }
    if d in by_domain:
        return by_domain[d]
    if d == "binary_sensor":
        if dc in ("door", "window", "garage_door", "opening"):
            return "window"
        if dc in ("motion", "occupancy", "presence"):
            return "person"
        if dc in ("smoke", "gas", "safety", "problem", "carbon_monoxide", "tamper"):
            return "warning"
        if dc == "moisture":
            return "drop"
        if dc == "battery":
            return "battery"
        if dc in ("power", "plug"):
            return "bolt"
        return "pulse"
    if dc == "temperature" or unit in ("°C", "°F"):
        return "thermometer"
    if dc in ("humidity", "moisture", "precipitation", "water"):
        return "drop"
    if dc in ("power", "energy", "current", "voltage", "power_factor") or unit in ("W", "kW", "kWh", "Wh", "A", "V"):
        return "bolt"
    if dc == "battery":
        return "battery"
    if dc == "illuminance" or unit == "lx":
        return "sun"
    if dc == "wind_speed":
        return "wind"
    return "pulse"


def icon_key(item, st):
    """Cle de l'icone d'un element ("auto" resolu), ou None si pas d'icone."""
    key = item.get("icon") or "auto"
    if key == "none":
        return None
    if key == "auto":
        key = auto_icon(item.get("entity_id", ""), st)
    return key


def anim_active(item, st):
    """Une icone animee bouge-t-elle ? Allume / en marche ; un thermostat seulement quand il chauffe
    (ou refroidit) ; un capteur quand sa valeur est au-dessus de 0."""
    if not st:
        return False
    state = st.get("state")
    if state in ("unavailable", "unknown", None):
        return False
    domain = item.get("entity_id", "").split(".", 1)[0]
    attrs = st.get("attributes", {})
    if domain in ("climate", "water_heater") and attrs.get("hvac_action") is not None:
        return attrs["hvac_action"] not in ("idle", "off")
    if domain == "sensor":
        try:
            return float(state) > 0
        except ValueError:
            return False
    if domain == "media_player":
        return state == "playing"
    return state in ACTIVE_STATES


def resolve_icon(item, st):
    """Glyphe a afficher pour un element (ou None si pas d'icone). Une icone animee renvoie
    l'icone de police equivalente (carte de controle, reglages)."""
    key = icon_key(item, st)
    if key is None:
        return None
    if key in ANIM_ICONS:
        key = ANIM_ICONS[key][0]
    state = (st or {}).get("state")
    if key == "toggle" and state != "on":
        return TOGGLE_OFF
    if key == "lock" and state in ("unlocked", "open", "opening", "unlocking"):
        return UNLOCKED
    return ICONS.get(key, (None,))[0]


# --------------------------------------------------------------------------- client HA
class HomeAssistant:
    def __init__(self, url, token, verify_ssl=True):
        self.url = (url or "").rstrip("/")
        self.token = token or ""
        self.ctx = None if verify_ssl else ssl._create_unverified_context()

    def _request(self, method, path, body=None, timeout=10):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.url + path, data=data, method=method,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None

    def config(self):
        return self._request("GET", "/api/config")

    def states(self):
        return {s["entity_id"]: s for s in self._request("GET", "/api/states")}

    def services(self):
        """{domaine: [noms de services]}"""
        return {d["domain"]: sorted(d.get("services", {})) for d in self._request("GET", "/api/services")}

    def call_service(self, service, data):
        domain, name = service.split(".", 1)
        return self._request("POST", "/api/services/%s/%s" % (domain, name), data)

    def history(self, entity_id, hours=24, attributes=False):
        """Historique [(datetime UTC, etat, attributs)] sur les `hours` dernieres heures."""
        start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        q = "filter_entity_id=" + urllib.parse.quote(entity_id)
        if not attributes:
            q += "&minimal_response&no_attributes"
        data = self._request("GET", "/api/history/period/%s?%s" % (urllib.parse.quote(start.isoformat()), q),
                             timeout=20)
        out = []
        for e in (data[0] if data else []):
            t = parse_time(e.get("last_changed") or e.get("last_updated"))
            if t is not None:
                out.append((t, e.get("state"), e.get("attributes") or {}))
        return out


def parse_time(iso):
    try:
        t = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


# --------------------------------------------------------------------------- mises a jour (GitHub)
GITHUB_REPO = "bbtoff/home-assistant-taskbar"
RELEASES_URL = "https://github.com/%s/releases" % GITHUB_REPO
_ASSET_PREFIX = "https://github.com/%s/releases/download/" % GITHUB_REPO


def parse_version(v):
    """"v1.2.0" -> (1, 2, 0). Les morceaux non numeriques comptent pour 0."""
    out = []
    for part in str(v).strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


def latest_release(timeout=10):
    """Derniere version publiee sur GitHub (API publique, sans jeton).
    Renvoie {version, notes, page, asset_url, asset_name, size, sha256} ; asset_url vaut None
    si la version n'a pas de programme d'installation."""
    req = urllib.request.Request("https://api.github.com/repos/%s/releases/latest" % GITHUB_REPO,
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "HATaskbar/%s" % __version__})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rel = json.loads(r.read().decode("utf-8"))
    info = {"version": str(rel.get("tag_name", "")).lstrip("vV"), "notes": rel.get("body") or "",
            "page": rel.get("html_url") or RELEASES_URL, "asset_url": None, "asset_name": None,
            "size": None, "sha256": None}
    for a in rel.get("assets", []):
        url = a.get("browser_download_url") or ""
        name = a.get("name") or ""
        # Uniquement le programme d'installation, et uniquement depuis les versions de ce depot
        if name.lower().endswith(".exe") and "setup" in name.lower() and url.startswith(_ASSET_PREFIX):
            digest = a.get("digest") or ""
            info.update(asset_url=url, asset_name=os.path.basename(name), size=a.get("size"),
                        sha256=digest[7:].lower() if digest.startswith("sha256:") else None)
            break
    return info


def update_available(info):
    return bool(info and info.get("version")) and parse_version(info["version"]) > parse_version(__version__)


def download_update(info, dest_dir, progress=None, cancelled=lambda: False):
    """Telecharge le programme d'installation, verifie taille et empreinte SHA-256. Renvoie son chemin."""
    import hashlib
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, info["asset_name"])
    tmp = path + ".part"
    req = urllib.request.Request(info["asset_url"], headers={"User-Agent": "HATaskbar/%s" % __version__})
    h = hashlib.sha256()
    done = 0
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
            total = info.get("size") or int(r.headers.get("Content-Length") or 0)
            while True:
                if cancelled():
                    raise RuntimeError("téléchargement annulé")
                chunk = r.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if info.get("size") and done != info["size"]:
            raise RuntimeError("fichier incomplet (%d octets sur %d)" % (done, info["size"]))
        if info.get("sha256") and h.hexdigest() != info["sha256"]:
            raise RuntimeError("empreinte SHA-256 incorrecte : fichier abîmé ou modifié")
        if os.path.exists(path):
            os.remove(path)
        os.replace(tmp, path)
        return path
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# --------------------------------------------------------------------------- demarrage Windows
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "HATaskbar"


def startup_command():
    if FROZEN:
        return '"%s"' % sys.executable
    pyw =os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    return '"%s" "%s"' % (pyw, os.path.join(HERE, "ha_taskbar.py"))


def get_startup():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except OSError:
        return False


def set_startup(enabled):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except OSError:
                pass
