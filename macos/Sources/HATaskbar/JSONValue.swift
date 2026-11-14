import Foundation

/// Valeur JSON quelconque (attributs d'entite, donnees de service, configuration...).
enum JSONValue: Codable, Equatable, Hashable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() {
            self = .null
        } else if let b = try? c.decode(Bool.self) {
            self = .bool(b)
        } else if let d = try? c.decode(Double.self) {
            self = .number(d)
        } else if let s = try? c.decode(String.self) {
            self = .string(s)
        } else if let a = try? c.decode([JSONValue].self) {
            self = .array(a)
        } else if let o = try? c.decode([String: JSONValue].self) {
            self = .object(o)
        } else {
            throw DecodingError.dataCorruptedError(in: c, debugDescription: "valeur JSON invalide")
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let b): try c.encode(b)
        case .number(let d):
            if d.rounded() == d && abs(d) < 1e15 { try c.encode(Int64(d)) } else { try c.encode(d) }
        case .string(let s): try c.encode(s)
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        }
    }

    // MARK: acces pratiques
    var string: String? {
        switch self {
        case .string(let s): return s
        case .number(let d): return JSONValue.format(d)
        case .bool(let b): return b ? "true" : "false"
        default: return nil
        }
    }
    var double: Double? {
        switch self {
        case .number(let d): return d
        case .string(let s): return Double(s.replacingOccurrences(of: ",", with: "."))
        case .bool(let b): return b ? 1 : 0
        default: return nil
        }
    }
    var bool: Bool? {
        if case .bool(let b) = self { return b }
        return nil
    }
    var array: [JSONValue]? {
        if case .array(let a) = self { return a }
        return nil
    }
    var object: [String: JSONValue]? {
        if case .object(let o) = self { return o }
        return nil
    }
    var stringArray: [String] {
        (array ?? []).compactMap { $0.string }
    }
    subscript(key: String) -> JSONValue? {
        object?[key]
    }
    var isNull: Bool {
        if case .null = self { return true }
        return false
    }

    /// Texte lisible (comme str() en Python, sans ".0" inutile).
    var display: String {
        switch self {
        case .null: return "—"
        case .bool(let b): return b ? "oui" : "non"
        case .number(let d): return JSONValue.format(d)
        case .string(let s): return s
        case .array(let a): return a.map { $0.display }.joined(separator: ", ")
        case .object: return "…"
        }
    }

    static func format(_ d: Double) -> String {
        if d.rounded() == d && abs(d) < 1e15 { return String(Int64(d)) }
        var s = String(format: "%.4f", d)
        while s.hasSuffix("0") { s.removeLast() }
        if s.hasSuffix(".") { s.removeLast() }
        return s
    }
}

extension JSONValue: ExpressibleByStringLiteral, ExpressibleByFloatLiteral, ExpressibleByIntegerLiteral,
    ExpressibleByBooleanLiteral, ExpressibleByArrayLiteral, ExpressibleByDictionaryLiteral {
    init(stringLiteral value: String) { self = .string(value) }
    init(floatLiteral value: Double) { self = .number(value) }
    init(integerLiteral value: Int) { self = .number(Double(value)) }
    init(booleanLiteral value: Bool) { self = .bool(value) }
    init(arrayLiteral elements: JSONValue...) { self = .array(elements) }
    init(dictionaryLiteral elements: (String, JSONValue)...) {
        self = .object(Dictionary(elements, uniquingKeysWith: { a, _ in a }))
    }
}

/// Etat d'une entite Home Assistant.
struct EntityState: Equatable {
    var entityId: String
    var state: String
    var attributes: [String: JSONValue]
    var lastChanged: Date?

    init(entityId: String, state: String, attributes: [String: JSONValue] = [:], lastChanged: Date? = nil) {
        self.entityId = entityId
        self.state = state
        self.attributes = attributes
        self.lastChanged = lastChanged
    }

    init?(json: JSONValue) {
        guard let o = json.object, let eid = o["entity_id"]?.string else { return nil }
        entityId = eid
        state = o["state"]?.string ?? "unknown"
        attributes = o["attributes"]?.object ?? [:]
        lastChanged = parseHADate(o["last_changed"]?.string ?? o["last_updated"]?.string)
    }

    var domain: String { entityId.domain }
    var name: String { attributes["friendly_name"]?.string ?? entityId }
    var isUnavailable: Bool { state == "unavailable" || state == "unknown" }
    func num(_ key: String) -> Double? { attributes[key]?.double }
    func str(_ key: String) -> String? { attributes[key]?.string }
    var supportedFeatures: Int { Int(num("supported_features") ?? 0) }
}

extension String {
    var domain: String { split(separator: ".", maxSplits: 1).first.map(String.init) ?? "" }
}

/// Date ISO 8601 de Home Assistant ("2026-11-14T10:00:00.123456+00:00").
func parseHADate(_ s: String?) -> Date? {
    guard var s = s, !s.isEmpty else { return nil }
    // Les fractions de seconde (jusqu'a 6 chiffres) ne sont pas toujours acceptees : on les retire.
    if let r = s.range(of: #"\.\d+"#, options: .regularExpression) {
        s.removeSubrange(r)
    }
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    if let d = f.date(from: s) { return d }
    f.formatOptions = [.withFullDate, .withTime, .withColonSeparatorInTime, .withDashSeparatorInDate]
    return f.date(from: s)
}
