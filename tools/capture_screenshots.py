"""Capture annotated screenshots of the running SolarSage UI.

Run from the repo root (after `solarsage start`):
    backend/.venv/bin/python tools/capture_screenshots.py

Uses Playwright headless chromium. Auth is done via the public
/api/auth/use_saved endpoint (no password needed). Outputs go to
docs/screenshots/.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import async_playwright

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

UI = "http://127.0.0.1:5173"
BACKEND = "http://127.0.0.1:8000"


def get_token() -> str:
    req = Request(f"{BACKEND}/api/auth/use_saved", method="POST")
    with urlopen(req, timeout=10) as r:
        return json.load(r)["token"]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def annotate(src: Path, callouts: list[dict]) -> Path:
    """callouts: [{xy: (x, y), label: "1", color: "#58a6ff", radius: 18}]"""
    img = Image.open(src).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(22)

    for c in callouts:
        x, y = c["xy"]
        r = c.get("radius", 20)
        color = c.get("color", "#58a6ff")
        # Circle background (semi-transparent fill, opaque border)
        draw.ellipse(
            [x - r, y - r, x + r, y + r],
            fill=(255, 255, 255, 230),
            outline=color,
            width=3,
        )
        # Label text — center it
        text = c["label"]
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            (x - tw / 2, y - th / 2 - 2),
            text,
            fill=color,
            font=font,
        )

    combined = Image.alpha_composite(img, overlay)
    out = src.with_name(src.stem + ".annotated.png")
    combined.convert("RGB").save(out, "PNG", optimize=True)
    return out


async def capture():
    token = get_token()
    print(f"got auth token: {token[:12]}…")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )

        # 1. LOGIN SCREEN — no token, block auto-recovery so login form renders
        page = await ctx.new_page()
        async def block_use_saved(route):
            await route.fulfill(status=404, body='{"detail":"no saved credentials"}',
                                headers={"content-type": "application/json"})
        await page.route("**/api/auth/use_saved", block_use_saved)
        await page.goto(UI, wait_until="networkidle")
        await page.wait_for_selector(".login-card", timeout=15000)
        await page.wait_for_timeout(400)
        login_path = OUT / "login.png"
        await page.screenshot(path=str(login_path), full_page=False)
        print(f"  captured {login_path.name}")
        await page.close()

        # 2. DASHBOARD — plant token, then load
        page = await ctx.new_page()
        await page.add_init_script(f"window.localStorage.setItem('eg4.token','{token}');")
        await page.goto(UI, wait_until="networkidle")
        await page.wait_for_selector(".topbar", timeout=15000)
        # Wait for live tiles to populate
        await page.wait_for_timeout(3000)

        # Top bar / brand
        topbar = await page.locator(".topbar").bounding_box()
        if topbar:
            tp = OUT / "topbar.png"
            await page.screenshot(
                path=str(tp),
                clip={"x": topbar["x"], "y": topbar["y"],
                      "width": topbar["width"], "height": topbar["height"]},
            )
            print(f"  captured {tp.name}")

        # Sidebar (sites + inverters)
        sidebar = await page.locator(".sidebar").first.bounding_box()
        if sidebar:
            sp = OUT / "sidebar.png"
            await page.screenshot(
                path=str(sp),
                clip={"x": sidebar["x"], "y": sidebar["y"],
                      "width": sidebar["width"], "height": min(sidebar["height"], 600)},
            )
            print(f"  captured {sp.name}")

        # Full dashboard above the fold
        fold_path = OUT / "dashboard_top.png"
        await page.screenshot(path=str(fold_path), full_page=False)
        print(f"  captured {fold_path.name}")

        # Live tiles panel (first panel containing .tiles)
        tiles_loc = page.locator(".panel:has(.tiles)").first
        try:
            await tiles_loc.scroll_into_view_if_needed(timeout=3000)
            tb = await tiles_loc.bounding_box()
            if tb:
                lp = OUT / "live_tiles.png"
                await page.screenshot(
                    path=str(lp),
                    clip={"x": tb["x"], "y": tb["y"], "width": tb["width"], "height": tb["height"]},
                )
                print(f"  captured {lp.name}")
        except Exception as e:
            print(f"  live tiles capture failed: {e}")

        # For each major panel-by-h3 title, screenshot it
        h3_targets = [
            ("Smart load scheduler", "scheduler"),
            ("Weather & AC forecast", "weather"),
            ("Production headroom & excess", "excess"),
            ("Battery charge forecast", "battery_forecast"),
            ("Today's production vs expected", "today"),
            ("Range view", "range"),
            ("Production heatmap", "heatmap"),
            ("System health", "health"),
            ("Alerts", "alerts"),
            ("Appliances", "appliances"),
            ("Sites", "sites_panel"),
            ("Raw data", "raw_data"),
        ]
        for label, slug in h3_targets:
            try:
                panel = page.locator(f".panel:has(h3:has-text('{label}'))").first
                await panel.scroll_into_view_if_needed(timeout=2000)
                await page.wait_for_timeout(600)
                bb = await panel.bounding_box()
                if not bb:
                    continue
                out = OUT / f"{slug}.png"
                await page.screenshot(
                    path=str(out),
                    clip={"x": bb["x"], "y": bb["y"],
                          "width": bb["width"], "height": min(bb["height"], 950)},
                )
                print(f"  captured {out.name}")
            except Exception as e:
                print(f"  {slug} failed: {e}")

        # Settings modal
        try:
            await page.click("button:has-text('Settings')")
            await page.wait_for_selector(".modal", timeout=3000)
            await page.wait_for_timeout(400)
            sm = OUT / "settings_modal.png"
            await page.screenshot(path=str(sm), full_page=False)
            print(f"  captured {sm.name}")
            await page.keyboard.press("Escape")
        except Exception as e:
            print(f"  settings modal failed: {e}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(capture())
