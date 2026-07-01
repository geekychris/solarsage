# Mobile / touch view

SolarSage has two layouts:

* **Desktop** — the default. Multi-tab grid with sidebar. Best for a
  laptop or wall display.
* **Mobile** — single vertical stream of collapsible cards with a
  bottom tab bar and 48-px touch targets. Best for a phone browser or
  a tablet.

## How it picks

On first load, `App.jsx` auto-detects:

* Viewport ≤ 768px wide **and** device has touch → **Mobile**
* Otherwise → **Desktop**

The choice is stored in `localStorage["eg4.mobile"]` so it sticks
after the first pick.

## Manual override

Any of:

* `?view=mobile` or `?view=desktop` in the URL — sets the mode for
  this session (and persists to localStorage).
* Desktop topbar → **📱 Mobile** button — switches to the mobile view.
* Mobile header → **🖥** button — switches back to desktop.

Clear `localStorage["eg4.mobile"]` (or open in a private window) to
reset to auto-detect.

## Add to iOS home screen

The dashboard is a light PWA — Safari on iOS can pin it to the home
screen:

1. Open `https://pi-sf.hitorro.com/` in Safari.
2. Share sheet → **Add to Home Screen** → name it "SolarSage".
3. Tap the icon on your home screen — it opens in a fullscreen web
   view without Safari chrome. `manifest.json`-style theme colour +
   `apple-touch-icon` are already set in `index.html`.

## Same widgets, tighter layout

The mobile view reuses every widget renderer from the desktop. The
differences are purely presentational:

* Cards stack vertically (single-column) instead of the responsive
  grid.
* Card header is a tap target that collapses the body.
* Sub-tabs (Safety / Outdoor / Travel / Solar / Community / Lists)
  live in a horizontally scrollable bottom bar, thumb-reachable.
* Padding scales up for touch: 12 px card padding, 48 px min tap
  targets.

## What doesn't work well on mobile yet

* Wide tables (border log history, tide table) — they scroll
  horizontally inside the card. Might trim columns later.
* Rich editors (subscriptions form) — usable but cramped on narrow
  screens.
* Settings modal — hasn't been retested on mobile; may need padding
  tweaks.

If you find something painful to use with a thumb, tell me — the
widget renderers all take the same props on both sides so fixes are
usually one-liners.
