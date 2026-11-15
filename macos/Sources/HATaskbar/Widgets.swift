import AppKit
import Charts
import SwiftUI

// MARK: - Fenetres des widgets

/// Widgets de bureau : petites fenetres sans bordure, posees sur le bureau (sous les fenetres)
/// ou au premier plan, deplacables a la souris. Position et reglages sont dans config.json.
@MainActor
final class WidgetController {
    let model: AppModel
    let history: HistoryStore
    var openSettings: (_ widgetId: UUID?) -> Void = { _ in }
    private var panels: [UUID: WidgetPanel] = [:]

    init(model: AppModel, history: HistoryStore) {
        self.model = model
        self.history = history
    }

    /// Cree, met a jour ou ferme les fenetres d'apres la configuration.
    func sync() {
        let widgets = model.config.widgets.filter { !$0.hidden && !$0.entities.isEmpty }
        let ids = Set(widgets.map(\.id))
        for (id, p) in panels where !ids.contains(id) {
            p.close()
            panels.removeValue(forKey: id)
        }
        for (i, w) in widgets.enumerated() {
            if let p = panels[w.id] {
                p.apply(w)
                if w.x == nil || w.y == nil {      // « remettre a sa place »
                    p.setFrameOrigin(Self.defaultOrigin(size: w.pixelSize, index: i))
                }
            } else {
                let p = WidgetPanel(widget: w, index: i, controller: self)
                panels[w.id] = p
                p.orderFront(nil)
                Demo.log("widget \(w.entities.joined(separator: ",")) shown=\(p.isVisible)")
            }
        }
    }

    func update(_ id: UUID, _ change: (inout WidgetConfig) -> Void) {
        model.update { c in
            if let i = c.widgets.firstIndex(where: { $0.id == id }) { change(&c.widgets[i]) }
        }
    }

    func remove(_ id: UUID) {
        model.update { $0.widgets.removeAll { $0.id == id } }
    }

    /// Menu du clic droit sur un widget.
    func menu(for id: UUID) -> NSMenu {
        let m = NSMenu()
        guard let w = model.config.widgets.first(where: { $0.id == id }) else { return m }
        func item(_ title: String, checked: Bool = false, _ action: @escaping () -> Void) -> NSMenuItem {
            let i = ClosureMenuItem(title: title, action: #selector(ClosureMenuItem.fire), keyEquivalent: "")
            i.target = i
            i.handler = action
            i.state = checked ? .on : .off
            return i
        }
        let period = NSMenu()
        for (label, h) in [("24 heures", 24.0), ("7 jours", 168.0), ("30 jours", 720.0)] {
            period.addItem(item(label, checked: w.hours == h) { [weak self] in self?.update(id) { $0.hours = h } })
        }
        let p = NSMenuItem(title: "Période", action: nil, keyEquivalent: "")
        p.submenu = period
        m.addItem(p)
        let size = NSMenu()
        for (label, s) in [("Petit", "small"), ("Moyen", "medium"), ("Grand", "large")] {
            size.addItem(item(label, checked: w.size == s) { [weak self] in self?.update(id) { $0.size = s } })
        }
        let sz = NSMenuItem(title: "Taille", action: nil, keyEquivalent: "")
        sz.submenu = size
        m.addItem(sz)
        let style = NSMenu()
        style.addItem(item("Graphique", checked: w.style == "graph") { [weak self] in self?.update(id) { $0.style = "graph" } })
        style.addItem(item("Valeur en grand", checked: w.style == "value") { [weak self] in self?.update(id) { $0.style = "value" } })
        let st = NSMenuItem(title: "Affichage", action: nil, keyEquivalent: "")
        st.submenu = style
        m.addItem(st)
        m.addItem(item("Toujours au premier plan", checked: w.onTop) { [weak self] in self?.update(id) { $0.onTop.toggle() } })
        m.addItem(.separator())
        m.addItem(item("Modifier le widget…") { [weak self] in self?.openSettings(id) })
        m.addItem(item("Masquer") { [weak self] in self?.update(id) { $0.hidden = true } })
        m.addItem(item("Supprimer") { [weak self] in self?.remove(id) })
        return m
    }

    /// Position par defaut d'un nouveau widget : en haut a droite de l'ecran, les uns sous les autres.
    static func defaultOrigin(size: CGSize, index: Int) -> NSPoint {
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let x = screen.maxX - size.width - 24
        var y = screen.maxY - 24 - size.height - CGFloat(index) * (size.height + 16)
        if y < screen.minY + 16 { y = screen.maxY - 24 - size.height }
        return NSPoint(x: x, y: y)
    }
}

/// Fenetre d'un widget.
final class WidgetPanel: NSPanel {
    let widgetId: UUID
    private weak var controller: WidgetController?
    private var moveObserver: NSObjectProtocol?
    private var saveTask: Task<Void, Never>?

    @MainActor
    init(widget w: WidgetConfig, index: Int, controller: WidgetController) {
        widgetId = w.id
        self.controller = controller
        let size = w.pixelSize
        let origin = (w.x != nil && w.y != nil) ? NSPoint(x: w.x!, y: w.y!) : WidgetController.defaultOrigin(size: size, index: index)
        super.init(contentRect: NSRect(origin: origin, size: size), styleMask: [.borderless, .nonactivatingPanel],
                   backing: .buffered, defer: false)
        isOpaque = false
        backgroundColor = .clear
        hasShadow = true
        hidesOnDeactivate = false
        isReleasedWhenClosed = false
        collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenNone]

        let effect = NSVisualEffectView(frame: NSRect(origin: .zero, size: size))
        effect.material = .popover
        effect.blendingMode = .behindWindow
        effect.state = .active
        effect.maskImage = WidgetPanel.roundedMask(16)
        effect.autoresizingMask = [.width, .height]
        let host = NSHostingView(rootView: WidgetView(model: controller.model, history: controller.history, widgetId: w.id))
        host.frame = effect.bounds
        host.autoresizingMask = [.width, .height]
        effect.addSubview(host)
        let grip = WidgetGrip(frame: effect.bounds, panel: self)
        grip.autoresizingMask = [.width, .height]
        effect.addSubview(grip)
        contentView = effect
        apply(w)

        moveObserver = NotificationCenter.default.addObserver(forName: NSWindow.didMoveNotification, object: self,
                                                              queue: .main) { [weak self] _ in
            Task { @MainActor in self?.scheduleSave() }
        }
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) non utilise") }

    deinit {
        if let o = moveObserver { NotificationCenter.default.removeObserver(o) }
    }

    /// Masque aux coins arrondis, etirable (fond flou du widget).
    static func roundedMask(_ r: CGFloat) -> NSImage {
        let img = NSImage(size: NSSize(width: 2 * r + 1, height: 2 * r + 1), flipped: false) { rect in
            NSColor.black.setFill()
            NSBezierPath(roundedRect: rect, xRadius: r, yRadius: r).fill()
            return true
        }
        img.capInsets = NSEdgeInsets(top: r, left: r, bottom: r, right: r)
        img.resizingMode = .stretch
        return img
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }

    /// Niveau (bureau ou premier plan) et taille d'apres la configuration.
    @MainActor
    func apply(_ w: WidgetConfig) {
        level = w.onTop ? .floating
            : NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.desktopIconWindow)) + 1)
        let size = w.pixelSize
        if frame.size != size {
            // On garde le coin haut gauche en place
            let top = frame.maxY
            setFrame(NSRect(x: frame.minX, y: top - size.height, width: size.width, height: size.height), display: true)
        }
    }

    @MainActor
    private func scheduleSave() {
        saveTask?.cancel()
        saveTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 500_000_000)
            guard let self = self, !Task.isCancelled else { return }
            let f = self.frame
            self.controller?.update(self.widgetId) { w in
                w.x = Double(f.minX.rounded())
                w.y = Double(f.minY.rounded())
            }
        }
    }

    @MainActor
    func showMenu(with event: NSEvent, in view: NSView) {
        guard let m = controller?.menu(for: widgetId) else { return }
        NSMenu.popUpContextMenu(m, with: event, for: view)
    }

    @MainActor
    func openSettings() { controller?.openSettings(widgetId) }
}

/// Couche transparente au-dessus du contenu : glisser pour deplacer, clic droit pour le menu,
/// double-clic pour les reglages.
final class WidgetGrip: NSView {
    private weak var panel: WidgetPanel?

    init(frame: NSRect, panel: WidgetPanel) {
        self.panel = panel
        super.init(frame: frame)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) non utilise") }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func mouseDown(with e: NSEvent) {
        if e.clickCount == 2 {
            panel?.openSettings()
        } else if e.modifierFlags.contains(.control) {
            panel?.showMenu(with: e, in: self)
        } else {
            window?.performDrag(with: e)
        }
    }

    override func rightMouseDown(with e: NSEvent) {
        panel?.showMenu(with: e, in: self)
    }
}

// MARK: - Contenu d'un widget

let widgetColors: [Color] = [.accentColor, .orange, .green, .pink, .purple, .teal]

struct WidgetView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var history: HistoryStore
    let widgetId: UUID

    private var widget: WidgetConfig? { model.config.widgets.first { $0.id == widgetId } }

    var body: some View {
        Group {
            if let w = widget {
                content(w)
            } else {
                Color.clear
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func name(_ eid: String) -> String {
        model.config.items.first(where: { $0.entityId == eid })?.label.nonEmpty ?? model.states[eid]?.name ?? eid
    }

    private func value(_ eid: String) -> String {
        displayFor(ItemConfig(entityId: eid), states: model.states, offline: model.offline,
                   batteryLow: model.config.batteryLow, timerLeft: nil).text
    }

    private func period(_ h: Double) -> String {
        h <= 24 ? "24 h" : h <= 168 ? "7 jours" : "30 jours"
    }

    @ViewBuilder
    private func content(_ w: WidgetConfig) -> some View {
        let single = w.entities.count == 1
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(w.title.nonEmpty ?? (single ? name(w.entities[0]) : "Capteurs"))
                    .font(.headline)
                    .lineLimit(1)
                Spacer(minLength: 4)
                if w.style == "graph" {
                    Text(period(w.hours)).font(.caption).foregroundStyle(.secondary)
                }
                if model.offline {
                    Image(systemName: "wifi.exclamationmark").foregroundStyle(.secondary)
                }
            }
            if single {
                Text(value(w.entities[0]))
                    .font(.system(size: w.style == "value" ? (w.size == "large" ? 44 : 34) : 22, weight: .light))
                    .monospacedDigit()
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
            } else {
                legend(w)
            }
            chart(w)
            if single && w.style == "graph" && w.size != "small" {
                stats(w.entities[0], hours: w.hours)
            }
        }
        .task(id: "\(w.entities.joined())|\(w.hours)|\(w.style)") {
            for e in w.entities { history.request(e, hours: w.style == "value" ? 24 : w.hours) }
        }
    }

    private func legend(_ w: WidgetConfig) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(w.entities.enumerated()), id: \.offset) { i, e in
                HStack(spacing: 6) {
                    Circle().fill(widgetColors[i % widgetColors.count]).frame(width: 7, height: 7)
                    Text(name(e)).lineLimit(1)
                    Spacer(minLength: 4)
                    Text(value(e)).monospacedDigit()
                }
                .font(.callout)
            }
        }
    }

    @ViewBuilder
    private func chart(_ w: WidgetConfig) -> some View {
        let hours = w.style == "value" ? 24 : w.hours
        let series: [(Int, String, [HistPoint])] = w.entities.enumerated().map { pair in
            (pair.offset, name(pair.element), history.points(pair.element, hours: hours))
        }
        let hasData = series.contains { $0.2.count >= 2 }
        if !hasData {
            if w.style == "graph" {
                Text(model.states.isEmpty ? "En attente de Home Assistant…" : "Pas encore de valeurs numériques.")
                    .font(.caption).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        } else {
            Chart {
                ForEach(series, id: \.0) { s in
                    ForEach(s.2) { p in
                        LineMark(x: .value("Heure", p.date), y: .value("Valeur", p.value),
                                 series: .value("Capteur", s.1))
                            .foregroundStyle(widgetColors[s.0 % widgetColors.count])
                            .interpolationMethod(.monotone)
                            .lineStyle(StrokeStyle(lineWidth: 1.6))
                    }
                    if series.count == 1 {
                        ForEach(s.2) { p in
                            AreaMark(x: .value("Heure", p.date), y: .value("Valeur", p.value))
                                .foregroundStyle(.linearGradient(colors: [Color.accentColor.opacity(0.25), .clear],
                                                                 startPoint: .top, endPoint: .bottom))
                                .interpolationMethod(.monotone)
                        }
                    }
                }
            }
            .chartYScale(domain: .automatic(includesZero: false))
            .chartLegend(.hidden)
            .chartXAxis(w.style == "value" ? .hidden : .automatic)
            .chartYAxis(w.style == "value" ? .hidden : .automatic)
            .frame(maxHeight: .infinity)
        }
    }

    private func stats(_ eid: String, hours: Double) -> some View {
        let vals = history.points(eid, hours: hours).map(\.value)
        let unit = model.states[eid]?.str("unit_of_measurement").map { " " + $0 } ?? ""
        return HStack {
            if let lo = vals.min(), let hi = vals.max(), !vals.isEmpty {
                Text("min " + JSONValue.format((lo * 10).rounded() / 10) + unit)
                Spacer()
                Text("moy. " + JSONValue.format((vals.reduce(0, +) / Double(vals.count) * 10).rounded() / 10) + unit)
                Spacer()
                Text("max " + JSONValue.format((hi * 10).rounded() / 10) + unit)
            }
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
        .monospacedDigit()
    }
}

// MARK: - Onglet des reglages

struct WidgetsTab: View {
    @ObservedObject var model: AppModel
    @ObservedObject var nav: SettingsNav
    @State private var picking = false
    @State private var addingTo: UUID?

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                List(selection: $nav.selectedWidget) {
                    ForEach(model.config.widgets) { w in
                        HStack {
                            Image(systemName: w.style == "value" ? "textformat.123" : "chart.xyaxis.line")
                                .frame(width: 18)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(title(w)).lineLimit(1)
                                Text(w.entities.joined(separator: ", ")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                            }
                            Spacer()
                            if w.hidden { Image(systemName: "eye.slash").foregroundStyle(.secondary) }
                        }
                        .opacity(w.hidden ? 0.5 : 1)
                        .tag(w.id)
                    }
                }
                .frame(minWidth: 250)
                HStack(spacing: 4) {
                    Button { addingTo = nil; picking = true } label: { Image(systemName: "plus") }
                        .help("Nouveau widget")
                    Button {
                        if let id = nav.selectedWidget { model.update { $0.widgets.removeAll { $0.id == id } } }
                        nav.selectedWidget = nil
                    } label: { Image(systemName: "minus") }
                        .disabled(nav.selectedWidget == nil)
                    Spacer()
                }
                Text("Clic droit sur un widget : période, taille, premier plan… Glisse-le pour le déplacer.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .frame(width: 270)
            Group {
                if let id = nav.selectedWidget, let b = binding(id) {
                    WidgetEditor(model: model, widget: b) { addingTo = id; picking = true }
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "chart.xyaxis.line").font(.system(size: 40)).foregroundStyle(.secondary)
                        Text("Des graphiques de tes capteurs, posés sur le bureau.\nUn widget peut suivre plusieurs capteurs.")
                            .multilineTextAlignment(.center)
                            .foregroundStyle(.secondary)
                        Button("Nouveau widget…") { addingTo = nil; picking = true }
                            .disabled(model.states.isEmpty)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .sheet(isPresented: $picking) {
            EntityPicker(model: model, title: addingTo == nil ? "Nouveau widget : choisis un ou plusieurs capteurs"
                                                                : "Ajouter des capteurs au widget",
                         numericOnly: true, already: { eid in
                             guard let id = addingTo else { return false }
                             return model.config.widgets.first(where: { $0.id == id })?.entities.contains(eid) ?? false
                         }) { ids in
                if let id = addingTo {
                    model.update { c in
                        if let i = c.widgets.firstIndex(where: { $0.id == id }) { c.widgets[i].entities += ids }
                    }
                } else if !ids.isEmpty {
                    let w = WidgetConfig(entities: ids)
                    model.update { $0.widgets.append(w) }
                    nav.selectedWidget = w.id
                }
            }
        }
    }

    private func title(_ w: WidgetConfig) -> String {
        w.title.nonEmpty ?? (w.entities.count == 1 ? (model.states[w.entities[0]]?.name ?? w.entities[0]) : "Capteurs")
    }

    private func binding(_ id: UUID) -> Binding<WidgetConfig>? {
        guard let start = model.config.widgets.first(where: { $0.id == id }) else { return nil }
        return Binding(
            get: { model.config.widgets.first(where: { $0.id == id }) ?? start },
            set: { new in
                model.update { c in
                    if let i = c.widgets.firstIndex(where: { $0.id == id }) { c.widgets[i] = new }
                }
            })
    }
}

struct WidgetEditor: View {
    @ObservedObject var model: AppModel
    @Binding var widget: WidgetConfig
    var addEntities: () -> Void

    var body: some View {
        Form {
            Section {
                TextField("Titre", text: optional($widget.title), prompt: Text("automatique"))
                Picker("Affichage", selection: $widget.style) {
                    Text("Graphique").tag("graph")
                    Text("Valeur en grand").tag("value")
                }
                Picker("Période", selection: $widget.hours) {
                    Text("24 heures").tag(24.0)
                    Text("7 jours").tag(168.0)
                    Text("30 jours").tag(720.0)
                }
                .disabled(widget.style == "value")
                Picker("Taille", selection: $widget.size) {
                    Text("Petit").tag("small")
                    Text("Moyen").tag("medium")
                    Text("Grand").tag("large")
                }
                Toggle("Toujours au premier plan (sinon sur le bureau, sous les fenêtres)", isOn: $widget.onTop)
                Toggle("Masqué", isOn: $widget.hidden)
            } header: {
                Text("Widget")
            }
            Section {
                ForEach(widget.entities, id: \.self) { e in
                    HStack {
                        Text(model.states[e]?.name ?? e)
                        Text(e).font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Button {
                            widget.entities.removeAll { $0 == e }
                        } label: { Image(systemName: "minus.circle") }
                            .buttonStyle(.borderless)
                            .disabled(widget.entities.count <= 1)
                    }
                }
                Button("Ajouter des capteurs…", action: addEntities)
            } header: {
                Text("Capteurs")
            } footer: {
                Text("Plusieurs capteurs se partagent le même graphique, chacun avec sa couleur. Idéal pour comparer des températures ou des consommations.")
                    .foregroundStyle(.secondary)
            }
            Section {
                Button("Remettre en haut à droite de l'écran") {
                    widget.x = nil
                    widget.y = nil
                }
            } footer: {
                Text("La position est enregistrée quand tu déplaces le widget. Après une remise à zéro, il réapparaît à sa place par défaut au prochain démarrage.")
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
    }
}
