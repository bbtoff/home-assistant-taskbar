"""
Langue de l'interface : francais ou anglais.

Par defaut, la langue suit celle de Windows (francais si Windows est en francais, anglais sinon).
Elle peut etre forcee dans Reglages -> Connexion -> Langue ("language" dans config.json) ;
le changement s'applique au prochain lancement.

Les textes du programme sont ecrits en francais et passes a _() ; les traductions anglaises sont
dans i18n_en.py (texte francais -> texte anglais). Un texte sans traduction reste en francais.
"""
import ctypes
import json
import os

LANG = "fr"
LANGUAGES = [("auto", None), ("fr", "Français"), ("en", "English")]
_EN = None


def system_language():
    """"fr" si Windows est en francais (toutes variantes : France, Belgique, Canada, Suisse...), sinon "en"."""
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except Exception:
        return "en"
    return "fr" if (lid & 0x3FF) == 0x0C else "en"


def init(config_path):
    """Choisit la langue d'apres config.json (cle "language") puis Windows. Appele une fois au demarrage,
    avant la creation des textes."""
    global LANG
    choice = "auto"
    try:
        with open(config_path, encoding="utf-8") as f:
            choice = json.load(f).get("language") or "auto"
    except (OSError, ValueError, AttributeError):
        pass
    forced = os.environ.get("HATASKBAR_LANG")
    if forced in ("fr", "en"):
        choice = forced
    LANG = choice if choice in ("fr", "en") else system_language()


def _(text):
    """Texte traduit dans la langue de l'interface."""
    global _EN
    if LANG == "fr":
        return text
    if _EN is None:
        try:
            from i18n_en import EN
        except ImportError:
            EN = {}
        _EN = EN
    return _EN.get(text, text)


def decimal_sep():
    return "," if LANG == "fr" else "."
