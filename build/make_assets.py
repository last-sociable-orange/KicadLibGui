"""Generate the bundled app icon and 16 px toolbar icons (Pillow).

Run from the repository root::

    python build/make_assets.py

The generated PNG/ICO files are committed so a build never needs Pillow.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ICONS = ASSETS / "icons"
ACCENT = (22, 104, 179, 255)
ACCENT_DARK = (18, 85, 146, 255)
MUTED = (107, 114, 128, 255)
WHITE = (255, 255, 255, 255)
CLEAR = (0, 0, 0, 0)
SIZE = 64
OUT = 16


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (SIZE, SIZE), CLEAR)
    return image, ImageDraw.Draw(image)


def save(image: Image.Image, name: str) -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    image.resize((OUT, OUT), Image.LANCZOS).save(ICONS / f"{name}-{OUT}.png")
    # 32 px copies are loaded on high-DPI displays if present.
    image.resize((32, 32), Image.LANCZOS).save(ICONS / f"{name}-32.png")


def icon_search() -> None:
    image, draw = canvas()
    draw.ellipse((10, 8, 42, 40), outline=ACCENT, width=5)
    draw.line((37, 36, 54, 53), fill=ACCENT, width=6)
    save(image, "search")


def icon_open() -> None:
    image, draw = canvas()
    draw.polygon([(6, 20), (26, 20), (31, 26), (58, 26), (58, 52), (6, 52)],
                 fill=None, outline=MUTED, width=4)
    draw.line((6, 30, 58, 30), fill=MUTED, width=4)
    save(image, "open")


def icon_new() -> None:
    image, draw = canvas()
    draw.rounded_rectangle((14, 8, 48, 56), radius=5, outline=MUTED, width=4)
    draw.line((31, 20, 31, 42), fill=ACCENT, width=5)
    draw.line((20, 31, 42, 31), fill=ACCENT, width=5)
    save(image, "new")


def icon_batch() -> None:
    image, draw = canvas()
    for row in range(3):
        y = 12 + row * 13
        draw.rectangle((8, y, 32, y + 8), outline=MUTED, width=3)
    draw.line((44, 10, 44, 42), fill=ACCENT, width=5)
    draw.polygon([(44, 54), (34, 40), (54, 40)], fill=ACCENT)
    save(image, "batch")


def icon_key() -> None:
    image, draw = canvas()
    draw.ellipse((8, 22, 28, 42), outline=ACCENT, width=4)
    draw.line((28, 32, 56, 32), fill=ACCENT, width=4)
    draw.line((48, 32, 48, 42), fill=ACCENT, width=4)
    draw.line((55, 32, 55, 40), fill=ACCENT, width=4)
    save(image, "key")


def icon_gear() -> None:
    image, draw = canvas()
    draw.ellipse((8, 8, 56, 56), outline=MUTED, width=4)
    draw.ellipse((24, 24, 40, 40), outline=MUTED, width=4)
    for x1, y1, x2, y2 in ((32, 2, 32, 12), (32, 52, 32, 62),
                           (2, 32, 12, 32), (52, 32, 62, 32),
                           (10, 10, 17, 17), (47, 47, 54, 54),
                           (10, 54, 17, 47), (47, 17, 54, 10)):
        draw.line((x1, y1, x2, y2), fill=MUTED, width=4)
    save(image, "gear")


def icon_database() -> None:
    image, draw = canvas()
    draw.ellipse((12, 6, 52, 20), outline=ACCENT, width=4)
    draw.line((12, 13, 12, 50), fill=ACCENT, width=4)
    draw.line((52, 13, 52, 50), fill=ACCENT, width=4)
    draw.arc((12, 42, 52, 58), start=0, end=180, fill=ACCENT, width=4)
    draw.arc((12, 24, 52, 40), start=0, end=180, fill=ACCENT, width=3)
    save(image, "database")


def icon_refresh() -> None:
    image, draw = canvas()
    draw.arc((10, 10, 54, 54), start=40, end=320, fill=ACCENT, width=5)
    draw.polygon([(52, 10), (54, 28), (38, 18)], fill=ACCENT)
    save(image, "refresh")


def icon_link() -> None:
    image, draw = canvas()
    draw.line((20, 44, 44, 20), fill=ACCENT, width=5)
    draw.arc((8, 30, 34, 56), start=90, end=270, fill=ACCENT, width=4)
    draw.arc((30, 8, 56, 34), start=270, end=90, fill=ACCENT, width=4)
    save(image, "link")


def app_icon() -> None:
    image = Image.new("RGBA", (256, 256), CLEAR)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 248, 248), radius=48, fill=ACCENT)
    # Chip body
    draw.rounded_rectangle((64, 64, 192, 192), radius=14, fill=WHITE)
    draw.rounded_rectangle((86, 86, 170, 170), radius=8, fill=ACCENT)
    # Pins
    for offset in range(4):
        position = 84 + offset * 28
        draw.rectangle((40, position, 64, position + 10), fill=WHITE)
        draw.rectangle((192, position, 216, position + 10), fill=WHITE)
        draw.rectangle((position, 40, position + 10, 64), fill=WHITE)
        draw.rectangle((position, 192, position + 10, 216), fill=WHITE)
    # "K" in the middle
    draw.line((106, 100, 106, 156), fill=WHITE, width=12)
    draw.line((106, 128, 142, 100), fill=WHITE, width=12)
    draw.line((106, 128, 142, 156), fill=WHITE, width=12)
    image.save(ASSETS / "app.png")
    image.save(ASSETS / "app.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    app_icon()
    for function in (icon_search, icon_open, icon_new, icon_batch, icon_key,
                     icon_gear, icon_database, icon_refresh, icon_link):
        function()
    print("assets written to", ASSETS)


if __name__ == "__main__":
    main()
