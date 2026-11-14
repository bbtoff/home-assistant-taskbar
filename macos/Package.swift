// swift-tools-version:5.9
// HA Taskbar pour macOS : capteurs et boutons Home Assistant dans la barre des menus.
// Ouvrir dans Xcode : double-clic sur ce fichier (ou `open Package.swift`).
// Construire l'application (.app, .zip, .dmg) : ./build.sh
import PackageDescription

let package = Package(
    name: "HATaskbar",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "HATaskbar",
            path: "Sources/HATaskbar"
        )
    ]
)
