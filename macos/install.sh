#!/bin/bash
# Installe (ou met a jour) HA Taskbar pour macOS depuis les Releases GitHub, sans blocage de Gatekeeper.
#
#   curl -fsSL https://raw.githubusercontent.com/bbtoff/home-assistant-taskbar/main/macos/install.sh | bash
#
# Le script telecharge la derniere version publiee, verifie son empreinte SHA-256 (fournie par GitHub),
# ferme HA Taskbar s'il est ouvert, installe l'application dans /Applications (ou ~/Applications) et la lance.
# Un fichier telecharge par curl n'est pas marque « venu d'Internet » : macOS ne demande pas de confirmation.
#
# Variables facultatives : HATB_DEST (dossier d'installation), HATB_NO_OPEN=1 (ne pas lancer l'application).
set -euo pipefail

REPO="bbtoff/home-assistant-taskbar"
APP_NAME="HA Taskbar.app"

say() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[31mErreur : %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || fail "ce script est pour macOS."

say "== HA Taskbar pour macOS : recherche de la dernière version"
API="https://api.github.com/repos/$REPO/releases/latest"
JSON="$(curl -fsSL -H "Accept: application/vnd.github+json" "$API")" || fail "GitHub ne répond pas."

# Lecture du JSON avec JavaScript for Automation (toujours present sur macOS)
INFO="$(osascript -l JavaScript -e '
function run(argv) {
  var r = JSON.parse(argv[0]);
  var v = String(r.tag_name || "").replace(/^v/i, "");
  var a = (r.assets || []).filter(function (x) { return x.name === "HATaskbar-macOS-" + v + ".zip"; })[0];
  if (!a) return "";
  var sha = String(a.digest || "").replace(/^sha256:/, "");
  return [v, a.browser_download_url, sha, a.size].join("\n");
}' "$JSON")" || fail "réponse de GitHub illisible."
[ -n "$INFO" ] || fail "la dernière version publiée ne contient pas encore l'application Mac."

VERSION="$(sed -n 1p <<<"$INFO")"
URL="$(sed -n 2p <<<"$INFO")"
SHA="$(sed -n 3p <<<"$INFO")"
case "$URL" in
  "https://github.com/$REPO/releases/download/"*) ;;
  *) fail "adresse de téléchargement inattendue : $URL" ;;
esac

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
say "== Téléchargement de la version $VERSION"
curl -fL --progress-bar -o "$TMP/app.zip" "$URL" || fail "téléchargement impossible."

if [ -n "$SHA" ]; then
  GOT="$(shasum -a 256 "$TMP/app.zip" | cut -d' ' -f1)"
  [ "$GOT" = "$SHA" ] || fail "empreinte SHA-256 incorrecte : fichier abîmé ou modifié."
  echo "Empreinte SHA-256 vérifiée : $SHA"
else
  echo "(GitHub n'a pas fourni d'empreinte pour ce fichier : vérification impossible)"
fi

ditto -x -k "$TMP/app.zip" "$TMP/x" || fail "archive illisible."
[ -d "$TMP/x/$APP_NAME" ] || fail "l'archive ne contient pas « $APP_NAME »."
BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$TMP/x/$APP_NAME/Contents/Info.plist" 2>/dev/null || true)"
[ "$BUNDLE_ID" = "io.github.bbtoff.hataskbar" ] || fail "application inattendue ($BUNDLE_ID)."

# Dossier d'installation : celui d'une installation existante, sinon /Applications (ou ~/Applications)
if [ -n "${HATB_DEST:-}" ]; then
  DEST="$HATB_DEST"
elif [ -d "$HOME/Applications/$APP_NAME" ] && [ ! -d "/Applications/$APP_NAME" ]; then
  DEST="$HOME/Applications"
elif [ -w "/Applications" ]; then
  DEST="/Applications"
else
  DEST="$HOME/Applications"
fi
mkdir -p "$DEST"

if pgrep -x HATaskbar >/dev/null 2>&1; then
  say "== Fermeture de HA Taskbar"
  osascript -e 'tell application id "io.github.bbtoff.hataskbar" to quit' >/dev/null 2>&1 || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do pgrep -x HATaskbar >/dev/null 2>&1 || break; sleep 0.5; done
  pkill -x HATaskbar 2>/dev/null || true
fi

say "== Installation dans $DEST"
rm -rf "$DEST/$APP_NAME"
ditto "$TMP/x/$APP_NAME" "$DEST/$APP_NAME"
xattr -dr com.apple.quarantine "$DEST/$APP_NAME" 2>/dev/null || true

INSTALLED="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$DEST/$APP_NAME/Contents/Info.plist")"
say "== HA Taskbar $INSTALLED installé : $DEST/$APP_NAME"
if [ -z "${HATB_NO_OPEN:-}" ]; then
  open "$DEST/$APP_NAME"
  echo "HA Taskbar est lancé : son icône 🏠 est dans la barre des menus, en haut à droite."
fi
echo "Les mises à jour suivantes se font depuis l'application (menu 🏠 → Mettre à jour), ou en relançant cette commande."
