// Compte les pixels clairs et sombres d'une zone d'une capture : pixels <image.png> <x> <y> <l> <h>
import AppKit

let a = CommandLine.arguments
guard a.count == 6, let img = NSImage(contentsOfFile: a[1]),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil),
      let x = Int(a[2]), let y = Int(a[3]), let w = Int(a[4]), let h = Int(a[5]) else {
    print("usage : pixels image x y l h")
    exit(2)
}
let rep = NSBitmapImageRep(cgImage: cg)
let scale = Double(rep.pixelsWide) / Double(img.size.width)
var light = 0, dark = 0
for py in Int(Double(y) * scale)..<Int(Double(y + h) * scale) {
    for px in Int(Double(x) * scale)..<Int(Double(x + w) * scale) {
        guard let c = rep.colorAt(x: px, y: py)?.usingColorSpace(.sRGB) else { continue }
        let l = 0.2126 * c.redComponent + 0.7152 * c.greenComponent + 0.0722 * c.blueComponent
        if l > 0.65 { light += 1 } else if l < 0.25 { dark += 1 }
    }
}
print("\(light) \(dark)")
