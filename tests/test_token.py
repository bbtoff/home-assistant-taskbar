"""Le jeton est chiffre dans config.json (DPAPI sous Windows) et relu correctement.
Lancement : python tests/test_token.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ha_core  # noqa: E402

SECRET = "eyJhbGciOiJIUzI1NiJ9.test-jeton-longue-duree.é"


def main():
    d = tempfile.mkdtemp()
    ha_core.CONFIG_DIR = d
    ha_core.CONFIG_PATH = os.path.join(d, "config.json")
    windows = ha_core.token_protection_available()
    print("Chiffrement DPAPI disponible :", windows)

    # 1. ancienne configuration, jeton en clair : migree des le chargement
    with open(ha_core.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"ha_url": "http://ha.local:8123", "token": SECRET, "items": []}, f)
    cfg = ha_core.load_config()
    assert cfg["token"] == SECRET, "jeton mal relu"
    raw = open(ha_core.CONFIG_PATH, encoding="utf-8").read()
    if windows:
        assert SECRET not in raw, "le jeton est encore en clair dans config.json"
        assert json.loads(raw)["token_protected"].startswith("dpapi:")

    # 2. aller-retour enregistrement / chargement
    cfg["token"] = SECRET + "2"
    ha_core.save_config(cfg)
    raw = open(ha_core.CONFIG_PATH, encoding="utf-8").read()
    if windows:
        assert SECRET not in raw
    assert ha_core.load_config()["token"] == SECRET + "2"
    assert "token_protected" not in ha_core.load_config()

    # 3. jeton chiffre ailleurs (illisible) : a ressaisir, sans erreur
    data = json.loads(raw)
    data["token_protected"] = "dpapi:AAAA"
    data["token"] = ""
    with open(ha_core.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)
    cfg = ha_core.load_config()
    assert cfg["token"] == "" and ha_core.needs_setup(cfg)
    if windows:
        assert ha_core.TOKEN_UNREADABLE
    print("OK")


if __name__ == "__main__":
    main()
