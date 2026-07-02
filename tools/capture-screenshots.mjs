// Automated screenshot capture for the SolarSage README.
//
// Run from the repo root after `npm install --save-dev playwright &&
// npx playwright install chromium`:
//
//   SOLARSAGE_URL=https://pi-sf.hitorro.com \
//   EG4_USERNAME=... EG4_PASSWORD=... \
//   node tools/capture-screenshots.mjs
//
// Writes PNGs to docs/screenshots/. Idempotent — each run overwrites
// the previous captures.

import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";

const URL = process.env.SOLARSAGE_URL || "https://pi-sf.hitorro.com";
const USERNAME = process.env.EG4_USERNAME;
const PASSWORD = process.env.EG4_PASSWORD;
const OUT_DIR  = path.resolve("docs/screenshots");
const VIEWPORT = { width: 1400, height: 900 };
const MOBILE_VIEWPORT = { width: 390, height: 844 };

if (!USERNAME || !PASSWORD) {
  console.error("Set EG4_USERNAME and EG4_PASSWORD env vars.");
  process.exit(1);
}

// One config per screenshot. `open` runs before the shot; result files
// live under docs/screenshots/<file>.
const SHOTS = [
  {
    file: "01-dashboard-solar.png",
    caption: "Solar tab — vitals + climate + peak load + forecast accuracy",
    async open(page) {
      await clickSubTab(page, "Solar");
      await settle(page, 3000);
    },
  },
  {
    file: "02-dashboard-outdoor.png",
    caption: "Outdoor tab — weather, tides, marine, sunset, sky tonight, meteor showers",
    async open(page) {
      await clickSubTab(page, "Outdoor");
      await settle(page, 2500);
    },
  },
  {
    file: "03-dashboard-safety.png",
    caption: "Safety tab — earthquakes, storms, UV & heat, air quality",
    async open(page) {
      await clickSubTab(page, "Safety");
      await settle(page, 2000);
    },
  },
  {
    file: "04-dashboard-travel.png",
    caption: "Travel tab — trip planner, border wait times, fuel prices with live Pemex data",
    async open(page) {
      await clickSubTab(page, "Travel");
      await settle(page, 2000);
    },
  },
  {
    file: "05-dashboard-community.png",
    caption: "Community tab — events, HOA activities, news, Spanish practice",
    async open(page) {
      await clickSubTab(page, "Community");
      await settle(page, 2000);
    },
  },
  {
    file: "06-widget-solar-vitals.png",
    caption: "Solar Vitals — SoC, PV per string, load breakdown, per-AC override, per-room temp/humidity",
    async open(page) {
      await clickSubTab(page, "Solar");
      await settle(page, 3000);
      // Scroll the widget into view
      await page.evaluate(() => {
        const el = document.querySelector(".sv2");
        if (el) el.scrollIntoView({ block: "start" });
      });
      await settle(page, 500);
    },
    async region(page) {
      const el = page.locator(".sv2").first();
      try { await el.waitFor({ state: "attached", timeout: 5000 }); } catch { return null; }
      return el.boundingBox();
    },
  },
  {
    file: "07-widget-climate-chart.png",
    caption: "Room Climate History — 24h/3d/7d temp + humidity with hover crosshair",
    async open(page) {
      await clickSubTab(page, "Solar");
      await settle(page, 2000);
    },
    async region(page) {
      const el = page.locator(".climate-chart").first();
      try { await el.waitFor({ state: "attached", timeout: 5000 }); } catch { return null; }
      return el.boundingBox();
    },
  },
  {
    file: "08-widget-water-tank.png",
    caption: "Water Tank — gallons + days-remaining projection with tiered warning bar",
    async open(page) {
      // water_tank widget may be on Local or House tab after aliasing
      const localTab = await page.locator('.local-subtab', { hasText: /^(Local|House)$/ }).first();
      if (await localTab.count() > 0) await localTab.click();
      await settle(page, 1500);
    },
    async region(page) {
      const el = page.locator(".water-tank").first();
      try { await el.waitFor({ state: "attached", timeout: 5000 }); } catch { return null; }
      return el.boundingBox();
    },
  },
  {
    file: "09-widget-peak-load.png",
    caption: "Peak Load — rolling 30-day max simultaneous house load",
    async open(page) {
      await clickSubTab(page, "Solar");
      await settle(page, 2000);
    },
    async region(page) {
      const el = page.locator(".peak-load").first();
      try { await el.waitFor({ state: "attached", timeout: 5000 }); } catch { return null; }
      return el.boundingBox();
    },
  },
  {
    file: "10-widget-acpv-overlay.png",
    caption: "AC vs PV Overlay — 24h of PV production against smart_ac consumption",
    async open(page) {
      await clickSubTab(page, "Solar");
      await settle(page, 2000);
    },
    async region(page) {
      const el = page.locator(".acpv-overlay").first();
      try { await el.waitFor({ state: "attached", timeout: 5000 }); } catch { return null; }
      return el.boundingBox();
    },
  },
  {
    file: "11-widget-sky-tonight.png",
    caption: "Sky Tonight — naked-eye planets tonight + moon phase, computed locally",
    async open(page) {
      await clickSubTab(page, "Outdoor");
      await settle(page, 2000);
    },
    async region(page) {
      const el = page.locator(".sky-tonight").first();
      try { await el.waitFor({ state: "attached", timeout: 5000 }); } catch { return null; }
      return el.boundingBox();
    },
  },
  {
    file: "12-settings-system.png",
    caption: "Settings → System — location map picker + external service URLs and tokens",
    async open(page) {
      await openSettings(page, "system");
      await settle(page, 2500);
    },
    async region(page) {
      const el = page.locator(".modal-wide").first();
      try { await el.waitFor({ state: "attached", timeout: 5000 }); } catch { return null; }
      return el.boundingBox();
    },
  },
  {
    file: "13-settings-notifications.png",
    caption: "Settings → Notifications — per-source enable, quiet hours, test-fire, history + replay",
    async open(page) {
      await openSettings(page, "notifications");
      await settle(page, 1500);
    },
    async region(page) {
      const el = page.locator(".modal-wide").first();
      try { await el.waitFor({ state: "attached", timeout: 5000 }); } catch { return null; }
      return el.boundingBox();
    },
  },
  {
    file: "14-settings-ha-integrations.png",
    caption: "Settings → HA Integrations — per-widget entity pickers with live values from Home Assistant",
    async open(page) {
      await openSettings(page, "ha");
      await settle(page, 2500);
    },
    async region(page) {
      const el = page.locator(".modal-wide").first();
      try { await el.waitFor({ state: "attached", timeout: 5000 }); } catch { return null; }
      return el.boundingBox();
    },
  },
  {
    file: "15-settings-rotation.png",
    caption: "Settings → Rotation — fullscreen 'screensaver' widget rotation with per-step dwell",
    async open(page) {
      await openSettings(page, "rotation");
      await settle(page, 1500);
    },
    async region(page) {
      const el = page.locator(".modal-wide").first();
      try { await el.waitFor({ state: "attached", timeout: 5000 }); } catch { return null; }
      return el.boundingBox();
    },
  },
  {
    file: "16-rotation-mode.png",
    caption: "Rotation mode — full-screen kiosk view walking through configured widgets",
    async open(page) {
      // Close any modal first
      await page.keyboard.press("Escape").catch(() => {});
      await settle(page, 300);
      await page.goto(`${URL}/?view=rotation`);
      await settle(page, 4000);
    },
  },
  {
    file: "17-mobile-dashboard.png",
    caption: "Mobile viewport — same widgets, 1-column grid",
    viewport: MOBILE_VIEWPORT,
    async open(page) {
      await page.goto(URL);
      await settle(page, 2500);
    },
  },
];

async function clickSubTab(page, name) {
  // Subtabs render as ``<div class="local-subtab">Solar<span>10</span></div>`` —
  // multi-node text confuses Playwright's hasText matcher. Do the
  // find + click inside the page so we're comparing textContent
  // directly to the tab name.
  const clicked = await page.evaluate((n) => {
    const els = Array.from(document.querySelectorAll(".local-subtab"));
    const hit = els.find((e) => e.textContent.trim().replace(/\s+\d+$/, "") === n);
    if (hit) { hit.click(); return true; }
    return false;
  }, name);
  if (!clicked) console.warn(`subtab '${name}' not found`);
  await page.waitForTimeout(400);
}

async function openSettings(page, tabId) {
  // If a modal is already open (previous shot), close it via the
  // dedicated close button. Escape doesn't seem to be wired.
  const closeBtn = page.locator(".settings-tab-close").first();
  if (await closeBtn.isVisible().catch(() => false)) {
    await closeBtn.click();
    await settle(page, 300);
  }
  // Then click the top-level Dashboard "Settings" text button —
  // widget-level gears also have title="Settings" so match text.
  await page.getByRole("button", { name: /^Settings$/ }).first().click();
  await page.waitForSelector(".modal-wide", { timeout: 5000 });
  const tabButton = page.locator(".settings-tab", { hasText: new RegExp(tabName(tabId), "i") }).first();
  if (await tabButton.count() > 0) await tabButton.click();
}

function tabName(id) {
  return ({
    system: "System",
    rotation: "Rotation",
    notifications: "Notifications",
    ha: "HA Integrations",
  })[id] || id;
}

async function settle(page, ms) {
  await page.waitForTimeout(ms);
}

async function login(page) {
  await page.goto(URL, { waitUntil: "domcontentloaded" });
  // Two paths: either the app already has a saved session and jumps
  // straight to the dashboard, or the login form is presented.
  await page.waitForFunction(
    () => document.querySelector(".tabs .tab") ||
          document.querySelector("#u"),
    { timeout: 30_000 },
  );
  const hasLogin = await page.$("#u");
  if (hasLogin) {
    await page.fill("#u", USERNAME);
    await page.fill("#p", PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForSelector(".tabs .tab", { timeout: 30_000 });
  }
  // Switch to the "Local" top-level tab — that's where the widget
  // system lives (subtabs Solar / Outdoor / Safety / etc). The
  // default landing is "Now" which shows the legacy Power Flow view.
  const localTab = page.locator(".tabs .tab", { hasText: /^Local$/ }).first();
  if (await localTab.count() > 0) {
    await localTab.click();
    await page.waitForSelector(".local-subtab", { timeout: 15_000 });
  }
}

async function main() {
  await fs.mkdir(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  await login(page);

  const manifest = [];
  for (const shot of SHOTS) {
    // For mobile-only shots we swap the viewport before capture.
    if (shot.viewport) {
      await page.setViewportSize(shot.viewport);
    } else {
      await page.setViewportSize(VIEWPORT);
    }
    try {
      await shot.open(page);
    } catch (ex) {
      console.warn(`open failed for ${shot.file}: ${ex.message}`);
      continue;
    }
    const clip = shot.region ? await shot.region(page) : null;
    await page.screenshot({
      path: path.join(OUT_DIR, shot.file),
      clip: clip || undefined,
      fullPage: shot.fullPage || false,
    });
    manifest.push({ file: shot.file, caption: shot.caption });
    console.log(`✓ ${shot.file}`);
  }
  await fs.writeFile(
    path.join(OUT_DIR, "manifest.json"),
    JSON.stringify(manifest, null, 2) + "\n",
  );
  await browser.close();
  console.log(`\nWrote ${manifest.length} screenshots to ${OUT_DIR}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
