import Foundation

/// Mode demonstration (`--demo`) : donnees fictives, rien n'est enregistre ni envoye.
/// Sert aux captures d'ecran du README.
///   --demo                    elements et etats de demonstration
///   --demo-card <n>           ouvre la carte du n-ieme element (0 = le premier)
///   --demo-settings [onglet]  ouvre les reglages (items, connection, notifications, general)
///   --demo-picker             ouvre la fenetre « Ajouter des entites »
///   --demo-items 0,2,3        n'affiche que ces elements dans la barre (petits ecrans)
enum Demo {
    static let enabled = CommandLine.arguments.contains("--demo")

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
        let power = ItemConfig(entityId: "sensor.consommation", label: "Consommation")
        var ext = ItemConfig(entityId: "sensor.temperature_exterieure", label: "Extérieur")
        ext.decimals = 1
        ext.thresholds = "< 5 bleu ; > 25 orange ; > 30 rouge"
        let scene = ItemConfig(entityId: "scene.cinema", label: "Ciné")
        c.items = [light, plug, heat, power, ext, scene]
        if let keep = arg("--demo-items") {
            let idx = Set(keep.split(separator: ",").compactMap { Int($0) })
            for i in c.items.indices where !idx.contains(i) { c.items[i].hidden = true }
        }
        c.notifications = [NotifyRule(entityId: "binary_sensor.porte_entree", to: "on", message: "La porte d'entrée est ouverte")]
        c.quietFrom = "22:00"
        c.quietTo = "07:00"
        return c
    }

    private static func ago(_ min: Double) -> Date { Date().addingTimeInterval(-min * 60) }

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
                "friendly_name": "Température extérieure", "unit_of_measurement": "°C", "device_class": "temperature"],
                lastChanged: ago(4)),
            EntityState(entityId: "scene.cinema", state: ISO8601DateFormatter().string(from: ago(1500)), attributes: [
                "friendly_name": "Soirée cinéma"], lastChanged: ago(1500)),
            EntityState(entityId: "fan.plafond", state: "on", attributes: [
                "friendly_name": "Ventilateur de plafond", "percentage": 66, "percentage_step": 33.333333,
                "direction": "forward", "oscillating": false], lastChanged: ago(30)),
            EntityState(entityId: "cover.volet_salon", state: "open", attributes: [
                "friendly_name": "Volet du salon", "current_position": 75, "device_class": "shutter"], lastChanged: ago(300)),
            EntityState(entityId: "binary_sensor.porte_entree", state: "off", attributes: [
                "friendly_name": "Porte d'entrée", "device_class": "door"], lastChanged: ago(45)),
            EntityState(entityId: "media_player.salon", state: "playing", attributes: [
                "friendly_name": "Enceinte du salon", "volume_level": 0.35, "media_title": "Clair de lune",
                "media_artist": "Claude Debussy", "is_volume_muted": false], lastChanged: ago(8)),
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
        "sensor.temperature_exterieure": "Jardin", "sensor.capteur_porte_batterie": "Entrée",
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
            case "sensor.humidite_salle_de_bain":
                v = 55 + 8 * sin(day) + 3 * wobble
            default:
                return [(now.addingTimeInterval(-hours * 2400), "off"), (now.addingTimeInterval(-hours * 1500), "on"),
                        (now.addingTimeInterval(-hours * 900), "off"), (now.addingTimeInterval(-720), "on")]
            }
            out.append((t, String(format: "%.1f", v)))
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
}
