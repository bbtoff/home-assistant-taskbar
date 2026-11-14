import AppKit
import UserNotifications

/// Etat de l'application : configuration, etats Home Assistant, connexion, actions.
@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var config: AppConfig
    @Published private(set) var token: String
    @Published private(set) var states: [String: EntityState] = [:]
    @Published private(set) var offline = false
    @Published private(set) var realtimeConnected = false
    @Published private(set) var lastError: String?
    @Published private(set) var lastOK: Date?
    @Published private(set) var timers: [String: Date] = [:]      // arret programme (entite -> heure)
    @Published var areas: [String: String] = [:]

    /// Appele apres chaque changement d'etat ou de configuration (barre des menus).
    var onStatesChanged: (() -> Void)?
    var onConfigChanged: (() -> Void)?

    private(set) var client: HAClient?
    private var realtime: Realtime?
    private var pollTask: Task<Void, Never>?
    private var timerTask: Task<Void, Never>?
    private var pending: [String: (value: Double, task: Task<Void, Never>)] = [:]
    private var pausedUntil: Date?
    private var everConnected = false

    init() {
        var cfg = ConfigStore.load()
        var tok = TokenStore.load()
        // Ancienne config (ou import Windows) avec le jeton dans le fichier : il passe dans le trousseau
        if let data = try? Data(contentsOf: ConfigStore.configURL),
           let decoded = try? ConfigStore.decode(data), let t = decoded.token {
            if tok.isEmpty {
                tok = t
                TokenStore.save(t)
            }
            cfg = decoded.config
            ConfigStore.save(cfg)         // reecrit le fichier sans le jeton
        }
        config = cfg
        token = tok
    }

    var needsSetup: Bool { token.isEmpty }

    // MARK: demarrage / connexion

    func start() {
        stop()
        guard !token.isEmpty else { return }
        let c = HAClient(url: config.haURL, token: token, verifySSL: config.verifySSL)
        client = c
        if config.realtime {
            let rt = Realtime(client: c, notifications: config.haNotifications)
            rt.onState = { [weak self] eid, st in self?.applyState(eid, st) }
            rt.onNotify = { [weak self] title, msg in self?.notify(title, msg) }
            rt.onStatus = { [weak self] ok, detail in self?.realtimeStatus(ok, detail) }
            realtime = rt
            rt.start()
        }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self = self else { return }
                await self.poll()
                // En temps reel, une resynchronisation de temps en temps suffit
                let every = self.realtimeConnected ? 300 : max(2, self.config.pollInterval)
                try? await Task.sleep(nanoseconds: UInt64(every * 1_000_000_000))
            }
        }
        timerTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 15_000_000_000)
                self?.checkTimers()
            }
        }
        Task { [weak self] in
            guard let c = self?.client else { return }
            if let a = try? await c.areas() { self?.areas = a }
        }
    }

    func stop() {
        pollTask?.cancel()
        pollTask = nil
        timerTask?.cancel()
        timerTask = nil
        realtime?.stop()
        realtime = nil
        realtimeConnected = false
        client = nil
    }

    func refreshNow() {
        Task { await poll() }
    }

    private func poll() async {
        guard let c = client else { return }
        do {
            let new = try await c.states()
            guard c === client else { return }
            let old = states
            states = new
            lastOK = Date()
            lastError = nil
            setOffline(false)
            if !old.isEmpty {
                for (eid, st) in new where old[eid]?.state != st.state {
                    checkRules(eid, old: old[eid], new: st)
                }
            }
            onStatesChanged?()
        } catch {
            guard c === client else { return }
            lastError = error.localizedDescription
            setOffline(true)
            onStatesChanged?()
        }
    }

    private func applyState(_ eid: String, _ st: EntityState?) {
        let old = states[eid]
        if let st = st { states[eid] = st } else { states.removeValue(forKey: eid) }
        lastOK = Date()
        if let st = st, old?.state != st.state { checkRules(eid, old: old, new: st) }
        onStatesChanged?()
    }

    private func realtimeStatus(_ ok: Bool, _ detail: String) {
        realtimeConnected = ok
        if ok {
            setOffline(false)
            refreshNow()              // resynchronise tout apres une (re)connexion
        } else if !detail.isEmpty {
            lastError = detail
        }
    }

    private func setOffline(_ off: Bool) {
        if off == offline {
            if !off { everConnected = true }
            return
        }
        offline = off
        if config.notifyOffline && everConnected {
            if off {
                notify("Home Assistant hors ligne", lastError ?? "Home Assistant ne répond plus.", force: true)
            } else {
                notify("Home Assistant est de retour", "La connexion est rétablie.", force: true)
            }
        }
        if !off { everConnected = true }
    }

    // MARK: configuration

    func update(_ change: (inout AppConfig) -> Void) {
        var c = config
        change(&c)
        guard c != config else { return }
        let reconnect = c.haURL != config.haURL || c.verifySSL != config.verifySSL || c.realtime != config.realtime
            || c.haNotifications != config.haNotifications
        config = c
        ConfigStore.save(c)
        onConfigChanged?()
        if reconnect { start() }
    }

    func setConnection(url: String, token newToken: String, verifySSL: Bool) {
        token = newToken
        TokenStore.save(newToken)
        var c = config
        c.haURL = url
        c.verifySSL = verifySSL
        config = c
        ConfigStore.save(c)
        states = [:]
        everConnected = false
        onConfigChanged?()
        start()
    }

    /// Importe un config.json (macOS ou Windows). Le jeton eventuel passe dans le trousseau.
    func importConfig(from url: URL) throws {
        let data = try Data(contentsOf: url)
        let (cfg, tok) = try ConfigStore.decode(data)
        config = cfg
        ConfigStore.save(cfg)
        if let t = tok {
            token = t
            TokenStore.save(t)
        }
        onConfigChanged?()
        start()
    }

    /// Exporte la configuration, sans le jeton.
    func exportConfig(to url: URL) throws {
        try ConfigStore.encode(config).write(to: url, options: .atomic)
    }

    func addItems(_ ids: [String]) {
        update { c in
            for id in ids where !c.items.contains(where: { $0.entityId == id }) {
                c.items.append(ItemConfig(entityId: id))
            }
        }
    }

    // MARK: actions

    func call(_ service: String, _ data: [String: JSONValue]) {
        guard let c = client else { return }
        Task {
            do {
                try await c.callService(service, data: data)
                if !self.realtimeConnected {
                    try? await Task.sleep(nanoseconds: 400_000_000)
                    await self.poll()
                }
            } catch {
                self.lastError = error.localizedDescription
                self.notify("Action impossible", "\(service) : \(error.localizedDescription)", force: true)
            }
        }
    }

    func call(_ service: String, entity: String, _ extra: [String: JSONValue] = [:]) {
        var d = extra
        d["entity_id"] = .string(entity)
        call(service, d)
    }

    /// Action du clic. false si l'element n'a pas d'action (la carte s'ouvre alors).
    @discardableResult
    func click(_ item: ItemConfig) -> Bool {
        let members = item.members
        if members.count > 1 && item.service.nonEmpty == nil && item.data == nil {
            let on = members.contains { activeStates.contains(states[$0]?.state ?? "") }
            call("homeassistant.turn_\(on ? "off" : "on")", ["entity_id": .array(members.map { .string($0) })])
            return true
        }
        guard let svc = resolveService(item) else { return false }
        let target: JSONValue = members.count > 1 ? .array(members.map { .string($0) }) : .string(item.entityId)
        call(svc, item.data ?? ["entity_id": target])
        return true
    }

    /// Molette / glissement sur un element : luminosite, vitesse, volume, position, consigne, valeur.
    /// Renvoie le texte a afficher tout de suite ; la commande part a la fin du geste.
    func wheel(_ item: ItemConfig, _ d: Int) -> String? {
        let eid = item.entityId, dom = item.domain
        guard let st = states[eid], !st.isUnavailable else { return nil }
        let pend = pending[eid]?.value
        let on = st.state == "on"
        let v: Double, text: String
        let send: (Double) -> Void

        switch dom {
        case "light":
            let modes = Set(st.attributes["supported_color_modes"]?.stringArray ?? [])
            if st.num("brightness") == nil && modes.subtracting(["onoff"]).isEmpty { return nil }
            if pend == nil && !on && d < 0 { return nil }
            let base = pend ?? (on ? (st.num("brightness") ?? 0) * 100 / 255 : 0)
            v = max(0, min(100, (base / 5).rounded() * 5 + Double(10 * d)))
            text = v > 0 ? "\(Int(v))%" : "OFF"
            send = { [weak self] v in
                if v <= 0 { self?.call("light.turn_off", entity: eid) }
                else { self?.call("light.turn_on", entity: eid, ["brightness_pct": .number(v)]) }
            }
        case "fan":
            guard st.attributes["percentage"] != nil else { return nil }
            if pend == nil && !on && d < 0 { return nil }
            var step = st.num("percentage_step") ?? 10
            if step < 5 { step = 10 }
            let base = pend ?? (on ? st.num("percentage") ?? 0 : 0)
            v = max(0, min(100, ((base + step * Double(d)) / step).rounded() * step))
            text = v > 0 ? "\(Int(v.rounded()))%" : "OFF"
            send = { [weak self] v in
                if v <= 0 { self?.call("fan.turn_off", entity: eid) }
                else { self?.call("fan.set_percentage", entity: eid, ["percentage": .number(v.rounded())]) }
            }
        case "media_player":
            guard let vol = st.num("volume_level") else { return nil }
            let base = pend ?? vol * 100
            v = max(0, min(100, (base / 5).rounded() * 5 + Double(5 * d)))
            text = "\(Int(v))%"
            send = { [weak self] v in
                self?.call("media_player.volume_set", entity: eid, ["volume_level": .number((v / 100 * 100).rounded() / 100)])
            }
        case "cover":
            guard let pos = st.num("current_position") else { return nil }
            let base = pend ?? pos
            v = max(0, min(100, (base / 10).rounded() * 10 + Double(10 * d)))
            text = "\(Int(v))%"
            send = { [weak self] v in self?.call("cover.set_cover_position", entity: eid, ["position": .number(v)]) }
        case "climate", "water_heater":
            guard let t = st.num("temperature") else { return nil }
            let step = st.num("target_temp_step") ?? 0.5
            let lo = st.num("min_temp") ?? 5, hi = st.num("max_temp") ?? 35
            let base = pend ?? t
            v = max(lo, min(hi, ((base + step * Double(d)) / step).rounded() * step))
            text = "→ \(JSONValue.format(v))°"
            send = { [weak self] v in self?.call("\(dom).set_temperature", entity: eid, ["temperature": .number(v)]) }
        case "input_number", "number":
            let step = st.num("step") ?? 1
            let lo = st.num("min") ?? 0, hi = st.num("max") ?? 100
            let base = pend ?? Double(st.state) ?? lo
            v = max(lo, min(hi, ((base + step * Double(d)) / step).rounded() * step))
            text = JSONValue.format(v)
            send = { [weak self] v in self?.call("\(dom).set_value", entity: eid, ["value": .number(v)]) }
        default:
            return nil
        }
        pending[eid]?.task.cancel()
        let task = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 600_000_000)
            guard !Task.isCancelled, let self = self, let p = self.pending.removeValue(forKey: eid) else { return }
            send(p.value)
        }
        pending[eid] = (v, task)
        return text
    }

    // MARK: arret programme

    func startTimer(_ eid: String, minutes: Int) {
        timers[eid] = Date().addingTimeInterval(Double(minutes) * 60)
        onStatesChanged?()
    }

    func cancelTimer(_ eid: String) {
        timers.removeValue(forKey: eid)
        onStatesChanged?()
    }

    func timerLeft(_ eid: String) -> TimeInterval? {
        timers[eid].map { max(0, $0.timeIntervalSinceNow) }
    }

    private func checkTimers() {
        let now = Date()
        for (eid, end) in timers where end <= now {
            timers.removeValue(forKey: eid)
            let dom = eid.domain
            let svc = dom == "media_player" ? "media_player.turn_off"
                : dom == "climate" ? "climate.turn_off" : "homeassistant.turn_off"
            call(svc, entity: eid)
            notify("Arrêt programmé", "\(states[eid]?.name ?? eid) a été éteint.")
        }
        onStatesChanged?()
    }

    // MARK: notifications

    var notificationsPaused: Bool {
        if let p = pausedUntil, p > Date() { return true }
        return false
    }

    func pauseNotifications(until: Date?) {
        pausedUntil = until
    }

    private func checkRules(_ eid: String, old: EntityState?, new: EntityState) {
        guard old != nil else { return }
        for r in config.notifications where r.entityId == eid {
            if !r.to.isEmpty && r.to != new.state { continue }
            let name = new.name
            let msg = r.message.isEmpty ? "\(name) : \(translate(new.state, domain: new.domain))" : r.message
            notify(name, msg)
        }
    }

    func notify(_ title: String, _ body: String, force: Bool = false) {
        if !force {
            if notificationsPaused { return }
            if inRange(config.quietFrom, config.quietTo, empty: false) { return }
        }
        Notifier.send(title: title, body: body)
    }

    // MARK: divers

    /// Entites connues, triees par nom.
    var sortedEntities: [EntityState] {
        states.values.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    var statusLine: String {
        if token.isEmpty { return "Pas encore configuré" }
        if offline { return "● Hors ligne — \(lastError ?? "Home Assistant ne répond pas")" }
        if realtimeConnected { return "● Connecté (temps réel)" }
        if lastOK != nil { return "● Connecté" }
        return "Connexion…"
    }
}

/// Notifications macOS (Centre de notifications). Uniquement depuis l'application (.app).
enum Notifier {
    static var available: Bool { Bundle.main.bundleURL.pathExtension == "app" }

    static func requestAuthorization() {
        guard available else { return }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    static func send(title: String, body: String) {
        guard available else {
            NSLog("HA Taskbar : \(title) — \(body)")
            return
        }
        let c = UNMutableNotificationContent()
        c.title = title
        c.body = body
        let req = UNNotificationRequest(identifier: UUID().uuidString, content: c, trigger: nil)
        UNUserNotificationCenter.current().add(req)
    }
}
