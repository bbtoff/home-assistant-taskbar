import SwiftUI

// MARK: - Recherche d'entites (comme autocomplete.py de la version Windows)

enum EntitySearch {
    /// entity_id qui correspondent au texte, les meilleurs d'abord. Tous les mots tapes doivent se trouver
    /// dans l'entity_id, le nom ou la piece (sans tenir compte des accents).
    /// Tri : l'entity_id commence par le texte, puis le nom, puis un mot, puis le reste.
    static func search(_ text: String, states: [String: EntityState], areas: [String: String], limit: Int = 8) -> [String] {
        let words = fold(text).split(separator: " ").map(String.init)
        guard let w0 = words.first else { return [] }
        var out: [(Int, Int, String)] = []
        for (eid, st) in states {
            let e = eid.lowercased()
            let name = fold(st.name)
            let area = fold(areas[eid] ?? "")
            let hay = e + " " + name + " " + area
            guard words.allSatisfy({ hay.contains($0) }) else { continue }
            let obj = e.split(separator: ".", maxSplits: 1).last.map(String.init) ?? e
            let score: Int
            if e.hasPrefix(w0) || obj.hasPrefix(w0) {
                score = 0
            } else if name.hasPrefix(w0) {
                score = 1
            } else if (name.split(separator: " ") + obj.split(separator: "_")).contains(where: { $0.hasPrefix(w0) }) {
                score = 2
            } else {
                score = 3
            }
            out.append((score, e.count, eid))
        }
        out.sort { a, b in a.0 != b.0 ? a.0 < b.0 : (a.1 != b.1 ? a.1 < b.1 : a.2 < b.2) }
        return out.prefix(limit).map { $0.2 }
    }

    /// Entite qui ressemble le plus a un entity_id inconnu (renommee dans Home Assistant...) :
    /// meme domaine et ressemblance de 0,6 au moins, sinon un seul resultat avec un mot commun (3 lettres et plus).
    static func closest(_ eid: String, states: [String: EntityState]) -> String? {
        let parts = eid.split(separator: ".", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { return nil }
        let same = states.keys.filter { $0.hasPrefix(parts[0] + ".") }.sorted()
        var best: (Double, String)?
        for e in same {
            let r = ratio(eid, e)
            if r >= 0.6 && (best == nil || r > best!.0) { best = (r, e) }
        }
        if let b = best { return b.1 }
        let words = parts[1].split(separator: "_").filter { $0.count >= 3 }
        let hits = same.filter { e in words.contains { e.contains($0) } }
        return hits.count == 1 ? hits[0] : nil
    }

    /// Ressemblance de deux textes, comme difflib.SequenceMatcher.ratio() : 2 × M / T, ou M est le nombre
    /// de caracteres des plus longs blocs communs (recherche recursive de Ratcliff / Obershelp).
    static func ratio(_ a: String, _ b: String) -> Double {
        let x = Array(a), y = Array(b)
        guard !x.isEmpty || !y.isEmpty else { return 1 }
        func matches(_ a0: Int, _ a1: Int, _ b0: Int, _ b1: Int) -> Int {
            guard a0 < a1, b0 < b1 else { return 0 }
            var best = (i: a0, j: b0, n: 0)
            var prev = [Int](repeating: 0, count: b1 - b0 + 1)
            for i in a0..<a1 {
                var cur = [Int](repeating: 0, count: b1 - b0 + 1)
                for j in b0..<b1 where x[i] == y[j] {
                    let n = prev[j - b0] + 1
                    cur[j - b0 + 1] = n
                    if n > best.n { best = (i - n + 1, j - n + 1, n) }
                }
                prev = cur
            }
            guard best.n > 0 else { return 0 }
            return best.n + matches(a0, best.i, b0, best.j) + matches(best.i + best.n, a1, best.j + best.n, b1)
        }
        return 2 * Double(matches(0, x.count, 0, y.count)) / Double(x.count + y.count)
    }
}

// MARK: - Champ « Entite » avec suggestions

/// Champ de saisie d'une entite : des qu'on tape, 8 suggestions (nom, piece, entity_id) ; une entite qui
/// n'existe plus propose « Tu voulais dire … ? ».
struct EntityField: View {
    @ObservedObject var model: AppModel
    let title: String
    @Binding var text: String
    var prompt = "light.salon"
    @FocusState private var focused: Bool
    @State private var dismissed = false

    private var known: Bool { model.states[text] != nil || text == batteriesId }

    private var suggestions: [String] {
        guard !text.isEmpty, !known, !dismissed, !model.states.isEmpty else { return [] }
        return EntitySearch.search(text, states: model.states, areas: model.areas)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            TextField(title, text: $text, prompt: Text(prompt))
                .focused($focused)
                .onChange(of: text) { _ in dismissed = false }
                .onSubmit { if let first = suggestions.first { pick(first) } }
            if !text.isEmpty && !known && !model.states.isEmpty {
                if text.contains("."), let guess = EntitySearch.closest(text, states: model.states), guess != text {
                    Button {
                        pick(guess)
                    } label: {
                        Label("Entité inconnue. Tu voulais dire « \(guess) » ?", systemImage: "questionmark.circle")
                    }
                    .buttonStyle(.link)
                    .font(.caption)
                } else if suggestions.isEmpty {
                    Label("Entité inconnue dans Home Assistant.", systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
                if !suggestions.isEmpty {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(suggestions, id: \.self) { eid in
                            Button { pick(eid) } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: Icons.symbol(autoIcon(eid, model.states[eid]))).frame(width: 16)
                                    VStack(alignment: .leading, spacing: 0) {
                                        Text(model.states[eid]?.name ?? eid).lineLimit(1)
                                        Text(eid).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                                    }
                                    Spacer()
                                    if let a = model.areas[eid] {
                                        Text(a).font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                                .padding(.vertical, 3)
                                .padding(.horizontal, 6)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(4)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.05)))
                }
            }
        }
    }

    private func pick(_ eid: String) {
        text = eid
        dismissed = true
        Demo.log("autocomplete \(eid)")
    }
}
