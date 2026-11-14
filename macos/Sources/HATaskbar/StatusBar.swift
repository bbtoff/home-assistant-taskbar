import AppKit
import SwiftUI

/// Les elements dans la barre des menus : un NSStatusItem par element, plus l'icone de l'application.
@MainActor
final class StatusBarController: NSObject, NSMenuDelegate {
    let model: AppModel
    var openSettings: (_ itemId: UUID?) -> Void = { _ in }
    var openPicker: () -> Void = {}

    private var appItem: NSStatusItem?
    private var entries: [ItemView] = []
    private var signature = ""
    private var popover: NSPopover?

    init(model: AppModel) {
        self.model = model
        super.init()
    }

    // MARK: construction

    private func currentSignature() -> String {
        let c = model.config
        let ids = c.items.filter(itemVisible).map { $0.id.uuidString }.joined(separator: ",")
        return "\(ids)|\(c.compact)|\(c.showAppIcon)|\(model.needsSetup)"
    }

    /// Recree les elements si la liste a change, puis met a jour les valeurs.
    func refresh() {
        let sig = currentSignature()
        if sig != signature {
            signature = sig
            rebuild()
        } else {
            let byId = Dictionary(model.config.items.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
            for v in entries {
                if let it = byId[v.item.id] { v.item = it }
            }
        }
        updateValues()
    }

    private func rebuild() {
        popover?.close()
        let bar = NSStatusBar.system
        for v in entries { bar.removeStatusItem(v.statusItem) }
        entries.removeAll()
        if let a = appItem { bar.removeStatusItem(a) }
        appItem = nil

        let visible = model.config.items.filter(itemVisible)
        // Un nouvel element se place a gauche des precedents : on cree d'abord l'icone de l'application
        // (la plus a droite), puis les elements du dernier au premier.
        if model.config.showAppIcon || visible.isEmpty || model.needsSetup {
            let a = bar.statusItem(withLength: NSStatusItem.squareLength)
            a.button?.image = Icons.image("house.fill", size: 14)
            a.button?.image?.isTemplate = true
            a.button?.toolTip = "HA Taskbar"
            let m = NSMenu()
            m.delegate = self
            a.menu = m
            appItem = a
        }
        for item in visible.reversed() {
            let si = bar.statusItem(withLength: NSStatusItem.variableLength)
            let v = ItemView(item: item, statusItem: si, controller: self)
            entries.insert(v, at: 0)
        }
    }

    private func updateValues() {
        let c = model.config
        for v in entries {
            let d = displayFor(v.item, states: model.states, offline: model.offline, batteryLow: c.batteryLow,
                               timerLeft: model.timerLeft(v.item.entityId))
            v.apply(d, compact: c.compact, animate: c.animIcons, flash: c.flashChanges && !model.offline)
            v.toolTip = tooltip(v.item, d)
        }
        if let b = appItem?.button {
            let off = model.offline && !model.needsSetup
            b.image = Icons.image(off ? "wifi.exclamationmark" : "house.fill", size: 14)
            b.image?.isTemplate = true
            b.toolTip = "HA Taskbar\n" + model.statusLine
        }
    }

    private func tooltip(_ item: ItemConfig, _ d: ItemDisplay) -> String {
        let st = model.states[item.entityId]
        var lines = [itemName(item, st) + " : " + d.text]
        if let ch = st?.lastChanged {
            let f = RelativeDateTimeFormatter()
            f.locale = Locale(identifier: "fr_FR")
            lines.append("modifié " + f.localizedString(for: ch, relativeTo: Date()))
        }
        if let left = model.timerLeft(item.entityId) {
            lines.append("arrêt dans \(max(1, Int((left / 60).rounded()))) min")
        }
        lines.append(resolveService(item) != nil
                     ? "Clic : action · Appui long ou ⌥-clic : carte · Molette : régler"
                     : "Clic : carte · Clic droit : menu")
        return lines.joined(separator: "\n")
    }

    // MARK: gestes (appeles par ItemView)

    func click(_ v: ItemView) {
        if model.needsSetup { openSettings(nil); return }
        if !model.click(v.item) { openCard(v) }
    }

    func wheel(_ v: ItemView, _ d: Int) {
        if let text = model.wheel(v.item, d) { v.showPending(text) }
    }

    func openCard(_ v: ItemView) {
        guard let button = v.statusItem.button else { return }
        if let p = popover, p.isShown {
            p.close()
            popover = nil
            return
        }
        let host = NSHostingController(rootView: CardView(model: model, itemId: v.item.id,
                                                          edit: { [weak self] in
                                                              self?.popover?.close()
                                                              self?.openSettings(v.item.id)
                                                          }))
        host.sizingOptions = .preferredContentSize
        let p = NSPopover()
        p.behavior = .transient
        p.animates = true
        p.contentViewController = host
        NSApp.activate(ignoringOtherApps: true)
        p.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        popover = p
    }

    func showMenu(_ v: ItemView) {
        let m = NSMenu()
        let item = v.item
        let st = model.states[item.entityId]
        let title = NSMenuItem(title: itemName(item, st), action: nil, keyEquivalent: "")
        title.isEnabled = false
        m.addItem(title)
        m.addItem(.separator())
        m.addItem(menuItem("Ouvrir la carte") { [weak self] in self?.openCard(v) })
        if resolveService(item) != nil {
            m.addItem(menuItem("Action du clic") { [weak self] in self?.model.click(item) })
        }
        if ["light", "switch", "fan", "media_player", "climate", "input_boolean", "humidifier"].contains(item.domain) {
            let sub = NSMenu()
            if model.timerLeft(item.entityId) != nil {
                sub.addItem(menuItem("Annuler l'arrêt programmé") { [weak self] in self?.model.cancelTimer(item.entityId) })
                sub.addItem(.separator())
            }
            for (label, min) in [("Dans 15 min", 15), ("Dans 30 min", 30), ("Dans 1 h", 60), ("Dans 2 h", 120)] {
                sub.addItem(menuItem(label) { [weak self] in self?.model.startTimer(item.entityId, minutes: min) })
            }
            let t = NSMenuItem(title: "Arrêt programmé", action: nil, keyEquivalent: "")
            t.submenu = sub
            m.addItem(t)
        }
        m.addItem(.separator())
        m.addItem(menuItem("Modifier cet élément…") { [weak self] in self?.openSettings(item.id) })
        m.addItem(menuItem("Masquer") { [weak self] in
            self?.model.update { c in
                if let i = c.items.firstIndex(where: { $0.id == item.id }) { c.items[i].hidden = true }
            }
        })
        m.addItem(.separator())
        addCommonItems(m)
        v.statusItem.menu = m
        v.statusItem.button?.performClick(nil)
        v.statusItem.menu = nil
    }

    // Menu de l'icone de l'application, reconstruit a chaque ouverture
    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()
        let s = NSMenuItem(title: model.statusLine, action: nil, keyEquivalent: "")
        s.isEnabled = false
        menu.addItem(s)
        if let ok = model.lastOK, model.offline {
            let f = DateFormatter()
            f.timeStyle = .short
            let l = NSMenuItem(title: "Dernière réponse à \(f.string(from: ok))", action: nil, keyEquivalent: "")
            l.isEnabled = false
            menu.addItem(l)
        }
        menu.addItem(.separator())
        let hidden = model.config.items.filter { $0.hidden == true }
        if !hidden.isEmpty {
            menu.addItem(menuItem("Réafficher les éléments masqués (\(hidden.count))") { [weak self] in
                self?.model.update { c in for i in c.items.indices { c.items[i].hidden = nil } }
            })
        }
        menu.addItem(menuItem("Ajouter des entités…") { [weak self] in self?.openPicker() })
        let pause = NSMenu()
        if model.notificationsPaused {
            pause.addItem(menuItem("Reprendre maintenant") { [weak self] in self?.model.pauseNotifications(until: nil) })
        }
        pause.addItem(menuItem("Pendant 1 h") { [weak self] in self?.model.pauseNotifications(until: Date().addingTimeInterval(3600)) })
        pause.addItem(menuItem("Pendant 3 h") { [weak self] in self?.model.pauseNotifications(until: Date().addingTimeInterval(3 * 3600)) })
        pause.addItem(menuItem("Jusqu'à demain 8 h") { [weak self] in
            let cal = Calendar.current
            var d = cal.date(bySettingHour: 8, minute: 0, second: 0, of: Date()) ?? Date()
            if d <= Date() { d = cal.date(byAdding: .day, value: 1, to: d) ?? d }
            self?.model.pauseNotifications(until: d)
        })
        let p = NSMenuItem(title: model.notificationsPaused ? "Notifications en pause" : "Mettre les notifications en pause",
                           action: nil, keyEquivalent: "")
        p.submenu = pause
        menu.addItem(p)
        menu.addItem(.separator())
        addCommonItems(menu)
    }

    private func addCommonItems(_ m: NSMenu) {
        m.addItem(menuItem("Ouvrir Home Assistant") { [weak self] in
            if let s = self?.model.config.haURL, let u = URL(string: s) { NSWorkspace.shared.open(u) }
        })
        m.addItem(menuItem("Actualiser") { [weak self] in self?.model.refreshNow() })
        m.addItem(menuItem("Réglages…", key: ",") { [weak self] in self?.openSettings(nil) })
        m.addItem(.separator())
        m.addItem(menuItem("Quitter HA Taskbar", key: "q") { NSApp.terminate(nil) })
    }

    private func menuItem(_ title: String, key: String = "", _ action: @escaping () -> Void) -> NSMenuItem {
        let i = ClosureMenuItem(title: title, action: #selector(ClosureMenuItem.fire), keyEquivalent: key)
        i.target = i
        i.handler = action
        return i
    }
}

/// Element de menu qui execute une fermeture.
final class ClosureMenuItem: NSMenuItem {
    var handler: (() -> Void)?
    @objc func fire() { handler?() }
}

// MARK: - Vue d'un element dans la barre des menus

@MainActor
final class ItemView: NSView {
    var item: ItemConfig
    let statusItem: NSStatusItem
    weak var controller: StatusBarController?

    private let imageView = NSImageView()
    private let label = NSTextField(labelWithString: "")
    private let badgeLabel = NSTextField(labelWithString: "")
    private var shown: ItemDisplay?
    private var compact = false
    private var holdUntil = Date.distantPast
    private var pressTask: Task<Void, Never>?
    private var holdTask: Task<Void, Never>?
    private var flashTask: Task<Void, Never>?
    private var longFired = false
    private var scrollAccum: CGFloat = 0

    init(item: ItemConfig, statusItem: NSStatusItem, controller: StatusBarController) {
        self.item = item
        self.statusItem = statusItem
        self.controller = controller
        super.init(frame: .zero)
        imageView.imageScaling = .scaleProportionallyDown
        imageView.translatesAutoresizingMaskIntoConstraints = true
        label.font = NSFont.monospacedDigitSystemFont(ofSize: NSFont.systemFontSize, weight: .regular)
        label.lineBreakMode = .byClipping
        badgeLabel.font = NSFont.systemFont(ofSize: 8, weight: .semibold)
        badgeLabel.textColor = .secondaryLabelColor
        for v in [imageView, label, badgeLabel] as [NSView] { addSubview(v) }
        if let b = statusItem.button {
            b.title = ""
            b.image = nil
            b.addSubview(self)
        }
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) non utilise") }

    override var isFlipped: Bool { false }

    func apply(_ d: ItemDisplay, compact: Bool, animate: Bool, flash: Bool) {
        if Date() < holdUntil { return }            // une valeur de la molette est affichee
        if d == shown && compact == self.compact { return }
        let old = shown
        shown = d
        self.compact = compact
        let color = colorFor(d)
        let symbolChanged = old?.symbol != d.symbol || old?.variable != d.variable
        if let s = d.symbol {
            if symbolChanged || imageView.image == nil {
                let img = Icons.image(s, variable: d.variable, size: 14)
                img?.isTemplate = true
                imageView.image = img
            }
            imageView.contentTintColor = color
            imageView.isHidden = false
        } else {
            imageView.image = nil
            imageView.isHidden = true
        }
        updateAnimation(animate ? d.anim : nil, force: symbolChanged || old?.anim != d.anim)
        label.stringValue = d.text
        label.textColor = color
        label.isHidden = compact && d.symbol != nil
        badgeLabel.stringValue = d.badge
        badgeLabel.isHidden = d.badge.isEmpty
        layoutContent()
        if flash, let o = old, o.text != d.text { flashValue() }
    }

    private func colorFor(_ d: ItemDisplay) -> NSColor {
        if let c = d.color, let col = NSColor(hex: c) { return col }
        switch d.tone {
        case .normal: return .labelColor
        case .on: return .haOn
        case .dim: return .tertiaryLabelColor
        case .error: return .systemRed
        }
    }

    private var currentAnim: AnimEffect?

    private func updateAnimation(_ anim: AnimEffect?, force: Bool) {
        guard #available(macOS 14.0, *) else { return }
        if anim == currentAnim && !force { return }
        currentAnim = anim
        imageView.removeAllSymbolEffects(animated: false)
        guard let a = anim else { return }
        switch a {
        case .variable:
            imageView.addSymbolEffect(.variableColor.iterative, options: .repeating)
        case .pulse:
            imageView.addSymbolEffect(.pulse, options: .repeating)
        case .rotate:
            if #available(macOS 15.0, *) {
                imageView.addSymbolEffect(.rotate, options: .repeating)
            } else {
                imageView.addSymbolEffect(.pulse, options: .repeating)
            }
        case .bounce:
            if #available(macOS 15.0, *) {
                imageView.addSymbolEffect(.wiggle, options: .repeating)
            } else {
                imageView.addSymbolEffect(.pulse, options: .repeating)
            }
        }
    }

    private func layoutContent() {
        let h = NSStatusBar.system.thickness
        let pad: CGFloat = 4
        var x = pad
        if !imageView.isHidden {
            imageView.frame = NSRect(x: x, y: (h - 18) / 2, width: 18, height: 18)
            x += 18
        }
        if !badgeLabel.isHidden {
            badgeLabel.sizeToFit()
            let bw = badgeLabel.frame.width
            badgeLabel.frame = NSRect(x: x - 3, y: h / 2, width: bw, height: badgeLabel.frame.height)
            x += max(0, bw - 3)
        }
        if !label.isHidden {
            label.sizeToFit()
            let lw = ceil(label.frame.width)
            let lh = label.frame.height
            if !imageView.isHidden { x += 3 }
            label.frame = NSRect(x: x, y: (h - lh) / 2, width: lw, height: lh)
            x += lw
        }
        x += pad
        frame = NSRect(x: 0, y: 0, width: x, height: h)
        statusItem.length = x
    }

    func showPending(_ text: String) {
        label.stringValue = text
        label.textColor = .haOn
        label.isHidden = false
        layoutContent()
        holdUntil = Date().addingTimeInterval(2.5)
        shown = nil
        holdTask?.cancel()
        holdTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 2_600_000_000)
            guard let self = self, !Task.isCancelled else { return }
            self.holdUntil = .distantPast
            self.controller?.refresh()
        }
    }

    private func flashValue() {
        flashTask?.cancel()
        let target: NSView = compact ? imageView : label
        target.alphaValue = 0.35
        flashTask = Task { @MainActor [weak target] in
            try? await Task.sleep(nanoseconds: 120_000_000)
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.6
                target?.animator().alphaValue = 1
            }
        }
    }

    // MARK: souris

    override func hitTest(_ point: NSPoint) -> NSView? {
        frame.contains(point) ? self : nil
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func mouseDown(with e: NSEvent) {
        if e.modifierFlags.contains(.control) {
            controller?.showMenu(self)
            return
        }
        statusItem.button?.highlight(true)
        longFired = false
        pressTask?.cancel()
        pressTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 450_000_000)
            guard let self = self, !Task.isCancelled else { return }
            self.longFired = true
            self.statusItem.button?.highlight(false)
            self.controller?.openCard(self)
        }
    }

    override func mouseUp(with e: NSEvent) {
        pressTask?.cancel()
        statusItem.button?.highlight(false)
        if longFired { return }
        guard bounds.contains(convert(e.locationInWindow, from: nil)) else { return }
        if e.modifierFlags.contains(.option) {
            controller?.openCard(self)
        } else {
            controller?.click(self)
        }
    }

    override func rightMouseDown(with e: NSEvent) {
        controller?.showMenu(self)
    }

    override func otherMouseDown(with e: NSEvent) {
        controller?.openCard(self)
    }

    override func scrollWheel(with e: NSEvent) {
        var dy = e.scrollingDeltaY
        if e.isDirectionInvertedFromDevice { dy = -dy }
        if e.hasPreciseScrollingDeltas {
            if e.phase == .began { scrollAccum = 0 }
            scrollAccum += dy
            while scrollAccum >= 14 { scrollAccum -= 14; controller?.wheel(self, 1) }
            while scrollAccum <= -14 { scrollAccum += 14; controller?.wheel(self, -1) }
        } else if dy != 0 {
            controller?.wheel(self, dy > 0 ? 1 : -1)
        }
    }
}
