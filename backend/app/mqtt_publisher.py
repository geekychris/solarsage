"""MQTT publisher with Home Assistant auto-discovery.

Each Sheets-backed / cached widget publishes:

    solarsage/widgets/<widget_id>/state       — JSON payload of ``data``
    solarsage/widgets/<widget_id>/attributes  — extra metadata

And registers a corresponding HA discovery config at:

    homeassistant/sensor/solarsage_<widget_id>/config

so the entity shows up automatically in Home Assistant.

Configuration (backend/.env):

    MQTT_BROKER=192.168.1.10
    MQTT_PORT=1883                # optional, default 1883
    MQTT_USER=solarsage           # optional
    MQTT_PASS=secret              # optional
    MQTT_DISCOVERY_PREFIX=homeassistant   # default; matches HA's default

If ``MQTT_BROKER`` isn't set, publisher stays dormant.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time as _time
from typing import Any

log = logging.getLogger("eg4.mqtt")


class MqttPublisher:
    """Async wrapper around aiomqtt with connection retry + HA discovery."""

    def __init__(
        self,
        broker: str,
        *,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        base_topic: str = "solarsage",
        discovery_prefix: str = "homeassistant",
    ) -> None:
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.base_topic = base_topic
        self.discovery_prefix = discovery_prefix
        self._client = None
        self._connect_lock = asyncio.Lock()
        self._discovered: set[str] = set()

    async def _client_or_none(self):
        """Lazy-connect. Returns an aiomqtt.Client or None on failure.
        We DON'T raise on connect failure so widget refreshes stay
        healthy even without a broker."""
        if self._client is not None:
            return self._client
        async with self._connect_lock:
            if self._client is not None:
                return self._client
            try:
                import aiomqtt  # noqa: F401
            except ImportError:
                log.warning("aiomqtt not installed; MQTT publishing disabled")
                return None
            try:
                client = aiomqtt.Client(
                    hostname=self.broker,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    identifier=f"solarsage-{os.getpid()}",
                )
                # aiomqtt uses async-context manager per session; we
                # wrap in a persistent client via manual __aenter__
                await client.__aenter__()
                self._client = client
                log.info(
                    "MQTT connected to %s:%s as %s",
                    self.broker, self.port, self.username or "anon",
                )
                return client
            except Exception as exc:  # noqa: BLE001
                log.warning("MQTT connect failed: %s", exc)
                return None

    async def close(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        self._client = None

    # --- publishing ----------------------------------------------------

    def _widget_state_topic(self, widget_id: str) -> str:
        return f"{self.base_topic}/widgets/{widget_id}/state"

    def _widget_attrs_topic(self, widget_id: str) -> str:
        return f"{self.base_topic}/widgets/{widget_id}/attributes"

    def _discovery_topic(self, widget_id: str) -> str:
        return f"{self.discovery_prefix}/sensor/solarsage_{widget_id}/config"

    def _discovery_config(self, widget) -> dict[str, Any]:
        """HA MQTT-discovery config for a widget.

        We surface each widget as a sensor whose state is the fetch
        timestamp (something that always exists) and whose attributes
        hold the full data payload — so an HA template sensor can pull
        arbitrary fields from ``attributes.data`` without extra topics.
        """
        return {
            "name": widget.name,
            "unique_id": f"solarsage_{widget.id}",
            "state_topic": self._widget_state_topic(widget.id),
            "value_template": "{{ value_json.fetched_at }}",
            "json_attributes_topic": self._widget_attrs_topic(widget.id),
            "icon": "mdi:widgets",
            "device": {
                "identifiers": ["solarsage"],
                "name": "SolarSage",
                "manufacturer": "SolarSage",
                "model": "Widget dashboard",
            },
        }

    async def publish_widget(self, widget, state: dict[str, Any]) -> None:
        """Publish one widget's state + attributes; register HA
        discovery on first sight."""
        client = await self._client_or_none()
        if client is None:
            return
        try:
            # HA discovery — publish once per widget id per process
            if widget.id not in self._discovered:
                await client.publish(
                    self._discovery_topic(widget.id),
                    payload=json.dumps(self._discovery_config(widget)),
                    retain=True,
                )
                self._discovered.add(widget.id)
            payload = {
                "fetched_at": state.get("fetched_at"),
                "error": state.get("error"),
                "widget_id": widget.id,
                "widget_kind": widget.kind,
            }
            await client.publish(
                self._widget_state_topic(widget.id),
                payload=json.dumps(payload),
                retain=True,
            )
            attrs = {
                "data": state.get("data"),
                "meta": widget.meta(),
                "published_at": _time.time(),
            }
            await client.publish(
                self._widget_attrs_topic(widget.id),
                payload=json.dumps(attrs, default=str),
                retain=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("MQTT publish %s failed: %s", widget.id, exc)
            # Nuke the client so we reconnect on the next call
            self._client = None


def load_from_env() -> MqttPublisher | None:
    broker = os.getenv("MQTT_BROKER")
    if not broker:
        return None
    return MqttPublisher(
        broker=broker,
        port=int(os.getenv("MQTT_PORT", "1883")),
        username=os.getenv("MQTT_USER") or None,
        password=os.getenv("MQTT_PASS") or None,
        base_topic=os.getenv("MQTT_BASE_TOPIC", "solarsage"),
        discovery_prefix=os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant"),
    )
