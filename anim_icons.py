"""
Icones animees de la barre (flamme, ventilateur, ampoule, egaliseur, goutte).

Dessinees en vectoriel puis rasterisees avec anticrenelage, en Python pur (pas de dependance),
a la taille exacte des autres icones. Chaque image est un PNG avec transparence : Tk la fond
proprement sur le fond de la barre comme sur le rectangle de survol.

Rythme volontairement lent et mouvements doux, pour ne pas attirer l'oeil pendant qu'on travaille.
"""
import math
import struct
import zlib

FRAME_MS = 125          # 8 images par seconde : fluide, et presque rien pour le processeur

# cle -> (icone de police equivalente pour la carte et les reglages, libelle, nombre d'images du cycle)
ANIM_ICONS = {
    "flame_anim": ("flame", "Flamme animée (chauffage)", 26),       # cycle de 3,25 s
    "fan_anim": ("wind", "Ventilateur qui tourne", 16),              # 1/3 de tour en 2 s
    "bulb_anim": ("lightbulb", "Ampoule qui rayonne", 32),           # respiration de 4 s
    "eq_anim": ("music", "Égaliseur (musique)", 24),                 # cycle de 3 s
    "drop_anim": ("drop", "Goutte qui tombe (arrosage)", 24),        # cycle de 3 s
    "snow_anim": ("snow", "Flocon qui tourne (climatisation)", 32),  # 1/6 de tour en 4 s
    "sun_anim": ("sun", "Soleil qui rayonne", 32),                   # 1/8 de tour en 4 s
    "wifi_anim": ("wifi", "Ondes Wi-Fi / signal", 24),               # vague de 3 s
    "bell_anim": ("bell", "Cloche qui sonne (sonnette, sirène)", 32),  # 2 balancements puis pause, 4 s
    "washer_anim": ("refresh", "Lave-linge qui tourne", 24),         # 1 tour de tambour en 3 s
    "bolt_anim": ("bolt", "Éclair (énergie qui monte)", 20),         # 2,5 s
    "battery_anim": ("battery", "Batterie en charge", 32),           # remplissage en 4 s
    "radar_anim": ("pulse", "Détection (mouvement, présence)", 24),  # ondes de 3 s
    "heater_anim": ("flame", "Radiateur (chaleur qui monte)", 24),   # 3 s
    "speaker_anim": ("speaker", "Haut-parleur (son)", 24),           # 3 s
    "timer_anim": ("timer", "Minuteur (aiguille qui tourne)", 48),   # 1 tour en 6 s
    "rain_anim": ("cloud", "Pluie", 24),                             # 3 s
    "gear_anim": ("gear", "Engrenage qui tourne (automatisme)", 32), # 1/8 de tour en 4 s
}


# --------------------------------------------------------------------------- geometrie
def _cubic(p0, p1, p2, p3, n=10):
    out = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        a, b, c, d = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def _path(start, *segs):
    """Courbe fermee : depart puis segments de Bezier (controle 1, controle 2, arrivee)."""
    pts, cur = [start], start
    for c1, c2, end in segs:
        pts += _cubic(cur, c1, c2, end)[1:]
        cur = end
    return pts


def _circle(cx, cy, r, n=28, a0=0.0, a1=2 * math.pi):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def _ellipse(cx, cy, rx, ry, n=28):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# --------------------------------------------------------------------------- rasterisation (0..1 -> S x S)
def fill(polys, S, ss=4):
    """Couverture (0..1 par pixel) de polygones pleins. Horizontal exact, vertical sur-echantillonne."""
    cov = [0.0] * (S * S)
    for poly in polys:
        pts = [(x * S, y * S) for x, y in poly]
        n = len(pts)
        edges = [(pts[i], pts[(i + 1) % n]) for i in range(n) if pts[i][1] != pts[(i + 1) % n][1]]
        if not edges:
            continue
        ymin = max(0, int(min(p[1] for p in pts)))
        ymax = min(S - 1, int(max(p[1] for p in pts)))
        for row in range(ymin, ymax + 1):
            base = row * S
            for k in range(ss):
                y = row + (k + 0.5) / ss
                xs = sorted(x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                            for (x0, y0), (x1, y1) in edges if (y0 <= y < y1) or (y1 <= y < y0))
                for j in range(0, len(xs) - 1, 2):
                    xa, xb = max(0.0, xs[j]), min(float(S), xs[j + 1])
                    for px in range(int(xa), int(math.ceil(xb))):
                        ov = min(xb, px + 1) - max(xa, px)
                        if ov > 0:
                            cov[base + px] += ov / ss
    return [c if c < 1.0 else 1.0 for c in cov]


def stroke(lines, S, width, ss=3):
    """Couverture d'un trait d'epaisseur `width` (en fraction de S) le long de lignes.
    lines : liste de (points, fermee)."""
    hw = width * S / 2
    segs = []
    for pts, closed in lines:
        p = [(x * S, y * S) for x, y in pts]
        if closed:
            p.append(p[0])
        for (ax, ay), (bx, by) in zip(p, p[1:]):
            dx, dy = bx - ax, by - ay
            segs.append((ax, ay, dx, dy, dx * dx + dy * dy or 1e-9,
                         min(ax, bx) - hw - 1, max(ax, bx) + hw + 1, min(ay, by) - hw - 1, max(ay, by) + hw + 1))
    hw2 = hw * hw
    cov = [0.0] * (S * S)
    inv = 1.0 / (ss * ss)
    offs = [(i + 0.5) / ss for i in range(ss)]
    for py in range(S):
        row_segs = [s for s in segs if s[7] <= py + 1 and py <= s[8]]
        if not row_segs:
            continue
        for px in range(S):
            cands = [s for s in row_segs if s[5] <= px + 1 and px <= s[6]]
            if not cands:
                continue
            hit = 0
            for oy in offs:
                y = py + oy
                for ox in offs:
                    x = px + ox
                    for ax, ay, dx, dy, l2, *_ in cands:
                        t = ((x - ax) * dx + (y - ay) * dy) / l2
                        t = 0.0 if t < 0 else 1.0 if t > 1 else t
                        ex, ey = ax + t * dx - x, ay + t * dy - y
                        if ex * ex + ey * ey <= hw2:
                            hit += 1
                            break
            if hit:
                cov[py * S + px] = hit * inv
    return cov


def _sub(a, b):
    return [x - y if x > y else 0.0 for x, y in zip(a, b)]


# --------------------------------------------------------------------------- dessins
LINE = 0.085            # epaisseur du trait des icones "eteintes" (proche des icones Windows)


def _flame(sway=0.0, h=0.0, w=1.0, lick=0.0):
    """Flamme : corps arrondi, pointe principale penchee, petite langue de feu a gauche."""
    def P(x, y):                                  # largeur variable autour de l'axe central
        return (0.5 + (x - 0.5) * w, y)
    return _path(P(0.5, 0.94),
                 (P(0.68, 0.94), P(0.79, 0.82), P(0.79, 0.64)),
                 (P(0.79, 0.45), P(0.63 + sway * 0.4, 0.33), P(0.56 + sway, 0.05 + h)),
                 (P(0.56 + sway * 0.6, 0.24), P(0.50, 0.36), P(0.43, 0.45)),
                 (P(0.40, 0.39), P(0.36, 0.34), P(0.31 + lick, 0.25 - h * 0.5)),
                 (P(0.23, 0.39), P(0.21, 0.51), P(0.21, 0.64)),
                 (P(0.21, 0.82), P(0.32, 0.94), P(0.5, 0.94)))


def _core(sway=0.0, h=0.0):
    """Coeur de la flamme, plus clair."""
    return _path((0.5, 0.88),
                 ((0.6, 0.88), (0.65, 0.80), (0.64, 0.71)),
                 ((0.63, 0.62), (0.56 + sway * 0.5, 0.56), (0.52 + sway, 0.44 + h)),
                 ((0.47 + sway * 0.5, 0.56), (0.36, 0.62), (0.36, 0.71)),
                 ((0.35, 0.80), (0.40, 0.88), (0.5, 0.88)))


def _blade(theta):
    c = 0.5
    left, right = [], []
    n = 12
    for i in range(n + 1):
        u = 0.03 + 0.95 * i / n
        r = 0.07 + 0.36 * u
        a = theta + 0.55 * u
        x, y = c + r * math.cos(a), c + r * math.sin(a)
        da = a + math.pi / 2 - 0.35            # normale, un peu inclinee : pale "en virgule"
        hw = 0.145 * math.sin(math.pi * u) ** 0.6
        left.append((x + hw * math.cos(da), y + hw * math.sin(da)))
        right.append((x - hw * math.cos(da), y - hw * math.sin(da)))
    return left + right[::-1]


def _fan_shapes(theta):
    return [_blade(theta + k * 2 * math.pi / 3) for k in range(3)] + [_circle(0.5, 0.5, 0.085, 18)]


BULB_C, BULB_R = (0.5, 0.41), 0.21


def _bulb_outline():
    cx, cy = BULB_C
    arc = _circle(cx, cy, BULB_R, 26, math.radians(135), math.radians(405))
    return arc + [(0.575, 0.67), (0.425, 0.67)]


def _bulb_lines():
    return [(_bulb_outline(), True), ([(0.42, 0.765), (0.58, 0.765)], False), ([(0.45, 0.86), (0.55, 0.86)], False)]


def _rays():
    cx, cy = BULB_C
    out = []
    for deg in (-90, -35, -145, 10, 170):
        a = math.radians(deg)
        out.append(([(cx + 0.30 * math.cos(a), cy + 0.30 * math.sin(a)),
                     (cx + 0.38 * math.cos(a), cy + 0.38 * math.sin(a))], False))
    return out


EQ_X = (0.19, 0.39, 0.61, 0.81)
EQ_REST = (0.32, 0.58, 0.44, 0.26)


def _bars(heights):
    return [_rect(x - 0.075, 0.9 - h, x + 0.075, 0.9) for x, h in zip(EQ_X, heights)]


def _drop(cx, ty, s):
    return _path((cx, ty),
                 ((cx + 0.06 * s, ty + 0.10 * s), (cx + 0.17 * s, ty + 0.18 * s), (cx + 0.17 * s, ty + 0.28 * s)),
                 ((cx + 0.17 * s, ty + 0.37 * s), (cx + 0.09 * s, ty + 0.43 * s), (cx, ty + 0.43 * s)),
                 ((cx - 0.09 * s, ty + 0.43 * s), (cx - 0.17 * s, ty + 0.37 * s), (cx - 0.17 * s, ty + 0.28 * s)),
                 ((cx - 0.17 * s, ty + 0.18 * s), (cx - 0.06 * s, ty + 0.10 * s), (cx, ty)))


def layers(key, S, active, n_frames):
    """Liste d'images ; chaque image = liste de couches (couverture, role de couleur, opacite).
    Roles : "fg" (couleur normale de l'icone), "on" (allume), "core" (coeur de flamme, plus clair)."""
    if key in _BUILDERS:
        return _BUILDERS[key](S, active, n_frames)
    tau = 2 * math.pi
    if not active:
        if key == "flame_anim":
            return [[(stroke([(_flame(), True)], S, LINE), "fg", 1.0)]]
        if key == "fan_anim":
            return [[(stroke([(p, True) for p in _fan_shapes(-0.4)], S, LINE * 0.9), "fg", 1.0)]]
        if key == "bulb_anim":
            return [[(stroke(_bulb_lines(), S, LINE), "fg", 1.0)]]
        if key == "eq_anim":
            return [[(fill(_bars(EQ_REST), S), "fg", 1.0)]]
        if key == "drop_anim":
            return [[(stroke([(_drop(0.5, 0.1, 1.75), True)], S, LINE), "fg", 1.0)]]
        return []

    frames = []
    if key == "bulb_anim":           # formes fixes, seule l'opacite du halo et des rayons respire
        body = fill([_bulb_outline()], S)
        lines = stroke(_bulb_lines(), S, LINE)
        rays = stroke(_rays(), S, LINE * 0.9)
        for i in range(n_frames):
            b = 0.5 + 0.5 * math.sin(tau * i / n_frames)
            frames.append([(body, "on", 0.4 + 0.25 * b), (lines, "on", 1.0), (rays, "on", 0.25 + 0.75 * b)])
        return frames
    for i in range(n_frames):
        t = i / n_frames
        if key == "flame_anim":
            sway = 0.045 * math.sin(tau * t) + 0.018 * math.sin(2 * tau * t + 0.7)
            h = 0.025 * math.sin(tau * t + 1.3) + 0.015 * math.sin(3 * tau * t)
            w = 1 + 0.03 * math.sin(2 * tau * t + 0.4)
            lick = 0.03 * math.sin(tau * t + 2.2)
            core = _core(-sway * 0.6 + 0.015 * math.sin(3 * tau * t + 2), h * 0.8)
            frames.append([(fill([_flame(sway, h, w, lick)], S), "on", 1.0), (fill([core], S), "core", 1.0)])
        elif key == "fan_anim":
            frames.append([(fill(_fan_shapes(-0.4 + t * tau / 3), S), "on", 1.0)])
        elif key == "eq_anim":
            hs = [0.2 + 0.55 * (0.5 + 0.5 * math.sin(tau * (f * t) + ph))
                  for f, ph in ((1, 0.0), (2, 1.9), (1, 3.6), (2, 5.0))]
            frames.append([(fill(_bars(hs), S), "on", 1.0)])
        elif key == "drop_anim":
            ls = []
            if t < 0.6:                                   # grosse goutte qui descend, de plus en plus vite
                q = t / 0.6
                ls.append((fill([_drop(0.5, -0.04 + 0.2 * q * q, 1.55)], S), "on", min(1.0, 0.35 + q * 2.5)))
            if 0.5 <= t:                                  # rond dans l'eau qui s'elargit et s'efface
                q = (t - 0.5) / 0.5
                rx = 0.16 + 0.3 * q
                ring = _sub(fill([_ellipse(0.5, 0.88, rx, rx * 0.3)], S),
                            fill([_ellipse(0.5, 0.88, rx - 0.09, (rx - 0.09) * 0.27)], S))
                ls.append((ring, "on", 1.0 - q * 0.9))
            frames.append(ls)
    return frames


# --------------------------------------------------------------------------- icones supplementaires
TAU = 2 * math.pi
W = 0.085                       # epaisseur des traits


def _rot(pts, a, cx=0.5, cy=0.5):
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def _quad(p0, p1, w=W):
    """Trait droit plein (rectangle) de p0 a p1."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    d = math.hypot(dx, dy) or 1e-9
    nx, ny = -dy / d * w / 2, dx / d * w / 2
    return [(p0[0] + nx, p0[1] + ny), (p1[0] + nx, p1[1] + ny), (p1[0] - nx, p1[1] - ny), (p0[0] - nx, p0[1] - ny)]


def _arc_band(cx, cy, r, a0, a1, w=W, n=18):
    """Arc epais (bande) de l'angle a0 a a1 (radians, y vers le bas)."""
    outer = [(cx + (r + w / 2) * math.cos(a0 + (a1 - a0) * i / n), cy + (r + w / 2) * math.sin(a0 + (a1 - a0) * i / n))
             for i in range(n + 1)]
    inner = [(cx + (r - w / 2) * math.cos(a0 + (a1 - a0) * i / n), cy + (r - w / 2) * math.sin(a0 + (a1 - a0) * i / n))
             for i in range(n, -1, -1)]
    return outer + inner


def _ring(S, cx, cy, r, w=W):
    return _sub(fill([_circle(cx, cy, r + w / 2, 32)], S), fill([_circle(cx, cy, max(0.001, r - w / 2), 32)], S))


def _scale(cov, a):
    return [c * a for c in cov]


def _max(*covs):
    return [max(v) for v in zip(*covs)]


def _wave(f, n):
    """Impulsion douce 0..1 qui passe une fois par cycle (f = phase 0..1)."""
    f %= 1.0
    return 0.5 - 0.5 * math.cos(TAU * f)


# --- flocon
def _snow_polys(a):
    polys = []
    for k in range(6):
        ang = a + k * TAU / 6
        tip = (0.5 + 0.4 * math.cos(ang), 0.5 + 0.4 * math.sin(ang))
        polys.append(_quad((0.5, 0.5), tip))
        b = (0.5 + 0.24 * math.cos(ang), 0.5 + 0.24 * math.sin(ang))
        for s in (-1, 1):
            e = (b[0] + 0.12 * math.cos(ang + s * 0.8), b[1] + 0.12 * math.sin(ang + s * 0.8))
            polys.append(_quad(b, e, W * 0.85))
    return polys


def _b_snow(S, active, n):
    if not active:
        return [[(fill(_snow_polys(-TAU / 4), S), "fg", 1.0)]]
    return [[(fill(_snow_polys(-TAU / 4 + (i / n) * TAU / 6), S), "on", 1.0)] for i in range(n)]


# --- soleil
def _sun_rays(a, l0=0.29, l1=0.43):
    return [_quad((0.5 + l0 * math.cos(a + k * TAU / 8), 0.5 + l0 * math.sin(a + k * TAU / 8)),
                  (0.5 + l1 * math.cos(a + k * TAU / 8), 0.5 + l1 * math.sin(a + k * TAU / 8))) for k in range(8)]


def _b_sun(S, active, n):
    if not active:
        return [[(_max(_ring(S, 0.5, 0.5, 0.15), fill(_sun_rays(0), S)), "fg", 1.0)]]
    disc = fill([_circle(0.5, 0.5, 0.19, 32)], S)
    out = []
    for i in range(n):
        t = i / n
        ext = 0.43 + 0.03 * math.sin(TAU * t)
        out.append([(disc, "on", 1.0), (fill(_sun_rays(t * TAU / 8, 0.29, ext), S), "on", 1.0)])
    return out


# --- wi-fi
_WIFI_C = (0.5, 0.8)


def _b_wifi(S, active, n):
    cx, cy = _WIFI_C
    dot = fill([_circle(cx, cy, 0.065, 20)], S)
    arcs = [fill([_arc_band(cx, cy, r, math.radians(-135), math.radians(-45))], S) for r in (0.22, 0.38, 0.54)]
    if not active:
        return [[(_max(dot, *arcs), "fg", 1.0)]]
    out = []
    for i in range(n):
        t = i / n
        ls = [(dot, "on", 1.0)]
        for k, a in enumerate(arcs):
            ls.append((a, "on", 0.25 + 0.75 * _wave(t - 0.12 - k * 0.16, n)))
        out.append(ls)
    return out


# --- cloche
def _bell_polys():
    body = _path((0.5, 0.17),
                 ((0.68, 0.17), (0.73, 0.31), (0.73, 0.47)),
                 ((0.73, 0.61), (0.77, 0.69), (0.86, 0.75)),
                 ((0.62, 0.75), (0.38, 0.75), (0.14, 0.75)),
                 ((0.23, 0.69), (0.27, 0.61), (0.27, 0.47)),
                 ((0.27, 0.31), (0.32, 0.17), (0.5, 0.17)))
    return body, _circle(0.5, 0.84, 0.075, 18), _circle(0.5, 0.12, 0.045, 14)


def _b_bell(S, active, n):
    body, clap, knob = _bell_polys()
    if not active:
        return [[(_max(stroke([(body, True)], S, W), fill([clap, knob], S)), "fg", 1.0)]]
    out = []
    for i in range(n):
        t = i / n
        a = math.radians(16) * math.sin(TAU * 2 * t / 0.6) * (1 - t / 0.6) if t < 0.6 else 0.0
        polys = [_rot(p, a, 0.5, 0.12) for p in (body, knob)]
        cl = _rot(clap, a * 1.6, 0.5, 0.12)          # le battant suit avec un peu de retard
        out.append([(fill(polys + [cl], S), "on", 1.0)])
    return out


# --- lave-linge
def _b_washer(S, active, n):
    frame_ = stroke([(_rect(0.15, 0.08, 0.85, 0.92), True), ([(0.15, 0.25), (0.85, 0.25)], False)], S, W)
    knob = fill([_circle(0.3, 0.165, 0.035, 12), _circle(0.42, 0.165, 0.035, 12)], S)
    door = _ring(S, 0.5, 0.585, 0.2)
    base = _max(frame_, knob, door)
    if not active:
        return [[(base, "fg", 1.0)]]
    out = []
    for i in range(n):
        a = (i / n) * TAU
        ox, oy = 0.5 + 0.055 * math.cos(a), 0.585 + 0.055 * math.sin(a)
        crescent = _sub(fill([_circle(0.5, 0.585, 0.13, 28)], S), fill([_circle(ox, oy, 0.12, 28)], S))
        out.append([(base, "on", 1.0), (crescent, "on", 1.0)])
    return out


# --- eclair
_BOLT = [(0.6, 0.04), (0.2, 0.56), (0.46, 0.56), (0.38, 0.96), (0.8, 0.42), (0.54, 0.42), (0.64, 0.04)]


def _b_bolt(S, active, n):
    if not active:
        return [[(stroke([(_BOLT, True)], S, W * 0.9), "fg", 1.0)]]
    full = fill([_BOLT], S)
    out = []
    for i in range(n):
        t = i / n
        level = 1.05 - 1.25 * t                       # l'energie monte du bas vers le haut
        rows = []
        for y in range(S):
            k = 1.0 if (y + 0.5) / S >= level else 0.35
            rows.extend(c * k for c in full[y * S:(y + 1) * S])
        out.append([(rows, "on", 1.0)])
    return out


# --- batterie en charge
def _b_battery(S, active, n):
    body = stroke([(_rect(0.27, 0.17, 0.73, 0.92), True)], S, W)
    cap = fill([_rect(0.4, 0.07, 0.6, 0.17)], S)
    bars = [fill([_rect(0.36, 0.73 - k * 0.165, 0.64, 0.83 - k * 0.165)], S) for k in range(4)]
    if not active:
        return [[(_max(body, cap, bars[0], bars[1]), "fg", 1.0)]]
    out = []
    for i in range(n):
        shown = int((i / n) * 5)                      # 0, 1, 2, 3 puis 4 barres
        ls = [(_max(body, cap), "on", 1.0)]
        for k in range(min(shown, 4)):
            ls.append((bars[k], "on", 1.0))
        out.append(ls)
    return out


# --- detection (ondes)
def _b_radar(S, active, n):
    dot = fill([_circle(0.5, 0.5, 0.1, 20)], S)
    if not active:
        return [[(_max(dot, _ring(S, 0.5, 0.5, 0.3, W * 0.8)), "fg", 1.0)]]
    out = []
    for i in range(n):
        t = i / n
        ls = [(dot, "on", 1.0)]
        for ph in (0.0, 0.5):
            q = (t + ph) % 1.0
            ls.append((_ring(S, 0.5, 0.5, 0.15 + 0.3 * q, W * 0.8), "on", 1.0 - q))
        out.append(ls)
    return out


# --- radiateur
def _radiator(S):
    body = stroke([(_rect(0.13, 0.5, 0.87, 0.86), True)], S, W)
    fins = fill([_quad((x, 0.57), (x, 0.79), W * 0.8) for x in (0.32, 0.5, 0.68)], S)
    feet = fill([_rect(0.2, 0.86, 0.28, 0.94), _rect(0.72, 0.86, 0.8, 0.94)], S)
    return _max(body, fins, feet)


def _heat_wave(x, y0, y1, phase, w=W * 0.75):
    n = 16
    pts = [(x + 0.035 * math.sin(TAU * 1.25 * (k / n) + phase), y0 + (y1 - y0) * k / n) for k in range(n + 1)]
    return [_quad(a, b, w) for a, b in zip(pts, pts[1:])] + [_circle(p[0], p[1], w / 2, 8) for p in pts[1:-1]]


def _b_heater(S, active, n):
    rad = _radiator(S)
    if not active:
        return [[(rad, "fg", 1.0)]]
    out = []
    for i in range(n):
        t = i / n
        ls = [(rad, "on", 1.0)]
        for k, x in enumerate((0.3, 0.5, 0.7)):
            q = (t + k / 3) % 1.0
            dy = -0.1 * q                            # les ondes montent et s'effacent
            ls.append((fill(_heat_wave(x, 0.12 + dy, 0.42 + dy, TAU * t + k), S), "on", 1.0 - q * 0.85))
        out.append(ls)
    return out


# --- haut-parleur
_SPK = [(0.1, 0.38), (0.27, 0.38), (0.5, 0.17), (0.5, 0.83), (0.27, 0.62), (0.1, 0.62)]


def _b_speaker(S, active, n):
    spk = fill([_SPK], S)
    arcs = [fill([_arc_band(0.5, 0.5, r, math.radians(-50), math.radians(50))], S) for r in (0.17, 0.32)]
    if not active:
        return [[(spk, "fg", 1.0)]]
    out = []
    for i in range(n):
        t = i / n
        ls = [(spk, "on", 1.0)]
        for k, a in enumerate(arcs):
            ls.append((a, "on", 0.2 + 0.8 * _wave(t - k * 0.2, n)))
        out.append(ls)
    return out


# --- minuteur
def _b_timer(S, active, n):
    ring = _ring(S, 0.5, 0.56, 0.34)
    top = fill([_rect(0.42, 0.06, 0.58, 0.13), _quad((0.5, 0.13), (0.5, 0.22), W * 0.9)], S)
    pivot = fill([_circle(0.5, 0.56, 0.05, 12)], S)
    base = _max(ring, top, pivot)

    def hand(a):
        return fill([_quad((0.5, 0.56), (0.5 + 0.24 * math.cos(a), 0.56 + 0.24 * math.sin(a)), W * 0.85)], S)
    if not active:
        return [[(_max(base, hand(-TAU / 4)), "fg", 1.0)]]
    return [[(base, "on", 1.0), (hand(-TAU / 4 + TAU * i / n), "on", 1.0)] for i in range(n)]


# --- pluie
def _cloud():
    pts = [(0.32 + 0.15 * math.cos(a), 0.42 + 0.15 * math.sin(a)) for a in
           [math.radians(90 + 180 * k / 10) for k in range(11)]]
    pts += [(0.53 + 0.2 * math.cos(a), 0.34 + 0.2 * math.sin(a)) for a in
            [math.radians(200 + 140 * k / 12) for k in range(13)]]
    pts += [(0.71 + 0.15 * math.cos(a), 0.42 + 0.15 * math.sin(a)) for a in
            [math.radians(270 + 180 * k / 10) for k in range(11)]]
    return pts


def _b_rain(S, active, n):
    cloud = _cloud()
    if not active:
        return [[(stroke([(cloud, True)], S, W), "fg", 1.0)]]
    body = fill([cloud], S)
    out = []
    for i in range(n):
        t = i / n
        drops = []
        for k, x in enumerate((0.33, 0.52, 0.71)):
            q = (t + k * 0.37) % 1.0
            y = 0.62 + 0.3 * q
            drops.append((fill([_quad((x, y), (x - 0.03, y + 0.1), W * 0.8)], S), "on", min(1.0, (1 - q) * 2.2)))
        out.append([(body, "on", 1.0)] + drops)
    return out


# --- engrenage
def _gear(a):
    pts = []
    teeth = 8
    for k in range(teeth * 4):
        ang = a + TAU * k / (teeth * 4)
        r = 0.43 if (k % 4) in (1, 2) else 0.32
        pts.append((0.5 + r * math.cos(ang), 0.5 + r * math.sin(ang)))
    return pts


def _b_gear(S, active, n):
    hole = fill([_circle(0.5, 0.5, 0.12, 20)], S)
    if not active:
        return [[(_sub(fill([_gear(0)], S), hole), "fg", 1.0)]]
    return [[(_sub(fill([_gear(TAU / 8 * i / n)], S), hole), "on", 1.0)] for i in range(n)]


_BUILDERS = {
    "snow_anim": _b_snow, "sun_anim": _b_sun, "wifi_anim": _b_wifi, "bell_anim": _b_bell,
    "washer_anim": _b_washer, "bolt_anim": _b_bolt, "battery_anim": _b_battery, "radar_anim": _b_radar,
    "heater_anim": _b_heater, "speaker_anim": _b_speaker, "timer_anim": _b_timer, "rain_anim": _b_rain,
    "gear_anim": _b_gear,
}


# --------------------------------------------------------------------------- PNG
def _hex(c):
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a, b, k):
    (r1, g1, b1), (r2, g2, b2) = _hex(a), _hex(b)
    return "#%02x%02x%02x" % (round(r1 + (r2 - r1) * k), round(g1 + (g2 - g1) * k), round(b1 + (b2 - b1) * k))


def to_png(S, frame, colors):
    """Compose les couches (operateur "over") -> PNG RGBA. colors : {role: "#rrggbb"}."""
    px = [[0.0, 0.0, 0.0, 0.0] for _ in range(S * S)]    # premultiplie : r, g, b, a
    for cov, role, alpha in frame:
        r, g, b = _hex(colors[role])
        for i, c in enumerate(cov):
            a = c * alpha
            if a <= 0:
                continue
            p = px[i]
            k = 1 - a
            p[0] = r * a + p[0] * k
            p[1] = g * a + p[1] * k
            p[2] = b * a + p[2] * k
            p[3] = a + p[3] * k
    rows = []
    for y in range(S):
        row = bytearray(b"\x00")
        for p in px[y * S:(y + 1) * S]:
            a = p[3]
            if a > 0:
                row += bytes((min(255, round(p[0] / a)), min(255, round(p[1] / a)), min(255, round(p[2] / a)),
                              min(255, round(a * 255))))
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(bytes(row))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", S, S, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))


_cache = {}


def frames_png(key, S, active, on, fg):
    """PNG des images d'une icone (1 seule si eteinte). Mis en cache."""
    ck = (key, S, active, on, fg)
    if ck not in _cache:
        n = ANIM_ICONS[key][2]
        colors = {"fg": fg, "on": on, "core": mix(on, fg, 0.45)}
        _cache[ck] = [to_png(S, f, colors) for f in layers(key, S, active, n)]
    return _cache[ck]
