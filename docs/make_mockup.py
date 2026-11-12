"""Generate the GUI mockup images for the KiCad LibGen GUI development plan.

This is a design mockup, not a screenshot of the final Tk/ttk application.
Rendered at 2x and downsampled for clean edges.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT

S = 2  # supersampling factor

# ---------------------------------------------------------------- palette
PAGE = (233, 238, 245, 255)
WINDOW = (255, 255, 255, 255)
CHROME = (248, 250, 253, 255)
BODY = (245, 247, 251, 255)
CARD = (255, 255, 255, 255)
BORDER = (222, 229, 239, 255)
BORDER_STRONG = (203, 213, 225, 255)
TEXT = (28, 39, 51, 255)
MUTED = (100, 116, 139, 255)
FAINT = (148, 163, 184, 255)
ACCENT = (22, 104, 179, 255)
ACCENT_DARK = (15, 82, 143, 255)
ACCENT_SOFT = (232, 241, 251, 255)
ACCENT_LINE = (176, 212, 243, 255)
GREEN = (21, 127, 74, 255)
GREEN_BG = (231, 246, 238, 255)
AMBER = (180, 83, 9, 255)
AMBER_BG = (255, 244, 229, 255)
RED = (180, 35, 24, 255)
RED_BG = (253, 236, 234, 255)
SHADOW = (15, 23, 42, 42)


# ---------------------------------------------------------------- fonts
FONT_FILES = {
    "regular": r"C:\Windows\Fonts\segoeui.ttf",
    "semibold": r"C:\Windows\Fonts\seguisb.ttf",
    "bold": r"C:\Windows\Fonts\segoeuib.ttf",
    "mono": r"C:\Windows\Fonts\consola.ttf",
    "monob": r"C:\Windows\Fonts\consolab.ttf",
}


@lru_cache(maxsize=None)
def font(weight: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_FILES[weight], int(round(size * S)))


# ---------------------------------------------------------------- primitives
def px(v: float) -> int:
    return int(round(v * S))


def rr(draw: ImageDraw.ImageDraw, xy, r, fill, outline=None, width=1):
    x0, y0, x1, y1 = [px(v) for v in xy]
    draw.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=px(r),
        fill=fill,
        outline=outline,
        width=px(width) if outline else 1,
    )


def rect(draw, xy, fill, outline=None, width=1):
    x0, y0, x1, y1 = [px(v) for v in xy]
    draw.rectangle([x0, y0, x1, y1], fill=fill, outline=outline, width=px(width) if outline else 1)


def line(draw, p1, p2, fill, width=1):
    draw.line([px(p1[0]), px(p1[1]), px(p2[0]), px(p2[1])], fill=fill, width=px(width))


def text(
    draw,
    xy,
    value,
    size=11,
    color=TEXT,
    weight="regular",
    anchor="la",
    spacing=4,
):
    draw.multiline_text(
        (px(xy[0]), px(xy[1])),
        value,
        font=font(weight, size),
        fill=color,
        anchor=anchor,
        spacing=px(spacing),
    )


def text_width(draw, value, size=11, weight="regular") -> float:
    return draw.textlength(value, font=font(weight, size)) / S


def ellipsize(draw, value, max_width, size=11, weight="regular") -> str:
    if text_width(draw, value, size, weight) <= max_width:
        return value
    ell = "..."
    while value and text_width(draw, value + ell, size, weight) > max_width:
        value = value[:-1]
    return value + ell


def shadow_box(img: Image.Image, xy, r=14, blur=14, dy=8):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = [px(v) for v in xy]
    d.rounded_rectangle(
        [x0, y0 + px(dy), x1, y1 + px(dy)],
        radius=px(r),
        fill=SHADOW,
    )
    layer = layer.filter(ImageFilter.GaussianBlur(px(blur)))
    img.alpha_composite(layer)


# ---------------------------------------------------------------- icons
def icon_search(draw, x, y, color, size=14):
    w = px(size)
    cx, cy = px(x + size * 0.42), px(y + size * 0.42)
    r = px(size * 0.29)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=px(1.8))
    draw.line(
        [cx + px(size * 0.2), cy + px(size * 0.2), px(x + size * 0.96), px(y + size * 0.96)],
        fill=color,
        width=px(1.8),
    )


def icon_folder(draw, x, y, color, size=14):
    rr(draw, (x + 1, y + size * 0.28, x + size * 0.72, y + size * 0.78), size * 0.12, None, color, 1.4)
    rr(draw, (x, y + size * 0.42, x + size, y + size * 0.92), size * 0.12, None, color, 1.4)
    line(draw, (x + 1.5, y + size * 0.42), (x + size * 0.62, y + size * 0.42), color, 1.4)


def icon_chevron(draw, x, y, color, size=10, down=True):
    if down:
        line(draw, (x, y), (x + size / 2, y + size * 0.55), color, 1.6)
        line(draw, (x + size / 2, y + size * 0.55), (x + size, y), color, 1.6)
    else:
        line(draw, (x, y + size * 0.55), (x + size / 2, y), color, 1.6)
        line(draw, (x + size / 2, y), (x + size, y + size * 0.55), color, 1.6)


def icon_external(draw, x, y, color, size=12):
    rr(draw, (x, y + size * 0.26, x + size * 0.72, y + size), 1.5, None, color, 1.4)
    line(draw, (x + size * 0.45, y + size * 0.55), (x + size, y), color, 1.4)
    line(draw, (x + size * 0.62, y), (x + size, y), color, 1.4)
    line(draw, (x + size, y), (x + size, y + size * 0.38), color, 1.4)


def icon_gear(draw, x, y, color, size=15):
    cx, cy = px(x + size / 2), px(y + size / 2)
    r_out = px(size * 0.48)
    r_in = px(size * 0.18)
    # eight teeth
    import math

    for i in range(8):
        a = math.radians(i * 45)
        x1 = cx + math.cos(a) * px(size * 0.30)
        y1 = cy + math.sin(a) * px(size * 0.30)
        x2 = cx + math.cos(a) * px(size * 0.49)
        y2 = cy + math.sin(a) * px(size * 0.49)
        draw.line([x1, y1, x2, y2], fill=color, width=px(3.2))
    draw.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], outline=color, width=px(1.7))
    draw.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], fill=color)


def icon_key(draw, x, y, color, size=14):
    cx, cy = px(x + size * 0.28), px(y + size * 0.32)
    r = px(size * 0.22)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=px(1.6))
    line(draw, (x + size * 0.43, y + size * 0.47), (x + size * 0.92, y + size * 0.92), color, 1.6)
    line(draw, (x + size * 0.72, y + size * 0.74), (x + size * 0.86, y + size * 0.60), color, 1.6)
    line(draw, (x + size * 0.83, y + size * 0.85), (x + size * 0.96, y + size * 0.72), color, 1.6)


def icon_db(draw, x, y, color, size=14):
    rr(draw, (x, y + size * 0.08, x + size, y + size * 0.32), size * 0.1, None, color, 1.4)
    line(draw, (x, y + size * 0.32), (x, y + size * 0.85), color, 1.4)
    line(draw, (x + size, y + size * 0.32), (x + size, y + size * 0.85), color, 1.4)
    draw.arc([px(x), px(y + size * 0.68), px(x + size), px(y + size * 0.98)], 0, 180, fill=color, width=px(1.4))
    draw.arc([px(x), px(y + size * 0.20), px(x + size), px(y + size * 0.44)], 0, 180, fill=color, width=px(1.4))


def icon_info(draw, x, y, color, size=12):
    cx, cy = px(x + size / 2), px(y + size / 2)
    r = px(size / 2)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=px(1.2))
    draw.ellipse([cx - px(0.9), cy - px(size * 0.22), cx + px(0.9), cy - px(size * 0.22) + px(1.8)], fill=color)
    line(draw, (cx, cy - px(size * 0.02)), (cx, cy + px(size * 0.22)), color, 1.4)


# ---------------------------------------------------------------- chrome
def window_frame(img, x, y, w, h, title, icon=None):
    shadow_box(img, (x, y, x + w, y + h), r=14, blur=16, dy=9)
    d = ImageDraw.Draw(img)
    rr(d, (x, y, x + w, y + h), 14, WINDOW, BORDER, 1)
    # title bar
    rr(d, (x, y, x + w, y + 40), 14, CHROME)
    rect(d, (x, y + 24, x + w, y + 40), CHROME)
    line(d, (x + 14, y + 40), (x + w - 14, y + 40), BORDER, 1)
    # icon
    if icon:
        icon(d, x + 18, y + 12, ACCENT, 16)
    # window buttons
    bx = x + w - 34
    line(d, (bx - 1, y + 20), (bx + 11, y + 20), MUTED, 1.4)
    rect(d, (bx + 24, y + 14.5, bx + 34, y + 25.5), None, MUTED, 1.1)
    line(d, (bx + 48, y + 15), (bx + 58, y + 25), MUTED, 1.4)
    line(d, (bx + 58, y + 15), (bx + 48, y + 25), MUTED, 1.4)
    # title text
    text(d, (x + 42, y + 12), title, 13, TEXT, "semibold")


def card(img, xy, r=10):
    d = ImageDraw.Draw(img)
    rr(d, xy, r, CARD, BORDER, 1)


def pill(d, x, y, label, fg, bg, size=9.5, pad_x=8, h=19):
    tw = text_width(d, label, size, "semibold")
    rr(d, (x, y, x + tw + pad_x * 2, y + h), h / 2, bg)
    text(d, (x + pad_x, y + (h - size) / 2 - 1.5), label, size, fg, "semibold")


def button(d, x, y, w, h, label, primary=False, icon=None, size=11):
    fill = ACCENT if primary else (250, 252, 254, 255)
    border = ACCENT if primary else BORDER_STRONG
    fg = (255, 255, 255, 255) if primary else TEXT
    rr(d, (x, y, x + w, y + h), 7, fill, border, 1)
    tw = text_width(d, label, size, "semibold")
    ix = x + (w - tw) / 2
    if icon:
        icon(d, x + 12, y + (h - 14) / 2, fg if primary else ACCENT, 14)
        ix = x + 32
    text(d, (ix, y + (h - size) / 2 - 1.5), label, size, fg, "semibold")


def checkbox(d, x, y, label, checked=True, size=10.5):
    rr(d, (x, y + 1, x + 13, y + 14), 3, (255, 255, 255, 255), BORDER_STRONG, 1)
    if checked:
        rr(d, (x + 2, y + 3, x + 11, y + 12), 2, ACCENT)
        line(d, (x + 4.2, y + 7.7), (x + 6.3, y + 9.7), (255, 255, 255, 255), 1.4)
        line(d, (x + 6.3, y + 9.7), (x + 9.4, y + 4.9), (255, 255, 255, 255), 1.4)
    text(d, (x + 20, y), label, size, TEXT)


def text_input(d, x, y, w, h, value, size=11.5, mono=False, placeholder=False, focus=False):
    border = ACCENT if focus else BORDER_STRONG
    rr(d, (x, y, x + w, y + h), 7, (255, 255, 255, 255), border, 1.2 if focus else 1)
    text(
        d,
        (x + 11, y + (h - size) / 2 - 1.3),
        value,
        size,
        FAINT if placeholder else TEXT,
        "mono" if mono else "regular",
    )


def combobox(d, x, y, w, h, value, size=11.5, focus=False):
    border = ACCENT if focus else BORDER_STRONG
    rr(d, (x, y, x + w, y + h), 7, (255, 255, 255, 255), border, 1.2 if focus else 1)
    text(d, (x + 11, y + (h - size) / 2 - 1.3), value, size, TEXT, "regular")
    icon_chevron(d, x + w - 20, y + h / 2 - 3, MUTED, 9)


def section_label(d, x, y, label):
    text(d, (x, y), label.upper(), 8.8, MUTED, "semibold")


# ---------------------------------------------------------------- table
def draw_table(
    d,
    x,
    y,
    w,
    headers,
    widths,
    rows,
    row_h=34,
    header_h=28,
    selected=0,
    status_col=-1,
    mono_cols=(),
):
    # header
    rr(d, (x, y, x + w, y + header_h), 6, (244, 247, 251, 255))
    cx = x + 12
    for label, cw in zip(headers, widths):
        text(d, (cx, y + 8), label.upper(), 8.8, MUTED, "semibold")
        cx += cw
    row_y = y + header_h
    for ri, row in enumerate(rows):
        if ri == selected:
            rect(d, (x, row_y, x + w, row_y + row_h), ACCENT_SOFT)
            rect(d, (x, row_y, x + 3, row_y + row_h), ACCENT)
        elif ri % 2 == 1:
            rect(d, (x, row_y, x + w, row_y + row_h), (250, 252, 254, 255))
        line(d, (x + 12, row_y + row_h), (x + w - 12, row_y + row_h), (237, 242, 248, 255), 1)
        cx = x + 12
        status_idx = len(row) - 1 if status_col == -1 else status_col
        for ci, (cell, cw) in enumerate(zip(row, widths)):
            row_size = 11.2 if row_h >= 30 else 9.2
            top = row_y + (row_h - row_size) / 2 - 0.5
            if ci == 0:
                text(d, (cx, top), cell, row_size, TEXT, "semibold")
            elif status_idx is not None and ci == status_idx:
                if cell == "Active":
                    pill(d, cx, row_y + 8, cell, GREEN, GREEN_BG, 9)
                elif cell == "Obsolete":
                    pill(d, cx, row_y + 8, cell, RED, RED_BG, 9)
                else:
                    pill(d, cx, row_y + 8, cell, AMBER, AMBER_BG, 9)
            elif ci in mono_cols:
                text(
                    d,
                    (cx, top),
                    ellipsize(d, cell, cw - 14, row_size, "mono"),
                    row_size,
                    MUTED,
                    "mono",
                )
            else:
                text(
                    d,
                    (cx, top),
                    ellipsize(d, cell, cw - 14, row_size),
                    row_size,
                    MUTED,
                    "regular",
                )
            cx += cw
        row_y += row_h


# ---------------------------------------------------------------- main window
def build_main() -> Image.Image:
    w, h = 1180, 880
    img = Image.new("RGBA", (w * S, h * S), PAGE)
    d = ImageDraw.Draw(img)

    x, y, ww, wh = 30, 30, 1120, 820
    window_frame(img, x, y, ww, wh, "KiCad LibGen", icon_db)
    d = ImageDraw.Draw(img)

    # ------------------------------------------------------------ toolbar
    rect(d, (x + 1, y + 41, x + ww - 1, y + 86), WINDOW)
    line(d, (x + 14, y + 86), (x + ww - 14, y + 86), BORDER, 1)

    # database chip
    rr(d, (x + 18, y + 52, x + 368, y + 78), 7, (247, 250, 253, 255), BORDER, 1)
    icon_db(d, x + 28, y + 58, ACCENT, 14)
    text(d, (x + 50, y + 57), "components.db", 11.2, TEXT, "semibold")
    text(d, (x + 152, y + 58.5), r"...\MyBoard\Library", 8.8, FAINT, "mono")
    pill(d, x + 288, y + 56.5, "128 parts", (71, 85, 105, 255), (236, 241, 247, 255), 8.5, 7, 17)

    button(d, x + 382, y + 51, 78, 28, "Open...", size=10)
    button(d, x + 470, y + 51, 74, 28, "New...", size=10)

    button(d, x + 786, y + 51, 104, 28, "Batch import", size=10)
    button(d, x + 900, y + 51, 104, 28, "Authenticate", size=10)
    icon_gear(d, x + 1022, y + 57, MUTED, 16)

    # ------------------------------------------------------------ tabs
    rect(d, (x + 1, y + 87, x + ww - 1, y + 124), (248, 250, 253, 255))
    line(d, (x + 14, y + 124), (x + ww - 14, y + 124), BORDER, 1)

    text(d, (x + 26, y + 98), "Search DigiKey", 11.2, ACCENT, "semibold")
    rect(d, (x + 26, y + 119, x + 122, y + 122), ACCENT)
    text(d, (x + 154, y + 98), "Database", 11.2, MUTED, "regular")
    pill(d, x + 218, y + 96.5, "128", (71, 85, 105, 255), (233, 238, 245, 255), 8, 6, 16)

    text(d, (x + 930, y + 99), "Token valid", 9.2, GREEN, "semibold")
    text(d, (x + 1003, y + 99), "23 days remaining", 9.2, MUTED, "regular")

    rect(d, (x + 1, y + 125, x + ww - 1, y + 747), BODY)

    # ------------------------------------------------------------ search card
    card(img, (x + 18, y + 136, x + ww - 18, y + 208), 10)
    d = ImageDraw.Draw(img)
    section_label(d, x + 34, y + 146, "Search DigiKey")
    text_input(
        d,
        x + 34,
        y + 160,
        858,
        32,
        "LM324N",
        12,
        focus=True,
    )
    text(d, (x + 34, y + 196), "Tip: exact manufacturer part numbers return the fewest variants.", 8.6, MUTED)
    button(d, x + 906, y + 160, 162, 32, "Search", primary=True, icon=icon_search, size=11)

    # ------------------------------------------------------------ results card
    card(img, (x + 18, y + 220, x + ww - 18, y + 462), 10)
    d = ImageDraw.Draw(img)
    text(d, (x + 34, y + 232), "Search results", 13, TEXT, "semibold")
    pill(d, x + 152, y + 231.5, "5 found", (71, 85, 105, 255), (236, 241, 247, 255), 8.5, 7, 17)
    text(d, (x + 1000, y + 234), "Sort: Relevance", 8.8, MUTED)
    icon_chevron(d, x + 1093, y + 237, MUTED, 7)

    headers = ["MPN", "Manufacturer", "Description", "Qty", "Status"]
    widths = [148, 150, 492, 78, 106]
    rows = [
        ["LM324N", "Texas Instruments", "IC OPAMP GP 4 CIRCUIT 14DIP", "2,500", "Active"],
        ["LM324NE4", "Texas Instruments", "IC OPAMP GP 4 CIRCUIT 14DIP", "1,800", "Active"],
        ["LM324NP", "Texas Instruments", "IC OPAMP GP 4 CIRCUIT 14DIP", "0", "Obsolete"],
        ["LM2902N", "Texas Instruments", "IC OPAMP GP 4 CIRCUIT 14DIP", "4,212", "Active"],
        ["LM324DR", "Texas Instruments", "IC OPAMP GP 4 CIRCUIT 14SOIC", "15,000", "Active"],
    ]
    draw_table(d, x + 34, y + 254, 1052, headers, widths, rows, selected=0)

    # ------------------------------------------------------------ details card
    card(img, (x + 18, y + 474, x + ww - 18, y + 726), 10)
    d = ImageDraw.Draw(img)

    section_label(d, x + 34, y + 486, "Selected part")
    text(d, (x + 34, y + 499), "LM324N", 14, TEXT, "semibold")
    text(d, (x + 104, y + 503), "Texas Instruments", 9.6, MUTED, "regular")
    pill(d, x + 208, y + 499, "NOT IN DATABASE", AMBER, AMBER_BG, 7.6, 7, 17)

    text(d, (x + 944, y + 501), "Datasheet", 9.2, ACCENT, "semibold")
    icon_external(d, x + 1001, y + 499, ACCENT, 10)
    text(d, (x + 1024, y + 501), "Product page", 9.2, ACCENT, "semibold")
    icon_external(d, x + 1089, y + 499, ACCENT, 10)

    line(d, (x + 34, y + 530), (x + ww - 34, y + 530), BORDER, 1)

    # left details
    section_label(d, x + 34, y + 542, "Overview")
    meta = [
        ("Manufacturer", "Texas Instruments"),
        ("Package", '14-DIP (0.300", 7.62mm)'),
        ("Category", "ICs  >  Amplifiers  >  Op Amps"),
        ("Part status", "Active"),
        ("DigiKey PN", "LM324N-ND"),
        ("Unit price", "$0.45 @ 1"),
    ]
    my = y + 562
    for label, value in meta:
        text(d, (x + 34, my), label, 9.2, MUTED)
        color = GREEN if label == "Part status" else TEXT
        weight = "semibold" if label == "Part status" else "regular"
        text(d, (x + 122, my - 0.5), value, 9.8, color, weight)
        my += 25

    text(d, (x + 34, y + 714), "32 parameters available", 8.4, FAINT)
    text(d, (x + 152, y + 714), "View all", 8.4, ACCENT, "semibold")

    # divider
    line(d, (x + 548, y + 542), (x + 548, y + 710), BORDER, 1)

    # right mapping
    section_label(d, x + 566, y + 542, "KiCad mapping")
    text(d, (x + 566, y + 560), "Symbol library", 9.2, MUTED)
    combobox(d, x + 566, y + 574, 486, 32, "Symbol:IC_LM324N", 11, focus=True)
    text(d, (x + 566, y + 614), "Footprint library", 9.2, MUTED)
    combobox(d, x + 566, y + 628, 486, 32, "Footprint:IC_LM324N", 11)
    icon_info(d, x + 567, y + 672, FAINT, 10)
    text(d, (x + 583, y + 671), "Use ? in place of the MPN; it is replaced when you save.", 8.4, MUTED)

    button(d, x + 832, y + 690, 76, 28, "Clear", size=10)
    button(d, x + 918, y + 690, 134, 28, "Add to database", primary=True, size=10)

    # ------------------------------------------------------------ status bar
    line(d, (x + 14, y + 748), (x + ww - 14, y + 748), BORDER, 1)
    d.ellipse([px(x + 26), px(y + 765), px(x + 34), px(y + 773)], fill=GREEN)
    text(d, (x + 40, y + 762), "Database ready", 9.4, TEXT, "semibold")
    text(d, (x + 130, y + 762), "components.db", 9.4, MUTED)
    text(d, (x + 230, y + 762), "128 parts", 9.4, MUTED)
    text(d, (x + 296, y + 762), "5,432 parameter rows", 9.4, FAINT)
    text(d, (x + 830, y + 762), "DigiKey token valid for 23 days", 9.4, GREEN)
    text(d, (x + 1032, y + 762), "v1.0.0", 9.4, FAINT)

    return img.resize((w, h), Image.LANCZOS)


# ---------------------------------------------------------------- dialogs
def build_dialogs() -> Image.Image:
    w, h = 1180, 610
    img = Image.new("RGBA", (w * S, h * S), PAGE)
    d = ImageDraw.Draw(img)

    # ============================================================ auth dialog
    ax, ay, aw, ah = 30, 30, 540, 520
    window_frame(img, ax, ay, aw, ah, "DigiKey authentication", icon_key)
    d = ImageDraw.Draw(img)

    text(d, (ax + 20, ay + 56), "Connect your DigiKey account", 14, TEXT, "semibold")
    text(
        d,
        (ax + 20, ay + 80),
        "Use the Client ID and Client Secret from your DigiKey developer app.",
        8.8,
        MUTED,
    )

    text(d, (ax + 20, ay + 110), "Client ID", 9.2, MUTED)
    text_input(d, ax + 20, ay + 124, aw - 40, 31, "my-kicad-libgen-app", 10.5, mono=True)
    text(d, (ax + 20, ay + 166), "Client secret", 9.2, MUTED)
    text_input(d, ax + 20, ay + 180, 420, 31, "••••••••••••••••••••••••••••", 10.5, mono=True)
    checkbox(d, ax + 450, ay + 189, "Show", checked=False, size=8.8)

    # steps box
    rr(d, (ax + 20, ay + 228, ax + aw - 20, ay + 310), 8, (242, 248, 254, 255), (214, 230, 247, 255), 1)
    steps = [
        ("1", "Open the DigiKey sign-in page."),
        ("2", "Authorize this app for your account."),
        ("3", "Copy the localhost URL from your browser and paste it below."),
    ]
    sy = ay + 238
    for num, step in steps:
        d.ellipse([px(ax + 32), px(sy), px(ax + 46), px(sy + 14)], fill=ACCENT)
        text(d, (ax + 36, sy + 1.4), num, 8, (255, 255, 255, 255), "semibold")
        text(d, (ax + 54, sy + 0.4), step, 8.7, TEXT)
        sy += 22

    button(d, ax + 20, ay + 322, aw - 40, 31, "Open DigiKey sign-in page", size=10)

    text(d, (ax + 20, ay + 368), "Redirect URL", 9.2, MUTED)
    text_input(
        d,
        ax + 20,
        ay + 382,
        aw - 40,
        31,
        "https://localhost:8000/oauth2/callback?code=...",
        9.2,
        placeholder=True,
    )
    d.ellipse([px(ax + 22), px(ay + 430), px(ax + 30), px(ay + 438)], fill=GREEN)
    text(d, (ax + 36, ay + 427), "Token valid - expires in 23 days", 8.8, GREEN, "semibold")

    button(d, ax + 350, ay + 466, 74, 28, "Cancel", size=10)
    button(d, ax + 434, ay + 466, 86, 28, "Connect", primary=True, size=10)

    # ============================================================ batch dialog
    bx, by, bw, bh = 610, 30, 540, 520
    window_frame(img, bx, by, bw, bh, "Batch import from CSV", icon_folder)
    d = ImageDraw.Draw(img)

    text(d, (bx + 20, by + 56), "Import parts from a CSV file", 14, TEXT, "semibold")
    text(
        d,
        (bx + 20, by + 80),
        "Header: manufacturer_product_number, kicad_symbol_library, kicad_footprint_library",
        7.8,
        MUTED,
    )

    text(d, (bx + 20, by + 110), "CSV file", 9.2, MUTED)
    text_input(d, bx + 20, by + 124, 402, 31, r"C:\Projects\MyBoard\bom_parts.csv", 8.8, mono=True)
    button(d, bx + 430, by + 124, 90, 31, "Browse...", size=9)

    section_label(d, bx + 20, by + 172, "Preview")
    headers = ["MPN", "Symbol", "Footprint"]
    widths = [150, 174, 176]
    rows = [
        ["LM324N", "Symbol:IC_LM324N", "Footprint:IC_LM324N"],
        ["ATMega328P", "Symbol:IC_ATMega328P", "Footprint:IC_ATMega328P"],
        ["STM32F103C8T6", "Symbol:IC_STM32F103", "Footprint:IC_STM32F103"],
    ]
    draw_table(
        d,
        bx + 20,
        by + 186,
        500,
        headers,
        widths,
        rows,
        row_h=26,
        header_h=22,
        selected=-1,
        status_col=None,
        mono_cols=(1, 2),
    )

    checkbox(d, bx + 20, by + 300, "Skip duplicates", checked=True, size=9.2)
    checkbox(d, bx + 158, by + 300, "Overwrite existing mapping", checked=False, size=9.2)
    text(d, (bx + 362, by + 300), "Delay", 8.8, MUTED)
    rr(d, (bx + 398, by + 297, bx + 470, by + 314), 5, (255, 255, 255, 255), BORDER_STRONG, 1)
    text(d, (bx + 406, by + 300.5), "250 ms", 8.2, TEXT, "mono")

    text(d, (bx + 20, by + 332), "Progress", 9.2, TEXT, "semibold")
    text(d, (bx + 448, by + 332), "42 / 120", 9, MUTED, "mono")
    rr(d, (bx + 20, by + 348, bx + 520, by + 358), 5, (232, 238, 245, 255))
    rr(d, (bx + 20, by + 348, bx + 20 + 500 * 0.35, by + 358), 5, ACCENT)
    text(d, (bx + 20, by + 368), "42 inserted  ·  3 skipped  ·  1 error", 8.8, MUTED)

    text(d, (bx + 20, by + 398), "Log file will be written next to the CSV when the import finishes.", 8.2, FAINT)

    button(d, bx + 350, by + 466, 74, 28, "Cancel", size=10)
    button(d, bx + 434, by + 466, 86, 28, "Start", primary=True, size=10)

    # captions
    text(d, (ax + aw / 2, 574), "Authentication dialog", 10, MUTED, "semibold", "ma")
    text(d, (bx + bw / 2, 574), "Batch import dialog", 10, MUTED, "semibold", "ma")

    return img.resize((w, h), Image.LANCZOS)


if __name__ == "__main__":
    main = build_main()
    dialogs = build_dialogs()
    main.save(OUT / "gui-main.png")
    dialogs.save(OUT / "gui-dialogs.png")
    print("wrote", OUT / "gui-main.png")
    print("wrote", OUT / "gui-dialogs.png")
