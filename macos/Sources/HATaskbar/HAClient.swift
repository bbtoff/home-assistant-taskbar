import Foundation

enum HAError: LocalizedError {
    case badURL
    case http(Int)
    case auth
    case invalid

    var errorDescription: String? {
        switch self {
        case .badURL: return "adresse de Home Assistant invalide"
        case .http(let c): return "Home Assistant a répondu \(c)"
        case .auth: return "jeton refusé (401)"
        case .invalid: return "réponse inattendue de Home Assistant"
        }
    }
}

/// Accepte les certificats auto-signes quand « Vérifier le certificat » est decoche.
final class TrustDelegate: NSObject, URLSessionDelegate {
    let verify: Bool
    init(verify: Bool) { self.verify = verify }

    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        if !verify, challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
           let trust = challenge.protectionSpace.serverTrust {
            completionHandler(.useCredential, URLCredential(trust: trust))
        } else {
            completionHandler(.performDefaultHandling, nil)
        }
    }
}

/// Client de l'API REST de Home Assistant.
final class HAClient {
    let base: String
    let token: String
    let verifySSL: Bool
    let session: URLSession

    init(url: String, token: String, verifySSL: Bool) {
        var u = url.trimmingCharacters(in: .whitespacesAndNewlines)
        while u.hasSuffix("/") { u.removeLast() }
        base = u
        self.token = token
        self.verifySSL = verifySSL
        let conf = URLSessionConfiguration.ephemeral
        conf.timeoutIntervalForRequest = 15
        conf.waitsForConnectivity = false
        session = URLSession(configuration: conf, delegate: TrustDelegate(verify: verifySSL), delegateQueue: nil)
    }

    deinit { session.invalidateAndCancel() }

    var webSocketURL: URL? {
        guard var comps = URLComponents(string: base) else { return nil }
        comps.scheme = (comps.scheme == "https") ? "wss" : "ws"
        comps.path = (comps.path.hasSuffix("/") ? String(comps.path.dropLast()) : comps.path) + "/api/websocket"
        return comps.url
    }

    func request(_ method: String, _ path: String, body: JSONValue? = nil, timeout: TimeInterval = 10) async throws -> Data {
        guard let url = URL(string: base + path), url.scheme == "http" || url.scheme == "https" else {
            throw HAError.badURL
        }
        var req = URLRequest(url: url, timeoutInterval: timeout)
        req.httpMethod = method
        req.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("HATaskbar-macOS/\(appVersion)", forHTTPHeaderField: "User-Agent")
        if let body = body { req.httpBody = try JSONEncoder().encode(body) }
        let (data, resp) = try await session.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 || code == 403 { throw HAError.auth }
        guard (200..<300).contains(code) else { throw HAError.http(code) }
        return data
    }

    func json(_ method: String, _ path: String, body: JSONValue? = nil, timeout: TimeInterval = 10) async throws -> JSONValue {
        let data = try await request(method, path, body: body, timeout: timeout)
        if data.isEmpty { return .null }
        return try JSONDecoder().decode(JSONValue.self, from: data)
    }

    /// Verifie l'adresse et le jeton. Renvoie le nom et la version de Home Assistant.
    func check() async throws -> String {
        let cfg = try await json("GET", "/api/config")
        let name = cfg["location_name"]?.string ?? "Home Assistant"
        let ver = cfg["version"]?.string ?? ""
        return ver.isEmpty ? name : "\(name) (Home Assistant \(ver))"
    }

    func states() async throws -> [String: EntityState] {
        let all = try await json("GET", "/api/states", timeout: 20)
        guard let arr = all.array else { throw HAError.invalid }
        var out: [String: EntityState] = [:]
        for v in arr {
            if let st = EntityState(json: v) { out[st.entityId] = st }
        }
        return out
    }

    func callService(_ service: String, data: [String: JSONValue]) async throws {
        let parts = service.split(separator: ".", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { throw HAError.invalid }
        _ = try await request("POST", "/api/services/\(parts[0])/\(parts[1])", body: .object(data))
    }

    /// Historique [(date, etat)] sur les `hours` dernieres heures.
    func history(_ entityId: String, hours: Double) async throws -> [(Date, String)] {
        let start = Date().addingTimeInterval(-hours * 3600)
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        let eid = entityId.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? entityId
        let path = "/api/history/period/\(f.string(from: start))?filter_entity_id=\(eid)&minimal_response&no_attributes"
        let data = try await json("GET", path, timeout: 30)
        guard let series = data.array?.first?.array else { return [] }
        var out: [(Date, String)] = []
        for e in series {
            if let d = parseHADate(e["last_changed"]?.string ?? e["last_updated"]?.string), let s = e["state"]?.string {
                out.append((d, s))
            }
        }
        return out
    }

    /// Previsions meteo (service weather.get_forecasts, Home Assistant 2023.9+).
    func forecast(_ entityId: String, kind: String = "daily") async throws -> [[String: JSONValue]] {
        let r = try await json("POST", "/api/services/weather/get_forecasts?return_response",
                               body: ["entity_id": .string(entityId), "type": .string(kind)], timeout: 15)
        let f = r["service_response"]?[entityId]?["forecast"]?.array ?? []
        return f.compactMap { $0.object }
    }

    /// Phrase envoyee a Assist (comme a la voix) -> (reponse, erreur ?, conversation_id).
    func converse(_ text: String, conversationId: String?) async throws -> (speech: String, error: Bool, id: String?) {
        var body: [String: JSONValue] = ["text": .string(text)]
        if let id = conversationId { body["conversation_id"] = .string(id) }
        let r = try await json("POST", "/api/conversation/process", body: .object(body), timeout: 30)
        let resp = r["response"]
        let speech = resp?["speech"]?["plain"]?["speech"]?.string ?? ""
        return (speech, resp?["response_type"]?.string == "error", r["conversation_id"]?.string)
    }

    /// Commande ponctuelle de l'API WebSocket (ex. « homeassistant/expose_entity/list ») : connexion,
    /// authentification, une requete, son resultat. Erreur si Home Assistant la refuse.
    func wsCommand(_ type: String, timeout: TimeInterval = 15) async throws -> JSONValue {
        guard let url = webSocketURL else { throw HAError.badURL }
        let ws = session.webSocketTask(with: url)
        ws.maximumMessageSize = 32 * 1024 * 1024
        ws.resume()
        defer { ws.cancel(with: .goingAway, reason: nil) }
        func receive() async throws -> JSONValue {
            switch try await ws.receive() {
            case .string(let s): return (try? JSONDecoder().decode(JSONValue.self, from: Data(s.utf8))) ?? .null
            case .data(let d): return (try? JSONDecoder().decode(JSONValue.self, from: d)) ?? .null
            @unknown default: return .null
            }
        }
        func send(_ v: JSONValue) async throws {
            let data = try JSONEncoder().encode(v)
            try await ws.send(.string(String(decoding: data, as: UTF8.self)))
        }
        guard try await receive()["type"]?.string == "auth_required" else { throw HAError.invalid }
        try await send(["type": "auth", "access_token": .string(token)])
        guard try await receive()["type"]?.string == "auth_ok" else { throw HAError.auth }
        try await send(["id": 1, "type": .string(type)])
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            let m = try await receive()
            if m["id"]?.double == 1 && m["type"]?.string == "result" {
                guard m["success"]?.bool == true else { throw HAError.invalid }
                return m["result"] ?? .null
            }
        }
        throw HAError.invalid
    }

    /// Entites exposees a Assist : {entity_id: exposee ?}. Demande un compte administrateur.
    func assistExposure() async throws -> [String: Bool] {
        let r = try await wsCommand("homeassistant/expose_entity/list")
        var out: [String: Bool] = [:]
        for (eid, v) in r["exposed_entities"]?.object ?? [:] {
            if let b = v["conversation"]?.bool { out[eid] = b }
        }
        return out
    }

    /// Image actuelle d'une camera (camera.*) ou d'une entite image.* (octets JPEG / PNG).
    func cameraImage(_ entityId: String) async throws -> Data {
        let kind = entityId.hasPrefix("image.") ? "image_proxy" : "camera_proxy"
        let data = try await request("GET", "/api/\(kind)/\(entityId)", timeout: 10)
        return data
    }

    /// Photo d'une personne, pochette d'un lecteur... (attribut entity_picture), 8 Mo au plus.
    /// Un chemin relatif se lit sur Home Assistant avec le jeton ; une adresse externe sans le jeton.
    func picture(_ path: String) async throws -> Data {
        let data: Data
        if path.hasPrefix("/") || path.hasPrefix(base + "/") {
            data = try await request("GET", path.hasPrefix("/") ? path : String(path.dropFirst(base.count)), timeout: 10)
        } else if path.hasPrefix("http://") || path.hasPrefix("https://"), let url = URL(string: path) {
            var req = URLRequest(url: url, timeoutInterval: 10)
            req.setValue("HA-Taskbar", forHTTPHeaderField: "User-Agent")
            let (d, resp) = try await session.data(for: req)
            guard ((resp as? HTTPURLResponse)?.statusCode ?? 0) / 100 == 2 else { throw HAError.invalid }
            data = d
        } else {
            throw HAError.invalid
        }
        guard data.count <= 8 * 1024 * 1024 else { throw HAError.invalid }
        return data
    }

    /// Rend un modele Jinja cote Home Assistant.
    func template(_ tpl: String) async throws -> String {
        let data = try await request("POST", "/api/template", body: ["template": .string(tpl)], timeout: 20)
        return String(decoding: data, as: UTF8.self)
    }

    /// {entity_id: piece}
    func areas() async throws -> [String: String] {
        let tpl = "{% for s in states %}{% set a = area_name(s.entity_id) %}{% if a %}{{ s.entity_id }}\t{{ a }}\n{% endif %}{% endfor %}"
        var out: [String: String] = [:]
        for line in try await template(tpl).split(separator: "\n") {
            let p = line.split(separator: "\t", maxSplits: 1).map { $0.trimmingCharacters(in: .whitespaces) }
            if p.count == 2, !p[0].isEmpty { out[p[0]] = p[1] }
        }
        return out
    }
}
