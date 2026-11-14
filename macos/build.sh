#!/bin/bash
# Construit HA Taskbar pour macOS :
#   dist/HA Taskbar.app                    l'application (Intel + Apple Silicon)
#   dist/HATaskbar-macOS-<version>.zip     l'application compressee
#   dist/HATaskbar-macOS-<version>.dmg     image disque a glisser dans Applications
#
# Prerequis : Xcode (ou les outils en ligne de commande : xcode-select --install).
# Usage :     ./build.sh            (ajoute --native pour ne construire que pour ce Mac)
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(sed -n 's/^let appVersion = "\(.*\)"/\1/p' Sources/HATaskbar/Version.swift)
APP="dist/HA Taskbar.app"
echo "== HA Taskbar pour macOS $VERSION"

# --- 1. compilation
ARCHS=(--arch arm64 --arch x86_64)
if [[ "${1:-}" == "--native" ]]; then ARCHS=(); fi
if ! swift build -c release ${ARCHS[@]+"${ARCHS[@]}"}; then
    if [[ ${#ARCHS[@]} -gt 0 ]]; then
        echo "== Compilation universelle impossible, compilation pour ce Mac seulement"
        ARCHS=()
        swift build -c release
    else
        exit 1
    fi
fi
BIN="$(swift build -c release ${ARCHS[@]+"${ARCHS[@]}"} --show-bin-path)/HATaskbar"

# --- 2. paquet .app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/HATaskbar"
sed -e "s/__VERSION__/$VERSION/g" -e "s/__YEAR__/$(date +%Y)/g" Info.plist > "$APP/Contents/Info.plist"
printf 'APPL????' > "$APP/Contents/PkgInfo"

# Icone : a partir de assets/ha_taskbar.png (le meme dessin que sous Windows)
ICONSET="$(mktemp -d)/AppIcon.iconset"
mkdir -p "$ICONSET"
SRC=../assets/ha_taskbar.png
for s in 16 32 128 256; do
    sips -z $s $s "$SRC" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    d=$((s * 2))
    sips -z $d $d "$SRC" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
rm -rf "$(dirname "$ICONSET")"

# --- 3. signature locale (ad hoc) : suffit pour l'utiliser sur ce Mac
codesign --force --deep --sign - "$APP"
codesign --verify "$APP"

# --- 4. zip et dmg
ZIP="dist/HATaskbar-macOS-$VERSION.zip"
DMG="dist/HATaskbar-macOS-$VERSION.dmg"
rm -f "$ZIP" "$DMG"
ditto -c -k --keepParent "$APP" "$ZIP"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "HA Taskbar" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

echo "== Termine :"
echo "   $APP"
echo "   $ZIP"
echo "   $DMG"
shasum -a 256 "$ZIP" "$DMG"
echo
echo "Pour l'installer : glisse « HA Taskbar » dans Applications (ou : cp -R \"$APP\" /Applications/)"
