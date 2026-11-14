import AppKit

// MARK: - Icones (SF Symbols). Les cles sont celles de la version Windows.

enum AnimEffect: String { case pulse, variable, rotate, bounce }

struct IconDef {
    let key: String
    let symbol: String
    let name: String
}

enum Icons {
    static let all: [IconDef] = [
        IconDef(key: "lightbulb", symbol: "lightbulb.fill", name: "Ampoule"),
        IconDef(key: "lightbulb2", symbol: "lightbulb", name: "Ampoule (contour)"),
        IconDef(key: "toggle", symbol: "lightswitch.on", name: "Interrupteur (suit l'état)"),
        IconDef(key: "power", symbol: "power", name: "Marche / arrêt"),
        IconDef(key: "plug", symbol: "powerplug", name: "Prise"),
        IconDef(key: "tap", symbol: "hand.tap", name: "Bouton / appui"),
        IconDef(key: "thermometer", symbol: "thermometer.medium", name: "Thermomètre"),
        IconDef(key: "flame", symbol: "flame", name: "Flamme / chauffage"),
        IconDef(key: "heater", symbol: "heater.vertical", name: "Radiateur"),
        IconDef(key: "ac", symbol: "air.conditioner.horizontal", name: "Climatiseur"),
        IconDef(key: "drop", symbol: "drop", name: "Goutte / humidité"),
        IconDef(key: "humidity", symbol: "humidity", name: "Humidité"),
        IconDef(key: "bolt", symbol: "bolt", name: "Éclair / énergie"),
        IconDef(key: "battery", symbol: "battery.100", name: "Batterie"),
        IconDef(key: "sun", symbol: "sun.max", name: "Soleil / luminosité"),
        IconDef(key: "moon", symbol: "moon", name: "Lune / nuit"),
        IconDef(key: "cloud", symbol: "cloud", name: "Nuage / météo"),
        IconDef(key: "rain", symbol: "cloud.rain", name: "Pluie"),
        IconDef(key: "snow", symbol: "snowflake", name: "Flocon / froid"),
        IconDef(key: "wind", symbol: "wind", name: "Vent"),
        IconDef(key: "fan", symbol: "fan", name: "Ventilateur"),
        IconDef(key: "home", symbol: "house", name: "Maison"),
        IconDef(key: "home_filled", symbol: "house.fill", name: "Maison (plein)"),
        IconDef(key: "window", symbol: "window.vertical.closed", name: "Fenêtre / volet"),
        IconDef(key: "blinds", symbol: "blinds.vertical.closed", name: "Store"),
        IconDef(key: "door", symbol: "door.left.hand.closed", name: "Porte"),
        IconDef(key: "garage", symbol: "door.garage.closed", name: "Garage"),
        IconDef(key: "lock", symbol: "lock", name: "Cadenas (suit l'état)"),
        IconDef(key: "shield", symbol: "shield", name: "Bouclier / alarme"),
        IconDef(key: "bell", symbol: "bell", name: "Cloche"),
        IconDef(key: "bell_off", symbol: "bell.slash", name: "Sonnerie coupée"),
        IconDef(key: "warning", symbol: "exclamationmark.triangle", name: "Alerte"),
        IconDef(key: "speaker", symbol: "speaker.wave.3", name: "Haut-parleur"),
        IconDef(key: "music", symbol: "music.note", name: "Musique"),
        IconDef(key: "play", symbol: "play", name: "Lecture"),
        IconDef(key: "pause", symbol: "pause", name: "Pause"),
        IconDef(key: "stop", symbol: "stop", name: "Stop"),
        IconDef(key: "prev", symbol: "backward.end", name: "Précédent"),
        IconDef(key: "next", symbol: "forward.end", name: "Suivant"),
        IconDef(key: "tv", symbol: "tv", name: "Écran / TV"),
        IconDef(key: "video", symbol: "video", name: "Caméra"),
        IconDef(key: "camera", symbol: "camera", name: "Appareil photo"),
        IconDef(key: "photo", symbol: "photo", name: "Photo / cadre"),
        IconDef(key: "person", symbol: "person", name: "Personne"),
        IconDef(key: "person_filled", symbol: "person.fill", name: "Personne (plein)"),
        IconDef(key: "people", symbol: "person.2", name: "Personnes"),
        IconDef(key: "car", symbol: "car", name: "Voiture"),
        IconDef(key: "wifi", symbol: "wifi", name: "Wi-Fi"),
        IconDef(key: "antenna", symbol: "cellularbars", name: "Antenne / signal"),
        IconDef(key: "bluetooth", symbol: "dot.radiowaves.left.and.right", name: "Radio / Bluetooth"),
        IconDef(key: "gear", symbol: "gearshape", name: "Engrenage"),
        IconDef(key: "gears", symbol: "gearshape.2", name: "Automatisation"),
        IconDef(key: "code", symbol: "chevron.left.forwardslash.chevron.right", name: "Script"),
        IconDef(key: "palette", symbol: "paintpalette", name: "Scène"),
        IconDef(key: "clock", symbol: "clock", name: "Horloge"),
        IconDef(key: "timer", symbol: "timer", name: "Minuteur"),
        IconDef(key: "history", symbol: "clock.arrow.circlepath", name: "Historique"),
        IconDef(key: "pulse", symbol: "waveform.path.ecg", name: "Capteur / activité"),
        IconDef(key: "sensor", symbol: "sensor", name: "Détecteur"),
        IconDef(key: "heart", symbol: "heart", name: "Cœur"),
        IconDef(key: "star", symbol: "star", name: "Étoile"),
        IconDef(key: "flag", symbol: "flag", name: "Drapeau"),
        IconDef(key: "location", symbol: "location", name: "Position"),
        IconDef(key: "refresh", symbol: "arrow.clockwise", name: "Actualiser"),
        IconDef(key: "washer", symbol: "washer", name: "Lave-linge"),
        IconDef(key: "dishwasher", symbol: "dishwasher", name: "Lave-vaisselle"),
        IconDef(key: "oven", symbol: "oven", name: "Four"),
        IconDef(key: "spigot", symbol: "spigot", name: "Robinet / arrosage"),
        IconDef(key: "leaf", symbol: "leaf", name: "Plante / jardin"),
        IconDef(key: "game", symbol: "gamecontroller", name: "Console / jeux"),
        IconDef(key: "laptop", symbol: "laptopcomputer", name: "Ordinateur portable"),
        IconDef(key: "desktop", symbol: "desktopcomputer", name: "Ordinateur"),
        IconDef(key: "phone", symbol: "iphone", name: "Téléphone"),
        IconDef(key: "headphones", symbol: "headphones", name: "Casque audio"),
        IconDef(key: "mic", symbol: "mic", name: "Micro"),
        IconDef(key: "mute", symbol: "speaker.slash", name: "Son coupé"),
        IconDef(key: "eye", symbol: "eye", name: "Œil / surveillance"),
        IconDef(key: "fingerprint", symbol: "touchid", name: "Empreinte"),
        IconDef(key: "key", symbol: "key", name: "Clé"),
        IconDef(key: "check", symbol: "checkmark.circle", name: "Validé"),
        IconDef(key: "sunrise", symbol: "sunrise", name: "Lever du soleil"),
        IconDef(key: "sunset", symbol: "sunset", name: "Coucher du soleil"),
        IconDef(key: "health", symbol: "cross.case", name: "Santé"),
        IconDef(key: "smile", symbol: "face.smiling", name: "Humeur"),
        IconDef(key: "like", symbol: "hand.thumbsup", name: "J'aime"),
        IconDef(key: "mail", symbol: "envelope", name: "Courrier"),
        IconDef(key: "message", symbol: "message", name: "Message"),
        IconDef(key: "calendar", symbol: "calendar", name: "Calendrier"),
        IconDef(key: "cart", symbol: "cart", name: "Courses"),
        IconDef(key: "bag", symbol: "bag", name: "Achats"),
        IconDef(key: "trash", symbol: "trash", name: "Poubelle"),
        IconDef(key: "work", symbol: "briefcase", name: "Travail"),
        IconDef(key: "school", symbol: "graduationcap", name: "École"),
        IconDef(key: "building", symbol: "building.2", name: "Bâtiment"),
        IconDef(key: "globe", symbol: "globe", name: "Internet / monde"),
        IconDef(key: "map", symbol: "map", name: "Carte"),
        IconDef(key: "plane", symbol: "airplane", name: "Avion / voyage"),
        IconDef(key: "bus", symbol: "bus", name: "Bus"),
        IconDef(key: "train", symbol: "tram", name: "Train"),
        IconDef(key: "chip", symbol: "cpu", name: "Processeur"),
        IconDef(key: "chart", symbol: "chart.line.uptrend.xyaxis", name: "Tendance"),
        IconDef(key: "pie", symbol: "chart.pie", name: "Statistiques"),
        IconDef(key: "wrench", symbol: "wrench.and.screwdriver", name: "Outils / entretien"),
        IconDef(key: "puzzle", symbol: "puzzlepiece", name: "Extension"),
    ]

    /// Icones animees (noms de la version Windows) : icone de base + effet macOS (macOS 14+).
    static let animated: [(key: String, base: String, effect: AnimEffect, name: String)] = [
        ("flame_anim", "flame", .pulse, "Flamme animée (chauffage)"),
        ("fan_anim", "fan", .rotate, "Ventilateur qui tourne"),
        ("bulb_anim", "lightbulb", .pulse, "Ampoule qui rayonne"),
        ("eq_anim", "music", .bounce, "Musique qui bat"),
        ("drop_anim", "drop", .bounce, "Goutte qui tombe (arrosage)"),
        ("snow_anim", "snow", .rotate, "Flocon qui tourne (climatisation)"),
        ("sun_anim", "sun", .rotate, "Soleil qui rayonne"),
        ("wifi_anim", "wifi", .variable, "Ondes Wi-Fi / signal"),
        ("bell_anim", "bell", .bounce, "Cloche qui sonne"),
        ("washer_anim", "washer", .pulse, "Lave-linge en marche"),
        ("bolt_anim", "bolt", .pulse, "Éclair (énergie)"),
        ("battery_anim", "battery", .pulse, "Batterie en charge"),
        ("radar_anim", "sensor", .variable, "Détection (mouvement, présence)"),
        ("heater_anim", "heater", .variable, "Radiateur (chaleur qui monte)"),
        ("speaker_anim", "speaker", .variable, "Haut-parleur (son)"),
        ("timer_anim", "timer", .rotate, "Minuteur"),
        ("rain_anim", "rain", .pulse, "Pluie"),
        ("gear_anim", "gear", .rotate, "Engrenage qui tourne"),
    ]

    static let byKey: [String: IconDef] = Dictionary(all.map { ($0.key, $0) }, uniquingKeysWith: { a, _ in a })
    static let animByKey = Dictionary(animated.map { ($0.key, $0) }, uniquingKeysWith: { a, _ in a })

    static func symbol(_ key: String) -> String {
        byKey[key]?.symbol ?? "circle.fill"
    }

    /// Image SF Symbol (avec repli si le symbole n'existe pas dans cette version de macOS).
    static func image(_ symbol: String, variable: Double? = nil, size: CGFloat = 13) -> NSImage? {
        let cfg = NSImage.SymbolConfiguration(pointSize: size, weight: .regular)
        var img: NSImage?
        if let v = variable {
            img = NSImage(systemSymbolName: symbol, variableValue: v, accessibilityDescription: nil)
        } else {
            img = NSImage(systemSymbolName: symbol, accessibilityDescription: nil)
        }
        if img == nil {
            img = NSImage(systemSymbolName: fallbacks[symbol] ?? "circle.fill", accessibilityDescription: nil)
        }
        return img?.withSymbolConfiguration(cfg)
    }

    static let fallbacks: [String: String] = [
        "lightswitch.on": "switch.2", "lightswitch.off": "switch.2", "thermometer.medium": "thermometer",
        "heater.vertical": "flame", "air.conditioner.horizontal": "snowflake", "humidity": "drop",
        "fan": "wind", "window.vertical.closed": "rectangle.split.2x1",
        "window.vertical.open": "rectangle.split.2x1", "blinds.vertical.closed": "rectangle.split.3x1",
        "blinds.vertical.open": "rectangle.split.3x1", "door.left.hand.closed": "door.left.hand.open",
        "door.garage.closed": "car", "door.garage.open": "car", "sensor": "dot.radiowaves.left.and.right",
        "washer": "arrow.triangle.2.circlepath", "dishwasher": "drop", "oven": "flame", "spigot": "drop",
        "powerplug": "bolt",
    ]
}

// MARK: - Textes

let activeStates: Set<String> = ["on", "open", "opening", "playing", "home", "unlocked", "heat", "cool", "heat_cool", "auto"]

let stateText: [String: String] = [
    "on": "ON", "off": "OFF", "unavailable": "indispo", "unknown": "?", "open": "ouvert", "closed": "fermé",
    "opening": "ouverture", "closing": "fermeture", "playing": "lecture", "paused": "pause", "idle": "inactif",
    "standby": "veille", "home": "présent", "not_home": "absent", "locked": "verrouillé", "unlocked": "ouvert",
    "heat": "chauffe", "cool": "froid", "heat_cool": "auto", "auto": "auto", "dry": "sec", "fan_only": "ventilation",
    "cleaning": "nettoyage", "docked": "à la base", "returning": "retour", "armed_away": "armée (absent)",
    "armed_home": "armée (présent)", "armed_night": "armée (nuit)", "disarmed": "désarmée", "triggered": "déclenchée",
    "above_horizon": "levé", "below_horizon": "couché", "active": "actif", "detected": "détecté", "clear": "rien",
]

let weatherText: [String: String] = [
    "clear-night": "Nuit claire", "cloudy": "Nuageux", "exceptional": "Exceptionnel", "fog": "Brouillard",
    "hail": "Grêle", "lightning": "Orages", "lightning-rainy": "Orages et pluie", "partlycloudy": "Éclaircies",
    "pouring": "Averses", "rainy": "Pluie", "snowy": "Neige", "snowy-rainy": "Neige et pluie", "sunny": "Ensoleillé",
    "windy": "Venteux", "windy-variant": "Venteux et nuageux",
]

let weatherSymbol: [String: String] = [
    "clear-night": "moon.stars", "cloudy": "cloud", "exceptional": "exclamationmark.triangle", "fog": "cloud.fog",
    "hail": "cloud.hail", "lightning": "cloud.bolt", "lightning-rainy": "cloud.bolt.rain", "partlycloudy": "cloud.sun",
    "pouring": "cloud.heavyrain", "rainy": "cloud.rain", "snowy": "cloud.snow", "snowy-rainy": "cloud.sleet",
    "sunny": "sun.max", "windy": "wind", "windy-variant": "wind",
]

func translate(_ state: String, domain: String) -> String {
    if domain == "weather" { return weatherText[state] ?? state }
    return stateText[state] ?? state
}

// MARK: - Icone automatique

func autoIcon(_ entityId: String, _ st: EntityState?) -> String {
    if entityId == batteriesId { return "battery" }
    let d = entityId.domain
    let dc = st?.str("device_class") ?? ""
    let unit = st?.str("unit_of_measurement") ?? ""
    let byDomain: [String: String] = [
        "light": "lightbulb", "switch": "toggle", "input_boolean": "toggle", "fan": "fan",
        "climate": "flame", "water_heater": "flame", "cover": "window", "lock": "lock",
        "media_player": "music", "scene": "palette", "script": "code", "automation": "gears",
        "button": "tap", "input_button": "tap", "person": "person", "device_tracker": "person",
        "weather": "cloud", "camera": "video", "sun": "sun", "alarm_control_panel": "shield",
        "vacuum": "home", "update": "refresh", "timer": "timer", "siren": "bell",
        "humidifier": "humidity", "valve": "spigot", "lawn_mower": "leaf",
    ]
    if d == "switch" && dc == "outlet" { return "plug" }
    if d == "cover" {
        if dc == "garage" { return "garage" }
        if dc == "door" || dc == "gate" { return "door" }
        if dc == "blind" || dc == "shade" || dc == "curtain" { return "blinds" }
    }
    if let k = byDomain[d] { return k }
    if d == "binary_sensor" {
        switch dc {
        case "door", "garage_door": return "door"
        case "window", "opening": return "window"
        case "motion", "occupancy", "presence": return "person"
        case "smoke", "gas", "safety", "problem", "carbon_monoxide", "tamper": return "warning"
        case "moisture": return "drop"
        case "battery": return "battery"
        case "power", "plug": return "bolt"
        default: return "pulse"
        }
    }
    if dc == "temperature" || unit == "°C" || unit == "°F" { return "thermometer" }
    if dc == "humidity" { return "humidity" }
    if ["moisture", "precipitation", "water"].contains(dc) { return "drop" }
    if ["power", "energy", "current", "voltage", "power_factor"].contains(dc)
        || ["W", "kW", "kWh", "Wh", "A", "V"].contains(unit) { return "bolt" }
    if dc == "battery" { return "battery" }
    if dc == "illuminance" || unit == "lx" { return "sun" }
    if dc == "wind_speed" { return "wind" }
    return "pulse"
}

// MARK: - Seuils de couleur ("> 25 orange ; > 30 rouge ; < 15 bleu")

let colorWords: [String: String] = [
    "rouge": "#e74856", "red": "#e74856", "orange": "#f7630c", "jaune": "#e8b900", "yellow": "#e8b900",
    "vert": "#16c60c", "green": "#16c60c", "bleu": "#3a96dd", "blue": "#3a96dd", "violet": "#b146c2",
    "purple": "#b146c2", "rose": "#e3008c", "pink": "#e3008c", "gris": "#9a9a9a", "grey": "#9a9a9a",
    "gray": "#9a9a9a", "blanc": "#ffffff", "white": "#ffffff", "noir": "#000000", "black": "#000000",
]

struct ThresholdRule { let op: String; let value: Double; let color: String }

func parseThresholds(_ text: String?) -> (rules: [ThresholdRule], bad: [String]) {
    var rules: [ThresholdRule] = [], bad: [String] = []
    let re = try! NSRegularExpression(pattern: #"^\s*(<=|>=|<|>|=)\s*(-?\d+(?:[.,]\d+)?)\s*(\S+)\s*$"#)
    for part in (text ?? "").split(separator: ";").map(String.init) {
        let p = part.trimmingCharacters(in: .whitespaces)
        if p.isEmpty { continue }
        let ns = p as NSString
        guard let m = re.firstMatch(in: p, range: NSRange(location: 0, length: ns.length)) else {
            bad.append(p); continue
        }
        let op = ns.substring(with: m.range(at: 1))
        let v = Double(ns.substring(with: m.range(at: 2)).replacingOccurrences(of: ",", with: ".")) ?? 0
        let w = ns.substring(with: m.range(at: 3)).lowercased()
        let isHex = w.range(of: #"^#[0-9a-f]{6}$"#, options: .regularExpression) != nil
        guard let col = colorWords[w] ?? (isHex ? w : nil) else { bad.append(p); continue }
        rules.append(ThresholdRule(op: op, value: v, color: col))
    }
    return (rules, bad)
}

/// Couleur de la regle la plus precise satisfaite (seuil le plus haut pour ">", le plus bas pour "<").
func thresholdColor(_ rules: [ThresholdRule], _ value: String?) -> String? {
    guard !rules.isEmpty, let s = value, let v = Double(s.replacingOccurrences(of: ",", with: ".")) else { return nil }
    var best: (Double, String)?
    for r in rules {
        let ok: Bool, score: Double
        switch r.op {
        case ">": ok = v > r.value; score = r.value
        case ">=": ok = v >= r.value; score = r.value
        case "<": ok = v < r.value; score = -r.value
        case "<=": ok = v <= r.value; score = -r.value
        default: ok = v == r.value; score = .infinity
        }
        if ok && (best == nil || score > best!.0) { best = (score, r.color) }
    }
    return best?.1
}

extension NSColor {
    convenience init?(hex: String) {
        var s = hex.trimmingCharacters(in: .whitespaces)
        if s.hasPrefix("#") { s.removeFirst() }
        guard s.count == 6, let v = UInt32(s, radix: 16) else { return nil }
        self.init(srgbRed: CGFloat((v >> 16) & 0xff) / 255, green: CGFloat((v >> 8) & 0xff) / 255,
                  blue: CGFloat(v & 0xff) / 255, alpha: 1)
    }

    /// Couleur « allumé » : jaune sur barre sombre, orange fonce sur barre claire.
    static let haOn = NSColor(name: "haOn") { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(srgbRed: 1, green: 0.784, blue: 0.239, alpha: 1)
            : NSColor(srgbRed: 0.75, green: 0.45, blue: 0, alpha: 1)
    }
}

// MARK: - Plages horaires

func parseHHMM(_ s: String?) -> Int? {
    guard let s = s?.trimmingCharacters(in: .whitespaces) else { return nil }
    let p = s.split(separator: ":")
    guard p.count == 2, let h = Int(p[0]), let m = Int(p[1]), (0..<24).contains(h), (0..<60).contains(m) else { return nil }
    return h * 60 + m
}

/// L'heure actuelle est-elle dans la plage (qui peut passer minuit) ? Plage vide ou invalide : `empty`.
func inRange(_ start: String?, _ end: String?, empty: Bool, now: Date = Date()) -> Bool {
    guard let a = parseHHMM(start), let b = parseHHMM(end), a != b else { return empty }
    let c = Calendar.current.dateComponents([.hour, .minute], from: now)
    let t = (c.hour ?? 0) * 60 + (c.minute ?? 0)
    return a < b ? (a <= t && t < b) : (t >= a || t < b)
}

func itemVisible(_ item: ItemConfig) -> Bool {
    if item.hidden == true { return false }
    return inRange(item.showFrom, item.showTo, empty: true)
}

// MARK: - Piles faibles

let batteriesId = "@batteries"

func batteryLevels(_ states: [String: EntityState]) -> [(id: String, name: String, level: Double?)] {
    var out: [(id: String, name: String, level: Double?)] = []
    for (eid, st) in states where st.str("device_class") == "battery" {
        if eid.hasPrefix("sensor."), st.str("unit_of_measurement") == "%", let v = Double(st.state) {
            out.append((eid, st.name, v))
        } else if eid.hasPrefix("binary_sensor."), st.state == "on" || st.state == "off" {
            out.append((eid, st.name, st.state == "on" ? 0 : nil))
        }
    }
    return out
}

func lowBatteries(_ states: [String: EntityState], threshold: Double) -> [(id: String, name: String, level: Double)] {
    batteryLevels(states).compactMap { b in
        guard let l = b.level, l < threshold else { return nil }
        return (b.id, b.name, l)
    }.sorted { $0.level < $1.level }
}

// MARK: - Ce qu'affiche un element

enum Tone { case normal, on, dim, error }

struct ItemDisplay: Equatable {
    var symbol: String?
    var variable: Double?
    var text: String
    var tone: Tone
    var color: String?          // couleur de seuil (#rrggbb)
    var anim: AnimEffect?
    var badge: String = ""
}

func isActive(_ st: EntityState) -> Bool {
    if st.isUnavailable { return false }
    switch st.domain {
    case "climate", "water_heater":
        if let a = st.str("hvac_action") { return a != "idle" && a != "off" }
        return activeStates.contains(st.state)
    case "sensor": return (Double(st.state) ?? 0) > 0
    case "media_player": return st.state == "playing"
    default: return activeStates.contains(st.state)
    }
}

/// Symbole et valeur variable (pile, signal, volume, meteo) d'un element.
func resolveSymbol(_ item: ItemConfig, _ st: EntityState?) -> (String?, Double?, AnimEffect?) {
    var key = item.icon ?? "auto"
    if key == "none" { return (nil, nil, nil) }
    if key.isEmpty || key == "auto" { key = autoIcon(item.entityId, st) }
    var anim: AnimEffect?
    if let a = Icons.animByKey[key] {
        key = a.base
        anim = a.effect
    }
    guard let st = st, !st.isUnavailable else { return (Icons.symbol(key), nil, anim) }
    let raw: String? = item.attribute.nonEmpty != nil ? st.attributes[item.attribute.nonEmpty!]?.string : st.state
    let domain = st.domain
    switch key {
    case "battery":
        var v = st.num("battery_level") ?? (item.attribute == nil ? st.num("battery") : nil)
        if v == nil && (item.attribute != nil || st.str("unit_of_measurement") == "%" || st.str("device_class") == "battery") {
            v = Double(raw ?? "")
        }
        if let v = v {
            let steps = [0, 25, 50, 75, 100]
            let n = steps.min(by: { abs(Double($0) - v) < abs(Double($1) - v) }) ?? 100
            return ("battery.\(n)", nil, anim)
        }
    case "wifi", "antenna":
        if let v = Double(raw ?? "") {
            let unit = item.attribute == nil ? (st.str("unit_of_measurement") ?? "") : ""
            var pct: Double?
            if unit == "dBm" || (v < 0 && unit.isEmpty) { pct = (v + 100) * 2 }
            else if unit == "%" { pct = v }
            else if unit == "lqi" || (item.attribute ?? item.entityId).contains("link") { pct = v * 100 / 255 }
            if let p = pct { return (Icons.symbol(key), max(0, min(1, p / 100)), anim) }
        }
    case "speaker" where domain == "media_player":
        if st.attributes["is_volume_muted"]?.bool == true { return ("speaker.slash", nil, anim) }
        if let v = st.num("volume_level") { return ("speaker.wave.3", v, anim) }
    case "toggle":
        return (st.state == "on" ? "lightswitch.on" : "lightswitch.off", nil, anim)
    case "lock":
        if ["unlocked", "open", "opening", "unlocking"].contains(st.state) { return ("lock.open", nil, anim) }
    case "window":
        if ["open", "opening", "on"].contains(st.state) { return ("window.vertical.open", nil, anim) }
    case "blinds":
        if ["open", "opening"].contains(st.state) { return ("blinds.vertical.open", nil, anim) }
    case "garage":
        if ["open", "opening", "on"].contains(st.state) { return ("door.garage.open", nil, anim) }
    case "door":
        if ["open", "opening", "on"].contains(st.state) { return ("door.left.hand.open", nil, anim) }
    case "lightbulb":
        if domain == "light" && st.state != "on" { return ("lightbulb", nil, anim) }
    default:
        break
    }
    if domain == "weather" && item.attribute == nil && (item.icon ?? "auto") == "auto",
       let s = weatherSymbol[st.state] {
        return (s, nil, anim)
    }
    return (Icons.symbol(key), nil, anim)
}

func badgeText(_ item: ItemConfig, _ st: EntityState?, timerLeft: TimeInterval?) -> String {
    if let left = timerLeft { return "⏲\(max(1, Int((left / 60).rounded())))" }
    guard let mode = item.badge.nonEmpty, let st = st, !st.isUnavailable else { return "" }
    switch mode {
    case "direction":
        return ["forward": "↻", "reverse": "↺"][st.str("direction") ?? ""] ?? ""
    case "percentage":
        var p = st.num("percentage")
        if p == nil, let b = st.num("brightness") { p = (b * 100 / 255).rounded() }
        return (p != nil && st.state == "on") ? "\(Int(p!))" : ""
    case "battery":
        if let b = st.attributes["battery_level"] ?? st.attributes["battery"] { return "\(b.display)%" }
        return ""
    default:
        return String((st.attributes[mode]?.display ?? "").prefix(6))
    }
}

func displayFor(_ item: ItemConfig, states: [String: EntityState], offline: Bool, batteryLow: Double,
                timerLeft: TimeInterval?) -> ItemDisplay {
    let st = states[item.entityId]
    let (symbol, variable, anim) = resolveSymbol(item, st)

    if item.entityId == batteriesId {
        let n = lowBatteries(states, threshold: batteryLow).count
        let lowest = batteryLevels(states).compactMap { $0.level }.min()
        var sym = "battery.100"
        if let l = lowest { sym = l < 13 ? "battery.0" : l < 38 ? "battery.25" : l < 63 ? "battery.50" : l < 88 ? "battery.75" : "battery.100" }
        if item.icon != nil && item.icon != "auto" { sym = symbol ?? sym }
        return ItemDisplay(symbol: sym, text: n > 0 ? "\(n)" : "OK", tone: offline ? .dim : (n > 0 ? .error : .normal))
    }

    let badge = badgeText(item, st, timerLeft: timerLeft)

    if item.isGroup && item.attribute == nil {
        let known = item.members.compactMap { states[$0] }.filter { !$0.isUnavailable }
        if !known.isEmpty {
            let on = known.filter { activeStates.contains($0.state) }.count
            return ItemDisplay(symbol: symbol, variable: variable, text: "\(on)/\(item.members.count)",
                               tone: offline ? .dim : (on > 0 ? .on : .normal),
                               anim: (on > 0 && !offline) ? anim : nil, badge: badge)
        }
    }

    guard let st = st else {
        return ItemDisplay(symbol: symbol, text: "?", tone: .error)
    }
    let attr = item.attribute.nonEmpty
    let rawValue: JSONValue? = attr != nil ? st.attributes[attr!] : .string(st.state)
    let raw = rawValue?.string
    let unit = item.unit.nonEmpty ?? (attr == nil ? (st.str("unit_of_measurement") ?? "") : "")

    var text = rawValue?.display ?? "—"
    if let dec = item.decimals, let v = rawValue?.double {
        text = String(format: "%.\(max(0, min(6, dec)))f", v)
    } else if attr == nil {
        text = translate(st.state, domain: st.domain)
    }
    let domain = st.domain
    if attr == nil && st.state == "on" {
        if domain == "light", let b = st.num("brightness"), b > 0 { text = "\(Int((b * 100 / 255).rounded()))%" }
        if domain == "fan", let p = st.num("percentage"), p > 0 { text = "\(Int(p))%" }
    }
    if attr == nil && !st.isUnavailable {
        switch domain {
        case "scene": text = "Activer"
        case "button", "input_button": text = "Appuyer"
        case "script": text = st.state == "on" ? "en cours" : "Lancer"
        case "climate", "water_heater":
            if item.decimals == nil, let t = st.num("current_temperature") {
                text = JSONValue.format(t) + "°"
            }
        case "weather":
            if let t = st.num("temperature") {
                text = JSONValue.format(t) + (st.str("temperature_unit") ?? "°")
            }
        default: break
        }
    }
    if !unit.isEmpty { text += " " + unit }

    var tone: Tone = .normal
    let active = activeStates.contains(st.state) && domain != "sensor"
    if st.isUnavailable || offline { tone = .dim } else if active { tone = .on }
    var color: String?
    if !st.isUnavailable && !offline {
        color = thresholdColor(parseThresholds(item.thresholds).rules, raw)
    }
    return ItemDisplay(symbol: symbol, variable: variable, text: text, tone: tone, color: color,
                       anim: (isActive(st) && !offline) ? anim : nil, badge: badge)
}

func defaultService(_ entityId: String) -> String? {
    let actions = ["light": "toggle", "switch": "toggle", "input_boolean": "toggle", "fan": "toggle",
                   "cover": "toggle", "automation": "toggle", "media_player": "media_play_pause",
                   "script": "turn_on", "scene": "turn_on", "button": "press", "input_button": "press",
                   "siren": "toggle", "humidifier": "toggle", "valve": "toggle"]
    let d = entityId.domain
    if d == "lock" { return nil }       // un verrou ne s'ouvre pas d'un simple clic : carte
    return actions[d].map { "\(d).\($0)" }
}

func resolveService(_ item: ItemConfig) -> String? {
    if item.service == "none" { return nil }
    return item.service.nonEmpty ?? defaultService(item.entityId)
}

func itemName(_ item: ItemConfig, _ st: EntityState?) -> String {
    item.label.nonEmpty ?? st?.name ?? item.entityId
}
