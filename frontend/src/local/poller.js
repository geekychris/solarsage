// Foreground poller — runs while the app is visible, idles when backgrounded.
//
// iOS/Android suspend JS timers when the WebView is in the background, so this
// loop simply stops on `visibilitychange:hidden` and resumes on `visible`. It
// won't fill in the gap created by the device being asleep — that's the
// fundamental tradeoff of a self-contained app, and is documented in MOBILE.md.

import { eg4 } from "./eg4Client.js";

const INTERVAL_MS = 60_000;

class Poller {
  constructor() {
    this.running = false;
    this.timer = null;
  }

  async start() {
    if (this.running) return;
    this.running = true;
    document.addEventListener("visibilitychange", this._onVis);
    this._tick();
  }

  stop() {
    this.running = false;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    document.removeEventListener("visibilitychange", this._onVis);
  }

  _onVis = () => {
    if (document.visibilityState === "visible" && this.running && !this.timer) {
      this._tick();
    }
  };

  async _tick() {
    if (!this.running) return;
    if (document.visibilityState === "hidden") {
      this.timer = null;
      return;
    }
    try {
      for (const inv of eg4.getInverters()) {
        await eg4.snapshot(inv.serialNum);
      }
    } catch (e) {
      // Swallow so the loop survives transient EG4 hiccups.
      // The UI surfaces errors when it polls /api/snapshot itself.
    }
    if (!this.running) return;
    this.timer = setTimeout(() => this._tick(), INTERVAL_MS);
  }
}

export const poller = new Poller();
