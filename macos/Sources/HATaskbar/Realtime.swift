import Foundation

/// Connexion permanente a Home Assistant (API WebSocket) : changements d'etat instantanes,
/// notifications persistantes et evenement `ha_taskbar_notify`. Se reconnecte toute seule.
@MainActor
final class Realtime {
    static let notifyEvent = "ha_taskbar_notify"

    var onState: ((String, EntityState?) -> Void)?
    var onNotify: ((String, String) -> Void)?
    var onStatus: ((Bool, String) -> Void)?

    private let client: HAClient
    private let notifications: Bool
    private var loop: Task<Void, Never>?
    private var socket: URLSessionWebSocketTask?
    private var lastAlive = Date()
    private(set) var connected = false

    init(client: HAClient, notifications: Bool) {
        self.client = client
        self.notifications = notifications
    }

    func start() {
        guard loop == nil else { return }
        loop = Task { [weak self] in await self?.run() }
    }

    func stop() {
        loop?.cancel()
        loop = nil
        socket?.cancel(with: .goingAway, reason: nil)
        socket = nil
    }

    private func setStatus(_ ok: Bool, _ detail: String = "") {
        if ok != connected || !ok {
            connected = ok
            if !Task.isCancelled { onStatus?(ok, detail) }
        }
    }

    private func run() async {
        var delay: Double = 2
        while !Task.isCancelled {
            do {
                try await session()
                delay = 2
            } catch HAError.auth {
                setStatus(false, HAError.auth.localizedDescription)
                delay = 300                 // jeton refuse : inutile d'insister
            } catch {
                if Task.isCancelled { break }
                setStatus(false, error.localizedDescription)
            }
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            delay = min(60, delay * 2)
        }
    }

    private func receive(_ ws: URLSessionWebSocketTask) async throws -> JSONValue {
        let msg = try await ws.receive()
        lastAlive = Date()
        let data: Data
        switch msg {
        case .string(let s): data = Data(s.utf8)
        case .data(let d): data = d
        @unknown default: throw HAError.invalid
        }
        return (try? JSONDecoder().decode(JSONValue.self, from: data)) ?? .null
    }

    private func send(_ ws: URLSessionWebSocketTask, _ obj: JSONValue) async throws {
        let data = try JSONEncoder().encode(obj)
        try await ws.send(.string(String(decoding: data, as: UTF8.self)))
    }

    private func session() async throws {
        guard let url = client.webSocketURL, !client.token.isEmpty else { throw HAError.auth }
        let ws = client.session.webSocketTask(with: url)
        ws.maximumMessageSize = 64 * 1024 * 1024
        socket = ws
        ws.resume()
        defer {
            ws.cancel(with: .goingAway, reason: nil)
            if socket === ws { socket = nil }
        }
        var msg = try await receive(ws)
        guard msg["type"]?.string == "auth_required" else { throw HAError.invalid }
        try await send(ws, ["type": "auth", "access_token": .string(client.token)])
        msg = try await receive(ws)
        guard msg["type"]?.string == "auth_ok" else { throw HAError.auth }
        try await send(ws, ["id": 1, "type": "subscribe_events", "event_type": "state_changed"])
        if notifications {
            try await send(ws, ["id": 2, "type": "persistent_notification/subscribe"])
            try await send(ws, ["id": 3, "type": "subscribe_events", "event_type": .string(Self.notifyEvent)])
        }
        setStatus(true)

        // Ping toutes les 30 s ; plus rien recu depuis 75 s -> connexion morte
        let pinger = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30_000_000_000)
                guard let self = self, !Task.isCancelled else { return }
                if Date().timeIntervalSince(self.lastAlive) > 75 {
                    ws.cancel(with: .abnormalClosure, reason: nil)
                    return
                }
                ws.sendPing { err in
                    if err == nil {
                        Task { @MainActor [weak self] in self?.lastAlive = Date() }
                    }
                }
            }
        }
        defer { pinger.cancel() }

        while !Task.isCancelled {
            let m = try await receive(ws)
            for one in m.array ?? [m] { handle(one) }
        }
    }

    private func handle(_ m: JSONValue) {
        guard m["type"]?.string == "event", let ev = m["event"] else { return }
        let id = Int(m["id"]?.double ?? 0)
        switch id {
        case 1:
            if let d = ev["data"], let eid = d["entity_id"]?.string {
                let new = d["new_state"].flatMap { EntityState(json: $0) }
                onState?(eid, new)
            }
        case 2:
            if ev["type"]?.string == "added" {         // "current" = deja presentes a la connexion
                for (_, n) in ev["notifications"]?.object ?? [:] {
                    onNotify?(n["title"]?.string ?? "Home Assistant", n["message"]?.string ?? "")
                }
            }
        case 3:
            let d = ev["data"]
            onNotify?(d?["title"]?.string ?? "Home Assistant", d?["message"]?.string ?? "")
        default:
            break
        }
    }
}
