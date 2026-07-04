"""Background network-connectivity monitor.

Probes two well-known HTTPS endpoints on an interval, records each result
into `network_checks`, and — when connectivity recovers after a confirmed
outage — sends a Telegram notification via the existing notify pipeline.

Two independent targets (Cloudflare + Google) so a single-provider hiccup
doesn't false-positive. Uses HTTP (not ICMP) so no root privileges needed.

Env-tunable:
  NETWORK_WATCHER_DISABLED=1      turn off entirely
  NETWORK_CHECK_INTERVAL=60       seconds between probe cycles
  NETWORK_CHECK_TIMEOUT=8         per-probe timeout
  NETWORK_OUTAGE_CONSEC_FAILS=2   consecutive failures before outage confirmed
  NETWORK_CHECK_TARGETS=url1,url2 override targets
  NETWORK_RETENTION_DAYS=30       raw check-log retention
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import aiohttp

from .notify import dispatch as notify_dispatch
from .storage import History

log = logging.getLogger("solarsage.network")

DEFAULT_TARGETS = [
    "https://1.1.1.1/cdn-cgi/trace",
    "https://www.gstatic.com/generate_204",
]


def _targets() -> list[str]:
    raw = os.getenv("NETWORK_CHECK_TARGETS")
    if not raw:
        return DEFAULT_TARGETS
    return [t.strip() for t in raw.split(",") if t.strip()]


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


async def _probe(
    session: aiohttp.ClientSession, url: str, timeout_s: int,
) -> tuple[bool, int | None, str | None]:
    started = time.monotonic()
    try:
        async with session.get(url, timeout=timeout_s, allow_redirects=False) as r:
            await r.read()
            latency_ms = int((time.monotonic() - started) * 1000)
            if 200 <= r.status < 400:
                return True, latency_ms, None
            return False, latency_ms, f"HTTP {r.status}"
    except asyncio.TimeoutError:
        return False, None, "timeout"
    except Exception as exc:  # noqa: BLE001
        return False, None, f"{exc.__class__.__name__}: {exc}"


async def _notify_recovery(started_ts_ms: int, ended_ts_ms: int) -> dict[str, Any]:
    duration_s = max(0, (ended_ts_ms - started_ts_ms) / 1000)
    started_str = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(started_ts_ms / 1000),
    )
    text = (
        f"⚠️ Network was unreachable for {_fmt_duration(duration_s)} "
        f"(since {started_str}). Connectivity has been restored."
    )
    return await notify_dispatch({
        "type": "telegram",
        "text": text,
        "title": "SolarSage — Network recovered",
    })


async def run_network_watcher(history: History) -> None:
    if os.getenv("NETWORK_WATCHER_DISABLED") == "1":
        log.info("network watcher disabled by NETWORK_WATCHER_DISABLED=1")
        return

    interval_s = int(os.getenv("NETWORK_CHECK_INTERVAL", "60"))
    timeout_s = int(os.getenv("NETWORK_CHECK_TIMEOUT", "8"))
    confirm_after = int(os.getenv("NETWORK_OUTAGE_CONSEC_FAILS", "2"))
    retention_days = int(os.getenv("NETWORK_RETENTION_DAYS", "30"))
    targets = _targets()
    log.info(
        "network watcher started (interval=%ss, targets=%s, confirm_after=%s fails)",
        interval_s, targets, confirm_after,
    )

    consecutive_fails = 0
    outage_id: int | None = None
    outage_started_ts: int | None = None
    last_success_ts: int | None = None
    last_prune_ts = 0

    open_outage = await history.get_open_network_outage()
    if open_outage:
        outage_id = open_outage["id"]
        outage_started_ts = open_outage["started_ts"]
        consecutive_fails = confirm_after
        log.info(
            "resumed open outage id=%s started_ts=%s",
            outage_id, outage_started_ts,
        )

    conn_timeout = aiohttp.ClientTimeout(total=timeout_s)
    async with aiohttp.ClientSession(timeout=conn_timeout) as http:
        while True:
            try:
                results = await asyncio.gather(
                    *[_probe(http, url, timeout_s) for url in targets],
                    return_exceptions=False,
                )
                now_ms = int(time.time() * 1000)
                for url, (ok, latency, err) in zip(targets, results):
                    await history.record_network_check(
                        now_ms, url, ok, latency, err,
                    )
                any_ok = any(ok for ok, _, _ in results)

                if any_ok:
                    last_success_ts = now_ms
                    if outage_id is not None:
                        notify_result = await _notify_recovery(
                            outage_started_ts or now_ms, now_ms,
                        )
                        notified = bool(notify_result.get("ok"))
                        await history.close_network_outage(
                            outage_id, now_ms, notified=notified,
                        )
                        log.info(
                            "network recovered after %s (notified=%s: %s)",
                            _fmt_duration((now_ms - (outage_started_ts or now_ms)) / 1000),
                            notified, notify_result.get("detail"),
                        )
                        outage_id = None
                        outage_started_ts = None
                    consecutive_fails = 0
                else:
                    consecutive_fails += 1
                    log.warning(
                        "network probe failed (%d/%d consecutive): %s",
                        consecutive_fails, confirm_after,
                        [err for _, _, err in results],
                    )
                    if consecutive_fails >= confirm_after and outage_id is None:
                        # Outage start = last known success, or estimate
                        # `confirm_after` intervals ago.
                        outage_started_ts = last_success_ts or (
                            now_ms - interval_s * 1000 * confirm_after
                        )
                        outage_id = await history.open_network_outage(
                            outage_started_ts,
                        )
                        log.warning(
                            "network outage opened id=%s started_ts=%s",
                            outage_id, outage_started_ts,
                        )

                # Prune old check rows once an hour
                if now_ms - last_prune_ts > 3_600_000:
                    cutoff = now_ms - retention_days * 86_400_000
                    removed = await history.prune_network_checks(cutoff)
                    if removed:
                        log.info("pruned %d old network_checks rows", removed)
                    last_prune_ts = now_ms

            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("network watcher loop error")

            try:
                await asyncio.sleep(interval_s)
            except asyncio.CancelledError:
                return
