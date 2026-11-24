# One-off: generate frontend/assets/favicon.ico (multi-size) + frontend/assets/icon-256.png
# (clean single-source PNG, the reliable input for electron-builder's win.icon).
# Matches frontend/assets/icon.svg using PIL primitives + default font only (no external .ttf).
# Run once with: backend\.venv\Scripts\python.exe scripts\make_favicon.py
import sys
from PIL import Image, ImageDraw, ImageFont

BG1 = (10, 15, 26)       # #0a0f1a
BG2 = (26, 35, 64)       # #1a2340
BUB_TOP = (139, 134, 201)   # #8b86c9
BUB_BOT = (90, 86, 148)     # #5a5694
DOT = (10, 15, 26)          # #0a0f1a
SPARK = (171, 165, 201)     # #aba5c9
SPARK_EDGE = (10, 15, 26)   # #0a0f1a
AMT_COL = (171, 165, 201)   # #aba5c9

def lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

# Load the default bitmap font once (available without any bundled .ttf).
_DEFAULT_FONT = ImageFont.load_default()

def draw_tile(size, want_png_source=False):
    """Draw at `size` px. Supersamples 4x internally for crisp edges.
    If want_png_source=True, draw at exactly `size` (256) with NO extra supersampling
    (the 256 source is already high-res enough; extra SS just slows things down).
    """
    ss = 4 if size <= 128 else 1  # only supersample the small sizes; 256 is already high-DPI
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = S * 8 / 256
    r = S * 52 / 256
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=r, fill=lerp(BG1, BG2, 0.0),
                        outline=BUB_TOP, width=max(1, int(S * 4 / 256)))

    # Vertical bg gradient (cheap banded approximation)
    bands = 32
    for i in range(bands):
        t = i / (bands - 1)
        c = lerp(BG1, BG2, t)
        y0 = pad + int((S - 2 * pad) * i / bands)
        y1 = pad + int((S - 2 * pad) * (i + 1) / bands)
        d.rectangle([pad + 1, y0, S - pad - 1, y1], fill=(*c, 255))

    # Chat bubble body (rounded rect + tail), shifted UP to leave room for AMT wordmark
    bx0, by0 = S * 76 / 256, S * 66 / 256
    bx1, by1 = S * 208 / 256, S * 162 / 256
    br = S * 28 / 256
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=br, fill=lerp(BUB_TOP, BUB_BOT, 0.25))
    # tail: small triangle under the left part of the bubble
    tx0, tx1 = S * 76 / 256, S * 128 / 256
    ty_top = by1
    ty_bot = S * 186 / 256
    d.polygon([(tx0 + 4, ty_top - 2), (tx1, ty_top - 2), (tx1, ty_bot)], fill=lerp(BUB_TOP, BUB_BOT, 0.35))

    # gradient fill for bubble (bands again, clipped visually by drawing over)
    b_h = by1 - by0
    for i in range(24):
        t = i / 23
        c = lerp(BUB_TOP, BUB_BOT, t)
        yy0 = by0 + int(b_h * i / 24)
        yy1 = by0 + int(b_h * (i + 1) / 24)
        d.rectangle([bx0 + 2, yy0, bx1 - 2, yy1], fill=(*c, 255))
    # re-draw tail on top so it keeps solid
    d.polygon([(tx0 + 4, ty_top - 2), (tx1, ty_top - 2), (tx1, ty_bot)], fill=lerp(BUB_TOP, BUB_BOT, 0.35))

    # three chat dots (moved up to match the shifted bubble, y=108/256)
    for cx_frac in (98, 128, 158):
        cx = S * cx_frac / 256
        cy = S * 108 / 256
        dr = S * 9 / 256
        d.ellipse([cx - dr, cy - dr, cx + dr, cy + dr], fill=DOT)

    # spark (4-pointed diamond star) at bubble's top-right (also shifted up, y=67/256)
    scx, scy = S * 176 / 256, S * 67 / 256
    long_r = S * 31 / 256
    d.polygon([
        (scx, scy - long_r),
        (scx + long_r, scy),
        (scx, scy + long_r),
        (scx - long_r, scy),
    ], fill=SPARK, outline=SPARK_EDGE)

    # AMT wordmark: bold, centered, below the bubble (y≈216/256 baseline, matching SVG's <text>)
    # Use the default font, scaled up via supersampling for legibility.
    # Approximate a "bold" look by drawing the text twice with a 1px horizontal offset
    # (cheap fake-bold, works with the small default bitmap font).
    font_scale = max(1, int(S * 44 / 256 / 11))  # default font is ~11px; scale proportionally
    font = _DEFAULT_FONT
    # ImageFont.load_default() returns a fixed small bitmap font; can't easily scale it
    # without an external .ttf. Fall back to a simple hand-drawn 3-letter geometric wordmark
    # using thick rectangle/line primitives instead, so it's fully self-contained (no font needed).
    # Letterforms: A, M, T — thick verticals/diagonals, same visual weight as the tile's border.
    stroke_w = max(2, int(S * 9 / 256))
    y_top = S * 194 / 256
    y_bot = S * 232 / 256
    # A: x 84..112
    ax0, ax1 = S * 84 / 256, S * 112 / 256
    d.line([(ax0, y_bot), ((ax0 + ax1) / 2, y_top)], fill=AMT_COL, width=stroke_w)
    d.line([((ax0 + ax1) / 2, y_top), (ax1, y_bot)], fill=AMT_COL, width=stroke_w)
    d.line([((ax0 + ax1) / 2 - ax0 * 0.1, y_bot - (y_bot - y_top) * 0.35),
            ((ax0 + ax1) / 2 + ax1 * 0.1, y_bot - (y_bot - y_top) * 0.35)], fill=AMT_COL, width=max(1, stroke_w // 2))
    # M: x 124..156
    mx0, mx1 = S * 124 / 256, S * 156 / 256
    d.line([(mx0, y_bot), (mx0, y_top)], fill=AMT_COL, width=stroke_w)
    d.line([(mx1, y_bot), (mx1, y_top)], fill=AMT_COL, width=stroke_w)
    d.line([(mx0, y_top), ((mx0 + mx1) / 2, y_bot - (y_bot - y_top) * 0.15)], fill=AMT_COL, width=max(1, stroke_w))
    d.line([((mx0 + mx1) / 2, y_bot - (y_bot - y_top) * 0.15), (mx1, y_top)], fill=AMT_COL, width=max(1, stroke_w))
    # T: x 168..200 (centered-ish; tile inner width is 8..248, so 168..200 keeps good margin)
    tx_a, tx_b = S * 168 / 256, S * 200 / 256
    txc = (tx_a + tx_b) / 2
    d.line([(tx_a, y_top), (tx_b, y_top)], fill=AMT_COL, width=stroke_w)
    d.line([(txc, y_top), (txc, y_bot)], fill=AMT_COL, width=stroke_w)

    out = img if size == ss else img.resize((size, size), Image.LANCZOS)
    return out

def main():
    # 1) Clean 256x256 PNG source — the reliable input for electron-builder (win.icon).
    png256 = draw_tile(256, want_png_source=True)
    png256.save("frontend/assets/icon-256.png")
    print("wrote frontend/assets/icon-256.png (clean 256x256 PNG source for electron-builder)")

    # 2) Multi-size .ico (for the in-app <link rel="icon"> fallback / legacy consumers).
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = {s: draw_tile(s) for s in sizes}
    out = "frontend/assets/favicon.ico"
    largest = imgs[sizes[-1]]
    others = [imgs[s] for s in sizes[:-1]]
    largest.save(out, format="ICO", append_images=others, sizes=[(s, s) for s in sizes])
    print("wrote", out)

if __name__ == "__main__":
    main()
