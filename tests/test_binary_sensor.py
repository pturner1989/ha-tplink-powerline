"""Tests for the TP-Link Powerline binary sensor."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.tplink_powerline.binary_sensor import (
    TplinkPowerlineBinarySensor,
)
from custom_components.tplink_powerline.const import DOMAIN


def _make_entry(
    host: str = "192.168.1.34", name: str = "Powerline Network"
) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: host, CONF_NAME: name}
    return entry


def _make_coordinator(data: dict | None = None) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = data
    return coordinator


def test_binary_sensor_connected_when_available() -> None:
    coordinator = _make_coordinator({"available": True})
    entry = _make_entry()
    sensor = TplinkPowerlineBinarySensor(coordinator, entry, None)
    assert sensor.is_on is True


def test_binary_sensor_disconnected_when_unavailable() -> None:
    coordinator = _make_coordinator({"available": False})
    entry = _make_entry()
    sensor = TplinkPowerlineBinarySensor(coordinator, entry, None)
    assert sensor.is_on is False


def test_device_info_is_correct() -> None:
    coordinator = _make_coordinator({"available": True})
    entry = _make_entry(host="192.168.1.34", name="Powerline Network")
    sensor = TplinkPowerlineBinarySensor(coordinator, entry, None)

    device_info = sensor.device_info
    assert device_info["manufacturer"] == "TP-Link"
    assert device_info["model"] == "Powerline Adapter"
    assert device_info["name"] == "Powerline Network"
    assert (DOMAIN, "192.168.1.34") in device_info["identifiers"]


# --- New tests for HTTP-sourced device info (TS-08, TS-09) ---


def test_device_info_from_http() -> None:
    """TS-08: Device info populated from HTTP data."""
    coordinator = _make_coordinator({"available": True})
    entry = _make_entry()
    http_info = {
        "model": "PG2400P",
        "firmware": "1.0.3 Build 20221213 Rel.62540",
        "hardware": "1.0",
    }
    sensor = TplinkPowerlineBinarySensor(coordinator, entry, http_info)

    di = sensor.device_info
    assert di["model"] == "PG2400P"
    assert di["sw_version"] == "1.0.3 Build 20221213 Rel.62540"
    assert di["hw_version"] == "1.0"
    assert di["manufacturer"] == "TP-Link"


def test_device_info_fallback_when_http_unavailable() -> None:
    """TS-09: Device info falls back when HTTP unavailable."""
    coordinator = _make_coordinator({"available": True})
    entry = _make_entry()
    sensor = TplinkPowerlineBinarySensor(coordinator, entry, None)

    di = sensor.device_info
    assert di["model"] == "Powerline Adapter"
    assert "sw_version" not in di
    assert "hw_version" not in di
