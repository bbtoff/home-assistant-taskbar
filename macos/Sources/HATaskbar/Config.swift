import Foundation

/// Un element affiche dans la barre des menus. Les cles JSON sont celles de la version Windows :
/// un config.json de Windows peut etre importe tel quel.
struct ItemConfig: Codable, Identifiable, Equatable {
    var id = UUID()
    var entityId: String
    var label: String?
    var icon: String?            // cle d'icone ("auto", "none", "lightbulb"...)
    var attribute: String?       // afficher un attribut au lieu de l'etat
    var unit: String?
    var decimals: Int?
    var service: String?         // service du clic ("none" = pas d'action)
    var data: [String: JSONValue]?
    var group: [String]?         // autres entites commandees par le meme element
    var hidden: Bool?
    var showFrom: String?        // plage horaire d'affichage HH:MM
    var showTo: String?
    var thresholds: String?      // "> 25 orange ; > 30 rouge"
    var badge: String?           // "", "percentage", "battery", "direction" ou un attribut
    var cardTitle: String?
    var favorites: [JSONValue]?

    enum CodingKeys: String, CodingKey {
        case entityId = "entity_id", label, icon, attribute, unit, decimals, service, data, group, hidden
        case showFrom = "show_from", showTo = "show_to", thresholds, badge, cardTitle = "card_title", favorites
    }

    init(entityId: String, label: String? = nil, icon: String? = nil) {
        self.entityId = entityId
        self.label = label
        self.icon = icon
    }

    // Decodage tolerant : un champ mal forme est ignore au lieu de tout refuser.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        entityId = (try? c.decode(String.self, forKey: .entityId)) ?? ""
        label = Self.str(c, .label)
        icon = Self.str(c, .icon)
        attribute = Self.str(c, .attribute)
        unit = Self.str(c, .unit)
        if let i = try? c.decodeIfPresent(Int.self, forKey: .decimals) {
            decimals = i
        } else if let s = Self.str(c, .decimals) {
            decimals = Int(s)
        }
        service = Self.str(c, .service)
        data = try? c.decodeIfPresent([String: JSONValue].self, forKey: .data)
        group = try? c.decodeIfPresent([String].self, forKey: .group)
        hidden = try? c.decodeIfPresent(Bool.self, forKey: .hidden)
        showFrom = Self.str(c, .showFrom)
        showTo = Self.str(c, .showTo)
        thresholds = Self.str(c, .thresholds)
        badge = Self.str(c, .badge)
        cardTitle = Self.str(c, .cardTitle)
        favorites = try? c.decodeIfPresent([JSONValue].self, forKey: .favorites)
    }

    private static func str(_ c: KeyedDecodingContainer<CodingKeys>, _ k: CodingKeys) -> String? {
        guard let s = try? c.decodeIfPresent(String.self, forKey: k) else { return nil }
        return s.isEmpty ? nil : s
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(entityId, forKey: .entityId)
        try c.encodeIfPresent(label.nonEmpty, forKey: .label)
        try c.encodeIfPresent(icon.nonEmpty, forKey: .icon)
        try c.encodeIfPresent(attribute.nonEmpty, forKey: .attribute)
        try c.encodeIfPresent(unit.nonEmpty, forKey: .unit)
        try c.encodeIfPresent(decimals, forKey: .decimals)
        try c.encodeIfPresent(service.nonEmpty, forKey: .service)
        try c.encodeIfPresent(data, forKey: .data)
        if let g = group, !g.isEmpty { try c.encode(g, forKey: .group) }
        if hidden == true { try c.encode(true, forKey: .hidden) }
        try c.encodeIfPresent(showFrom.nonEmpty, forKey: .showFrom)
        try c.encodeIfPresent(showTo.nonEmpty, forKey: .showTo)
        try c.encodeIfPresent(thresholds.nonEmpty, forKey: .thresholds)
        try c.encodeIfPresent(badge.nonEmpty, forKey: .badge)
        try c.encodeIfPresent(cardTitle.nonEmpty, forKey: .cardTitle)
        if let f = favorites, !f.isEmpty { try c.encode(f, forKey: .favorites) }
    }

    static func == (a: ItemConfig, b: ItemConfig) -> Bool {
        a.id == b.id && a.entityId == b.entityId && a.label == b.label && a.icon == b.icon
            && a.attribute == b.attribute && a.unit == b.unit && a.decimals == b.decimals
            && a.service == b.service && a.data == b.data && a.group == b.group && a.hidden == b.hidden
            && a.showFrom == b.showFrom && a.showTo == b.showTo && a.thresholds == b.thresholds
            && a.badge == b.badge && a.cardTitle == b.cardTitle && a.favorites == b.favorites
    }

    var domain: String { entityId.domain }
    var members: [String] {
        var out = [entityId]
        for e in group ?? [] where !e.isEmpty && !out.contains(e) { out.append(e) }
        return out.filter { !$0.isEmpty }
    }
    var isGroup: Bool { members.count > 1 }
}

/// Regle de notification : quand `entity_id` passe a l'etat `to` (vide = tout changement).
struct NotifyRule: Codable, Identifiable, Equatable {
    var id = UUID()
    var entityId: String
    var to: String
    var message: String

    enum CodingKeys: String, CodingKey { case entityId = "entity_id", to, message }

    init(entityId: String = "", to: String = "", message: String = "") {
        self.entityId = entityId
        self.to = to
        self.message = message
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        entityId = (try? c.decode(String.self, forKey: .entityId)) ?? ""
        to = (try? c.decode(String.self, forKey: .to)) ?? ""
        message = (try? c.decode(String.self, forKey: .message)) ?? ""
    }
}

struct AppConfig: Codable, Equatable {
    var haURL = "http://homeassistant.local:8123"
    var verifySSL = true
    var pollInterval: Double = 5
    var realtime = true
    var compact = false              // icones seules (la valeur est dans la carte)
    var showAppIcon = true           // icone HA Taskbar dans la barre des menus
    var animIcons = true             // icones animees quand l'element est actif (macOS 14+)
    var flashChanges = true          // une valeur qui change clignote brievement
    var clickOpensCard = false       // clic simple = carte (l'action passe sur ⌥-clic)
    var hoverCardDelay: Double = 0.8 // survol : la carte s'ouvre apres ce delai (s), 0 = jamais
    var notifyOffline = true
    var haNotifications = true       // notifications persistantes + evenement ha_taskbar_notify
    var quietFrom = ""
    var quietTo = ""
    var batteryLow: Double = 20
    var checkUpdates = true
    var skipVersion = ""             // version que l'utilisateur a choisi d'ignorer
    var notifications: [NotifyRule] = []
    var items: [ItemConfig] = []

    enum CodingKeys: String, CodingKey {
        case haURL = "ha_url", verifySSL = "verify_ssl", pollInterval = "poll_interval", realtime, compact
        case showAppIcon = "show_app_icon", animIcons = "anim_icons", flashChanges = "flash_changes"
        case clickOpensCard = "click_opens_card", hoverCardDelay = "hover_card_delay"
        case notifyOffline = "notify_offline", haNotifications = "ha_notifications"
        case quietFrom = "quiet_from", quietTo = "quiet_to", batteryLow = "battery_low"
        case checkUpdates = "check_updates", skipVersion = "skip_version", notifications, items
    }

    init() {}

    init(from decoder: Decoder) throws {
        let d = AppConfig()
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func get<T: Decodable>(_ k: CodingKeys, _ def: T) -> T {
            (try? c.decodeIfPresent(T.self, forKey: k)) ?? def
        }
        haURL = get(.haURL, d.haURL)
        verifySSL = get(.verifySSL, d.verifySSL)
        pollInterval = get(.pollInterval, d.pollInterval)
        realtime = get(.realtime, d.realtime)
        compact = get(.compact, d.compact)
        showAppIcon = get(.showAppIcon, d.showAppIcon)
        animIcons = get(.animIcons, d.animIcons)
        flashChanges = get(.flashChanges, d.flashChanges)
        clickOpensCard = get(.clickOpensCard, d.clickOpensCard)
        hoverCardDelay = get(.hoverCardDelay, d.hoverCardDelay)
        notifyOffline = get(.notifyOffline, d.notifyOffline)
        haNotifications = get(.haNotifications, d.haNotifications)
        quietFrom = get(.quietFrom, d.quietFrom)
        quietTo = get(.quietTo, d.quietTo)
        batteryLow = get(.batteryLow, d.batteryLow)
        checkUpdates = get(.checkUpdates, d.checkUpdates)
        skipVersion = get(.skipVersion, d.skipVersion)
        notifications = get(.notifications, d.notifications)
        items = get(.items, d.items)
    }
}

extension Optional where Wrapped == String {
    /// nil si la chaine est vide (ou absente).
    var nonEmpty: String? {
        guard let s = self?.trimmingCharacters(in: .whitespaces), !s.isEmpty else { return nil }
        return s
    }
}

// MARK: - Fichiers

enum ConfigStore {
    static var directory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
        return base.appendingPathComponent("HATaskbar", isDirectory: true)
    }
    static var configURL: URL { directory.appendingPathComponent("config.json") }

    static func load() -> AppConfig {
        guard let data = try? Data(contentsOf: configURL) else { return AppConfig() }
        return (try? decode(data).config) ?? AppConfig()
    }

    /// Decode un config.json (macOS ou Windows). Renvoie aussi le jeton s'il y en a un dans le fichier.
    static func decode(_ data: Data) throws -> (config: AppConfig, token: String?) {
        let cfg = try JSONDecoder().decode(AppConfig.self, from: data)
        var token: String?
        if let raw = try? JSONDecoder().decode([String: JSONValue].self, from: data),
           let t = raw["token"]?.string, !t.isEmpty, t != "COLLE_ICI_TON_JETON_LONGUE_DUREE" {
            token = t
        }
        return (cfg, token)
    }

    static func encode(_ cfg: AppConfig) throws -> Data {
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        return try enc.encode(cfg)
    }

    static func save(_ cfg: AppConfig) {
        if Demo.enabled { return }
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try encode(cfg).write(to: configURL, options: .atomic)
        } catch {
            NSLog("HA Taskbar : enregistrement de la configuration impossible : \(error)")
        }
    }
}

// MARK: - Jeton (trousseau macOS)

import Security

enum TokenStore {
    private static let service = "HATaskbar"
    private static let account = "home-assistant-token"

    static func load() -> String {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: service,
                                kSecAttrAccount as String: account,
                                kSecReturnData as String: true,
                                kSecMatchLimit as String: kSecMatchLimitOne]
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess,
              let data = out as? Data, let s = String(data: data, encoding: .utf8) else { return "" }
        return s
    }

    static func save(_ token: String) {
        if Demo.enabled { return }
        let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                   kSecAttrService as String: service,
                                   kSecAttrAccount as String: account]
        SecItemDelete(base as CFDictionary)
        guard !token.isEmpty else { return }
        var add = base
        add[kSecValueData as String] = Data(token.utf8)
        add[kSecAttrLabel as String] = "HA Taskbar – jeton Home Assistant"
        let st = SecItemAdd(add as CFDictionary, nil)
        if st != errSecSuccess {
            NSLog("HA Taskbar : enregistrement du jeton dans le trousseau impossible (\(st))")
        }
    }
}
