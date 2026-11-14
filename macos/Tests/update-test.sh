#!/bin/bash
# Test de bout en bout, sur un vrai Mac (GitHub Actions) :
#   1. install.sh installe la derniere version publiee (et verifie son empreinte)
#   2. une « vieille » application (--fake-version 0.0.1) se met a jour toute seule depuis GitHub
# Prerequis : ./build.sh deja lance.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-dist/update-test}"
rm -rf "$OUT"; mkdir -p "$OUT"
FAIL=0
version() { /usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$1/Contents/Info.plist" 2>/dev/null; }

LATEST=$(curl -fsSLI -o /dev/null -w '%{url_effective}' https://github.com/bbtoff/home-assistant-taskbar/releases/latest)
LATEST="${LATEST##*/v}"
echo "Derniere version publiee : $LATEST"

echo "== 1. Installation par install.sh (API de GitHub)"
HATB_DEST="$OUT/apps" HATB_NO_OPEN=1 bash install.sh
GOT=$(version "$OUT/apps/HA Taskbar.app")
if [ "$GOT" = "$LATEST" ]; then echo "OK    install.sh a installe la version $GOT"; else echo "ECHEC install.sh : '$GOT'"; FAIL=1; fi
if xattr "$OUT/apps/HA Taskbar.app" | grep -q quarantine; then echo "ECHEC marque de quarantaine presente"; FAIL=1; else echo "OK    pas de marque de quarantaine"; fi

echo "== 1b. Installation par install.sh sans l'API (page des Releases)"
rm -rf "$OUT/apps2"
sed 's|https://api.github.com/repos/|https://api.github.invalid/repos/|' install.sh > "$OUT/install-sans-api.sh"
HATB_DEST="$OUT/apps2" HATB_NO_OPEN=1 GITHUB_TOKEN= bash "$OUT/install-sans-api.sh"
GOT=$(version "$OUT/apps2/HA Taskbar.app")
if [ "$GOT" = "$LATEST" ]; then echo "OK    install.sh sans l'API : version $GOT"; else echo "ECHEC install.sh sans l'API : '$GOT'"; FAIL=1; fi

echo "== 2. Mise a jour automatique depuis l'application"
mkdir -p "$OUT/self"
ditto "dist/HA Taskbar.app" "$OUT/self/HA Taskbar.app"
LOG="$OUT/update.log"
"$OUT/self/HA Taskbar.app/Contents/MacOS/HATaskbar" --demo --demo-log "$LOG" --update-test --fake-version 0.0.1 &
PID=$!
for _ in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
for _ in $(seq 1 30); do [ "$(version "$OUT/self/HA Taskbar.app")" = "$LATEST" ] && break; sleep 1; done
echo "      journal : $(tr '\n' ' ' < "$LOG" 2>/dev/null)"
GOT=$(version "$OUT/self/HA Taskbar.app")
if [ "$GOT" = "$LATEST" ]; then echo "OK    l'application s'est mise a jour en $GOT"; else echo "ECHEC mise a jour : version '$GOT'"; FAIL=1; fi
codesign --verify "$OUT/self/HA Taskbar.app" && echo "OK    signature de l'application installee valide" || { echo "ECHEC signature"; FAIL=1; }

exit $FAIL
