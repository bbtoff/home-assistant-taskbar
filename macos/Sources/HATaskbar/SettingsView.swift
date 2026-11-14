import ServiceManagement
import SwiftUI
import UniformTypeIdentifiers

enum SettingsTab: Hashable { case connection, items, notifications, general }

/// Navigation de la fenetre de reglages (onglet, element selectionne...).
@MainActor
final class SettingsNav: ObservableObject {
    @Published var tab: SettingsTab = .items
    @Published var selected: UUID?
    @Published var showPicker = false
}

extension AppModel {
    /// Liaison SwiftUI vers un reglage : chaque modification est enregistree.
    func bind<T: Equatable>(_ kp: WritableKeyPath<AppConfig, T>) -> Binding<T> {
        Binding(get: { self.config[keyPath: kp] }, set: { v in self.update { $0[keyPath: kp] = v } })
    }

    func itemBinding(_ id: UUID) -> Binding<ItemConfig>? {
        guard let start = config.items.first(where: { $0.id == id }) else { return nil }
        return Binding(
            get: { self.config.items.first(where: { $0.id == id }) ?? start },
            set: { new in
                self.update { c in
                    if let i = c.items.firstIndex(where: { $0.id == id }) { c.items[i] = new }
                }
            })
    }
}

/// Champ texte pour une valeur facultative ("" = absente).
func optional(_ b: Binding<String?>) -> Binding<String> {
    Binding(get: { b.wrappedValue ?? "" }, set: { b.wrappedValue = $0.isEmpty ? nil : $0 })
}

struct SettingsView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var nav: SettingsNav

    var body: some View {
        TabView(selection: $nav.tab) {
            ItemsTab(model: model, nav: nav)
                .tabItem { Label("Éléments", systemImage: "square.grid.2x2") }
                .tag(SettingsTab.items)
            ConnectionTab(model: model)
                .tabItem { Label("Connexion", systemImage: "network") }
                .tag(SettingsTab.connection)
            NotificationsTab(model: model)
                .tabItem { Label("Notifications", systemImage: "bell") }
                .tag(SettingsTab.notifications)
            GeneralTab(model: model)
                .tabItem { Label("Général", systemImage: "gearshape") }
                .tag(SettingsTab.general)
        }
        .padding(12)
        .frame(minWidth: 760, minHeight: 540)
    }
}

// MARK: - Connexion

struct ConnectionTab: View {
    @ObservedObject var model: AppModel
    @State private var url = ""
    @State private var token = ""
    @State private var verify = true
    @State private var testing = false
    @State private var result: (Bool, String)?

    var body: some View {
        Form {
            Section {
                TextField("Adresse de Home Assistant", text: $url, prompt: Text("http://homeassistant.local:8123"))
                SecureField("Jeton d'accès longue durée", text: $token)
                Toggle("Vérifier le certificat HTTPS", isOn: $verify)
            } header: {
                Text("Home Assistant")
            } footer: {
                Text("Le jeton se crée dans Home Assistant : clique sur ton profil (en bas à gauche) → onglet Sécurité → « Jetons d'accès longue durée » → Créer un jeton. Il est rangé dans le trousseau de macOS, jamais dans un fichier.")
                    .foregroundStyle(.secondary)
            }
            Section {
                HStack {
                    Button("Tester la connexion") { test() }
                        .disabled(testing || url.isEmpty || token.isEmpty)
                    Button("Enregistrer et se connecter") {
                        model.setConnection(url: url, token: token, verifySSL: verify)
                        test()
                    }
                    .keyboardShortcut(.defaultAction)
                    .disabled(url.isEmpty || token.isEmpty)
                    if testing { ProgressView().controlSize(.small) }
                }
                if let r = result {
                    Label(r.1, systemImage: r.0 ? "checkmark.circle.fill" : "xmark.octagon.fill")
                        .foregroundStyle(r.0 ? Color.green : Color.red)
                }
                Text(model.statusLine).foregroundStyle(.secondary)
            }
            Section("Mises à jour des valeurs") {
                Toggle("Temps réel (connexion permanente, moins d'une seconde)", isOn: model.bind(\.realtime))
                Stepper("Sinon, interroger toutes les \(Int(model.config.pollInterval)) s",
                        value: model.bind(\.pollInterval), in: 2...300, step: 1)
            }
        }
        .formStyle(.grouped)
        .onAppear {
            url = model.config.haURL
            token = model.token
            verify = model.config.verifySSL
        }
    }

    private func test() {
        testing = true
        result = nil
        let c = HAClient(url: url, token: token, verifySSL: verify)
        Task { @MainActor in
            do {
                let name = try await c.check()
                result = (true, "Connecté à \(name)")
            } catch {
                result = (false, error.localizedDescription)
            }
            testing = false
        }
    }
}

// MARK: - Elements

struct ItemsTab: View {
    @ObservedObject var model: AppModel
    @ObservedObject var nav: SettingsNav

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                List(selection: $nav.selected) {
                    ForEach(model.config.items) { it in
                        ItemRow(model: model, item: it).tag(it.id)
                    }
                    .onMove { from, to in model.update { $0.items.move(fromOffsets: from, toOffset: to) } }
                }
                .frame(minWidth: 250)
                HStack(spacing: 4) {
                    Button { nav.showPicker = true } label: { Image(systemName: "plus") }
                        .help("Ajouter des entités")
                    Button { remove() } label: { Image(systemName: "minus") }
                        .disabled(nav.selected == nil)
                        .help("Retirer l'élément")
                    Button { move(-1) } label: { Image(systemName: "arrow.up") }
                        .disabled(nav.selected == nil)
                    Button { move(1) } label: { Image(systemName: "arrow.down") }
                        .disabled(nav.selected == nil)
                    Spacer()
                }
                Text("Ordre : de gauche à droite dans la barre des menus. Glisse une ligne pour la déplacer.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .frame(width: 270)
            Group {
                if let id = nav.selected, let b = model.itemBinding(id) {
                    ItemEditor(model: model, item: b)
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "menubar.rectangle").font(.system(size: 40)).foregroundStyle(.secondary)
                        Text(model.config.items.isEmpty
                             ? "Ajoute tes premières entités avec le bouton +."
                             : "Choisis un élément à gauche pour le modifier.")
                            .foregroundStyle(.secondary)
                        Button("Ajouter des entités…") { nav.showPicker = true }
                            .disabled(model.states.isEmpty)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .sheet(isPresented: $nav.showPicker) {
            EntityPicker(model: model) { ids in
                model.addItems(ids)
                if let last = ids.last, let it = model.config.items.first(where: { $0.entityId == last }) {
                    nav.selected = it.id
                }
            }
        }
    }

    private func remove() {
        guard let id = nav.selected else { return }
        model.update { $0.items.removeAll { $0.id == id } }
        nav.selected = nil
    }

    private func move(_ d: Int) {
        guard let id = nav.selected else { return }
        model.update { c in
            guard let i = c.items.firstIndex(where: { $0.id == id }) else { return }
            let j = i + d
            guard j >= 0 && j < c.items.count else { return }
            c.items.swapAt(i, j)
        }
    }
}

struct ItemRow: View {
    @ObservedObject var model: AppModel
    let item: ItemConfig

    var body: some View {
        let st = model.states[item.entityId]
        let d = displayFor(item, states: model.states, offline: false, batteryLow: model.config.batteryLow, timerLeft: nil)
        HStack(spacing: 8) {
            Image(systemName: d.symbol ?? "minus")
                .frame(width: 18)
                .foregroundStyle(d.tone == .on ? Color(nsColor: .haOn) : Color.primary)
            VStack(alignment: .leading, spacing: 1) {
                Text(itemName(item, st)).lineLimit(1)
                Text(item.entityId).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            if item.hidden == true {
                Image(systemName: "eye.slash").foregroundStyle(.secondary).help("Masqué")
            }
            Text(d.text).foregroundStyle(.secondary).lineLimit(1).font(.callout)
        }
        .opacity(item.hidden == true ? 0.5 : 1)
    }
}

struct ItemEditor: View {
    @ObservedObject var model: AppModel
    @Binding var item: ItemConfig

    var body: some View {
        let st = model.states[item.entityId]
        Form {
            Section {
                LabeledContent("Entité", value: item.entityId)
                TextField("Libellé (pour la carte et l'infobulle)", text: optional($item.label),
                          prompt: Text(st?.name ?? ""))
                Picker("Icône", selection: Binding(get: { item.icon ?? "auto" },
                                                   set: { item.icon = $0 == "auto" ? nil : $0 })) {
                    Text("Automatique").tag("auto")
                    Text("Aucune").tag("none")
                    Divider()
                    ForEach(Icons.all, id: \.key) { i in
                        Label(i.name, systemImage: i.symbol).tag(i.key)
                    }
                    Divider()
                    ForEach(Icons.animated, id: \.key) { a in
                        Label(a.name + " ✦", systemImage: Icons.symbol(a.base)).tag(a.key)
                    }
                }
                Toggle("Masqué", isOn: Binding(get: { item.hidden == true }, set: { item.hidden = $0 ? true : nil }))
            } header: {
                Text(itemName(item, st))
            }

            Section("Valeur affichée") {
                Picker("Afficher", selection: Binding(get: { item.attribute ?? "" },
                                                      set: { item.attribute = $0.isEmpty ? nil : $0 })) {
                    Text("L'état de l'entité").tag("")
                    ForEach(attributeKeys(st), id: \.self) { k in
                        Text("Attribut : \(k)").tag(k)
                    }
                }
                TextField("Unité", text: optional($item.unit), prompt: Text(st?.str("unit_of_measurement") ?? "automatique"))
                TextField("Décimales", text: Binding(get: { item.decimals.map(String.init) ?? "" },
                                                    set: { item.decimals = Int($0) }),
                          prompt: Text("telles quelles"))
                Picker("Badge", selection: Binding(get: { item.badge ?? "" },
                                                   set: { item.badge = $0.isEmpty ? nil : $0 })) {
                    Text("Aucun").tag("")
                    Text("Pourcentage").tag("percentage")
                    Text("Batterie").tag("battery")
                    Text("Sens de rotation").tag("direction")
                    if let b = item.badge, !["", "percentage", "battery", "direction"].contains(b) {
                        Text("Attribut : \(b)").tag(b)
                    }
                }
                VStack(alignment: .leading, spacing: 4) {
                    TextField("Couleur selon la valeur", text: optional($item.thresholds),
                              prompt: Text("> 25 orange ; > 30 rouge ; < 15 bleu"))
                    let bad = parseThresholds(item.thresholds).bad
                    if !bad.isEmpty {
                        Text("Non compris : " + bad.joined(separator: " ; ")).font(.caption).foregroundStyle(.red)
                    } else {
                        Text("Couleurs : rouge, orange, jaune, vert, bleu, violet, rose, gris ou #rrggbb.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }

            Section {
                TextField("Action du clic", text: optional($item.service),
                          prompt: Text(defaultService(item.entityId) ?? "aucune (ouvre la carte)"))
                TextField("Groupe : autres entités commandées", text: Binding(
                    get: { (item.group ?? []).joined(separator: ", ") },
                    set: { item.group = $0.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }),
                          prompt: Text("light.cuisine, light.entree"))
                HStack {
                    TextField("Visible de", text: optional($item.showFrom), prompt: Text("22:00"))
                    TextField("à", text: optional($item.showTo), prompt: Text("07:00"))
                }
                TextField("Titre de la carte", text: optional($item.cardTitle), prompt: Text(itemName(item, st)))
            } header: {
                Text("Plus d'options")
            } footer: {
                Text("Action du clic : un service Home Assistant (ex. light.toggle, script.turn_on), ou « none » pour ouvrir la carte. Groupe : le clic allume tout, ou éteint tout si l'une est allumée.")
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
    }

    private func attributeKeys(_ st: EntityState?) -> [String] {
        var keys = (st?.attributes.keys).map(Array.init) ?? []
        keys.removeAll { ["friendly_name", "icon", "entity_picture", "supported_features", "supported_color_modes"].contains($0) }
        if let a = item.attribute, !keys.contains(a) { keys.append(a) }
        return keys.sorted()
    }
}

// MARK: - Choix des entites

struct EntityPicker: View {
    @ObservedObject var model: AppModel
    var add: ([String]) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""
    @State private var domain = ""
    @State private var chosen: Set<String> = []

    private var domains: [String] {
        Array(Set(model.states.keys.map { $0.domain })).sorted()
    }

    private var rows: [EntityState] {
        let q = search.lowercased()
        var out = model.sortedEntities.filter { st in
            (domain.isEmpty || st.domain == domain)
                && (q.isEmpty || st.name.lowercased().contains(q) || st.entityId.contains(q)
                    || (model.areas[st.entityId]?.lowercased().contains(q) ?? false))
        }
        if domain.isEmpty && (q.isEmpty || "piles faibles batteries".contains(q)) {
            out.insert(EntityState(entityId: batteriesId, state: "", attributes: ["friendly_name": "Résumé des piles faibles"]), at: 0)
        }
        return out
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Ajouter des entités").font(.title3.weight(.semibold))
            HStack {
                TextField("Rechercher (nom, pièce, entity_id)", text: $search)
                    .textFieldStyle(.roundedBorder)
                Picker("", selection: $domain) {
                    Text("Tous les types").tag("")
                    ForEach(domains, id: \.self) { Text($0).tag($0) }
                }
                .labelsHidden()
                .frame(width: 180)
            }
            if model.states.isEmpty {
                Text("Aucune entité : vérifie d'abord la connexion à Home Assistant (onglet Connexion).")
                    .foregroundStyle(.secondary)
            }
            List(rows, id: \.entityId) { st in
                let already = model.config.items.contains { $0.entityId == st.entityId }
                HStack {
                    Image(systemName: chosen.contains(st.entityId) || already ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(already ? Color.secondary : Color.accentColor)
                    Image(systemName: Icons.symbol(autoIcon(st.entityId, st))).frame(width: 18)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(st.name)
                        Text(st.entityId).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if let a = model.areas[st.entityId] {
                        Text(a).font(.callout).foregroundStyle(.secondary)
                    }
                    if st.entityId != batteriesId {
                        Text(translate(st.state, domain: st.domain) + (st.str("unit_of_measurement").map { " " + $0 } ?? ""))
                            .font(.callout).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                .contentShape(Rectangle())
                .opacity(already ? 0.5 : 1)
                .onTapGesture {
                    guard !already else { return }
                    if chosen.contains(st.entityId) { chosen.remove(st.entityId) } else { chosen.insert(st.entityId) }
                }
            }
            HStack {
                Text("\(chosen.count) sélectionnée(s)").foregroundStyle(.secondary)
                Spacer()
                Button("Annuler") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button("Ajouter") {
                    let order = rows.map(\.entityId).filter { chosen.contains($0) }
                    add(order)
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(chosen.isEmpty)
            }
        }
        .padding(16)
        .frame(width: 640, height: 520)
    }
}

// MARK: - Notifications

struct NotificationsTab: View {
    @ObservedObject var model: AppModel

    var body: some View {
        Form {
            Section("Général") {
                Toggle("Prévenir quand Home Assistant ne répond plus, puis à son retour", isOn: model.bind(\.notifyOffline))
                Toggle("Notifications de Home Assistant (persistantes et événement ha_taskbar_notify)",
                       isOn: model.bind(\.haNotifications))
                HStack {
                    TextField("Pas de notification de", text: model.bind(\.quietFrom), prompt: Text("22:00"))
                    TextField("à", text: model.bind(\.quietTo), prompt: Text("07:00"))
                }
                if !Notifier.available {
                    Text("Les notifications macOS ne fonctionnent que depuis l'application construite (build.sh), pas depuis Xcode.")
                        .font(.caption).foregroundStyle(.orange)
                }
            }
            Section {
                ForEach(model.config.notifications) { r in
                    HStack {
                        TextField("Entité", text: ruleBinding(r.id, \.entityId), prompt: Text("binary_sensor.porte"))
                        TextField("Quand l'état devient", text: ruleBinding(r.id, \.to), prompt: Text("on (vide = tout)"))
                            .frame(width: 150)
                        TextField("Message", text: ruleBinding(r.id, \.message), prompt: Text("La porte est ouverte"))
                        Button {
                            model.update { $0.notifications.removeAll { $0.id == r.id } }
                        } label: { Image(systemName: "trash") }
                            .buttonStyle(.borderless)
                    }
                    .labelsHidden()
                }
                Button("Ajouter une règle") { model.update { $0.notifications.append(NotifyRule()) } }
            } header: {
                Text("Quand une entité change d'état")
            } footer: {
                Text("Depuis une automatisation : déclenche l'événement « ha_taskbar_notify » avec les données title et message.")
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
    }

    private func ruleBinding(_ id: UUID, _ kp: WritableKeyPath<NotifyRule, String>) -> Binding<String> {
        Binding(get: { model.config.notifications.first { $0.id == id }?[keyPath: kp] ?? "" },
                set: { v in
                    model.update { c in
                        if let i = c.notifications.firstIndex(where: { $0.id == id }) { c.notifications[i][keyPath: kp] = v }
                    }
                })
    }
}

// MARK: - General

struct GeneralTab: View {
    @ObservedObject var model: AppModel
    @State private var loginItem = SMAppService.mainApp.status == .enabled
    @State private var message: String?

    var body: some View {
        Form {
            Section("Barre des menus") {
                Picker("Clic sur un élément", selection: model.bind(\.clickOpensCard)) {
                    Text("Action : allumer, éteindre, lancer…").tag(false)
                    Text("Ouvrir la carte").tag(true)
                }
                Picker("Survol d'un élément", selection: model.bind(\.hoverCardDelay)) {
                    Text("Ne rien ouvrir (infobulle)").tag(0.0)
                    Text("Ouvrir la carte après ½ s").tag(0.5)
                    Text("Ouvrir la carte après 0,8 s").tag(0.8)
                    Text("Ouvrir la carte après 1,2 s").tag(1.2)
                    if ![0.0, 0.5, 0.8, 1.2].contains(model.config.hoverCardDelay) {
                        Text("Ouvrir la carte après \(JSONValue.format(model.config.hoverCardDelay)) s")
                            .tag(model.config.hoverCardDelay)
                    }
                }
                Text(model.config.clickOpensCard
                     ? "⌥-clic fait l'action. Les capteurs ouvrent toujours leur carte."
                     : "Pour la carte : appui long, ⌥-clic ou clic droit → Ouvrir la carte. Les capteurs l'ouvrent d'un simple clic.")
                    .font(.caption).foregroundStyle(.secondary)
                Toggle("Barre compacte : icônes seules (la valeur est dans l'infobulle et la carte)", isOn: model.bind(\.compact))
                Toggle("Icônes animées quand l'élément est actif (macOS 14 et plus)", isOn: model.bind(\.animIcons))
                Toggle("Une valeur qui change clignote un instant", isOn: model.bind(\.flashChanges))
                Toggle("Afficher l'icône HA Taskbar (menu et réglages)", isOn: model.bind(\.showAppIcon))
                Stepper("Piles faibles : sous \(Int(model.config.batteryLow)) %", value: model.bind(\.batteryLow), in: 5...90, step: 5)
            }
            Section("Démarrage") {
                Toggle("Ouvrir HA Taskbar à l'ouverture de session", isOn: Binding(get: { loginItem }, set: { on in
                    do {
                        if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
                        loginItem = SMAppService.mainApp.status == .enabled
                        message = nil
                    } catch {
                        message = "Impossible : \(error.localizedDescription). Place l'application dans le dossier Applications."
                    }
                }))
                .disabled(!Notifier.available)
                if !Notifier.available {
                    Text("Disponible depuis l'application construite (build.sh).").font(.caption).foregroundStyle(.secondary)
                }
            }
            Section("Sauvegarde") {
                HStack {
                    Button("Importer…") { importConfig() }
                    Button("Exporter…") { exportConfig() }
                    Button("Afficher le dossier") { NSWorkspace.shared.activateFileViewerSelecting([ConfigStore.configURL]) }
                }
                Text("L'import accepte aussi le config.json de la version Windows : ses éléments et ses notifications sont repris. L'export ne contient jamais le jeton.")
                    .font(.caption).foregroundStyle(.secondary)
                if let m = message { Text(m).font(.caption) }
            }
            Section("À propos") {
                LabeledContent("Version", value: appVersion)
                Link("Page du projet sur GitHub", destination: URL(string: "https://github.com/\(githubRepo)")!)
            }
        }
        .formStyle(.grouped)
    }

    private func importConfig() {
        let p = NSOpenPanel()
        p.allowedContentTypes = [.json]
        p.message = "Choisis un config.json de HA Taskbar (Mac ou Windows)"
        guard p.runModal() == .OK, let url = p.url else { return }
        do {
            try model.importConfig(from: url)
            message = "Configuration importée (\(model.config.items.count) éléments)."
        } catch {
            message = "Import impossible : \(error.localizedDescription)"
        }
    }

    private func exportConfig() {
        let p = NSSavePanel()
        p.allowedContentTypes = [.json]
        p.nameFieldStringValue = "HATaskbar-config.json"
        guard p.runModal() == .OK, let url = p.url else { return }
        do {
            try model.exportConfig(to: url)
            message = "Configuration exportée (sans le jeton)."
        } catch {
            message = "Export impossible : \(error.localizedDescription)"
        }
    }
}
