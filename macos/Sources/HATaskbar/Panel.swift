import AppKit
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Fenetre du panneau

/// Panneau : un clic sur l'icone Maison de la barre des menus ouvre, juste en dessous, la liste des
/// elements dont la zone est "panel", par piece. Esprit du Centre de controle du Mac.
@MainActor
final class PanelController: NSObject, NSWindowDelegate {
    let model: AppModel
    var openSettings: (_ itemId: UUID?) -> Void = { _ in }
    private var panel: KeyPanel?
    private var anchor: NSView?
    private var monitor: Any?

    static let defaultWidth: CGFloat = 360
    static let minSize = NSSize(width: 300, height: 260)
    static let maxWidth: CGFloat = 1800

    init(model: AppModel) {
        self.model = model
    }

    var isShown: Bool { panel?.isVisible ?? false }

    func toggle(anchor: NSView) {
        if isShown { close() } else { show(anchor: anchor) }
    }

    func show(anchor: NSView) {
        self.anchor = anchor
        let p = panel ?? makePanel()
        panel = p
        p.setFrame(frame(for: anchor), display: true)
        p.alphaValue = CGFloat(model.config.panelOpacity)
        NSApp.activate(ignoringOtherApps: true)
        p.makeKeyAndOrderFront(nil)
        if monitor == nil {
            // Un clic dans une autre application ferme le panneau
            monitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
                Task { @MainActor in self?.close() }
            }
        }
        Demo.log("panel shown=\(p.isVisible) frame=\(Int(p.frame.width))x\(Int(p.frame.height))")
    }

    func close() {
        panel?.orderOut(nil)
        if let m = monitor { NSEvent.removeMonitor(m) }
        monitor = nil
    }

    /// Opacite ou taille changees dans les reglages.
    func sync() {
        guard let p = panel, p.isVisible else { return }
        p.alphaValue = CGFloat(model.config.panelOpacity)
    }

    /// Juste sous l'icone, aligne sur son bord droit, dans l'ecran.
    private func frame(for anchor: NSView) -> NSRect {
        let screen = anchor.window?.screen ?? NSScreen.main
        let vis = screen?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let w = min(vis.width - 16, max(Self.minSize.width, CGFloat(model.config.panelWidth ?? Double(Self.defaultWidth))))
        let defaultH = min(vis.height - 16, 640)
        let h = min(vis.height - 8, max(Self.minSize.height, CGFloat(model.config.panelHeight ?? Double(defaultH))))
        var x = vis.maxX - w - 8
        if let win = anchor.window {
            let r = win.convertToScreen(anchor.convert(anchor.bounds, to: nil))
            x = min(max(vis.minX + 8, r.maxX - w), vis.maxX - w - 8)
        }
        return NSRect(x: x, y: vis.maxY - h - 4, width: w, height: h)
    }

    /// Taille choisie a la souris : enregistree dans la configuration.
    func saveSize(_ size: NSSize) {
        model.update { c in
            c.panelWidth = Double(size.width.rounded())
            c.panelHeight = Double(size.height.rounded())
        }
    }

    /// Double-clic sur un bord : taille par defaut.
    func resetSize() {
        model.update { c in
            c.panelWidth = nil
            c.panelHeight = nil
        }
        if let a = anchor, let p = panel { p.setFrame(frame(for: a), display: true, animate: true) }
    }

    private func makePanel() -> KeyPanel {
        let p = KeyPanel(contentRect: NSRect(x: 0, y: 0, width: Self.defaultWidth, height: 500),
                         styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        p.level = .popUpMenu
        p.hidesOnDeactivate = false
        p.isReleasedWhenClosed = false
        p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        p.delegate = self
        p.onCancel = { [weak self] in self?.close() }

        let effect = NSVisualEffectView()
        effect.material = .popover
        effect.blendingMode = .behindWindow
        effect.state = .active
        effect.maskImage = WidgetPanel.roundedMask(14)
        effect.autoresizingMask = [.width, .height]
        let host = NSHostingView(rootView: PanelView(model: model, panel: self))
        host.autoresizingMask = [.width, .height]
        effect.addSubview(host)
        // Bords a tirer pour agrandir : gauche, droit et bas (le panneau pend sous la barre des menus)
        for edge in [PanelGrip.Edge.left, .right, .bottom] {
            let g = PanelGrip(edge: edge, controller: self)
            effect.addSubview(g)
        }
        p.contentView = effect
        host.frame = effect.bounds
        return p
    }

    func windowDidResignKey(_ notification: Notification) {
        // Clic dans une autre fenetre de l'application (reglages...) : le panneau reste ouvert,
        // sauf si une carte ouverte depuis le panneau n'est pas en cause
    }
}

/// Fenetre sans bordure qui peut recevoir le clavier (recherche) et se ferme avec Echap.
final class KeyPanel: NSPanel {
    var onCancel: (() -> Void)?
    override var canBecomeKey: Bool { true }
    override func cancelOperation(_ sender: Any?) { onCancel?() }
}

/// Bord du panneau a tirer pour l'agrandir ; double-clic = taille par defaut.
final class PanelGrip: NSView {
    enum Edge { case left, right, bottom }
    let edge: Edge
    private weak var controller: PanelController?
    private var start: (mouse: NSPoint, frame: NSRect)?

    init(edge: Edge, controller: PanelController) {
        self.edge = edge
        self.controller = controller
        super.init(frame: .zero)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) non utilise") }

    override func viewDidMoveToSuperview() {
        super.viewDidMoveToSuperview()
        guard let s = superview else { return }
        let t: CGFloat = 6
        switch edge {
        case .left:
            frame = NSRect(x: 0, y: 0, width: t, height: s.bounds.height)
            autoresizingMask = [.height]
        case .right:
            frame = NSRect(x: s.bounds.width - t, y: 0, width: t, height: s.bounds.height)
            autoresizingMask = [.height, .minXMargin]
        case .bottom:
            frame = NSRect(x: 0, y: 0, width: s.bounds.width, height: t)
            autoresizingMask = [.width]
        }
    }

    override func resetCursorRects() {
        addCursorRect(bounds, cursor: edge == .bottom ? .resizeUpDown : .resizeLeftRight)
    }

    override func mouseDown(with e: NSEvent) {
        if e.clickCount == 2 {
            controller?.resetSize()
            return
        }
        guard let w = window else { return }
        start = (NSEvent.mouseLocation, w.frame)
    }

    override func mouseDragged(with e: NSEvent) {
        guard let s = start, let w = window else { return }
        let p = NSEvent.mouseLocation
        let dx = p.x - s.mouse.x, dy = p.y - s.mouse.y
        var f = s.frame
        let minS = PanelController.minSize
        switch edge {
        case .left:
            let width = min(PanelController.maxWidth, max(minS.width, s.frame.width - dx))
            f.origin.x = s.frame.maxX - width
            f.size.width = width
        case .right:
            f.size.width = min(PanelController.maxWidth, max(minS.width, s.frame.width + dx))
        case .bottom:
            let height = max(minS.height, s.frame.height - dy)
            f.origin.y = s.frame.maxY - height
            f.size.height = height
        }
        w.setFrame(f, display: true)
    }

    override func mouseUp(with e: NSEvent) {
        if start != nil, let w = window { controller?.saveSize(w.frame.size) }
        start = nil
    }
}

// MARK: - Contenu

/// Une piece (ou un morceau de piece, quand elle est coupee entre deux colonnes).
struct PanelGroup: Identifiable {
    let id: String
    let title: String
    let items: [ItemConfig]
}

struct PanelView: View {
    @ObservedObject var model: AppModel
    weak var panel: PanelController?

    @State private var search = ""
    @State private var assistBusy = false
    @State private var assistAnswer: (text: String, error: Bool)?
    @State private var showOpacity = false
    @FocusState private var searchFocused: Bool

    static let columnMin: CGFloat = 320

    private var panelItems: [ItemConfig] {
        model.config.items.filter { $0.inPanel && $0.hidden != true }
    }

    private var filtered: [ItemConfig] {
        let words = fold(search).split(separator: " ").map(String.init)
        guard !words.isEmpty else { return panelItems }
        return panelItems.filter { it in
            let hay = fold(itemName(it, model.states[it.entityId]) + " " + it.entityId + " "
                           + (model.areas[it.entityId] ?? ""))
            return words.allSatisfy { hay.contains($0) }
        }
    }

    private var assistQuestion: String? {
        let q = search.trimmingCharacters(in: .whitespaces)
        return q.split(separator: " ").count >= 2 ? q : nil
    }

    /// Elements regroupes par piece, dans l'ordre de la liste ; « Autres » en dernier.
    private func groups(_ items: [ItemConfig]) -> [PanelGroup] {
        guard model.config.panelByArea else { return [PanelGroup(id: "", title: "", items: items)] }
        var order: [String] = []
        var byArea: [String: [ItemConfig]] = [:]
        for it in items {
            let a = model.areas[it.entityId] ?? ""
            if byArea[a] == nil { order.append(a) }
            byArea[a, default: []].append(it)
        }
        order = order.filter { !$0.isEmpty } + order.filter { $0.isEmpty }      // « Autres » en dernier
        return order.map { PanelGroup(id: $0, title: $0.isEmpty ? "Autres" : $0, items: byArea[$0] ?? []) }
    }

    /// Hauteur approximative d'une ligne (pour equilibrer les colonnes).
    private func rowHeight(_ it: ItemConfig) -> CGFloat {
        var h: CGFloat = 50
        if PanelRow.sliderDomains.contains(it.domain) { h += 26 }
        if it.domain == "camera" || it.domain == "image" || it.camera != nil { h += 150 }
        return h
    }

    /// Repartit les pieces en colonnes de hauteur voisine ; une piece peut etre coupee.
    private func columns(width: CGFloat) -> [[PanelGroup]] {
        let gs = groups(filtered)
        let n = max(1, Int((width - 20) / Self.columnMin))
        guard n > 1 else { return [gs] }
        let total = gs.reduce(CGFloat(0)) { $0 + 30 + $1.items.reduce(0) { $0 + rowHeight($1) } }
        let target = total / CGFloat(n)
        var cols: [[PanelGroup]] = [[]]
        var height: CGFloat = 0
        for g in gs {
            var chunk: [ItemConfig] = []
            var part = 0
            height += 30
            for it in g.items {
                let rh = rowHeight(it)
                if height + rh > target * 1.05 && height > 30 && cols.count < n && !(chunk.isEmpty && cols.last!.isEmpty) {
                    if !chunk.isEmpty {
                        cols[cols.count - 1].append(PanelGroup(id: "\(g.id)#\(part)", title: g.title, items: chunk))
                        part += 1
                        chunk = []
                    }
                    cols.append([])
                    height = 30
                }
                chunk.append(it)
                height += rh
            }
            if !chunk.isEmpty {
                cols[cols.count - 1].append(PanelGroup(id: "\(g.id)#\(part)", title: g.title, items: chunk))
            }
        }
        return cols
    }

    private var onCount: Int {
        panelItems.filter { it in
            guard let st = model.states[it.entityId] else { return false }
            return activeStates.contains(st.state) && !["sensor", "binary_sensor", "person", "device_tracker"].contains(st.domain)
        }.count
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            searchField
            Divider().padding(.top, 8)
            GeometryReader { geo in
                ScrollView {
                    let cols = columns(width: geo.size.width)
                    if panelItems.isEmpty {
                        emptyState
                    } else if filtered.isEmpty {
                        Text(assistQuestion != nil ? "Aucun élément : demande plutôt à Assist (Entrée)."
                                                   : "Aucun élément ne correspond.")
                            .foregroundStyle(.secondary)
                            .padding(30)
                    } else {
                        HStack(alignment: .top, spacing: 10) {
                            ForEach(Array(cols.enumerated()), id: \.offset) { _, col in
                                VStack(spacing: 10) {
                                    ForEach(col) { g in
                                        PanelGroupView(model: model, group: g, panel: panel)
                                    }
                                }
                                .frame(maxWidth: .infinity, alignment: .top)
                            }
                        }
                        .padding(10)
                    }
                }
            }
            Divider()
            footer
        }
        .onAppear {
            searchFocused = true
            if let s = Demo.arg("--demo-search"), !s.isEmpty {
                search = s.replacingOccurrences(of: "_", with: " ")
                if Demo.arg("--demo-ask") != nil, let q = assistQuestion { ask(q) }
            }
        }
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(model.config.panelTitle.isEmpty ? "Maison" : model.config.panelTitle)
                    .font(.title3.weight(.semibold))
                HStack(spacing: 5) {
                    Circle()
                        .fill(model.offline ? Color.red : (model.realtimeConnected ? Color.green : Color.orange))
                        .frame(width: 7, height: 7)
                    Text(model.offline ? "Hors ligne" : (model.realtimeConnected ? "En direct" : "Connecté"))
                    if onCount > 0 {
                        Text("· \(onCount) allumé\(onCount > 1 ? "s" : "")")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            Spacer()
            Button { showOpacity.toggle() } label: { Image(systemName: "circle.lefthalf.filled") }
                .buttonStyle(.borderless)
                .help("Opacité du panneau")
                .popover(isPresented: $showOpacity, arrowEdge: .bottom) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Opacité : \(Int((model.config.panelOpacity * 100).rounded())) %").font(.callout)
                        Slider(value: Binding(get: { model.config.panelOpacity },
                                              set: { v in model.update { $0.panelOpacity = v } }), in: 0.5...1)
                            .frame(width: 180)
                    }
                    .padding(12)
                }
            Button { panel?.openSettings(nil) } label: { Image(systemName: "gearshape") }
                .buttonStyle(.borderless)
                .help("Réglages")
        }
        .font(.title3)
        .padding(.horizontal, 14)
        .padding(.top, 12)
    }

    private var searchField: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Rechercher, ou demander à Assist", text: $search)
                    .textFieldStyle(.plain)
                    .focused($searchFocused)
                    .onSubmit { if let q = assistQuestion { ask(q) } }
                if !search.isEmpty {
                    Button { search = ""; assistAnswer = nil } label: { Image(systemName: "xmark.circle.fill") }
                        .buttonStyle(.borderless)
                        .foregroundStyle(.secondary)
                }
                // ⌘↩ : envoyer a Assist meme une phrase d'un seul mot
                Button("") { let q = search.trimmingCharacters(in: .whitespaces); if !q.isEmpty { ask(q) } }
                    .keyboardShortcut(.return, modifiers: .command)
                    .frame(width: 0, height: 0)
                    .opacity(0)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 9).fill(Color.primary.opacity(0.06)))
            if let q = assistQuestion, assistAnswer == nil {
                Button { ask(q) } label: {
                    HStack {
                        Image(systemName: assistBusy ? "ellipsis.bubble" : "bubble.left.and.text.bubble.right")
                        Text("Demander à Assist : « \(q) »").lineLimit(1)
                        Spacer()
                        Text("↩").foregroundStyle(.secondary)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(assistBusy)
                .padding(.horizontal, 4)
            }
            if let a = assistAnswer {
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: a.error ? "exclamationmark.bubble" : "bubble.left.fill")
                        .foregroundStyle(a.error ? Color.orange : Color.accentColor)
                    Text(a.text).fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    Button { assistAnswer = nil } label: { Image(systemName: "xmark") }
                        .buttonStyle(.borderless)
                }
                .font(.callout)
                .padding(8)
                .background(RoundedRectangle(cornerRadius: 9).fill(Color.accentColor.opacity(0.10)))
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 10)
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "square.grid.2x2").font(.system(size: 34)).foregroundStyle(.secondary)
            Text("Le panneau est vide.").font(.headline)
            Text("Dans Réglages → Éléments, choisis « Panneau » comme emplacement, ou clic droit sur un élément de la barre → Mettre dans le panneau.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            Button("Ouvrir les réglages") { panel?.openSettings(nil) }
        }
        .padding(30)
        .frame(maxWidth: .infinity)
    }

    private var footer: some View {
        HStack {
            Button("Réglages") { panel?.openSettings(nil) }
            Spacer()
            Button("Ouvrir dans Home Assistant ↗") {
                if let u = URL(string: model.config.haURL) { NSWorkspace.shared.open(u) }
            }
        }
        .buttonStyle(.link)
        .font(.callout)
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
    }

    private func ask(_ q: String) {
        guard !assistBusy else { return }
        assistBusy = true
        Task { @MainActor in
            let r = await model.askAssist(q)
            assistAnswer = r
            assistBusy = false
            Demo.log("assist \(r.error ? "erreur" : "ok") \(r.text)")
        }
    }
}

/// Carte arrondie d'une piece : titre (a glisser pour deplacer toute la piece) puis les lignes.
struct PanelGroupView: View {
    @ObservedObject var model: AppModel
    let group: PanelGroup
    weak var panel: PanelController?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !group.title.isEmpty {
                Text(group.title.uppercased())
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 12)
                    .padding(.top, 9)
                    .padding(.bottom, 2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                    .onDrag { NSItemProvider(object: ("area:" + areaKey) as NSString) }
                    .help("Glisse le titre pour déplacer toute la pièce")
            }
            ForEach(Array(group.items.enumerated()), id: \.element.id) { i, it in
                if i > 0 { Divider().padding(.leading, 52) }
                PanelRow(model: model, item: it, panel: panel)
                    .onDrag { NSItemProvider(object: ("item:" + it.id.uuidString) as NSString) }
                    .onDrop(of: [UTType.text], isTargeted: nil) { providers in
                        drop(providers, before: it)
                    }
            }
        }
        .padding(.bottom, 4)
        .background(RoundedRectangle(cornerRadius: 14).fill(Color.primary.opacity(0.055)))
    }

    /// Cle de la piece (nom HA, vide pour « Autres »).
    private var areaKey: String { group.title == "Autres" ? "" : group.title }

    private func drop(_ providers: [NSItemProvider], before target: ItemConfig) -> Bool {
        guard let p = providers.first else { return false }
        _ = p.loadObject(ofClass: NSString.self) { obj, _ in
            guard let s = obj as? String else { return }
            Task { @MainActor in
                if s.hasPrefix("item:"), let id = UUID(uuidString: String(s.dropFirst(5))) {
                    model.moveItem(id, before: target.id)
                } else if s.hasPrefix("area:") {
                    model.moveArea(String(s.dropFirst(5)), before: target.id)
                }
            }
        }
        return true
    }
}

/// Une ligne du panneau : pastille, nom, phrase d'etat, valeur ou commande ; curseur ou camera dessous.
struct PanelRow: View {
    @ObservedObject var model: AppModel
    let item: ItemConfig
    weak var panel: PanelController?
    @State private var showCard = false

    static let toggleDomains: Set<String> = ["light", "switch", "input_boolean", "fan", "automation", "siren", "humidifier"]
    static let sliderDomains: Set<String> = ["light", "fan", "cover", "media_player"]

    private var st: EntityState? { model.states[item.entityId] }
    private var cameraId: String? {
        if item.domain == "camera" || item.domain == "image" { return item.entityId }
        return item.camera
    }

    var body: some View {
        let d = displayFor(item, states: model.states, offline: model.offline, batteryLow: model.config.batteryLow,
                           timerLeft: model.timerLeft(item.entityId))
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 10) {
                HStack(spacing: 10) {
                    PanelBadge(model: model, item: item, display: d)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(itemName(item, st)).lineLimit(1)
                        Text(statePhrase(item, states: model.states, batteryLow: model.config.batteryLow))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 4)
                }
                .contentShape(Rectangle())
                .onLongPressGesture(minimumDuration: 0.45) { showCard = true }
                .onTapGesture {
                    Demo.log("panel click \(item.entityId)")
                    if !model.click(item) { showCard = true }
                }
                trailing(d)
            }
            if let st = st, let s = slider(st) {
                PanelSlider(value: s.value, range: s.range, commit: s.commit)
                    .padding(.leading, 40)
            }
            if let cam = cameraId {
                CameraImageView(model: model, entityId: cam, interval: 3)
                    .frame(maxWidth: .infinity)
                    .frame(height: 140)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .onTapGesture { showCard = true }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .popover(isPresented: $showCard, arrowEdge: .leading) {
            CardView(model: model, itemId: item.id, edit: {
                showCard = false
                panel?.openSettings(item.id)
            })
        }
        .contextMenu {
            Button("Ouvrir la carte") { showCard = true }
            Button("Modifier l'élément…") { panel?.openSettings(item.id) }
            Button("Mettre dans la barre des menus") {
                model.update { c in
                    if let i = c.items.firstIndex(where: { $0.id == item.id }) { c.items[i].zone = nil }
                }
            }
            Divider()
            Button("Taille par défaut du panneau") { panel?.resetSize() }
        }
    }

    @ViewBuilder
    private func trailing(_ d: ItemDisplay) -> some View {
        if let st = st, Self.toggleDomains.contains(item.domain), !st.isUnavailable, !item.isGroup {
            Toggle("", isOn: Binding(get: { st.state == "on" }, set: { on in
                model.call("homeassistant.turn_\(on ? "on" : "off")", entity: item.entityId)
            }))
            .toggleStyle(.switch)
            .controlSize(.small)
            .labelsHidden()
        } else if let st = st, ["climate", "water_heater"].contains(item.domain), st.num("temperature") != nil {
            HStack(spacing: 6) {
                Button { _ = model.wheel(item, -1) } label: { Image(systemName: "minus") }
                Text(JSONValue.format(st.num("temperature") ?? 0) + "°").monospacedDigit().frame(minWidth: 34)
                Button { _ = model.wheel(item, 1) } label: { Image(systemName: "plus") }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        } else {
            Text(d.text).monospacedDigit().foregroundStyle(.secondary).lineLimit(1)
        }
    }

    private func slider(_ st: EntityState) -> (value: Double, range: ClosedRange<Double>, commit: (Double) -> Void)? {
        let eid = item.entityId
        switch item.domain {
        case "light":
            let modes = Set(st.attributes["supported_color_modes"]?.stringArray ?? [])
            guard st.num("brightness") != nil || !modes.subtracting(["onoff"]).isEmpty else { return nil }
            let v = st.state == "on" ? ((st.num("brightness") ?? 0) * 100 / 255).rounded() : 0
            return (v, 0...100, { v in
                if v <= 0 { model.call("light.turn_off", entity: eid) }
                else { model.call("light.turn_on", entity: eid, ["brightness_pct": .number(v.rounded())]) }
            })
        case "fan":
            guard st.attributes["percentage"] != nil else { return nil }
            return (st.state == "on" ? st.num("percentage") ?? 0 : 0, 0...100, { v in
                if v <= 0 { model.call("fan.turn_off", entity: eid) }
                else { model.call("fan.set_percentage", entity: eid, ["percentage": .number(v.rounded())]) }
            })
        case "cover":
            guard let p = st.num("current_position") else { return nil }
            return (p, 0...100, { v in model.call("cover.set_cover_position", entity: eid, ["position": .number(v.rounded())]) })
        case "media_player":
            guard let vol = st.num("volume_level") else { return nil }
            return ((vol * 100).rounded(), 0...100, { v in
                model.call("media_player.volume_set", entity: eid, ["volume_level": .number((v).rounded() / 100)])
            })
        default:
            return nil
        }
    }
}

/// Pastille ronde : icone (coloree si allume) ou photo de l'entite.
struct PanelBadge: View {
    @ObservedObject var model: AppModel
    let item: ItemConfig
    let display: ItemDisplay

    var body: some View {
        ZStack {
            Circle().fill(display.tone == .on ? Color(nsColor: .haOn).opacity(0.22) : Color.primary.opacity(0.08))
            Image(systemName: display.symbol ?? "circle")
                .font(.system(size: 14))
                .foregroundStyle(display.tone == .on ? Color(nsColor: .haOn) : Color.primary.opacity(0.75))
        }
        .frame(width: 30, height: 30)
    }
}

/// Curseur fin, sans titre, qui n'envoie la valeur qu'au relachement.
struct PanelSlider: View {
    let value: Double
    let range: ClosedRange<Double>
    let commit: (Double) -> Void
    @State private var local: Double = 0
    @State private var editing = false

    var body: some View {
        Slider(value: $local, in: range, onEditingChanged: { e in
            editing = e
            if !e { commit(local) }
        })
        .controlSize(.small)
        .onAppear { local = value }
        .onChange(of: value) { v in if !editing { local = v } }
    }
}

/// Image d'une camera (camera.*) ou d'une entite image.*, rafraichie toutes les `interval` secondes.
struct CameraImageView: View {
    @ObservedObject var model: AppModel
    let entityId: String
    let interval: Double
    @State private var image: NSImage?
    @State private var failed = false

    var body: some View {
        ZStack {
            Rectangle().fill(Color.black.opacity(0.85))
            if let img = image {
                Image(nsImage: img).resizable().aspectRatio(contentMode: .fill)
            } else {
                VStack(spacing: 4) {
                    Image(systemName: failed ? "video.slash" : "video")
                    Text(failed ? "Image indisponible" : "Chargement…").font(.caption)
                }
                .foregroundStyle(.white.opacity(0.7))
            }
        }
        .task(id: entityId) {
            while !Task.isCancelled {
                if let img = await model.cameraImage(entityId) {
                    image = img
                    failed = false
                } else {
                    failed = image == nil
                }
                try? await Task.sleep(nanoseconds: UInt64(interval * 1_000_000_000))
            }
        }
    }
}

// MARK: - Modele : ordre, Assist, images

extension AppModel {
    /// Glisser un element du panneau avant un autre (nouvel ordre enregistre dans items).
    func moveItem(_ id: UUID, before target: UUID) {
        guard id != target else { return }
        update { c in
            guard let i = c.items.firstIndex(where: { $0.id == id }) else { return }
            let it = c.items.remove(at: i)
            let j = c.items.firstIndex(where: { $0.id == target }) ?? c.items.count
            c.items.insert(it, at: j)
        }
    }

    /// Glisser le titre d'une piece : toutes ses lignes du panneau passent avant l'element vise.
    func moveArea(_ area: String, before target: UUID) {
        update { c in
            let inArea: (ItemConfig) -> Bool = { $0.inPanel && (self.areas[$0.entityId] ?? "") == area }
            guard let tIdx = c.items.firstIndex(where: { $0.id == target }), !inArea(c.items[tIdx]) else { return }
            let moving = c.items.filter(inArea)
            var rest = c.items.filter { !inArea($0) }
            let j = rest.firstIndex(where: { $0.id == target }) ?? rest.count
            rest.insert(contentsOf: moving, at: j)
            c.items = rest
        }
    }

    /// Question a Assist ; garde la conversation pour la question suivante.
    func askAssist(_ text: String) async -> (text: String, error: Bool) {
        if Demo.enabled {
            return ("C'est fait : j'ai allumé la lumière du salon. (réponse de démonstration)", false)
        }
        guard let c = client else { return ("Home Assistant n'est pas configuré.", true) }
        do {
            let r = try await c.converse(text, conversationId: assistConversation)
            assistConversation = r.id
            return (r.speech.isEmpty ? "(pas de réponse)" : r.speech, r.error)
        } catch {
            return ("Assist ne répond pas : \(error.localizedDescription)", true)
        }
    }

    /// Image actuelle d'une camera (ou image de demonstration).
    func cameraImage(_ entityId: String) async -> NSImage? {
        if Demo.enabled { return Demo.cameraImage(entityId) }
        guard let c = client, let data = try? await c.cameraImage(entityId) else { return nil }
        return NSImage(data: data)
    }
}
