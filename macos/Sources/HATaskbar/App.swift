import AppKit
import SwiftUI
import UserNotifications

/// Point d'entree : application de barre des menus (pas d'icone dans le Dock).
@main
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private static var instance: AppDelegate?

    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        instance = delegate
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
    }

    let model = AppModel()
    let nav = SettingsNav()
    private var bar: StatusBarController?
    private var settingsWindow: NSWindow?
    private let notificationDelegate = NotificationDelegate()

    func applicationDidFinishLaunching(_ notification: Notification) {
        installMainMenu()
        if Notifier.available {
            UNUserNotificationCenter.current().delegate = notificationDelegate
            Notifier.requestAuthorization()
        }
        let bar = StatusBarController(model: model)
        bar.openSettings = { [weak self] id in self?.showSettings(item: id) }
        bar.openPicker = { [weak self] in self?.showSettings(picker: true) }
        self.bar = bar
        model.onStatesChanged = { [weak self] in self?.bar?.refresh() }
        model.onConfigChanged = { [weak self] in self?.bar?.refresh() }
        bar.refresh()
        model.start()
        if model.needsSetup {
            showSettings(tab: .connection)
        }
        if Demo.enabled { runDemo() }
    }

    private func runDemo() {
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            if let s = Demo.arg("--demo-card"), let n = Int(s) {
                bar?.openCard(at: n)
            }
            if let t = Demo.arg("--demo-settings") {
                let tab: SettingsTab = ["connection": .connection, "notifications": .notifications,
                                        "general": .general][t] ?? .items
                showSettings(item: tab == .items ? model.config.items.first?.id : nil, tab: tab)
            }
            if Demo.arg("--demo-picker") != nil {
                showSettings(picker: true)
            }
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showSettings()               // double-clic sur l'application deja ouverte : reglages
        return false
    }

    func showSettings(item: UUID? = nil, tab: SettingsTab? = nil, picker: Bool = false) {
        if let id = item {
            nav.tab = .items
            nav.selected = id
        } else if let t = tab {
            nav.tab = t
        }
        if picker {
            nav.tab = .items
            nav.showPicker = true
        }
        if settingsWindow == nil {
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 820, height: 580),
                             styleMask: [.titled, .closable, .miniaturizable, .resizable],
                             backing: .buffered, defer: false)
            w.title = "HA Taskbar — Réglages"
            w.isReleasedWhenClosed = false
            w.contentView = NSHostingView(rootView: SettingsView(model: model, nav: nav))
            w.setContentSize(NSSize(width: 820, height: 580))
            w.center()
            w.setFrameAutosaveName("HATaskbarSettings")
            settingsWindow = w
        }
        NSApp.activate(ignoringOtherApps: true)
        settingsWindow?.makeKeyAndOrderFront(nil)
    }

    /// Menu principal invisible (application de barre des menus) : il fait marcher ⌘C, ⌘V, ⌘W...
    private func installMainMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Réglages…", action: #selector(openSettingsAction), keyEquivalent: ",").target = self
        appMenu.addItem(withTitle: "Quitter HA Taskbar", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        let editItem = NSMenuItem()
        let edit = NSMenu(title: "Édition")
        edit.addItem(withTitle: "Annuler", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Rétablir", action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: "Couper", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copier", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Coller", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Tout sélectionner", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        main.addItem(editItem)

        let winItem = NSMenuItem()
        let win = NSMenu(title: "Fenêtre")
        win.addItem(withTitle: "Fermer", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        win.addItem(withTitle: "Réduire", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        winItem.submenu = win
        main.addItem(winItem)
        NSApp.mainMenu = main
    }

    @objc private func openSettingsAction() { showSettings() }
}

/// Affiche les notifications meme quand la fenetre de reglages est au premier plan.
final class NotificationDelegate: NSObject, UNUserNotificationCenterDelegate {
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
}
