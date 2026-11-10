"""Generate the pixel-art GIFs used by README.md.

Everything is drawn on a tiny canvas (128x128 for icons, 200x64 for the hero)
with hard-edged rectangles only, then upscaled with NEAREST so the pixels stay
crisp. Frames are quantised against a single palette built from the colours that
were actually used, so there is no per-frame palette flicker.

Run:
    uv run --with pillow python scripts/generate_readme_gifs.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"

# --- palette ---------------------------------------------------------------

BG = (13, 20, 34)
PANEL = (17, 26, 43)
FRAME = (38, 56, 86)
INK = (232, 240, 250)
MUTED = (120, 140, 170)
DIM = (58, 76, 104)

TEAL = (46, 196, 182)
BLUE = (79, 142, 247)
PURPLE = (139, 92, 246)
ORANGE = (232, 134, 60)
GREEN = (74, 222, 128)
RED = (248, 113, 113)
YELLOW = (250, 204, 21)


def lt(c, f=0.35):
    return tuple(round(a + (255 - a) * f) for a in c)


def dk(c, f=0.35):
    return tuple(round(a * (1 - f)) for a in c)


# --- tiny 3x5 font ---------------------------------------------------------

FONT = {
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "J": ("001", "001", "001", "101", "010"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("110", "101", "101", "101", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "P": ("110", "101", "110", "100", "100"),
    "Q": ("010", "101", "101", "110", "011"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "011"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("110", "001", "010", "100", "111"),
    "3": ("110", "001", "010", "001", "110"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "110", "001", "110"),
    "6": ("011", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "110"),
    "+": ("000", "010", "111", "010", "000"),
    "-": ("000", "000", "111", "000", "000"),
    "%": ("101", "001", "010", "100", "101"),
    ".": ("000", "000", "000", "000", "010"),
    "/": ("001", "001", "010", "100", "100"),
    " ": ("000", "000", "000", "000", "000"),
}


def rect(img, x, y, w, h, color):
    if w <= 0 or h <= 0:
        return
    img.paste(color, (x, y, x + w, y + h))


def text(img, x, y, s, color, scale=1):
    cx = x
    for ch in s.upper():
        glyph = FONT.get(ch, FONT[" "])
        for r, row in enumerate(glyph):
            for c, bit in enumerate(row):
                if bit == "1":
                    rect(img, cx + c * scale, y + r * scale, scale, scale, color)
        cx += 4 * scale


def text_width(s, scale=1):
    return max(0, len(s) * 4 * scale - scale)


def line(img, x0, y0, x1, y1, color, thick=1):
    """Bresenham, drawn as thick square stamps."""
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        rect(img, x0, y0, thick, thick, color)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def dotted(img, x0, y0, x1, y1, color, step=3):
    """Bresenham with every `step`-th pixel skipped."""
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    n = 0
    while True:
        if n % step != step - 1:
            rect(img, x0, y0, 1, 1, color)
        n += 1
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def coin(img, x, y, c=ORANGE, size=5):
    """Little 5x5 pixel coin."""
    m = size // 2
    rect(img, x + 1, y, size - 2, 1, lt(c, 0.45))
    rect(img, x, y + 1, size, size - 2, c)
    rect(img, x + 1, y + size - 1, size - 2, 1, dk(c))
    rect(img, x + 1, y + 1, 2, 1, lt(c, 0.6))
    del m


def star(img, x, y, color, big=False):
    """Four-point pixel sparkle."""
    rect(img, x, y - 1, 1, 3, color)
    rect(img, x - 1, y, 3, 1, color)
    if big:
        rect(img, x - 3, y, 1, 1, color)
        rect(img, x + 3, y, 1, 1, color)
        rect(img, x, y - 3, 1, 1, color)
        rect(img, x, y + 3, 1, 1, color)


def tri_fill(img, p0, p1, p2, color):
    """Solid triangle via half-plane tests (pixel art, no antialiasing)."""
    xs = [p0[0], p1[0], p2[0]]
    ys = [p0[1], p1[1], p2[1]]

    def side(a, b, pt):
        return (b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0])

    for y in range(min(ys), max(ys) + 1):
        for x in range(min(xs), max(xs) + 1):
            d0 = side(p0, p1, (x, y))
            d1 = side(p1, p2, (x, y))
            d2 = side(p2, p0, (x, y))
            if (d0 >= 0 and d1 >= 0 and d2 >= 0) or (d0 <= 0 and d1 <= 0 and d2 <= 0):
                rect(img, x, y, 1, 1, color)


def panel(img, w, h):
    rect(img, 0, 0, w, h, BG)
    rect(img, 1, 1, w - 2, h - 2, PANEL)
    # corner brackets
    for cx, cy, sx, sy in ((0, 0, 1, 1), (w - 1, 0, -1, 1), (0, h - 1, 1, -1), (w - 1, h - 1, -1, -1)):
        x = cx if sx > 0 else cx - 1
        y = cy if sy > 0 else cy - 1
        rect(img, x, y, 1, 7, FRAME)
        rect(img, x, y, 7, 1, FRAME)
        del x, y


def grid(img, w, h, step=8, color=None):
    color = color or (20, 30, 48)
    for x in range(step, w, step):
        rect(img, x, 2, 1, h - 4, color)
    for y in range(step, h, step):
        rect(img, 2, y, w - 4, 1, color)


def tri(t):
    """0->1->0 triangle wave for t in [0,1)."""
    return 1 - abs(2 * t - 1)


# --- icons -----------------------------------------------------------------


def icon_performance(img, t):
    panel(img, 128, 128)
    text(img, 10, 8, "ROAS", MUTED, 3)

    values = ["2.4", "2.7", "2.9", "3.1"]
    idx = int(t * len(values)) % len(values)
    text(img, 118 - text_width(values[idx], 3), 8, values[idx], INK, 3)

    base = 108
    rect(img, 12, base, 104, 1, FRAME)
    bars = [(16, 34, TEAL), (42, 52, BLUE), (68, 68, PURPLE), (94, 84, ORANGE)]
    heights = []
    for i, (_, h, _) in enumerate(bars):
        bob = round(math.sin(2 * math.pi * (t * 2 + i * 0.18)) * 2)
        heights.append(h + bob)

    # dotted guide line through the bar tops, drawn behind the bars
    tops = [(x + 9, base - hh) for (x, _, _), hh in zip(bars, heights)]
    for i in range(len(tops) - 1):
        x0, y0 = tops[i]
        x1, y1 = tops[i + 1]
        dotted(img, x0, y0 - 5, x1, y0 - 5, DIM)
        dotted(img, x1, y0 - 5, x1, y1 - 5, DIM)

    for (x, _, c), hh in zip(bars, heights):
        rect(img, x, base - hh, 18, hh, c)
        rect(img, x, base - hh, 18, 2, lt(c, 0.5))
        rect(img, x, base - hh, 2, hh, lt(c, 0.22))
        rect(img, x + 16, base - hh, 2, hh, dk(c))

    # sweep cursor + sparkle on the tallest bar
    sx = 14 + int(100 * t)
    rect(img, sx, 30, 1, 78, lt(FRAME, 0.55))
    rect(img, sx - 1, 30, 3, 2, lt(TEAL, 0.4))
    phase = (t * 2) % 1.0
    star(img, 103, 24 - round(abs(math.sin(math.pi * phase)) * 2), YELLOW, big=phase > 0.45)


def icon_funnel(img, t):
    panel(img, 128, 128)
    text(img, 10, 8, "2.4K", INK, 3)

    bands = [(28, 96, TEAL), (41, 72, BLUE), (54, 50, PURPLE), (67, 30, ORANGE)]
    cx = 64
    for y, w, c in bands:
        x = cx - w // 2
        rect(img, x, y, w, 13, c)
        rect(img, x, y, w, 2, lt(c, 0.5))
        rect(img, x, y + 11, w, 2, dk(c))
        rect(img, x, y + 13, w, 1, (9, 14, 25))

    # falling enquiries
    for i in range(9):
        p = (t + i / 9) % 1.0
        y = 26 + round(64 * p)
        jitter = (i % 3 - 1) * 3 + (1 if i % 2 else -1)
        x = cx + jitter
        c = INK if p < 0.55 else lt(TEAL, 0.3)
        rect(img, x, y, 3, 3, c)
        if p < 0.55:
            rect(img, x, y, 1, 1, BG)

    # stem + collected conversions
    rect(img, cx - 4, 81, 8, 8, FRAME)
    rect(img, cx - 11, 100, 22, 4, ORANGE)
    rect(img, cx - 8, 95, 16, 5, ORANGE)
    rect(img, cx - 5, 90, 10, 5, ORANGE)
    rect(img, cx - 11, 100, 22, 1, lt(ORANGE, 0.45))
    rect(img, cx - 8, 95, 16, 1, lt(ORANGE, 0.45))
    rect(img, cx - 5, 90, 10, 1, lt(ORANGE, 0.45))

    pulse = 1 - ((t * 2) % 1.0)
    star(img, cx + 16, 96, lt(GREEN, 0.5), big=pulse > 0.65)
    text(img, 10, 106, "312", GREEN, 3)


def icon_abtest(img, t):
    panel(img, 128, 128)
    text(img, 10, 8, "A/B", MUTED, 3)

    tubes = [(30, "A", 0.62, BLUE), (74, "B", 0.84, GREEN)]
    for i, (x, label, level, c) in enumerate(tubes):
        top, bottom, w = 44, 106, 22
        rect(img, x, top, w, bottom - top, (10, 16, 28))
        rect(img, x, top, 1, bottom - top, FRAME)
        rect(img, x + w - 1, top, 1, bottom - top, FRAME)
        rect(img, x, bottom, w, 2, FRAME)

        wob = math.sin(2 * math.pi * (t * 2 + i * 0.5)) * 0.035
        hh = round((bottom - top - 4) * (level + wob))
        rect(img, x + 2, bottom - 2 - hh, w - 4, hh, c)
        rect(img, x + 2, bottom - 2 - hh, w - 4, 2, lt(c, 0.45))

        if label == "B":
            # caret riding above the winning level
            mid = x + w // 2
            fy = bottom - 2 - hh - 6
            rect(img, mid - 3, fy + 3, 7, 2, GREEN)
            rect(img, mid - 2, fy + 2, 5, 1, GREEN)
            rect(img, mid - 1, fy + 1, 3, 1, GREEN)
            rect(img, mid, fy, 1, 1, GREEN)

        # graduation ticks
        for k in range(1, 4):
            ty = top + k * (bottom - top) // 4
            rect(img, x - 2, ty, 2, 1, DIM)

        text(img, x + w // 2 - 4, top - 20, label, INK, 3)

    text(img, 118 - text_width("+12%", 3), 8, "+12%", GREEN, 3)


def icon_budget(img, t):
    panel(img, 128, 128)
    text(img, 10, 6, "SPLIT", MUTED, 3)

    cx, cy = 64, 68
    r_out, r_in = 33, 17
    rot = 2 * math.pi * t
    slices = [(0.44, TEAL), (0.31, PURPLE), (0.25, ORANGE)]

    edges = []
    acc = -math.pi / 2
    for frac, c in slices:
        edges.append((acc % (2 * math.pi), (acc + frac * 2 * math.pi) % (2 * math.pi), c))
        acc += frac * 2 * math.pi

    for y in range(cy - r_out - 1, cy + r_out + 2):
        for x in range(cx - r_out - 1, cx + r_out + 2):
            d = math.hypot(x - cx, y - cy)
            if not (r_in <= d <= r_out):
                continue
            ang = math.atan2(y - cy, x - cx) % (2 * math.pi)
            for a0, a1, c in edges:
                inside = (a0 <= ang < a1) if a0 < a1 else (ang >= a0 or ang < a1)
                if not inside:
                    continue
                delta = (ang - (rot % (2 * math.pi))) % (2 * math.pi)
                col = lt(c, 0.45) if delta < 0.45 else lt(c, 0.18) if delta < 0.9 else c
                rect(img, x, y, 1, 1, col)
                break

    text(img, cx - text_width("38%", 2) // 2, cy - 5, "38%", INK, 2)

    # coins orbiting the ring
    for i in range(3):
        a = rot + i * 2 * math.pi / 3
        x = round(cx + math.cos(a) * 44) - 2
        y = round(cy + math.sin(a) * 44) - 2
        coin(img, x, y, ORANGE if i != 1 else TEAL, size=7)


def icon_bid(img, t):
    panel(img, 128, 128)
    text(img, 10, 8, "CPC", MUTED, 3)

    x0, x1, track_y, track_h = 16, 112, 64, 18
    rect(img, x0, track_y, x1 - x0, track_h, (10, 16, 28))
    rect(img, x0, track_y, x1 - x0, 1, FRAME)
    rect(img, x0, track_y + track_h - 1, x1 - x0, 1, FRAME)
    rect(img, x0, track_y, 1, track_h, FRAME)
    rect(img, x1 - 1, track_y, 1, track_h, FRAME)

    # target band
    zone_a, zone_b = 74, 92
    pulse = 0.5 + 0.5 * math.sin(2 * math.pi * t * 2)
    rect(img, zone_a, track_y + 1, zone_b - zone_a, track_h - 2, lt(GREEN, 0.06 + 0.2 * pulse))
    rect(img, zone_a, track_y + 1, 1, track_h - 2, dk(GREEN, 0.1))
    rect(img, zone_b, track_y + 1, 1, track_h - 2, dk(GREEN, 0.1))

    for i in range(13):
        x = x0 + i * (x1 - x0) // 12
        hgt = 8 if i % 3 == 0 else 4
        rect(img, x, track_y - hgt - 3, 1, hgt, DIM)

    text(img, x0, 96, "0.50", MUTED, 2)
    text(img, x1 - text_width("1.55", 2), 96, "1.55", MUTED, 2)

    pos = tri(t)
    nx = round(x0 + (x1 - x0 - 6) * pos) + 3
    cpc = 0.60 + 0.95 * pos
    cpc = round(cpc / 0.1) * 0.1

    rect(img, nx - 1, track_y - 16, 3, track_h + 22, INK)
    rect(img, nx - 1, track_y - 16, 3, 4, lt(TEAL, 0.4))
    rect(img, nx - 3, track_y + track_h + 2, 7, 2, lt(INK, 0.15))

    in_zone = zone_a <= nx <= zone_b
    col = GREEN if in_zone else INK
    val = f"{cpc:.2f}"
    text(img, 118 - text_width(val, 3), 8, val, col, 3)

    # small win sparkle when the needle sits in the target band
    if in_zone:
        star(img, nx, track_y - 22, lt(GREEN, 0.5), big=True)


def icon_conversion(img, t):
    panel(img, 128, 128)
    text(img, 10, 8, "CVR", MUTED, 3)

    values = ["3.2%", "3.9%", "4.4%", "4.8%"]
    idx = int(t * len(values)) % len(values)
    text(img, 118 - text_width(values[idx], 3), 8, values[idx], GREEN, 3)

    # quarter arc, bottom-left -> top-right
    pts = []
    cx_arc, cy_arc, r = 100, 104, 66
    for i in range(61):
        a = math.pi + (math.pi / 2) * (i / 60)
        pts.append((round(cx_arc + r * math.cos(a)), round(cy_arc + r * math.sin(a))))

    for i, (x, y) in enumerate(pts):
        if i % 4 == 0:
            rect(img, x, y, 2, 2, DIM)

    head = int((t % 1.0) * (len(pts) - 1))
    for k in range(18):
        j = (head - k) % len(pts)
        x, y = pts[j]
        col = INK if k == 0 else lt(TEAL, max(0.05, 0.6 - k * 0.03))
        size = 5 if k == 0 else 2
        rect(img, x, y, size, size, col)
        if k == 0:
            rect(img, x + 1, y + 1, 3, 1, lt(INK, 0.6))

    # coin pile where the arc lands
    for yy, x, w in ((44, 92, 16), (40, 95, 10), (36, 97, 6)):
        rect(img, x, yy, w, 5, ORANGE)
        rect(img, x, yy, w, 1, lt(ORANGE, 0.5))
        rect(img, x, yy + 4, w, 1, dk(ORANGE))

    # arrival flash tied to the head reaching the end
    near = 1 - min(1.0, abs(head - (len(pts) - 1)) / 10)
    if near > 0.15:
        star(img, 112, 34, lt(YELLOW, 0.2), big=near > 0.6)


def icon_seo(img, t):
    panel(img, 128, 128)
    text(img, 10, 8, "RANK", MUTED, 3)
    text(img, 118 - text_width("01", 3), 8, "01", GREEN, 3)

    rows = [(34, 44), (56, 62), (78, 50)]
    lens_y = 62 + math.sin(2 * math.pi * t) * 24
    for y, w in rows:
        near = abs(lens_y - (y + 4)) < 11
        base = lt(TEAL, 0.35) if near else DIM
        rect(img, 14, y, w, 8, base)
        rect(img, 14, y, w, 1, lt(base, 0.35))
        if near:
            rect(img, 14 + w + 4, y + 2, 3, 2, GREEN)
            rect(img, 15 + w + 4, y + 1, 1, 4, GREEN)
            rect(img, 16 + w + 4, y, 1, 2, GREEN)

    # magnifier
    cx, cy, r = 96, round(lens_y), 14
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            d = math.hypot(x - cx, y - cy)
            if r - 2 <= d <= r:
                shade = lt(TEAL, 0.5) if (x - cx) + (y - cy) < -6 else TEAL
                rect(img, x, y, 1, 1, shade)
            elif d < r - 2:
                rect(img, x, y, 1, 1, (26, 40, 62))
    rect(img, cx - 7, cy - 8, 6, 2, (60, 88, 118))
    rect(img, cx - 8, cy - 6, 2, 3, (60, 88, 118))
    line(img, cx + 10, cy + 10, cx + 21, cy + 21, FRAME, thick=3)
    line(img, cx + 10, cy + 10, cx + 21, cy + 21, lt(FRAME, 0.25), thick=1)


# --- hero ------------------------------------------------------------------


def hero(img, t):
    w, h = 200, 64
    panel(img, w, h)
    grid(img, w, h, 16, (20, 30, 48))

    # robot head
    rect(img, 24, 16, 2, 6, FRAME)
    pulse = 0.5 + 0.5 * math.sin(2 * math.pi * t * 2)
    rect(img, 23, 11, 4, 4, lt(ORANGE, 0.2 + 0.4 * pulse))
    rect(img, 24, 12, 2, 2, lt(YELLOW, 0.5 * pulse))

    rect(img, 10, 22, 30, 26, FRAME)
    rect(img, 12, 24, 26, 22, (22, 32, 52))
    rect(img, 12, 24, 26, 2, lt(FRAME, 0.2))
    rect(img, 10, 44, 30, 2, dk(FRAME, 0.2))

    blink = (t * 2) % 1.0 > 0.94
    for ex in (17, 29):
        if blink:
            rect(img, ex, 33, 6, 2, TEAL)
        else:
            rect(img, ex, 31, 6, 5, TEAL)
            rect(img, ex, 31, 6, 1, lt(TEAL, 0.55))
            rect(img, ex + 2, 32, 2, 2, BG)

    for i in range(5):
        amp = math.sin(2 * math.pi * (t * 2 + i / 8)) * 2.5
        rect(img, 18 + i * 4, 40 - round(amp), 2, 4 + round(abs(amp)), lt(TEAL, 0.15))

    # body
    rect(img, 22, 48, 14, 6, FRAME)
    rect(img, 6, 54, 42, 8, FRAME)
    rect(img, 8, 56, 38, 6, (22, 32, 52))

    # rising bars
    base_y = 56
    rect(img, 54, base_y, 66, 1, FRAME)
    bars = [(58, 14), (70, 22), (82, 30), (94, 38), (106, 46)]
    cols = [TEAL, BLUE, PURPLE, ORANGE, GREEN]
    for i, ((x, bh), c) in enumerate(zip(bars, cols)):
        bob = round(math.sin(2 * math.pi * (t * 2 + i * 0.15)) * 1.5)
        hh = bh + bob
        rect(img, x, base_y - hh, 10, hh, c)
        rect(img, x, base_y - hh, 10, 2, lt(c, 0.5))
        rect(img, x, base_y - hh, 1, hh, lt(c, 0.25))

    # trend arrow
    arrow = [(120, 46), (134, 39), (148, 33), (162, 26), (176, 19)]
    for i, (x, y) in enumerate(arrow[:-1]):
        x2, y2 = arrow[i + 1]
        line(img, x, y, x2, y2, lt(TEAL, 0.15), thick=2)
    tri_fill(img, (190, 9), (177, 12), (183, 25), INK)

    # travelling glints along the arrow
    for k in range(3):
        p = (t * 1.0 + k / 3) % 1.0
        i = min(len(arrow) - 2, int(p * (len(arrow) - 1)))
        x = arrow[i][0] + round((arrow[i + 1][0] - arrow[i][0]) * 0.2)
        y = arrow[i][1] + round((arrow[i + 1][1] - arrow[i][1]) * 0.2)
        star(img, x, y, lt(YELLOW, 0.25 + 0.35 * (1 - p)))

    # twinkles
    for i, (x, y) in enumerate(((4, 6), (122, 8), (194, 46), (36, 4))):
        ph = (t + i * 0.25) % 1.0
        if ph < 0.35:
            star(img, x, y, lt(INK, 0.15 + 0.5 * math.sin(math.pi * ph / 0.35)))


# --- render ----------------------------------------------------------------


def save_gif(frames, path: Path, duration_ms: int):
    colours = set()
    for f in frames:
        colours.update(f.getdata())
    colours = sorted(colours)
    if len(colours) > 256:
        raise SystemExit(f"{path.name}: {len(colours)} colours, GIF allows 256")

    palette = Image.new("P", (1, 1))
    flat = []
    for c in colours:
        flat.extend(c[:3])
    flat.extend([0] * (768 - len(flat)))
    palette.putpalette(flat)

    converted = []
    for f in frames:
        converted.append(f.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE))

    converted[0].save(
        path,
        save_all=True,
        append_images=converted[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
        disposal=1,
    )
    print(f"{path.relative_to(ROOT)}  {len(frames)}f  {path.stat().st_size / 1024:.1f} KB  {len(colours)} colours")


def render(name, width, height, draw, frames=24, duration=70, scale=3):
    imgs = []
    for i in range(frames):
        img = Image.new("RGB", (width, height), BG)
        draw(img, i / frames)
        imgs.append(img.resize((width * scale, height * scale), Image.Resampling.NEAREST))
    save_gif(imgs, OUT / name, duration)


def main():
    OUT.mkdir(exist_ok=True)
    render("marketing-hero.gif", 200, 64, hero, frames=24, duration=80, scale=4)
    render("icon-performance.gif", 128, 128, icon_performance)
    render("icon-funnel.gif", 128, 128, icon_funnel)
    render("icon-abtest.gif", 128, 128, icon_abtest)
    render("icon-budget.gif", 128, 128, icon_budget)
    render("icon-bid.gif", 128, 128, icon_bid)
    render("icon-conversion.gif", 128, 128, icon_conversion)
    render("icon-seo.gif", 128, 128, icon_seo)


if __name__ == "__main__":
    main()
