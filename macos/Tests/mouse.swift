// Simule la souris pour les tests de l'interface : mouse <x> <y> <duree d'appui en s> [right|move]
// « move » deplace seulement le pointeur, sans cliquer.
import CoreGraphics
import Foundation

let a = CommandLine.arguments
guard a.count >= 4, let x = Double(a[1]), let y = Double(a[2]), let hold = Double(a[3]) else {
    print("usage : mouse x y duree [right]")
    exit(2)
}
let right = a.count > 4 && a[4] == "right"
let moveOnly = a.count > 4 && a[4] == "move"
let p = CGPoint(x: x, y: y)
let src = CGEventSource(stateID: .hidSystemState)
if moveOnly {
    CGEvent(mouseEventSource: src, mouseType: .mouseMoved, mouseCursorPosition: p, mouseButton: .left)?
        .post(tap: .cghidEventTap)
    usleep(200_000)
    exit(0)
}
func post(_ t: CGEventType) {
    CGEvent(mouseEventSource: src, mouseType: t, mouseCursorPosition: p, mouseButton: right ? .right : .left)?
        .post(tap: .cghidEventTap)
}
post(.mouseMoved)
usleep(300_000)
post(right ? .rightMouseDown : .leftMouseDown)
usleep(useconds_t(hold * 1_000_000))
post(right ? .rightMouseUp : .leftMouseUp)
usleep(300_000)
