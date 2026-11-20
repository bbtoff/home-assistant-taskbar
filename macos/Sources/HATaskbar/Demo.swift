import AppKit

/// Mode demonstration (`--demo`) : donnees fictives, rien n'est enregistre ni envoye.
/// Sert aux captures d'ecran du README.
///   --demo                    elements et etats de demonstration
///   --demo-card <n>           ouvre la carte du n-ieme element (0 = le premier)
///   --demo-settings [onglet]  ouvre les reglages (items, connection, notifications, general)
///   --demo-picker             ouvre la fenetre « Ajouter des entites »
///   --demo-items 0,2,3        n'affiche que ces elements dans la barre (petits ecrans)
///   --demo-click-card         reglage « le clic ouvre la carte »
///   --demo-hover <s>          delai d'ouverture de la carte au survol (0 = jamais)
///   --demo-log <fichier>      journal des gestes (tests automatiques de l'interface)
enum Demo {
    static let enabled = CommandLine.arguments.contains("--demo")

    private static var lastLogged: [String: String] = [:]

    /// Ajoute une ligne au journal de --demo-log (une seule fois par cle si `key` est donne).
    static func log(_ line: String, key: String? = nil) {
        guard enabled, let path = arg("--demo-log"), !path.isEmpty else { return }
        if let k = key {
            if lastLogged[k] == line { return }
            lastLogged[k] = line
        }
        let data = Data((line + "\n").utf8)
        if let h = FileHandle(forWritingAtPath: path) {
            h.seekToEndOfFile()
            h.write(data)
            h.closeFile()
        } else {
            FileManager.default.createFile(atPath: path, contents: data)
        }
    }

    static func arg(_ name: String) -> String? {
        let a = CommandLine.arguments
        guard let i = a.firstIndex(of: name) else { return nil }
        return i + 1 < a.count && !a[i + 1].hasPrefix("--") ? a[i + 1] : ""
    }

    static var config: AppConfig {
        var c = AppConfig()
        c.haURL = "http://homeassistant.local:8123"
        var light = ItemConfig(entityId: "light.salon", label: "Salon")
        light.badge = nil
        var plug = ItemConfig(entityId: "switch.prise_bureau", label: "Bureau", icon: "plug")
        plug.badge = nil
        var heat = ItemConfig(entityId: "climate.thermostat", label: "Chauffage", icon: "flame_anim")
        heat.cardTitle = "Thermostat du salon"
        var power = ItemConfig(entityId: "sensor.consommation", label: "Consommation")
        power.sparkline = true
        var ext = ItemConfig(entityId: "sensor.temperature_exterieure", label: "Extérieur")
        ext.decimals = 1
        ext.thresholds = "< 5 bleu ; > 25 orange ; > 30 rouge"
        let scene = ItemConfig(entityId: "scene.cinema", label: "Ciné")
        let clim = ItemConfig(entityId: "climate.clim_salon", label: "Clim", icon: "snow_anim")
        let cuisson = ItemConfig(entityId: "timer.cuisson", label: "Cuisson")
        var sonnette = ItemConfig(entityId: "binary_sensor.sonnette", label: "Sonnette", icon: "bell")
        sonnette.camera = "camera.entree"
        c.items = [light, plug, heat, power, ext, scene, clim, cuisson, sonnette]
        // Elements du panneau (icone Maison)
        for (eid, label) in [("light.cuisine", "Cuisine"), ("switch.cafetiere", "Cafetière"), ("fan.plafond", "Ventilateur"),
                             ("cover.volet_salon", "Volet"), ("media_player.salon", "Enceinte"),
                             ("climate.clim_salon", "Clim"), ("lock.porte_entree", "Serrure"),
                             ("binary_sensor.porte_entree", "Porte d'entrée"), ("camera.entree", "Caméra entrée"),
                             ("sensor.humidite_salle_de_bain", "Humidité"), ("timer.lessive", "Lessive"),
                             ("person.alex", "Alex")] {
            var it = ItemConfig(entityId: eid, label: label)
            it.zone = "panel"
            c.items.append(it)
        }
        c.panelTitle = "Maison"
        if CommandLine.arguments.contains("--demo-panel-wide") {     // panneau elargi : plusieurs colonnes
            c.panelWidth = 720
            c.panelHeight = 600
        }
        // Widgets de bureau (positions pour un ecran de 1024 x 768, comme sur les Mac de GitHub)
        if !CommandLine.arguments.contains("--demo-no-widgets") {
            var w1 = WidgetConfig(entities: ["sensor.consommation"])
            w1.x = 40; w1.y = 470
            var w2 = WidgetConfig(entities: ["sensor.temperature_exterieure", "sensor.temperature_chambre"])
            w2.title = "Températures"
            w2.x = 40; w2.y = 250
            var w3 = WidgetConfig(entities: ["sensor.humidite_salle_de_bain"])
            w3.style = "value"; w3.size = "small"
            w3.x = 360; w3.y = 525
            c.widgets = [w1, w2, w3]
        }
        if let keep = arg("--demo-items") {
            let idx = Set(keep.split(separator: ",").compactMap { Int($0) })
            for i in c.items.indices where !idx.contains(i) && !c.items[i].inPanel { c.items[i].hidden = true }
        }
        c.notifications = [NotifyRule(entityId: "binary_sensor.porte_entree", to: "on", message: "La porte d'entrée est ouverte")]
        c.quietFrom = "22:00"
        c.quietTo = "07:00"
        if CommandLine.arguments.contains("--demo-click-card") { c.clickOpensCard = true }
        if let h = arg("--demo-hover"), let v = Double(h) { c.hoverCardDelay = v }
        return c
    }

    private static func ago(_ min: Double) -> Date { Date().addingTimeInterval(-min * 60) }
    /// Lancement de l'application (les minuteurs de demonstration en dependent).
    static let startDate = Date()

    static var states: [String: EntityState] {
        let list: [EntityState] = [
            EntityState(entityId: "light.salon", state: "on", attributes: [
                "friendly_name": "Lumière du salon", "brightness": 178, "color_mode": "color_temp",
                "supported_color_modes": ["color_temp", "hs"], "color_temp_kelvin": 3000,
                "min_color_temp_kelvin": 2200, "max_color_temp_kelvin": 6500], lastChanged: ago(12)),
            EntityState(entityId: "switch.prise_bureau", state: "off", attributes: [
                "friendly_name": "Prise du bureau", "device_class": "outlet"], lastChanged: ago(95)),
            EntityState(entityId: "climate.thermostat", state: "heat", attributes: [
                "friendly_name": "Thermostat", "current_temperature": 20.5, "temperature": 21,
                "hvac_action": "heating", "hvac_modes": ["off", "heat", "auto"], "min_temp": 7, "max_temp": 30,
                "target_temp_step": 0.5, "current_humidity": 48, "preset_modes": ["comfort", "eco", "away"],
                "preset_mode": "comfort"], lastChanged: ago(240)),
            EntityState(entityId: "sensor.consommation", state: "1240", attributes: [
                "friendly_name": "Consommation de la maison", "unit_of_measurement": "W", "device_class": "power"],
                lastChanged: ago(1)),
            EntityState(entityId: "sensor.temperature_exterieure", state: "8.4", attributes: [
                "friendly_name": "Extérieur", "unit_of_measurement": "°C", "device_class": "temperature"],
                lastChanged: ago(4)),
            EntityState(entityId: "scene.cinema", state: ISO8601DateFormatter().string(from: ago(1500)), attributes: [
                "friendly_name": "Soirée cinéma"], lastChanged: ago(1500)),
            EntityState(entityId: "climate.clim_salon", state: "cool", attributes: [
                "friendly_name": "Clim Salon", "current_temperature": 24.5, "temperature": 22,
                "hvac_action": "cooling", "hvac_modes": ["auto", "cool", "dry", "fan_only", "heat", "off"],
                "min_temp": 16, "max_temp": 30, "target_temp_step": 1], lastChanged: ago(1080)),
            EntityState(entityId: "light.cuisine", state: "on", attributes: [
                "friendly_name": "Lumière de la cuisine", "brightness": 102, "supported_color_modes": ["brightness"]],
                lastChanged: ago(25)),
            EntityState(entityId: "timer.cuisson", state: "active", attributes: [
                "friendly_name": "Minuteur cuisson", "duration": "0:10:00",
                "finishes_at": .string(ISO8601DateFormatter().string(from: startDate.addingTimeInterval(372)))],
                lastChanged: ago(4)),
            EntityState(entityId: "timer.lessive", state: "paused", attributes: [
                "friendly_name": "Minuteur lessive", "duration": "1:30:00", "remaining": "0:23:15"],
                lastChanged: ago(12)),
            EntityState(entityId: "switch.cafetiere", state: "off", attributes: [
                "friendly_name": "Cafetière", "device_class": "outlet"], lastChanged: ago(180)),
            EntityState(entityId: "camera.entree", state: "idle", attributes: [
                "friendly_name": "Caméra de l'entrée"], lastChanged: ago(2)),
            EntityState(entityId: "fan.plafond", state: "on", attributes: [
                "friendly_name": "Ventilateur de plafond", "percentage": 66, "percentage_step": 33.333333,
                "direction": "forward", "oscillating": false], lastChanged: ago(30)),
            EntityState(entityId: "cover.volet_salon", state: "open", attributes: [
                "friendly_name": "Volet du salon", "current_position": 75, "device_class": "shutter"], lastChanged: ago(300)),
            EntityState(entityId: "binary_sensor.porte_entree", state: "off", attributes: [
                "friendly_name": "Porte d'entrée", "device_class": "door"], lastChanged: ago(45)),
            EntityState(entityId: "binary_sensor.sonnette", state: "off", attributes: [
                "friendly_name": "Sonnette", "device_class": "sound"], lastChanged: ago(30)),
            EntityState(entityId: "person.alex", state: "home", attributes: [
                "friendly_name": "Alex", "entity_picture": "/demo/alex.png"], lastChanged: ago(95)),
            EntityState(entityId: "media_player.salon", state: "playing", attributes: [
                "entity_picture": "/demo/pochette.png",
                "friendly_name": "Enceinte du salon", "volume_level": 0.35, "media_title": "Clair de lune",
                "media_artist": "Claude Debussy", "is_volume_muted": false], lastChanged: ago(8)),
            EntityState(entityId: "sensor.temperature_chambre", state: "19.2", attributes: [
                "friendly_name": "Chambre", "unit_of_measurement": "°C", "device_class": "temperature"],
                lastChanged: ago(6)),
            EntityState(entityId: "sensor.humidite_salle_de_bain", state: "62", attributes: [
                "friendly_name": "Humidité salle de bain", "unit_of_measurement": "%", "device_class": "humidity"],
                lastChanged: ago(3)),
            EntityState(entityId: "sensor.capteur_porte_batterie", state: "14", attributes: [
                "friendly_name": "Pile du capteur de porte", "unit_of_measurement": "%", "device_class": "battery"],
                lastChanged: ago(600)),
            EntityState(entityId: "lock.porte_entree", state: "locked", attributes: [
                "friendly_name": "Serrure de l'entrée"], lastChanged: ago(45)),
            EntityState(entityId: "weather.maison", state: "partlycloudy", attributes: [
                "friendly_name": "Météo", "temperature": 9, "humidity": 71, "wind_speed": 14,
                "wind_speed_unit": "km/h", "temperature_unit": "°C"], lastChanged: ago(20)),
        ]
        return Dictionary(list.map { ($0.entityId, $0) }, uniquingKeysWith: { a, _ in a })
    }

    static let areas: [String: String] = [
        "light.salon": "Salon", "climate.thermostat": "Salon", "fan.plafond": "Chambre", "cover.volet_salon": "Salon",
        "switch.prise_bureau": "Bureau", "media_player.salon": "Salon", "binary_sensor.porte_entree": "Entrée",
        "lock.porte_entree": "Entrée", "sensor.humidite_salle_de_bain": "Salle de bain",
        "sensor.temperature_exterieure": "Jardin", "light.cuisine": "Cuisine", "switch.cafetiere": "Cuisine",
        "camera.entree": "Entrée", "climate.clim_salon": "Salon", "timer.lessive": "Buanderie", "sensor.capteur_porte_batterie": "Entrée",
    ]

    /// Historique fictif, regulier d'une execution a l'autre.
    static func history(_ entityId: String, hours: Double) -> [(Date, String)] {
        let n = 160
        let now = Date()
        var out: [(Date, String)] = []
        for i in 0..<n {
            let t = now.addingTimeInterval(-hours * 3600 * Double(n - i) / Double(n))
            let h = Calendar.current.component(.hour, from: t)
            let m = Double(Calendar.current.component(.minute, from: t)) / 60
            let day = (Double(h) + m) / 24 * 2 * Double.pi
            let wobble = sin(Double(i) * 1.7) * 0.5 + sin(Double(i) * 0.37) * 0.5
            let v: Double
            switch entityId {
            case "sensor.consommation":
                let meals = exp(-pow(Double(h) + m - 12.5, 2) / 2) + 1.4 * exp(-pow(Double(h) + m - 19.5, 2) / 3)
                v = 380 + 1300 * meals + 160 * wobble
            case "sensor.temperature_exterieure":
                v = 7 + 4 * sin(day - 2.2) + 0.5 * wobble
            case "sensor.temperature_chambre":
                v = 19 + 1.2 * sin(day - 2.8) + 0.2 * wobble
            case "sensor.humidite_salle_de_bain":
                v = 55 + 8 * sin(day) + 3 * wobble
            default:
                return [(now.addingTimeInterval(-hours * 2400), "off"), (now.addingTimeInterval(-hours * 1500), "on"),
                        (now.addingTimeInterval(-hours * 900), "off"), (now.addingTimeInterval(-720), "on")]
            }
            out.append((t, String(format: "%.1f", v)))
        }
        // Les derniers points rejoignent la valeur actuelle (pas de saut au bout de la courbe)
        if let end = states[entityId].flatMap({ Double($0.state) }) {
            let k = 12
            for j in 0..<k {
                let i = n - k + j
                let t = Double(j + 1) / Double(k)
                let v = (Double(out[i].1) ?? end) * (1 - t) + end * t
                out[i] = (out[i].0, String(format: "%.1f", v))
            }
        }
        return out
    }

    static var forecast: [[String: JSONValue]] {
        let f = ISO8601DateFormatter()
        let days: [(String, Double, Double)] = [("rainy", 11, 6), ("cloudy", 10, 5), ("partlycloudy", 12, 4),
                                               ("sunny", 13, 3), ("sunny", 14, 5)]
        return days.enumerated().map { i, d in
            ["datetime": .string(f.string(from: Date().addingTimeInterval(Double(i + 1) * 86400))),
             "condition": .string(d.0), "temperature": .number(d.1), "templow": .number(d.2)]
        }
    }

    /// Image de demonstration d'une camera : un degrade, le nom et l'heure (change a chaque image).
    static func cameraImage(_ entityId: String) -> NSImage {
        let size = NSSize(width: 640, height: 360)
        return NSImage(size: size, flipped: false) { rect in
            NSGradient(colors: [NSColor(srgbRed: 0.18, green: 0.26, blue: 0.33, alpha: 1),
                                NSColor(srgbRed: 0.45, green: 0.52, blue: 0.44, alpha: 1)])?.draw(in: rect, angle: -70)
            NSColor(white: 1, alpha: 0.12).setFill()
            NSBezierPath(rect: NSRect(x: 230, y: 40, width: 180, height: 230)).fill()     // porte
            let f = DateFormatter()
            f.dateFormat = "HH:mm:ss"
            let text = "\(entityId)   \(f.string(from: Date()))" as NSString
            text.draw(at: NSPoint(x: 18, y: 18), withAttributes: [.font: NSFont.monospacedSystemFont(ofSize: 22, weight: .medium),
                                                                   .foregroundColor: NSColor.white])
            return true
        }
    }

    /// Photo ou pochette de demonstration (entity_picture « /demo/... »).
    static func picture(_ url: String) -> NSImage {
        let size = NSSize(width: 300, height: 300)
        let person = url.contains("alex")
        return NSImage(size: size, flipped: false) { rect in
            if person {
                NSColor(srgbRed: 0.36, green: 0.55, blue: 0.85, alpha: 1).setFill()
                rect.fill()
                NSColor(white: 1, alpha: 0.9).setFill()
                NSBezierPath(ovalIn: NSRect(x: 105, y: 150, width: 90, height: 90)).fill()     // tete
                NSBezierPath(ovalIn: NSRect(x: 60, y: -40, width: 180, height: 170)).fill()    // epaules
            } else {
                NSGradient(colors: [NSColor(srgbRed: 0.10, green: 0.12, blue: 0.30, alpha: 1),
                                    NSColor(srgbRed: 0.55, green: 0.35, blue: 0.75, alpha: 1)])?.draw(in: rect, angle: 60)
                NSColor(white: 1, alpha: 0.85).setFill()
                NSBezierPath(ovalIn: NSRect(x: 170, y: 170, width: 70, height: 70)).fill()     // lune
                ("Clair de lune" as NSString).draw(at: NSPoint(x: 24, y: 30), withAttributes: [
                    .font: NSFont.systemFont(ofSize: 30, weight: .semibold), .foregroundColor: NSColor.white])
            }
            return true
        }
    }
}
