import AppKit
import SwiftUI

/// Fenetre camera : quand une regle de notification a une camera (une sonnette par exemple), une petite
/// fenetre s'ouvre en haut a droite, sous la barre des menus, avec l'image en direct. Elle ne prend pas
/// le focus, se ferme seule apres 60 s, et un clic sur l'image ouvre la carte de la camera.
@MainActor
final class DoorbellController: ObservableObject {
    let model: AppModel
    var openCard: (_ camera: String) -> Void = { _ in }

    @Published var camera = ""
    @Published var text = ""
    @Published var deadline = Date()
    @Published var keepOpen = false
    private var panel: NSPanel?
    private var closer: Task<Void, Never>?

    static let seconds: TimeInterval = 60
    static let size = NSSize(width: 400, height: 330)

    init(model: AppModel) {
        self.model = model
    }

    var isShown: Bool { panel?.isVisible ?? false }

    /// Ouvre (ou remet a jour) la fenetre. Respecte la pause et la plage sans notification, sauf `force`.
    func show(camera: String, text: String, force: Bool) {
        if !force && (model.notificationsPaused || inRange(model.config.quietFrom, model.config.quietTo, empty: false)) {
            return
        }
        // Une seule fenetre : la meme camera remet le texte et le delai a zero, une autre la remplace
        self.camera = camera
        self.text = text
        deadline = Date().addingTimeInterval(Self.seconds)
        keepOpen = false
        let p = panel ?? makePanel()
        panel = p
        if !p.isVisible {
            let vis = (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
            p.setFrame(NSRect(x: vis.maxX - Self.size.width - 12, y: vis.maxY - Self.size.height - 8,
                              width: Self.size.width, height: Self.size.height), display: true)
            p.orderFrontRegardless()       // sans prendre le focus
        }
        scheduleClose()
        Demo.log("doorbell \(camera) shown=\(p.isVisible)")
    }

    func close() {
        closer?.cancel()
        panel?.orderOut(nil)
    }

    private func scheduleClose() {
        closer?.cancel()
        closer = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 500_000_000)
                guard let self = self else { return }
                if !self.keepOpen && Date() >= self.deadline {
                    self.close()
                    return
                }
                self.objectWillChange.send()       // « se ferme dans N s »
            }
        }
    }

    private func makePanel() -> NSPanel {
        let p = NSPanel(contentRect: NSRect(origin: .zero, size: Self.size),
                        styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        p.level = .floating
        p.hidesOnDeactivate = false
        p.isReleasedWhenClosed = false
        p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        let effect = NSVisualEffectView()
        effect.material = .popover
        effect.blendingMode = .behindWindow
        effect.state = .active
        effect.maskImage = WidgetPanel.roundedMask(14)
        let host = NSHostingView(rootView: DoorbellView(controller: self))
        host.autoresizingMask = [.width, .height]
        effect.addSubview(host)
        p.contentView = effect
        host.frame = effect.bounds
        return p
    }
}

struct DoorbellView: View {
    @ObservedObject var controller: DoorbellController

    private var cameraName: String {
        controller.model.states[controller.camera]?.name ?? controller.camera
    }

    var body: some View {
        let left = max(0, Int(controller.deadline.timeIntervalSinceNow.rounded(.up)))
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "bell.fill")
                    .foregroundStyle(Color(nsColor: .haOn))
                    .font(.title3)
                Text(controller.text)
                    .font(.headline)
                    .lineLimit(2)
                Spacer()
                Button { controller.close() } label: { Image(systemName: "xmark") }
                    .buttonStyle(.borderless)
                    .help("Fermer")
            }
            CameraImageView(model: controller.model, entityId: controller.camera, interval: 1)
                .frame(maxWidth: .infinity)
                .frame(height: 210)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .contentShape(Rectangle())
                .onTapGesture { controller.openCard(controller.camera) }
                .help("Ouvrir la carte de la caméra")
            HStack {
                Text(cameraName).font(.callout).foregroundStyle(.secondary).lineLimit(1)
                Spacer()
                Toggle("Garder ouverte", isOn: $controller.keepOpen)
                    .toggleStyle(.checkbox)
                    .font(.callout)
                if !controller.keepOpen {
                    Text("se ferme dans \(left) s").font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }
            }
        }
        .padding(14)
    }
}
