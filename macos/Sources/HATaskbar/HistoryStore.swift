import AppKit

/// Historique des capteurs pour les mini-graphiques de la barre des menus et les widgets.
/// Chaque serie (entite + periode) est chargee depuis Home Assistant, gardee en memoire et
/// rechargee toutes les 5 minutes tant qu'elle est utilisee. La valeur actuelle est ajoutee
/// en direct a la fin de la courbe.
@MainActor
final class HistoryStore: ObservableObject {
    @Published private(set) var revision = 0
    var onChange: (() -> Void)?

    private let model: AppModel
    private var series: [String: [HistPoint]] = [:]
    private var fetched: [String: Date] = [:]
    private var lastUsed: [String: Date] = [:]
    private var inflight: Set<String> = []
    private var loop: Task<Void, Never>?

    static let refreshEvery: TimeInterval = 300
    static let maxPoints = 240

    init(model: AppModel) {
        self.model = model
    }

    private func key(_ eid: String, _ hours: Double) -> String { "\(eid)|\(Int(hours))" }

    /// Points de la serie (charges ou non), avec la valeur actuelle a la fin.
    func points(_ eid: String, hours: Double) -> [HistPoint] {
        let k = key(eid, hours)
        lastUsed[k] = Date()
        var out = series[k] ?? []
        if let st = model.states[eid], let v = Double(st.state) {
            let now = Date()
            if let last = out.last, now.timeIntervalSince(last.date) < 30 {
                out[out.count - 1] = HistPoint(id: last.id, date: now, value: v)
            } else {
                out.append(HistPoint(id: (out.last?.id ?? 0) + 1, date: now, value: v))
            }
        }
        return out
    }

    /// Demande le chargement de la serie si elle manque ou date de plus de 5 minutes.
    func request(_ eid: String, hours: Double) {
        let k = key(eid, hours)
        lastUsed[k] = Date()
        startLoop()
        if inflight.contains(k) { return }
        if let f = fetched[k], Date().timeIntervalSince(f) < Self.refreshEvery { return }
        inflight.insert(k)
        Task { await self.load(eid, hours: hours) }
    }

    /// Oublie tout (changement de serveur).
    func reset() {
        series = [:]
        fetched = [:]
        revision += 1
    }

    private func startLoop() {
        guard loop == nil else { return }
        loop = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 60_000_000_000)
                guard let self = self else { return }
                let now = Date()
                for (k, used) in self.lastUsed where now.timeIntervalSince(used) < 900 {
                    let p = k.split(separator: "|")
                    if p.count == 2, let h = Double(p[1]) { self.request(String(p[0]), hours: h) }
                }
            }
        }
    }

    private func load(_ eid: String, hours: Double) async {
        let k = key(eid, hours)
        defer { inflight.remove(k) }
        var raw: [(Date, String)]
        if Demo.enabled {
            raw = Demo.history(eid, hours: hours)
        } else {
            guard let c = model.client, let r = try? await c.history(eid, hours: hours) else { return }
            raw = r
        }
        var pts: [(Date, Double)] = raw.compactMap { p in Double(p.1).map { (p.0, $0) } }
        pts = Self.downsample(pts, max: Self.maxPoints)
        series[k] = pts.enumerated().map { HistPoint(id: $0.offset, date: $0.element.0, value: $0.element.1) }
        fetched[k] = Date()
        revision += 1
        onChange?()
    }

    /// Reduit une longue serie a `max` points (moyenne par tranche de temps).
    static func downsample(_ pts: [(Date, Double)], max: Int) -> [(Date, Double)] {
        guard pts.count > max, let first = pts.first?.0, let last = pts.last?.0, last > first else { return pts }
        let span = last.timeIntervalSince(first)
        var buckets = [(sum: Double, n: Int, t: Double)](repeating: (0, 0, 0), count: max)
        for (d, v) in pts {
            let i = Swift.min(max - 1, Int(d.timeIntervalSince(first) / span * Double(max)))
            buckets[i].sum += v
            buckets[i].n += 1
            buckets[i].t += d.timeIntervalSince1970
        }
        return buckets.compactMap { b in
            b.n > 0 ? (Date(timeIntervalSince1970: b.t / Double(b.n)), b.sum / Double(b.n)) : nil
        }
    }
}

/// Image d'une mini-courbe (barre des menus).
enum Sparkline {
    static func image(_ values: [Double], size: NSSize = NSSize(width: 34, height: 14), color: NSColor) -> NSImage? {
        guard values.count >= 2, let lo = values.min(), let hi = values.max() else { return nil }
        let range = hi - lo
        let img = NSImage(size: size, flipped: false) { rect in
            let path = NSBezierPath()
            let n = values.count
            for (i, v) in values.enumerated() {
                let x = rect.minX + 1 + (rect.width - 2) * CGFloat(i) / CGFloat(n - 1)
                let t = range > 0 ? (v - lo) / range : 0.5
                let y = rect.minY + 1.5 + (rect.height - 3) * CGFloat(t)
                if i == 0 { path.move(to: NSPoint(x: x, y: y)) } else { path.line(to: NSPoint(x: x, y: y)) }
            }
            path.lineWidth = 1.3
            path.lineJoinStyle = .round
            path.lineCapStyle = .round
            color.setStroke()
            path.stroke()
            return true
        }
        return img
    }
}
