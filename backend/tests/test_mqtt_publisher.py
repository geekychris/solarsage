"""MQTT publisher — topic layout, HA discovery config shape,
env-var loader.

These tests don't require a running broker. They verify the topic
naming, discovery payload structure, and env-var handling; a real
publish is exercised only via a stub client.
"""

from __future__ import annotations

import json

import pytest

from app import mqtt_publisher as M


class _FakeWidget:
    id = "aqi"
    name = "Air quality"
    kind = "aqi"
    def meta(self):
        return {"id": self.id, "kind": self.kind, "name": self.name}


def test_load_from_env_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("MQTT_BROKER", raising=False)
    assert M.load_from_env() is None


def test_load_from_env_returns_instance_when_set(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER", "broker.local")
    monkeypatch.setenv("MQTT_PORT", "8883")
    monkeypatch.setenv("MQTT_USER", "u")
    monkeypatch.setenv("MQTT_PASS", "p")
    pub = M.load_from_env()
    assert pub is not None
    assert pub.broker == "broker.local"
    assert pub.port == 8883
    assert pub.username == "u"
    assert pub.password == "p"


def test_default_topics():
    pub = M.MqttPublisher(
        broker="x", base_topic="solarsage",
        discovery_prefix="homeassistant",
    )
    w = _FakeWidget()
    assert pub._widget_state_topic(w.id) == "solarsage/widgets/aqi/state"
    assert pub._widget_attrs_topic(w.id) == "solarsage/widgets/aqi/attributes"
    assert pub._discovery_topic(w.id) == "homeassistant/sensor/solarsage_aqi/config"


def test_discovery_config_shape():
    pub = M.MqttPublisher(broker="x")
    cfg = pub._discovery_config(_FakeWidget())
    assert cfg["unique_id"] == "solarsage_aqi"
    assert cfg["name"] == "Air quality"
    assert cfg["state_topic"] == "solarsage/widgets/aqi/state"
    assert cfg["json_attributes_topic"] == "solarsage/widgets/aqi/attributes"
    # HA needs the value template so the state field is scalar
    assert "value_template" in cfg
    assert "fetched_at" in cfg["value_template"]
    assert cfg["device"]["identifiers"] == ["solarsage"]


@pytest.mark.asyncio
async def test_publish_widget_calls_broker_and_registers_discovery():
    """publish_widget should emit the discovery config on first sight,
    then the state + attributes topics."""
    pub = M.MqttPublisher(broker="x")
    seen = []

    class _FakeClient:
        async def publish(self, topic, payload=None, retain=False):
            seen.append((topic, payload, retain))
    fake = _FakeClient()

    async def fake_client_or_none():
        return fake

    pub._client_or_none = fake_client_or_none

    w = _FakeWidget()
    state = {
        "fetched_at": 12345.0, "error": None,
        "data": {"current": {"us_aqi": 42}},
    }
    await pub.publish_widget(w, state)

    topics = [t for t, _, _ in seen]
    assert "homeassistant/sensor/solarsage_aqi/config" in topics
    assert "solarsage/widgets/aqi/state" in topics
    assert "solarsage/widgets/aqi/attributes" in topics

    # Second publish should skip discovery (already sent)
    seen.clear()
    await pub.publish_widget(w, state)
    topics = [t for t, _, _ in seen]
    assert "homeassistant/sensor/solarsage_aqi/config" not in topics
    assert "solarsage/widgets/aqi/state" in topics


@pytest.mark.asyncio
async def test_publish_widget_silent_when_no_client():
    """When the broker is unreachable, publish_widget must not raise."""
    pub = M.MqttPublisher(broker="x")
    async def none_client():
        return None
    pub._client_or_none = none_client
    # Should not raise
    await pub.publish_widget(_FakeWidget(), {"fetched_at": 1, "data": {}})
