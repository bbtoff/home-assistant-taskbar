import AppKit
import CryptoKit

/// Mises a jour automatiques depuis les Releases GitHub (comme la version Windows).
/// L'application telecharge elle-meme la nouvelle version : le fichier n'est pas marque « venu d'Internet »,
/// donc Gatekeeper ne bloque pas. L'empreinte SHA-256 publiee par GitHub est verifiee avant l'installation.
@MainActor
final class Updater: ObservableObject {
    struct Release: Equatable {
        let version: String
        let notes: String
        let page: URL
        let asset: URL
        let sha256: String?
        let size: Int?
    }

    enum State: Equatable {
        case idle
        case checking
        case upToDate
        case available(Release)
        case downloading
        case installing
        case failed(String)
    }

    @Published private(set) var state: State = .idle
    @Published private(set) var lastCheck: Date?
    private let model: AppModel
    private var loop: Task<Void, Never>?
    var onAvailable: ((Release) -> Void)?

    static let releasesPage = URL(string: "https://github.com/\(githubRepo)/releases")!

    init(model: AppModel) {
        self.model = model
    }

    /// Version de l'application en cours (remplacable pour les tests : --fake-version).
    static var currentVersion: String {
        if CommandLine.arguments.contains("--update-test"), let i = CommandLine.arguments.firstIndex(of: "--fake-version"),
           i + 1 < CommandLine.arguments.count {
            return CommandLine.arguments[i + 1]
        }
        return appVersion
    }

    /// L'application peut-elle se remplacer elle-meme ? (lancee depuis un .app dans un dossier modifiable)
    static var canInstall: Bool {
        let app = Bundle.main.bundleURL
        return app.pathExtension == "app"
            && FileManager.default.isWritableFile(atPath: app.deletingLastPathComponent().path)
    }

    var available: Release? {
        if case .available(let r) = state { return r }
        return nil
    }

    /// Verification au demarrage puis une fois par jour.
    func start() {
        loop?.cancel()
        guard !Demo.enabled else { return }
        loop = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 20_000_000_000)
            while !Task.isCancelled {
                guard let self = self else { return }
                if self.model.config.checkUpdates { await self.check(manual: false) }
                try? await Task.sleep(nanoseconds: 24 * 3600 * 1_000_000_000)
            }
        }
    }

    // MARK: verification

    func check(manual: Bool) async {
        if case .downloading = state { return }
        if case .installing = state { return }
        state = .checking
        do {
            let r = try await Self.latest()
            lastCheck = Date()
            if let r = r, Self.compare(r.version, Self.currentVersion) > 0 {
                state = .available(r)
                if manual || r.version != model.config.skipVersion { onAvailable?(r) }
            } else {
                state = .upToDate
            }
        } catch {
            state = manual ? .failed(error.localizedDescription) : .idle
        }
    }

    /// Derniere version : par l'API de GitHub, ou a defaut (limite de requetes atteinte...) par la page
    /// « latest » des Releases et le fichier SHA256SUMS.txt.
    static func latest() async throws -> Release? {
        if let r = try? await latestFromAPI() { return r }
        return try await latestFromPage()
    }

    static func latestFromPage() async throws -> Release? {
        var req = URLRequest(url: URL(string: "https://github.com/\(githubRepo)/releases/latest")!, timeoutInterval: 15)
        req.httpMethod = "HEAD"
        let (_, resp) = try await URLSession.shared.data(for: req)
        guard let final = resp.url, final.path.contains("/releases/tag/") else { throw UpdateError.github }
        let tag = final.lastPathComponent
        let version = tag.trimmingCharacters(in: CharacterSet(charactersIn: "vV"))
        guard Int(version.prefix(1)) != nil else { throw UpdateError.github }
        let base = "https://github.com/\(githubRepo)/releases/download/\(tag)/"
        let name = "HATaskbar-macOS-\(version).zip"
        var sha: String?
        if let sums = try? await URLSession.shared.data(from: URL(string: base + "SHA256SUMS.txt")!),
           (sums.1 as? HTTPURLResponse)?.statusCode == 200 {
            for line in String(decoding: sums.0, as: UTF8.self).split(separator: "\n") {
                let p = line.split(separator: " ", omittingEmptySubsequences: true)
                if p.count >= 2, p[1].trimmingCharacters(in: CharacterSet(charactersIn: "*")) == name {
                    sha = p[0].lowercased()
                }
            }
        }
        return Release(version: version, notes: "", page: final, asset: URL(string: base + name)!,
                       sha256: sha, size: nil)
    }

    static func latestFromAPI() async throws -> Release? {
        var req = URLRequest(url: URL(string: "https://api.github.com/repos/\(githubRepo)/releases/latest")!,
                             timeoutInterval: 15)
        req.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        req.setValue("HATaskbar-macOS/\(appVersion)", forHTTPHeaderField: "User-Agent")
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else { throw UpdateError.github }
        let rel = try JSONDecoder().decode(JSONValue.self, from: data)
        let version = (rel["tag_name"]?.string ?? "").trimmingCharacters(in: CharacterSet(charactersIn: "vV"))
        guard !version.isEmpty else { return nil }
        let name = "HATaskbar-macOS-\(version).zip"
        let prefix = "https://github.com/\(githubRepo)/releases/download/"
        // Uniquement l'application Mac, et uniquement depuis les versions de ce depot
        guard let asset = rel["assets"]?.array?.first(where: { $0["name"]?.string == name }),
              let urlString = asset["browser_download_url"]?.string, urlString.hasPrefix(prefix),
              let url = URL(string: urlString) else { return nil }
        var sha: String?
        if let d = asset["digest"]?.string, d.hasPrefix("sha256:") { sha = String(d.dropFirst(7)).lowercased() }
        return Release(version: version, notes: rel["body"]?.string ?? "",
                       page: URL(string: rel["html_url"]?.string ?? "") ?? releasesPage,
                       asset: url, sha256: sha, size: asset["size"].flatMap { $0.double }.map { Int($0) })
    }

    /// "1.10.0" > "1.9.2"
    static func compare(_ a: String, _ b: String) -> Int {
        func parts(_ s: String) -> [Int] {
            var p = s.trimmingCharacters(in: CharacterSet(charactersIn: "vV")).split(separator: ".").map { part in
                Int(part.filter(\.isNumber)) ?? 0
            }
            while p.count < 3 { p.append(0) }
            return Array(p.prefix(3))
        }
        let x = parts(a), y = parts(b)
        for i in 0..<3 where x[i] != y[i] { return x[i] < y[i] ? -1 : 1 }
        return 0
    }

    // MARK: installation

    /// Telecharge, verifie, remplace l'application puis la relance.
    func install(_ r: Release, relaunch: Bool = true) async {
        guard Self.canInstall else {
            state = .failed("Mise à jour automatique impossible ici : l'application n'est pas dans un dossier modifiable. Télécharge-la depuis GitHub.")
            return
        }
        state = .downloading
        do {
            let fm = FileManager.default
            let work = fm.temporaryDirectory.appendingPathComponent("HATaskbar-update-\(UUID().uuidString)")
            try fm.createDirectory(at: work, withIntermediateDirectories: true)
            let (tmp, resp) = try await URLSession.shared.download(from: r.asset)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else { throw UpdateError.download }
            let zip = work.appendingPathComponent("app.zip")
            try fm.moveItem(at: tmp, to: zip)
            let data = try Data(contentsOf: zip, options: .mappedIfSafe)
            if let size = r.size, data.count != size { throw UpdateError.incomplete }
            if let expected = r.sha256 {
                let got = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
                guard got == expected else { throw UpdateError.checksum }
            }
            state = .installing
            let out = work.appendingPathComponent("x")
            try run("/usr/bin/ditto", ["-x", "-k", zip.path, out.path])
            let newApp = out.appendingPathComponent("HA Taskbar.app")
            guard let info = NSDictionary(contentsOf: newApp.appendingPathComponent("Contents/Info.plist")),
                  info["CFBundleIdentifier"] as? String == Bundle.main.bundleIdentifier ?? "io.github.bbtoff.hataskbar"
            else { throw UpdateError.invalid }
            try? run("/usr/bin/xattr", ["-dr", "com.apple.quarantine", newApp.path])

            // Remplacement apres la fermeture de l'application, par un petit script independant
            let target = Bundle.main.bundleURL
            let script = work.appendingPathComponent("install.sh")
            let sh = """
            #!/bin/sh
            while kill -0 \(ProcessInfo.processInfo.processIdentifier) 2>/dev/null; do sleep 0.2; done
            rm -rf \(quote(target.path))
            /usr/bin/ditto \(quote(newApp.path)) \(quote(target.path))
            \(relaunch ? "/usr/bin/open " + quote(target.path) : "")
            rm -rf \(quote(work.path))
            """
            try sh.write(to: script, atomically: true, encoding: .utf8)
            let p = Process()
            p.executableURL = URL(fileURLWithPath: "/bin/sh")
            p.arguments = [script.path]
            p.standardOutput = FileHandle.nullDevice
            p.standardError = FileHandle.nullDevice
            try p.run()
            Demo.log("update installing \(r.version)")
            NSApp.terminate(nil)
        } catch {
            state = .failed((error as? LocalizedError)?.errorDescription ?? error.localizedDescription)
        }
    }

    private func run(_ tool: String, _ args: [String]) throws {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: tool)
        p.arguments = args
        try p.run()
        p.waitUntilExit()
        if p.terminationStatus != 0 { throw UpdateError.invalid }
    }

    private func quote(_ s: String) -> String { "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'" }

    enum UpdateError: LocalizedError {
        case download, incomplete, checksum, invalid, github
        var errorDescription: String? {
            switch self {
            case .github: return "GitHub ne répond pas, réessaie plus tard"
            case .download: return "téléchargement impossible"
            case .incomplete: return "fichier incomplet"
            case .checksum: return "empreinte SHA-256 incorrecte : fichier abîmé ou modifié"
            case .invalid: return "archive de mise à jour invalide"
            }
        }
    }

    // MARK: fenetre de confirmation

    /// Propose la mise a jour : Installer, Plus tard ou Ignorer cette version.
    func ask(_ r: Release) {
        let a = NSAlert()
        a.messageText = "HA Taskbar \(r.version) est disponible"
        var notes = r.notes.replacingOccurrences(of: "**", with: "")
        if notes.count > 900 { notes = String(notes.prefix(900)) + "…" }
        a.informativeText = "Tu as la version \(Self.currentVersion).\n\n" + notes
        a.addButton(withTitle: Self.canInstall ? "Installer et redémarrer" : "Ouvrir la page de téléchargement")
        a.addButton(withTitle: "Plus tard")
        a.addButton(withTitle: "Ignorer cette version")
        NSApp.activate(ignoringOtherApps: true)
        switch a.runModal() {
        case .alertFirstButtonReturn:
            if Self.canInstall {
                Task { await self.install(r) }
            } else {
                NSWorkspace.shared.open(r.page)
            }
        case .alertThirdButtonReturn:
            model.update { $0.skipVersion = r.version }
        default:
            break
        }
    }

    /// Test automatique (GitHub Actions) : --update-test --fake-version 0.0.1 installe la derniere version.
    func runSelfTest() {
        onAvailable = nil                     // pas de fenetre de confirmation pendant le test
        Demo.log("update test from \(Self.currentVersion)")
        Task { @MainActor in
            await check(manual: true)
            Demo.log("update state \(String(describing: state))")
            if let r = available {
                await install(r, relaunch: false)
                Demo.log("update failed \(String(describing: state))")
            }
            NSApp.terminate(nil)
        }
    }
}
