# Screenshots

Auto-generated from a live SolarSage instance. Do not edit by hand.

## Refreshing

```bash
export EG4_USERNAME=your-eg4-user
export EG4_PASSWORD=xxx
export SOLARSAGE_URL=https://pi-sf.hitorro.com   # or your host
./scripts/capture-screenshots.sh
```

The script installs Playwright + a headless Chromium into
`frontend/node_modules/` on first run (~200 MB one-time), logs into
SolarSage, walks the tab / widget / settings tree, and overwrites the
PNG set here plus `manifest.json`. It's idempotent — safe to re-run
any time UI changes land.

## What each file is

See `manifest.json` for the current caption per file.
