import Charts
import SwiftUI

/// Carte de controle (appui long, ⌥-clic ou clic sur un capteur), comme dans Home Assistant.
struct CardView: View {
    @ObservedObject var model: AppModel
    let itemId: UUID
    var edit: () -> Void

    private var item: ItemConfig? { model.config.items.first { $0.id == itemId } }

    var body: some View {
        Group {
            if let item = item {
                content(item)
            } else {
                Text("Cet élément n'existe plus.").padding()
            }
        }
        .frame(width: 330)
    }

    @ViewBuilder
    private func content(_ item: ItemConfig) -> some View {
        let st = model.states[item.entityId]
        VStack(alignment: .leading, spacing: 14) {
            CardHeader(model: model, item: item, st: st)
            if item.entityId == batteriesId {
                BatteryList(model: model)
            } else if let st = st {
                DomainControls(model: model, item: item, st: st)
                if timerDomains.contains(st.domain) {
                    TimerRow(model: model, entityId: st.entityId)
                }
            } else {
                Text(model.offline ? "Home Assistant ne répond pas." : "Entité introuvable : \(item.entityId)")
                    .foregroundStyle(.secondary)
            }
            Divider()
            HStack {
                Button("Modifier l'élément…", action: edit)
                Spacer()
                Button("Ouvrir Home Assistant") {
                    let base = model.config.haURL.trimmingCharacters(in: CharacterSet(charactersIn: "/ "))
                    if let u = URL(string: base + "/history?entity_id=" + item.entityId) { NSWorkspace.shared.open(u) }
                }
            }
            .buttonStyle(.link)
            .font(.callout)
        }
        .padding(16)
    }
}

let timerDomains: Set<String> = ["light", "switch", "fan", "media_player", "climate", "input_boolean", "humidifier"]

// MARK: - En-tete

struct CardHeader: View {
    @ObservedObject var model: AppModel
    let item: ItemConfig
    let st: EntityState?

    var body: some View {
        let d = displayFor(item, states: model.states, offline: model.offline, batteryLow: model.config.batteryLow,
                           timerLeft: nil)
        HStack(alignment: .center, spacing: 12) {
            ZStack {
                Circle().fill(d.tone == .on ? Color(nsColor: .haOn).opacity(0.18) : Color.secondary.opacity(0.12))
                Image(systemName: d.symbol ?? "circle")
                    .font(.system(size: 18))
                    .foregroundStyle(d.tone == .on ? Color(nsColor: .haOn) : Color.primary)
            }
            .frame(width: 38, height: 38)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.cardTitle.nonEmpty ?? itemName(item, st))
                    .font(.headline)
                    .lineLimit(2)
                Text(subtitle(d))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let st = st, toggleable(st) {
                Toggle("", isOn: Binding(
                    get: { activeStates.contains(st.state) },
                    set: { on in model.call("homeassistant.turn_\(on ? "on" : "off")", entity: st.entityId) }))
                    .toggleStyle(.switch)
                    .labelsHidden()
                    .disabled(st.isUnavailable)
            }
        }
    }

    private func toggleable(_ st: EntityState) -> Bool {
        ["light", "switch", "input_boolean", "fan", "automation", "siren", "humidifier"].contains(st.domain)
    }

    private func subtitle(_ d: ItemDisplay) -> String {
        guard let st = st else { return item.entityId == batteriesId ? "Piles sous \(Int(model.config.batteryLow)) %" : "" }
        var s = d.text
        if ["scene", "button", "input_button", "script"].contains(st.domain) { s = translate(st.state, domain: "x") }
        if ["scene", "button", "input_button"].contains(st.domain) { s = "Dernière fois" }
        if let ch = st.lastChanged {
            let f = RelativeDateTimeFormatter()
            f.locale = Locale(identifier: "fr_FR")
            s += " · " + f.localizedString(for: ch, relativeTo: Date())
        }
        return s
    }
}

// MARK: - Commandes selon le type d'entite

struct DomainControls: View {
    @ObservedObject var model: AppModel
    let item: ItemConfig
    let st: EntityState

    var body: some View {
        switch st.domain {
        case "light": LightControls(model: model, st: st)
        case "fan": FanControls(model: model, st: st)
        case "cover": CoverControls(model: model, st: st)
        case "climate", "water_heater": ClimateControls(model: model, st: st)
        case "media_player": MediaControls(model: model, st: st)
        case "lock": LockControls(model: model, st: st)
        case "scene", "script", "button", "input_button": ActivateControls(model: model, st: st)
        case "input_number", "number": NumberControls(model: model, st: st)
        case "input_select", "select": SelectControls(model: model, st: st)
        case "vacuum": VacuumControls(model: model, st: st)
        case "weather": WeatherControls(model: model, st: st)
        case "sensor":
            if Double(st.state) != nil {
                HistoryView(model: model, entityId: st.entityId, numeric: true,
                            unit: item.unit.nonEmpty ?? st.str("unit_of_measurement") ?? "")
            } else {
                HistoryView(model: model, entityId: st.entityId, numeric: false, unit: "")
            }
        default:
            HistoryView(model: model, entityId: st.entityId, numeric: false, unit: "")
        }
    }
}

/// Curseur qui n'envoie la valeur qu'au relachement, et suit l'etat reel le reste du temps.
struct CommitSlider: View {
    let title: String
    let value: Double
    let range: ClosedRange<Double>
    var step: Double = 1
    var unit: String = " %"
    let commit: (Double) -> Void

    @State private var local: Double = 0
    @State private var editing = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(title).foregroundStyle(.secondary)
                Spacer()
                Text(JSONValue.format(rounded(local)) + unit).monospacedDigit()
            }
            .font(.callout)
            // Sans « step » : SwiftUI dessinerait une graduation par pas sous le curseur
            Slider(value: $local, in: range, onEditingChanged: { e in
                editing = e
                if !e { commit(rounded(local)) }
            })
        }
        .onAppear { local = clamp(value) }
        .onChange(of: value) { v in if !editing { local = clamp(v) } }
    }

    private func clamp(_ v: Double) -> Double { min(range.upperBound, max(range.lowerBound, v)) }
    private func rounded(_ v: Double) -> Double { clamp(step > 0 ? (v / step).rounded() * step : v) }
}

struct LightControls: View {
    @ObservedObject var model: AppModel
    let st: EntityState

    private var modes: Set<String> { Set(st.attributes["supported_color_modes"]?.stringArray ?? []) }
    private var on: Bool { st.state == "on" }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if !modes.subtracting(["onoff"]).isEmpty || st.num("brightness") != nil {
                CommitSlider(title: "Luminosité", value: on ? ((st.num("brightness") ?? 0) * 100 / 255).rounded() : 0,
                             range: 0...100) { v in
                    if v <= 0 { model.call("light.turn_off", entity: st.entityId) }
                    else { model.call("light.turn_on", entity: st.entityId, ["brightness_pct": .number(v)]) }
                }
            }
            if modes.contains("color_temp") {
                let lo = st.num("min_color_temp_kelvin") ?? 2000, hi = st.num("max_color_temp_kelvin") ?? 6500
                CommitSlider(title: "Blanc (chaud → froid)", value: st.num("color_temp_kelvin") ?? (lo + hi) / 2,
                             range: lo...max(hi, lo + 1), step: 50, unit: " K") { v in
                    model.call("light.turn_on", entity: st.entityId, ["color_temp_kelvin": .number(v)])
                }
            }
            if !modes.intersection(["hs", "rgb", "rgbw", "rgbww", "xy"]).isEmpty {
                HStack(spacing: 8) {
                    ForEach(Array(swatches.enumerated()), id: \.offset) { _, hs in
                        Button {
                            model.call("light.turn_on", entity: st.entityId, ["hs_color": [.number(hs.0), .number(hs.1)]])
                        } label: {
                            Circle()
                                .fill(Color(hue: hs.0 / 360, saturation: hs.1 / 100, brightness: 1))
                                .frame(width: 22, height: 22)
                                .overlay(Circle().stroke(Color.secondary.opacity(0.4)))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            HStack {
                Text("Ambiance").foregroundStyle(.secondary).font(.callout)
                Spacer()
                ForEach(presets, id: \.0) { p in
                    Button(p.0) {
                        var data: [String: JSONValue] = ["brightness_pct": .number(p.1)]
                        if modes.contains("color_temp") { data["color_temp_kelvin"] = .number(p.2) }
                        model.call("light.turn_on", entity: st.entityId, data)
                    }
                }
            }
            .controlSize(.small)
        }
    }

    private let swatches: [(Double, Double)] = [(0, 100), (30, 100), (55, 100), (120, 80), (190, 80), (230, 90), (280, 70), (320, 70)]
    private let presets: [(String, Double, Double)] = [("Lecture", 100, 4000), ("Détente", 40, 2700), ("Veilleuse", 5, 2200)]
}

struct FanControls: View {
    @ObservedObject var model: AppModel
    let st: EntityState

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if st.attributes["percentage"] != nil {
                let step = max(1, st.num("percentage_step") ?? 1)
                let speeds = Int((100 / step).rounded())
                if speeds >= 2 && speeds <= 10 {
                    HStack {
                        Text("Vitesse").foregroundStyle(.secondary)
                        Spacer()
                        Picker("", selection: Binding(
                            get: { st.state == "on" ? Int(((st.num("percentage") ?? 0) / step).rounded()) : 0 },
                            set: { n in
                                if n == 0 { model.call("fan.turn_off", entity: st.entityId) }
                                else { model.call("fan.set_percentage", entity: st.entityId, ["percentage": .number((Double(n) * step).rounded())]) }
                            })) {
                            Text("0").tag(0)
                            ForEach(1...speeds, id: \.self) { Text("\($0)").tag($0) }
                        }
                        .pickerStyle(.segmented)
                        .labelsHidden()
                    }
                } else {
                    CommitSlider(title: "Vitesse", value: st.state == "on" ? st.num("percentage") ?? 0 : 0,
                                 range: 0...100, step: step) { v in
                        if v <= 0 { model.call("fan.turn_off", entity: st.entityId) }
                        else { model.call("fan.set_percentage", entity: st.entityId, ["percentage": .number(v.rounded())]) }
                    }
                }
            }
            if let osc = st.attributes["oscillating"]?.bool {
                Toggle("Oscillation", isOn: Binding(get: { osc }, set: {
                    model.call("fan.oscillate", entity: st.entityId, ["oscillating": .bool($0)])
                }))
            }
            if let dir = st.str("direction") {
                Picker("Sens", selection: Binding(get: { dir }, set: {
                    model.call("fan.set_direction", entity: st.entityId, ["direction": .string($0)])
                })) {
                    Text("↻ Été").tag("forward")
                    Text("↺ Hiver").tag("reverse")
                }
                .pickerStyle(.segmented)
            }
            PresetPicker(model: model, st: st, service: "fan.set_preset_mode")
        }
    }
}

struct PresetPicker: View {
    @ObservedObject var model: AppModel
    let st: EntityState
    let service: String

    var body: some View {
        let modes = st.attributes["preset_modes"]?.stringArray ?? []
        if !modes.isEmpty {
            Picker("Mode", selection: Binding(get: { st.str("preset_mode") ?? "" }, set: {
                model.call(service, entity: st.entityId, ["preset_mode": .string($0)])
            })) {
                if !modes.contains(st.str("preset_mode") ?? "") { Text("—").tag("") }
                ForEach(modes, id: \.self) { Text(presetName($0)).tag($0) }
            }
        }
    }
}

func presetName(_ m: String) -> String {
    let names = ["none": "Aucun", "eco": "Éco", "away": "Absent", "boost": "Boost", "comfort": "Confort",
                 "home": "Maison", "sleep": "Nuit", "activity": "Activité", "natural": "Naturel", "nature": "Naturel",
                 "auto": "Auto", "smart": "Intelligent", "cool": "Frais", "breeze": "Brise", "normal": "Normal",
                 "silent": "Silencieux", "turbo": "Turbo", "low": "Faible", "medium": "Moyen", "high": "Fort"]
    return names[m.lowercased()] ?? m
}

struct CoverControls: View {
    @ObservedObject var model: AppModel
    let st: EntityState

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Button { model.call("cover.open_cover", entity: st.entityId) } label: {
                    Label("Ouvrir", systemImage: "chevron.up")
                }
                Button { model.call("cover.stop_cover", entity: st.entityId) } label: {
                    Label("Stop", systemImage: "stop.fill")
                }
                Button { model.call("cover.close_cover", entity: st.entityId) } label: {
                    Label("Fermer", systemImage: "chevron.down")
                }
            }
            if let pos = st.num("current_position") {
                CommitSlider(title: "Position", value: pos, range: 0...100) { v in
                    model.call("cover.set_cover_position", entity: st.entityId, ["position": .number(v.rounded())])
                }
                HStack {
                    ForEach([25, 50, 75], id: \.self) { p in
                        Button("\(p) %") {
                            model.call("cover.set_cover_position", entity: st.entityId, ["position": .number(Double(p))])
                        }
                    }
                }
                .controlSize(.small)
            }
        }
    }
}

struct ClimateControls: View {
    @ObservedObject var model: AppModel
    let st: EntityState
    @State private var target: Double?
    @State private var sendTask: Task<Void, Never>?

    private var hvacNames: [String: String] {
        ["off": "Arrêt", "heat": "Chauffe", "cool": "Froid", "heat_cool": "Auto", "auto": "Auto", "dry": "Sec",
         "fan_only": "Ventil.", "eco": "Éco", "electric": "Électrique", "performance": "Performance",
         "high_demand": "Forte demande", "heat_pump": "Pompe à chaleur", "gas": "Gaz"]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let t = st.num("temperature") {
                let step = st.num("target_temp_step") ?? 0.5
                let shown = target ?? t
                HStack {
                    Button { change(-step, from: shown) } label: { Image(systemName: "minus").frame(width: 24, height: 20) }
                    Spacer()
                    VStack(spacing: 0) {
                        Text(JSONValue.format(shown) + "°").font(.system(size: 30, weight: .light)).monospacedDigit()
                        Text("consigne").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button { change(step, from: shown) } label: { Image(systemName: "plus").frame(width: 24, height: 20) }
                }
            }
            HStack(spacing: 14) {
                if let cur = st.num("current_temperature") {
                    Label(JSONValue.format(cur) + "°", systemImage: "thermometer.medium")
                }
                if let h = st.num("current_humidity") {
                    Label(JSONValue.format(h) + " %", systemImage: "humidity")
                }
                if let a = st.str("hvac_action") {
                    Text(["heating": "chauffe", "cooling": "refroidit", "idle": "au repos", "off": "arrêté",
                          "drying": "sèche", "fan": "ventile", "preheating": "préchauffe"][a] ?? a)
                        .foregroundStyle(a == "heating" ? Color.orange : a == "cooling" ? Color.blue : Color.secondary)
                }
            }
            .font(.callout)
            let modes = st.attributes["hvac_modes"]?.stringArray ?? st.attributes["operation_list"]?.stringArray ?? []
            if !modes.isEmpty && st.domain == "climate" {
                Picker("", selection: Binding(get: { st.state }, set: {
                    model.call("climate.set_hvac_mode", entity: st.entityId, ["hvac_mode": .string($0)])
                })) {
                    ForEach(modes, id: \.self) { Text(hvacNames[$0] ?? $0).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
            } else if !modes.isEmpty {
                Picker("Mode", selection: Binding(get: { st.str("operation_mode") ?? st.state }, set: {
                    model.call("water_heater.set_operation_mode", entity: st.entityId, ["operation_mode": .string($0)])
                })) {
                    ForEach(modes, id: \.self) { Text(hvacNames[$0] ?? $0).tag($0) }
                }
            }
            PresetPicker(model: model, st: st, service: "\(st.domain).set_preset_mode")
        }
        .onChange(of: st.num("temperature")) { _ in if sendTask == nil { target = nil } }
    }

    private func change(_ delta: Double, from: Double) {
        let step = st.num("target_temp_step") ?? 0.5
        let lo = st.num("min_temp") ?? 5, hi = st.num("max_temp") ?? 35
        let v = max(lo, min(hi, ((from + delta) / step).rounded() * step))
        target = v
        sendTask?.cancel()
        let eid = st.entityId, dom = st.domain
        sendTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 700_000_000)
            if Task.isCancelled { return }
            model.call("\(dom).set_temperature", entity: eid, ["temperature": .number(v)])
            sendTask = nil
        }
    }
}

struct MediaControls: View {
    @ObservedObject var model: AppModel
    let st: EntityState

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let title = st.str("media_title") {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.body.weight(.medium)).lineLimit(2)
                    if let a = st.str("media_artist") ?? st.str("media_album_name") {
                        Text(a).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
            }
            if let dur = st.num("media_duration"), dur > 0, let pos = st.num("media_position") {
                ProgressView(value: min(pos, dur), total: dur)
            }
            HStack(spacing: 18) {
                Spacer()
                Button { model.call("media_player.media_previous_track", entity: st.entityId) } label: {
                    Image(systemName: "backward.fill")
                }
                Button { model.call("media_player.media_play_pause", entity: st.entityId) } label: {
                    Image(systemName: st.state == "playing" ? "pause.fill" : "play.fill").font(.title2)
                }
                Button { model.call("media_player.media_next_track", entity: st.entityId) } label: {
                    Image(systemName: "forward.fill")
                }
                Spacer()
            }
            .buttonStyle(.plain)
            if let vol = st.num("volume_level") {
                HStack {
                    Button {
                        model.call("media_player.volume_mute", entity: st.entityId,
                                   ["is_volume_muted": .bool(!(st.attributes["is_volume_muted"]?.bool ?? false))])
                    } label: {
                        Image(systemName: st.attributes["is_volume_muted"]?.bool == true ? "speaker.slash.fill" : "speaker.wave.2.fill")
                    }
                    .buttonStyle(.plain)
                    CommitSlider(title: "Volume", value: (vol * 100).rounded(), range: 0...100) { v in
                        model.call("media_player.volume_set", entity: st.entityId, ["volume_level": .number(v / 100)])
                    }
                }
            }
            let sources = st.attributes["source_list"]?.stringArray ?? []
            if !sources.isEmpty {
                Picker("Source", selection: Binding(get: { st.str("source") ?? "" }, set: {
                    model.call("media_player.select_source", entity: st.entityId, ["source": .string($0)])
                })) {
                    if !sources.contains(st.str("source") ?? "") { Text("—").tag("") }
                    ForEach(sources, id: \.self) { Text($0).tag($0) }
                }
            }
            HStack {
                Spacer()
                Button(st.state == "off" ? "Allumer" : "Éteindre") {
                    model.call("media_player.turn_\(st.state == "off" ? "on" : "off")", entity: st.entityId)
                }
                .controlSize(.small)
            }
        }
    }
}

struct LockControls: View {
    @ObservedObject var model: AppModel
    let st: EntityState

    var body: some View {
        let locked = st.state == "locked"
        Button {
            model.call("lock.\(locked ? "unlock" : "lock")", entity: st.entityId)
        } label: {
            Label(locked ? "Déverrouiller" : "Verrouiller", systemImage: locked ? "lock.open" : "lock")
                .frame(maxWidth: .infinity)
        }
        .controlSize(.large)
        .disabled(st.isUnavailable)
    }
}

struct ActivateControls: View {
    @ObservedObject var model: AppModel
    let st: EntityState

    var body: some View {
        Button {
            model.call(action.1, entity: st.entityId)
        } label: {
            Text(action.0).frame(maxWidth: .infinity)
        }
        .controlSize(.large)
        .disabled(st.isUnavailable)
    }

    private var action: (String, String) {
        switch st.domain {
        case "scene": return ("Activer la scène", "scene.turn_on")
        case "script": return st.state == "on" ? ("Arrêter", "script.turn_off") : ("Lancer le script", "script.turn_on")
        default: return ("Appuyer", "\(st.domain).press")
        }
    }
}

struct NumberControls: View {
    @ObservedObject var model: AppModel
    let st: EntityState

    var body: some View {
        let lo = st.num("min") ?? 0, hi = max(st.num("max") ?? 100, lo + 1)
        CommitSlider(title: "Valeur", value: Double(st.state) ?? lo, range: lo...hi, step: st.num("step") ?? 1,
                     unit: (st.str("unit_of_measurement").map { " " + $0 }) ?? "") { v in
            model.call("\(st.domain).set_value", entity: st.entityId, ["value": .number(v)])
        }
    }
}

struct SelectControls: View {
    @ObservedObject var model: AppModel
    let st: EntityState

    var body: some View {
        let options = st.attributes["options"]?.stringArray ?? []
        Picker("Choix", selection: Binding(get: { st.state }, set: {
            model.call("\(st.domain).select_option", entity: st.entityId, ["option": .string($0)])
        })) {
            if !options.contains(st.state) { Text(st.state).tag(st.state) }
            ForEach(options, id: \.self) { Text($0).tag($0) }
        }
    }
}

struct VacuumControls: View {
    @ObservedObject var model: AppModel
    let st: EntityState

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Button { model.call("vacuum.start", entity: st.entityId) } label: { Label("Démarrer", systemImage: "play.fill") }
                Button { model.call("vacuum.pause", entity: st.entityId) } label: { Label("Pause", systemImage: "pause.fill") }
                Button { model.call("vacuum.return_to_base", entity: st.entityId) } label: { Label("Base", systemImage: "house") }
            }
            HStack {
                if let b = st.num("battery_level") { Label("\(Int(b)) %", systemImage: "battery.75") }
                Spacer()
                Button("Localiser") { model.call("vacuum.locate", entity: st.entityId) }.controlSize(.small)
            }
            .font(.callout)
            let speeds = st.attributes["fan_speed_list"]?.stringArray ?? []
            if !speeds.isEmpty {
                Picker("Aspiration", selection: Binding(get: { st.str("fan_speed") ?? "" }, set: {
                    model.call("vacuum.set_fan_speed", entity: st.entityId, ["fan_speed": .string($0)])
                })) {
                    if !speeds.contains(st.str("fan_speed") ?? "") { Text("—").tag("") }
                    ForEach(speeds, id: \.self) { Text(presetName($0)).tag($0) }
                }
            }
        }
    }
}

struct WeatherControls: View {
    @ObservedObject var model: AppModel
    let st: EntityState
    @State private var forecast: [[String: JSONValue]] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 14) {
                Image(systemName: weatherSymbol[st.state] ?? "cloud").font(.system(size: 30))
                VStack(alignment: .leading) {
                    if let t = st.num("temperature") {
                        Text(JSONValue.format(t) + (st.str("temperature_unit") ?? "°")).font(.system(size: 26, weight: .light))
                    }
                    Text(weatherText[st.state] ?? st.state).foregroundStyle(.secondary)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    if let h = st.num("humidity") { Label("\(Int(h)) %", systemImage: "humidity") }
                    if let w = st.num("wind_speed") {
                        Label(JSONValue.format(w) + " " + (st.str("wind_speed_unit") ?? "km/h"), systemImage: "wind")
                    }
                }
                .font(.callout)
            }
            if !forecast.isEmpty {
                HStack(spacing: 0) {
                    ForEach(Array(forecast.prefix(5).enumerated()), id: \.offset) { _, f in
                        VStack(spacing: 4) {
                            Text(day(f["datetime"]?.string)).font(.caption).foregroundStyle(.secondary)
                            Image(systemName: weatherSymbol[f["condition"]?.string ?? ""] ?? "cloud")
                            Text(f["temperature"]?.double.map { JSONValue.format($0.rounded()) + "°" } ?? "")
                                .font(.callout)
                            Text(f["templow"]?.double.map { JSONValue.format($0.rounded()) + "°" } ?? "")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                    }
                }
            }
        }
        .task(id: st.entityId) {
            if Demo.enabled { forecast = Demo.forecast; return }
            if let c = model.client, let f = try? await c.forecast(st.entityId) { forecast = f }
        }
    }

    private func day(_ s: String?) -> String {
        guard let d = parseHADate(s) else { return "" }
        let f = DateFormatter()
        f.locale = Locale(identifier: "fr_FR")
        f.dateFormat = "EEE"
        return f.string(from: d).capitalized
    }
}

struct TimerRow: View {
    @ObservedObject var model: AppModel
    let entityId: String

    var body: some View {
        HStack {
            Image(systemName: "timer").foregroundStyle(.secondary)
            if let left = model.timerLeft(entityId) {
                Text("Arrêt dans \(max(1, Int((left / 60).rounded()))) min")
                Spacer()
                Button("Annuler") { model.cancelTimer(entityId) }
            } else {
                Text("Arrêt dans").foregroundStyle(.secondary).lineLimit(1).fixedSize()
                Spacer()
                ForEach([(15, "15 min"), (30, "30 min"), (60, "1 h"), (120, "2 h")], id: \.0) { m in
                    Button(m.1) { model.startTimer(entityId, minutes: m.0) }
                }
            }
        }
        .controlSize(.small)
        .font(.callout)
    }
}

struct BatteryList: View {
    @ObservedObject var model: AppModel

    var body: some View {
        let low = lowBatteries(model.states, threshold: model.config.batteryLow)
        if low.isEmpty {
            Label("Toutes les piles sont au-dessus de \(Int(model.config.batteryLow)) %.", systemImage: "checkmark.circle")
                .foregroundStyle(.secondary)
        } else {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(low, id: \.id) { b in
                    HStack {
                        Text(b.name).lineLimit(1)
                        Spacer()
                        Text(b.level == 0 && b.id.hasPrefix("binary_sensor.") ? "faible" : "\(Int(b.level)) %")
                            .foregroundStyle(b.level < 10 ? Color.red : Color.orange)
                            .monospacedDigit()
                    }
                }
            }
        }
    }
}

// MARK: - Historique

struct HistPoint: Identifiable {
    let id: Int
    let date: Date
    let value: Double
}

struct HistoryView: View {
    @ObservedObject var model: AppModel
    let entityId: String
    let numeric: Bool
    let unit: String

    @State private var hours: Double = 24
    @State private var raw: [(Date, String)] = []
    @State private var loading = false
    @State private var failed = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if numeric, let st = model.states[entityId] {
                Text(st.state + (unit.isEmpty ? "" : " " + unit))
                    .font(.system(size: 28, weight: .light))
                    .monospacedDigit()
            }
            Picker("", selection: $hours) {
                Text("24 h").tag(24.0)
                Text("7 jours").tag(168.0)
                Text("30 jours").tag(720.0)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            if loading && raw.isEmpty {
                ProgressView().frame(maxWidth: .infinity, minHeight: 60)
            } else if failed {
                Text("Historique indisponible.").foregroundStyle(.secondary)
            } else if numeric {
                let pts = points
                if pts.count < 2 {
                    Text("Pas assez de valeurs sur cette période.").foregroundStyle(.secondary)
                } else {
                    Chart(pts) { p in
                        LineMark(x: .value("Heure", p.date), y: .value("Valeur", p.value))
                            .interpolationMethod(.monotone)
                        AreaMark(x: .value("Heure", p.date), y: .value("Valeur", p.value))
                            .foregroundStyle(.linearGradient(colors: [Color.accentColor.opacity(0.25), .clear],
                                                             startPoint: .top, endPoint: .bottom))
                            .interpolationMethod(.monotone)
                    }
                    .chartYScale(domain: .automatic(includesZero: false))
                    .chartXAxis {
                        AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                            AxisGridLine()
                            if hours <= 24 {
                                AxisValueLabel(format: .dateTime.hour())
                            } else {
                                AxisValueLabel(format: .dateTime.day().month(.abbreviated))
                            }
                        }
                    }
                    .frame(height: 120)
                    let vals = pts.map(\.value)
                    HStack {
                        stat("min", vals.min() ?? 0)
                        Spacer()
                        stat("moyenne", vals.reduce(0, +) / Double(vals.count))
                        Spacer()
                        stat("max", vals.max() ?? 0)
                    }
                    .font(.caption)
                }
            } else {
                let changes = Array(raw.suffix(8).reversed())
                if changes.isEmpty {
                    Text("Aucun changement sur cette période.").foregroundStyle(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(changes.enumerated()), id: \.offset) { _, c in
                            HStack {
                                Text(translate(c.1, domain: entityId.domain))
                                Spacer()
                                Text(c.0, format: .dateTime.weekday(.abbreviated).hour().minute())
                                    .foregroundStyle(.secondary)
                            }
                            .font(.callout)
                        }
                    }
                }
            }
        }
        .task(id: hours) { await load() }
    }

    private var points: [HistPoint] {
        var out: [HistPoint] = []
        for (i, p) in raw.enumerated() {
            if let v = Double(p.1) { out.append(HistPoint(id: i, date: p.0, value: v)) }
        }
        if let last = out.last, let st = model.states[entityId], let v = Double(st.state) {
            out.append(HistPoint(id: out.count + 100_000, date: max(Date(), last.date), value: v))
        }
        return out
    }

    private func stat(_ name: String, _ v: Double) -> some View {
        VStack(spacing: 0) {
            Text(String(format: "%.1f", v) + (unit.isEmpty ? "" : " " + unit)).monospacedDigit()
            Text(name).foregroundStyle(.secondary)
        }
    }

    private func load() async {
        if Demo.enabled {
            raw = Demo.history(entityId, hours: hours)
            return
        }
        guard let c = model.client else { failed = true; return }
        loading = true
        defer { loading = false }
        do {
            raw = try await c.history(entityId, hours: hours)
            failed = false
        } catch {
            failed = true
        }
    }
}
