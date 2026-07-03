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

// Bounding box of the widget-card whose <h3> text is exactly ``name``.
async function widgetCardBox(page, name) {
  return page.evaluate((n) => {
    for (const h of document.querySelectorAll(".widget-card h3")) {
      if (h.textContent.trim() === n) {
        const card = h.closest(".widget-card");
        if (!card) return null;
        card.scrollIntoView({ block: "start" });
        const r = card.getBoundingClientRect();
        return {
          x: r.x + window.scrollX,
          y: r.y + window.scrollY,
          width: r.width,
          height: r.height,
        };
      }
    }
    return null;
  }, name);
}

// Generate a SHOTS entry that captures one widget card.
function widget(seq, tab, id, name, caption) {
  return {
    file: `${String(seq).padStart(2, "0")}-widget-${id}.png`,
    caption,
    async open(page) {
      await clickSubTab(page, tab);
      await settle(page, 1500);
      // Ensure the widget scrolls into view before capture.
      await page.evaluate((n) => {
        for (const h of document.querySelectorAll(".widget-card h3")) {
          if (h.textContent.trim() === n) {
            h.closest(".widget-card")?.scrollIntoView({ block: "start" });
            break;
          }
        }
      }, name);
      await settle(page, 400);
    },
    async region(page) {
      const box = await widgetCardBox(page, name);
      if (!box) return null;
      // Return only the client-visible slice; Playwright's clip needs
      // viewport coords, so subtract scroll.
      const scroll = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
      return {
        x: Math.max(0, box.x - scroll.x),
        y: Math.max(0, box.y - scroll.y),
        width: box.width,
        height: box.height,
      };
    },
  };
}

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
  // ------- per-widget close-ups (auto-generated) -------
  widget(20, "Safety",    "aqi",              "Air quality",                 "Air Quality — US AQI + PM2.5/PM10/ozone/dust + 24h peak. Source: Open-Meteo."),
  widget(21, "Safety",    "quakes",           "Earthquakes",                 "Earthquakes — recent felt quakes (M ≥ 2.5) within a configurable radius. Source: USGS."),
  widget(22, "Safety",    "storms",           "Tropical storms",             "Tropical storms — active NHC cyclones, filtered to configured basins (default EP)."),
  widget(23, "Safety",    "uv_heat",          "UV & heat stress",            "UV & heat — peak UV time + apparent-temperature danger window today and tomorrow."),
  widget(24, "Outdoor",   "weather",          "Weather",                     "Weather — current conditions + 7-day forecast (Open-Meteo)."),
  widget(25, "Outdoor",   "tides",            "Tide tables",                 "Tide tables — highs/lows from the tidetime.org scraper (no API key)."),
  widget(26, "Outdoor",   "marine",           "Marine forecast",             "Marine — wave height, wind, sea temperature + 'best window' hint."),
  widget(27, "Outdoor",   "sea_temp",         "Sea temperature",             "Sea surface temp — current + 7-day forecast + swim/fishing context."),
  widget(28, "Outdoor",   "sun_moon",         "Sun & moon",                  "Sun & moon — sunrise/sunset/solar noon + moon phase (local math, no API)."),
  widget(29, "Outdoor",   "sunset",           "Sunset countdown",            "Sunset countdown — live-ticking minutes to sunset with 'golden 20' highlight."),
  widget(30, "Outdoor",   "fishing_window",   "Fishing windows",             "Fishing windows — best hours today/tomorrow from tide movement + dawn/dusk + sea state."),
  widget(31, "Outdoor",   "whale_season",     "Whale watching",              "Whale watching season — Sea of Cortez fin/blue/gray whale indicator."),
  widget(32, "Outdoor",   "meteor_showers",   "Meteor showers",              "Meteor showers — next shower peak with ZHR + hint. Announces N days before."),
  widget(33, "Outdoor",   "bird_migration",   "Bird migration",              "Bird migration — species currently moving through the Baja Pacific Flyway."),
  widget(34, "Travel",    "border",           "Border wait times",           "Border wait times — CBP data for US-Mexico crossings."),
  widget(35, "Travel",    "costco_fuel",      "Fuel prices",                 "Fuel prices — real CA retail avg from EIA + live per-station Pemex from CRE + manual Costco."),
  widget(36, "Travel",    "return_countdown", "Days until return",           "Return countdown — days to your next drive back north."),
  widget(37, "Travel",    "currency",         "MXN/USD",                     "MXN/USD — daily rate from Frankfurter (ECB) with a 14-day trailing series."),
  widget(38, "Travel",    "drive_time",       "Drive times",                 "Drive times — OSRM distance + duration between configured points."),
  widget(39, "Travel",    "holidays",         "Mexican holidays",            "Mexican holidays — federal public holidays with next-holiday countdown."),
  widget(40, "Travel",    "trip_planner",     "Trip planner",                "Trip planner — daily 'go-score' combining drive time + border wait + weather."),
  widget(41, "Solar",     "consumption_yoy",  "Consumption YoY",             "Consumption YoY — today's load vs. same-day-last-year from EG4 history."),
  widget(42, "Solar",     "forecast_accuracy","Forecast accuracy",           "Forecast accuracy — 30 days of forecast vs actual PV; tune peak_kw when biased."),
  widget(43, "Solar",     "property_mode",    "Property mode",               "Property mode — Occupied / Vacant / Arriving date; other widgets adjust off this."),
  widget(44, "Solar",     "solar_excess",     "Excess-energy planner",       "Excess-energy planner — today's expected surplus + suggested loads for midday."),
  widget(45, "Solar",     "precool",          "Pre-cool advisor",            "Pre-cool advisor — window based on apparent-temperature peak and current SoC."),
  widget(46, "Solar",     "when_to_run",      "When to run",                 "When to run — best contiguous window today/tomorrow per configured high-load appliance."),
  widget(47, "Community", "baja_news",        "Baja news",                   "Baja news — configurable regional RSS/Atom outlets."),
  widget(48, "Community", "baja_races",       "Baja races",                  "Baja races — SCORE International off-road schedule with ★ for SF-involved events."),
  widget(49, "Community", "hoa_newsletter",   "HOA newsletter",              "HOA newsletter — latest El Dorado Ranch weekly PDF, auto-scraped."),
  widget(50, "Community", "hoa",              "El Dorado Ranch — activities","El Dorado Ranch activities — auto-parsed weekly activities PDF."),
  widget(51, "Community", "news",             "News",                        "News — configurable RSS/Atom feeds (defaults: NHC + USGS)."),
  widget(52, "Community", "property_tax",     "Property tax (predial)",      "Property tax — San Felipe predial countdown with paid-this-year toggle."),
  widget(53, "Community", "reservations",     "Reservations",                "Reservations — upcoming bookings from configured iCal URLs."),
  widget(54, "Community", "spanish",          "Spanish practice",            "Spanish practice — daily phrase, speak button (via pi5 TTS), and dictation quiz."),
  widget(55, "Lists",     "border_log",       "Border crossing log",         "Border crossing log — every crossing with direction, port, actual vs quoted wait, notes."),
  widget(56, "Lists",     "contacts",         "Contacts",                    "Contacts — address book (name/phone/email/location) shared with the phone."),
  widget(57, "Lists",     "quicklinks",       "Quick links",                 "Quick links — grouped bookmarks. Ships an 'Apps' group with smart_ac + HA."),
  widget(58, "Lists",     "shopping_list",    "Shopping list (bring down)",  "Shopping list — items to buy in the US on your next border run."),
  widget(59, "Lists",     "todo",             "Todo",                        "Todo — priority (1..5), optional due date, done flag, notes. Syncs to Sheets when enabled."),
];

async function clickSubTab(page, name) {
  // Wait for the subtabs to render, then use Playwright's filter().
  try {
    await page.waitForSelector(".local-subtab", { timeout: 5000 });
  } catch {
    console.warn(`no subtabs visible when trying to click '${name}'`);
    return;
  }
  const btn = page.locator(".local-subtab").filter({ hasText: name }).first();
  if (await btn.count() === 0) {
    console.warn(`subtab '${name}' not found`);
    return;
  }
  await btn.click({ timeout: 5000 });
  await page.waitForTimeout(500);
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

  async function ensureLocalTab() {
    const isOnLocal = await page.locator(".local-subtab").count();
    if (isOnLocal > 0) return;
    const localTab = page.locator(".tabs .tab").filter({ hasText: /^Local$/ }).first();
    if (await localTab.count() > 0) {
      await localTab.click();
      await page.waitForSelector(".local-subtab", { timeout: 10_000 });
    }
  }

  const manifest = [];
  for (const shot of SHOTS) {
    // For mobile-only shots we swap the viewport before capture.
    if (shot.viewport) {
      await page.setViewportSize(shot.viewport);
    } else {
      await page.setViewportSize(VIEWPORT);
    }
    // If a previous Settings modal or Rotation view left us elsewhere,
    // return to the Local view before this shot's open() runs.
    // Skip for the rotation and mobile shots — they intentionally
    // navigate somewhere else.
    if (!/rotation|mobile/i.test(shot.file)) {
      try { await ensureLocalTab(); } catch {}
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
