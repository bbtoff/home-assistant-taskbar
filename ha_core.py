"""Partie commune : configuration, client Home Assistant, demarrage auto."""
import base64
import copy
import datetime
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request

from anim_icons import ANIM_ICONS

__version__ = "1.8.1"

HERE = os.path.dirname(os.path.abspath(__file__))
# Version installee (exe PyInstaller) : la config va dans %APPDATA%\HATaskbar,
# le dossier du programme n'etant pas fait pour etre modifie.
# Version portable (fichier "portable.txt" a cote de l'exe) : la config reste dans le dossier
# du programme, rien n'est ecrit ailleurs.
# Depuis les sources : config.json a cote du script, comme avant.
FROZEN = getattr(sys, "frozen", False)
RESOURCE_DIR = getattr(sys, "_MEIPASS", HERE)
APP_DIR = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else HERE
PORTABLE = FROZEN and os.path.exists(os.path.join(APP_DIR, "portable.txt"))
if FROZEN and not PORTABLE:
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "HATaskbar")
else:
    CONFIG_DIR = APP_DIR
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
    "monitor": "",                   # ecran des boutons (ex. "\\.\DISPLAY2") ; "" = ecran principal
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
    "notifications": [],             # regles {entity_id, to, message} -> notification Windows
    "notify_offline": True,          # prevenir quand Home Assistant ne repond plus / revient
    "ha_notifications": True,        # notifications persistantes de HA + evenement ha_taskbar_notify
    "quiet_from": "",                # plage sans notification (HH:MM), peut passer minuit
    "quiet_to": "",
    "realtime": True,                # connexion permanente (WebSocket) : mises a jour instantanees
    "palette_hotkey": "Ctrl+Alt+Space",   # palette de commandes ("" = desactivee)
    "compact": False,                # barre compacte : icones seules, valeur au survol
    "tooltips": True,                # infobulle au survol (etat, mini-courbe)
    "flash_changes": True,           # une valeur qui change brille un instant
    "battery_low": 20,               # seuil des piles faibles (%) pour l'element "@batteries"
    "items": [],
}


def load_config():
    global TOKEN_UNREADABLE
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        cfg.update(data)
        cfg["colors"] = dict(DARK_COLORS, **data.get("colors", {}))
        cfg["colors_light"] = dict(LIGHT_COLORS, **data.get("colors_light", {}))
        migrate_zones(cfg, data)
        # Jeton chiffre (DPAPI) -> en clair, en memoire seulement
        protected = cfg.pop(TOKEN_PROTECTED_KEY, None)
        TOKEN_UNREADABLE = False
        if protected:
            token = unprotect_token(protected)
            if token is None:
                TOKEN_UNREADABLE = True       # autre PC ou autre compte Windows : jeton a ressaisir
                cfg["token"] = ""
            else:
                cfg["token"] = token
        elif cfg.get("token") and cfg["token"] != PLACEHOLDER_TOKEN and token_protection_available():
            # Ancienne config avec le jeton en clair : on la reecrit tout de suite, jeton chiffre
            try:
                save_config(cfg)
            except OSError:
                pass
    return cfg


# --------------------------------------------------------------------------- jeton chiffre (DPAPI)
# Le jeton est chiffre avec la protection des donnees de Windows (CryptProtectData) : seul le meme compte
# Windows, sur le meme PC, peut le dechiffrer. config.json ne contient plus le jeton en clair.
TOKEN_PROTECTED_KEY = "token_protected"
TOKEN_UNREADABLE = False              # True si le jeton du fichier n'a pas pu etre dechiffre
_DPAPI_PREFIX = "dpapi:"
_DPAPI_ENTROPY = b"HATaskbar/token"


def token_protection_available():
    return sys.platform == "win32"


def _dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(b):
        buf = ctypes.create_string_buffer(b, len(b))
        return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    inp, _keep1 = blob(data)
    ent, _keep2 = blob(_DPAPI_ENTROPY)
    out = BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(BLOB), ctypes.c_void_p, ctypes.POINTER(BLOB), ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(BLOB)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(inp), None, ctypes.byref(ent), None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise OSError("CryptProtectData a échoué (%d)" % ctypes.GetLastError())
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def protect_token(token):
    """Jeton -> "dpapi:<base64>", ou None si le chiffrement n'est pas disponible."""
    if not token or not token_protection_available():
        return None
    try:
        return _DPAPI_PREFIX + base64.b64encode(_dpapi(token.encode("utf-8"), True)).decode("ascii")
    except (OSError, AttributeError, ValueError):
        return None


def unprotect_token(value):
    """Inverse de protect_token. None si le jeton ne peut pas etre dechiffre (autre PC / autre compte)."""
    if not isinstance(value, str) or not value.startswith(_DPAPI_PREFIX) or not token_protection_available():
        return None
    try:
        return _dpapi(base64.b64decode(value[len(_DPAPI_PREFIX):]), False).decode("utf-8")
    except (OSError, AttributeError, ValueError, UnicodeDecodeError):
        return None


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
    """Enregistre la configuration. Sous Windows, le jeton est chiffre (DPAPI) : il n'est jamais ecrit en clair."""
    data = dict(cfg)
    data.pop(TOKEN_PROTECTED_KEY, None)
    token = data.get("token") or ""
    if token and token != PLACEHOLDER_TOKEN:
        protected = protect_token(token)
        if protected:
            data["token"] = ""
            data[TOKEN_PROTECTED_KEY] = protected
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
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


def item_members(item):
    """Entites commandees par un element : la sienne + celles du groupe ("group")."""
    out = [item.get("entity_id", "")]
    for e in item.get("group") or []:
        if e and e not in out:
            out.append(e)
    return [e for e in out if e]


def group_state(item, states):
    """Etat combine d'un groupe : "on" si au moins un membre est actif. Renvoie (etat, actifs, total)."""
    members = item_members(item)
    sts = [states.get(e) for e in members]
    known = [s for s in sts if s and s.get("state") not in ("unavailable", "unknown")]
    on = sum(1 for s in known if s.get("state") in ACTIVE_STATES)
    if not known:
        return ("unavailable" if any(sts) else None), 0, len(members)
    return ("on" if on else "off"), on, len(members)


def parse_hhmm(v):
    try:
        h, m = str(v).strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return h * 60 + m
    except (ValueError, AttributeError):
        pass
    return None


def item_visible(item, now=None):
    """Plage horaire d'affichage ("show_from" / "show_to", HH:MM). Sans plage : toujours visible.
    La plage peut passer minuit (ex. 22:00 -> 07:00). Un element "masque" n'est jamais affiche."""
    if item.get("hidden"):
        return False
    return in_range(item.get("show_from"), item.get("show_to"), now, True)


def in_range(start, end, now=None, empty=False):
    """L'heure actuelle est-elle dans la plage HH:MM -> HH:MM (qui peut passer minuit) ?
    Plage vide ou invalide : `empty`."""
    a, b = parse_hhmm(start), parse_hhmm(end)
    if a is None or b is None or a == b:
        return empty
    now = now or datetime.datetime.now()
    t = now.hour * 60 + now.minute
    return a <= t < b if a < b else (t >= a or t < b)


def in_quiet_hours(cfg, now=None):
    """Plage horaire sans notification (Reglages -> Notifications)."""
    return in_range(cfg.get("quiet_from"), cfg.get("quiet_to"), now, False)


# --------------------------------------------------------------------------- couleurs selon la valeur
# "> 25 orange ; > 30 rouge ; < 15 bleu" : la regle la plus precise gagne
COLOR_WORDS = {"rouge": "#e74856", "red": "#e74856", "orange": "#f7630c", "jaune": "#e8b900",
               "yellow": "#e8b900", "vert": "#16c60c", "green": "#16c60c", "bleu": "#3a96dd",
               "blue": "#3a96dd", "violet": "#b146c2", "purple": "#b146c2", "rose": "#e3008c",
               "pink": "#e3008c", "gris": "#9a9a9a", "grey": "#9a9a9a", "gray": "#9a9a9a",
               "blanc": "#ffffff", "white": "#ffffff", "noir": "#000000", "black": "#000000"}
_THRESH_RE = re.compile(r"^\s*(<=|>=|<|>|=)\s*(-?\d+(?:[.,]\d+)?)\s*(\S+)\s*$")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def parse_thresholds(text):
    """Texte des seuils -> ([(operateur, valeur, couleur)], [morceaux incompris])."""
    rules, bad = [], []
    for part in str(text or "").split(";"):
        if not part.strip():
            continue
        m = _THRESH_RE.match(part)
        col = None
        if m:
            w = m.group(3).strip().lower()
            col = COLOR_WORDS.get(w) or (w if _HEX_RE.match(w) else None)
        if not m or not col:
            bad.append(part.strip())
            continue
        rules.append((m.group(1), float(m.group(2).replace(",", ".")), col))
    return rules, bad


def threshold_color(rules, value):
    """Couleur de la regle la plus precise satisfaite (le seuil le plus haut pour ">", le plus bas pour "<"),
    ou None."""
    if not rules:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    best = None
    for op, t, col in rules:
        if op == ">":
            ok, score = v > t, t
        elif op == ">=":
            ok, score = v >= t, t
        elif op == "<":
            ok, score = v < t, -t
        elif op == "<=":
            ok, score = v <= t, -t
        else:
            ok, score = v == t, float("inf")
        if ok and (best is None or score > best[0]):
            best = (score, col)
    return best[1] if best else None


def mix_color(a, b, t):
    """Melange de deux couleurs #rrggbb (t = 0 -> a, 1 -> b)."""
    try:
        ra = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
        rb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    except (TypeError, ValueError, IndexError):
        return b
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * t)) for x, y in zip(ra, rb))


# --------------------------------------------------------------------------- piles faibles
BATTERIES = "@batteries"        # element virtuel : resume des piles faibles


def battery_levels(states):
    """[(entity_id, nom, niveau % ou None si binaire "faible")] de toutes les piles connues."""
    out = []
    for eid, st in states.items():
        a = st.get("attributes", {})
        if a.get("device_class") != "battery":
            continue
        s = st.get("state")
        name = a.get("friendly_name") or eid
        if eid.startswith("sensor.") and a.get("unit_of_measurement") == "%":
            try:
                out.append((eid, name, float(s)))
            except (TypeError, ValueError):
                pass
        elif eid.startswith("binary_sensor.") and s in ("on", "off"):
            out.append((eid, name, 0.0 if s == "on" else None))
    return out


def low_batteries(states, threshold=20):
    """Piles sous le seuil (et capteurs binaires "pile faible"), de la plus vide a la moins vide."""
    try:
        thr = float(threshold)
    except (TypeError, ValueError):
        thr = 20.0
    low = [(e, n, v) for e, n, v in battery_levels(states) if v is not None and v < thr]
    low.sort(key=lambda x: x[2])
    return low


def battery_state(states, threshold=20):
    """Etat factice de l'element "@batteries" : nombre de piles faibles, niveau de la plus vide."""
    low = low_batteries(states, threshold)
    levels = [v for _e, _n, v in battery_levels(states) if v is not None]
    return {"entity_id": BATTERIES, "state": str(len(low)),
            "attributes": {"friendly_name": "Piles faibles", "battery_level": min(levels) if levels else None,
                           "low": low}}


# Raccourcis clavier globaux : "Ctrl+Alt+1"
HOTKEY_MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "ctl": 0x2, "shift": 0x4, "maj": 0x4, "win": 0x8}
HOTKEY_KEYS = dict({"f%d" % i: 0x6F + i for i in range(1, 25)},
                   space=0x20, espace=0x20, left=0x25, up=0x26, right=0x27, down=0x28,
                   gauche=0x25, haut=0x26, droite=0x27, bas=0x28, home=0x24, end=0x23,
                   insert=0x2D, delete=0x2E, pageup=0x21, pagedown=0x22,
                   **{"num%d" % i: 0x60 + i for i in range(10)})


def parse_hotkey(text):
    """"Ctrl+Alt+1" -> (modificateurs, code de touche), ou None si invalide.
    Il faut au moins un modificateur (sauf touches F1-F24)."""
    parts = [p.strip().lower() for p in str(text or "").replace(" ", "").split("+") if p.strip()]
    if not parts:
        return None
    mods, key = 0, None
    for p in parts[:-1]:
        if p not in HOTKEY_MODS:
            return None
        mods |= HOTKEY_MODS[p]
    k = parts[-1]
    if k in HOTKEY_KEYS:
        key = HOTKEY_KEYS[k]
    elif len(k) == 1 and (k.isalnum()):
        key = ord(k.upper())
    if key is None or (not mods and not 0x70 <= key <= 0x87):
        return None
    return mods, key


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


# Variantes selon la valeur : pile 0..100 %, Wi-Fi, barres de signal, volume
G_BATTERY = ["\ue850", "\ue851", "\ue852", "\ue853", "\ue854", "\ue855", "\ue856", "\ue857", "\ue858",
             "\ue859", "\ue83f"]
G_WIFI = ["\ue872", "\ue873", "\ue874", "\ue701"]
G_SIGNAL = ["\ue86c", "\ue86d", "\ue86e", "\ue86f", "\ue870"]
G_VOLUME = ["\ue992", "\ue993", "\ue994", "\ue995"]
G_MUTED = "\ue74f"

# Meteo : texte et icone selon la condition (entites weather.*)
WEATHER_TEXT = {"clear-night": "Nuit claire", "cloudy": "Nuageux", "exceptional": "Exceptionnel",
                "fog": "Brouillard", "hail": "Grêle", "lightning": "Orages", "lightning-rainy": "Orages et pluie",
                "partlycloudy": "Éclaircies", "pouring": "Averses", "rainy": "Pluie", "snowy": "Neige",
                "snowy-rainy": "Neige et pluie", "sunny": "Ensoleillé", "windy": "Venteux",
                "windy-variant": "Venteux et nuageux"}
WEATHER_ICON = {"clear-night": "moon", "cloudy": "cloud", "exceptional": "warning", "fog": "cloud",
                "hail": "snow", "lightning": "bolt", "lightning-rainy": "bolt", "partlycloudy": "cloud",
                "pouring": "drop", "rainy": "drop", "snowy": "snow", "snowy-rainy": "snow", "sunny": "sun",
                "windy": "wind", "windy-variant": "wind"}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def value_glyph(item, st, key):
    """Glyphe qui suit la valeur (pile, signal, volume, meteo), ou None."""
    if not st:
        return None
    a = st.get("attributes", {})
    attr = item.get("attribute")
    raw = a.get(attr) if attr else st.get("state")
    domain = item.get("entity_id", "").split(".", 1)[0]
    if key == "battery":
        v = _num(a.get("battery_level"))
        if v is None:
            v = _num(a.get("battery")) if not attr else None
        if v is None and (attr or a.get("unit_of_measurement") == "%" or a.get("device_class") == "battery"):
            v = _num(raw)
        if v is None:
            return None
        return G_BATTERY[int(round(max(0.0, min(100.0, v)) / 10.0))]
    if key in ("wifi", "antenna"):
        v = _num(raw)
        if v is None:
            return None
        unit = "" if attr else (a.get("unit_of_measurement") or "")
        if unit == "dBm" or (v < 0 and not unit):
            pct = (v + 100) * 2          # -50 dBm -> 100 %, -100 dBm -> 0 %
        elif unit == "%":
            pct = v
        elif "link" in (attr or item.get("entity_id", "")) or unit == "lqi":
            pct = v * 100 / 255.0
        else:
            return None
        pct = max(0.0, min(100.0, pct))
        levels = G_WIFI if key == "wifi" else G_SIGNAL
        return levels[min(len(levels) - 1, int(pct * len(levels) / 100.0))]
    if key == "speaker" and domain == "media_player":
        if a.get("is_volume_muted"):
            return G_MUTED
        v = _num(a.get("volume_level"))
        if v is None:
            return None
        return G_VOLUME[0] if v <= 0 else G_VOLUME[min(3, 1 + int(v * 3))]
    if domain == "weather" and not attr and (item.get("icon") or "auto") == "auto":
        k = WEATHER_ICON.get(st.get("state"))
        return ICONS[k][0] if k in ICONS else None
    return None


def auto_icon(entity_id, st):
    """Icone par defaut selon le domaine / device_class / unite de l'entite."""
    if entity_id == BATTERIES:
        return "battery"
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
    if state not in ("unavailable", "unknown"):
        g = value_glyph(item, st, key)
        if g:
            return g
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


    def template(self, tpl, timeout=10):
        """Rend un modele Jinja cote Home Assistant (texte)."""
        data = json.dumps({"template": tpl}).encode()
        req = urllib.request.Request(self.url + "/api/template", data=data, method="POST",
                                     headers={"Authorization": "Bearer " + self.token,
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as resp:
            return resp.read().decode("utf-8", "replace")

    def forecast(self, entity_id, kind="daily"):
        """Previsions meteo (service weather.get_forecasts, Home Assistant 2023.9+)."""
        r = self._request("POST", "/api/services/weather/get_forecasts?return_response",
                          {"entity_id": entity_id, "type": kind}, timeout=15)
        resp = ((r or {}).get("service_response") or {}).get(entity_id) or {}
        return resp.get("forecast") or []

    def areas(self):
        """{entity_id: nom de la piece} (entites sans piece absentes)."""
        tpl = ("{% for s in states %}{% set a = area_name(s.entity_id) %}"
               "{% if a %}{{ s.entity_id }}\t{{ a }}\n{% endif %}{% endfor %}")
        out = {}
        for line in self.template(tpl, timeout=20).splitlines():
            eid, _, area = line.partition("\t")
            if eid and area:
                out[eid.strip()] = area.strip()
        return out

    def device_entities(self, entity_id):
        """Autres entites du meme appareil (lumiere d'un ventilateur, minuteur, capteurs...)."""
        tpl = "{{ device_entities(device_id(%s)) | default([], true) | join(',') }}" % json.dumps(entity_id)
        out = self.template(tpl).strip()
        return [e for e in out.split(",") if e and e != entity_id]


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
