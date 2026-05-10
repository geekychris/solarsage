"""Overlay numbered callout circles on the captured screenshots.

Coordinates are in pixels at 2× device-scale-factor (so the image is twice
the logical viewport size). Each entry: (x, y, label, color). Outputs go to
docs/screenshots/<name>.annotated.png.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "screenshots"

BLUE = "#58a6ff"
GREEN = "#2ea043"
ORANGE = "#d29922"
RED = "#f85149"


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def annotate(src_name: str, callouts: list[tuple]) -> Path:
    """callouts = [(x, y, label, color, radius?), ...]"""
    src = OUT / src_name
    img = Image.open(src).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Fixed small markers — large enough to read in README, small enough not
    # to obscure the content. Two-digit labels get a slightly wider radius.
    font_size = 26
    font = _font(font_size)
    for c in callouts:
        x, y, label, color, *rest = c
        default_r = 26 if len(label) >= 2 else 22
        r = rest[0] if rest else default_r
        # Outer white ring + colored fill
        draw.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3],
                     fill=(0, 0, 0, 0), outline="#ffffff", width=4)
        draw.ellipse([x - r, y - r, x + r, y + r],
                     fill=color, outline="#ffffff", width=2)
        # Centered label
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((x - tw / 2, y - th / 2 - 4), label,
                  fill="#ffffff", font=font)
    combined = Image.alpha_composite(img, overlay)
    out = src.with_name(src.stem + ".annotated.png")
    combined.convert("RGB").save(out, "PNG", optimize=True)
    print(f"  {out.name}  ({combined.size[0]}×{combined.size[1]})")
    return out


# Coordinate ground rules — every screenshot is captured at device_scale_factor=2,
# so logical 1440×900 → 2880×1800. Coordinates below are in raw image pixels.

annotate("login.png", [
    (1090, 525, "1", GREEN),      # logo — just outside left edge of card
    (1090, 990, "2", BLUE),       # username row
    (1090, 1130, "3", BLUE),      # password row
    (1090, 1240, "4", ORANGE),    # remember-me row
    (1090, 1310, "5", GREEN),     # sign-in row
    (1090, 1420, "6", BLUE),      # security note row
])

# dashboard_top.png is 2880×1800 at 2× DSR.
# Strategy: callouts in margins or in the small gaps between tiles where
# there's genuinely empty space. Avoid placing over numeric values.
annotate("dashboard_top.png", [
    (40, 40, "1", GREEN),         # brand corner (top-left of logo, outside)
    (1300, 40, "2", BLUE),        # gap above 30d/Sync
    (1660, 40, "3", ORANGE),      # over the "updated" label
    (1830, 40, "4", ORANGE),      # Settings/Sign out/Forget cluster
    (40, 260, "5", GREEN),        # left of "Manage multiple solar systems"
    (40, 690, "6", BLUE),         # left of INVERTERS header
    (770, 150, "7", GREEN),       # gap above ChrisCollins title
    (1230, 280, "8", GREEN),      # gap above SOLAR PV header text
    (1600, 280, "9", ORANGE),     # gap above LOAD header
    (2280, 280, "10", BLUE),      # gap above FROM GRID (rightmost)
    (1230, 450, "11", BLUE),      # gap above BATTERY DISCHARGING header
    (770, 940, "12", GREEN),      # gap above "Smart load scheduler" heading
])

# weather.png — 2880×~880 logical (roughly)
annotate("weather.png", [
    (60, 50, "1", GREEN),      # left of title
    (60, 200, "2", ORANGE),    # left of OUTSIDE NOW tile
    (1490, 105, "3", BLUE),    # above AC MODEL header text
    (1990, 105, "4", GREEN),   # above TOMORROW PV header
    (2370, 105, "5", RED),     # above TOMORROW AC LOAD header
    (60, 540, "6", BLUE),      # left of 7-day strip
    (60, 770, "7", GREEN),     # left of "Next 48 hours"
])

annotate("excess.png", [
    (320, 90, "1", GREEN),     # MAX PRODUCIBLE NOW
    (700, 90, "2", RED),       # EXPECTED LOAD NOW
    (1080, 90, "3", BLUE),     # EXCESS AVAILABLE NOW
    (1450, 90, "4", ORANGE),   # UTILIZATION RIGHT NOW
    (1810, 90, "5", GREEN),    # PEAK EXCESS LATER
    (2170, 90, "6", BLUE),     # TOTAL EXCESS TODAY
    (320, 230, "7", BLUE),     # REMAINING EXCESS
    (1500, 600, "8", BLUE, 26),# the now line + chart center
])

annotate("scheduler.png", [
    (170, 90, "1", GREEN),     # title
    (350, 350, "2", ORANGE),   # appliance name
    (1800, 350, "3", BLUE),    # watts / runtime
    (2200, 350, "4", ORANGE),  # recommended start
    (2680, 350, "5", GREEN),   # avg surplus
])

annotate("range.png", [
    (170, 80, "1", GREEN),     # title
    (340, 240, "2", BLUE),     # 1d/3d/7d/14d/31d/90d presets
    (1100, 240, "3", ORANGE),  # end-date picker
    (1400, 240, "4", GREEN),   # Reset zoom (if visible)
    (200, 360, "5", BLUE),     # channel toggles
    (1500, 700, "6", ORANGE),  # drag-to-zoom area on chart
    (1500, 1380, "7", BLUE),   # bottom Brush bar
])

annotate("appliances.png", [
    (170, 70, "1", GREEN),     # title
    (110, 280, "2", BLUE),     # enable checkbox column
    (380, 280, "3", ORANGE),   # name column
    (940, 280, "4", BLUE),     # watts
    (1080, 280, "5", BLUE),    # run min
    (1240, 280, "6", BLUE),    # defer
    (1500, 280, "7", ORANGE),  # preferred window
    (170, 1380, "8", GREEN),   # add-new row
])

print("Done.")
