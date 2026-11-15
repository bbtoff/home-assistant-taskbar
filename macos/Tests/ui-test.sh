#!/bin/bash
# Test de l'interface sur un vrai Mac (GitHub Actions) : clic, appui long, reglage « le clic ouvre la carte ».
# Utilise le mode demonstration et simule la souris. Prerequis : ./build.sh (ou --native) deja lance.
set -uo pipefail
cd "$(dirname "$0")/.."
APP="dist/HA Taskbar.app/Contents/MacOS/HATaskbar"
OUT="${1:-dist/ui-test}"
mkdir -p "$OUT"
swiftc -O Tests/mouse.swift -o "$OUT/mouse" || exit 1
LOG="$OUT/ui.log"
FAIL=0
PID=""

start() {
    rm -f "$LOG"
    "$OUT/mouse" 600 450 0 move        # pointeur a l'ecart : pas de survol avant le geste teste
    "$APP" --demo --demo-items "${ITEMS:-0,2,3,4}" --demo-log "$LOG" "$@" &
    PID=$!
    sleep 6
    POS=$(grep "^frame light.salon " "$LOG" | tail -1 | cut -d' ' -f3,4)
    echo "   lumiere a : ${POS:-introuvable}"
}
stop() { kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null; sleep 1; }
check() {   # check <nom> <motif attendu> [motif interdit]
    if grep -q "$2" "$LOG" && { [ -z "${3:-}" ] || ! grep -q "$3" "$LOG"; }; then
        echo "OK    $1"
    else
        echo "ECHEC $1"; FAIL=1
    fi
    echo "      journal : $(grep -v '^frame' "$LOG" | tr '\n' ' ')"
}

echo "== 1. Clic simple sur une lumiere : action, pas de carte"
start
"$OUT/mouse" $POS 0.08; sleep 2
check "clic = action" "^click light.salon" "^card light.salon"
stop

echo "== 2. Appui long : la carte s'ouvre"
start
"$OUT/mouse" $POS 1.0; sleep 2
screencapture -x "$OUT/appui-long.png"
check "appui long = carte" "^card light.salon shown=true" "^click light.salon\|^hover"
stop

echo "== 3. Reglage « le clic ouvre la carte »"
start --demo-click-card
"$OUT/mouse" $POS 0.08; sleep 2
screencapture -x "$OUT/clic-carte.png"
check "clic = carte" "^card light.salon shown=true" "^hover"
stop

echo "== 4. Capteur : un clic ouvre la carte"
start
P2=$(grep "^frame sensor.consommation " "$LOG" | tail -1 | cut -d' ' -f3,4)
"$OUT/mouse" $P2 0.08; sleep 2
check "capteur = carte" "^click sensor.consommation" "^hover"
stop

echo "== 4b. Clim a 6 modes : la carte ne deborde pas"
ITEMS=0,6 start
P3=$(grep "^frame climate.clim_salon " "$LOG" | tail -1 | cut -d' ' -f3,4)
"$OUT/mouse" $P3 1.0; sleep 2
screencapture -x "$OUT/carte-clim.png"
W=$(grep "^cardwidth climate.clim_salon " "$LOG" | tail -1 | cut -d' ' -f3)
if [ -n "$W" ] && [ "$W" -le 340 ]; then echo "OK    carte de la clim : largeur $W"; else echo "ECHEC carte de la clim : largeur '$W' (> 340)"; FAIL=1; fi
stop

echo "== 4c. Widgets de bureau et mini-graphique"
start
sleep 2
screencapture -x "$OUT/widgets.png"
check "widget consommation affiche" "^widget sensor.consommation shown=true"
check "widget a deux capteurs affiche" "^widget sensor.temperature_exterieure,sensor.temperature_chambre shown=true"
stop

echo "== 4d. Mini-graphique visible sur une barre des menus sombre (application en theme clair)"
swiftc -O Tests/pixels.swift -o "$OUT/pixels" || exit 1
osascript -e 'tell application "System Events" to tell appearance preferences to set dark mode to true' || true
sleep 2
start --demo-app-light
sleep 2
SP=$(grep "^spark sensor.consommation " "$LOG" | tail -1 | cut -d' ' -f3-6)
screencapture -x "$OUT/mini-graphique-barre-sombre.png"
if [ -n "$SP" ]; then
    read LIGHT DARK <<< "$("$OUT/pixels" "$OUT/mini-graphique-barre-sombre.png" $SP)"
    if [ "${LIGHT:-0}" -ge 8 ]; then echo "OK    mini-graphique visible ($LIGHT pixels clairs)"
    else echo "ECHEC mini-graphique invisible sur barre sombre ($LIGHT clairs, $DARK sombres)"; FAIL=1; fi
else
    echo "ECHEC mini-graphique absent"; FAIL=1
fi
stop
osascript -e 'tell application "System Events" to tell appearance preferences to set dark mode to false' || true
sleep 2

echo "== 5. Survol : la carte s'ouvre apres le delai, puis se referme quand la souris s'en va"
start --demo-hover 0.8
"$OUT/mouse" 600 400 0 move; sleep 1
"$OUT/mouse" $POS 0 move; sleep 2.5
screencapture -x "$OUT/survol.png"
check "survol = carte" "^card light.salon shown=true" "^click light.salon"
"$OUT/mouse" 600 500 0 move; sleep 2.5
check "souris partie = carte fermee" "^close light.salon"
stop

echo "== 6. Survol desactive : rien ne s'ouvre"
start --demo-hover 0
"$OUT/mouse" 600 400 0 move; sleep 1
"$OUT/mouse" $POS 0 move; sleep 2.5
if grep -q "^card " "$LOG"; then echo "ECHEC survol desactive"; FAIL=1; else echo "OK    survol desactive"; fi
stop

exit $FAIL
