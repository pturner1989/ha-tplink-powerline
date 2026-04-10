"""Tests for the TP-Link Powerline binary sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.tplink_powerline.binary_sensor import (
    RemoteAdapterBinarySensor,
    TplinkPowerlineBinarySensor,
)
from custom_components.tplink_powerline.const import DOMAIN


def _make_entry(host: str = "192.168.1.34", name: str = "Powerline Network") -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: host, CONF_NAME: name}
    return entry


def _make_coordinator(data: dict | None = None) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = data
    return coordinator


# --- Root binary sensor tests ---


def test_binary_sensor_connected_when_available() -> None:
    coordinator = _make_coordinator({"available": True})
    sensor = TplinkPowerlineBinarySensor(coordinator, _make_entry(), None)
    assert sensor.is_on is True


def test_binary_sensor_disconnected_when_unavailable() -> None:
    coordinator = _make_coordinator({"available": False})
    sensor = TplinkPowerlineBinarySensor(coordinator, _make_entry(), None)
    assert sensor.is_on is False


def test_device_info_is_correct() -> None:
    coordinator = _make_coordinator({"available": True})
    sensor = TplinkPowerlineBinarySensor(coordinator, _make_entry(), None)
    di = sensor.device_info
    assert di["manufacturer"] == "TP-Link"
    assert di["model"] == "Powerline Adapter"
    assert (DOMAIN, "192.168.1.34") in di["identifiers"]


def test_device_info_from_http() -> None:
    coordinator = _make_coordinator({"available": True})
    http_info = {"model": "PG2400P", "firmware": "1.0.3", "hardware": "1.0"}
    sensor = TplinkPowerlineBinarySensor(coordinator, _make_entry(), http_info)
    di = sensor.device_info
    assert di["model"] == "PG2400P"
    assert di["sw_version"] == "1.0.3"
    assert di["hw_version"] == "1.0"


def test_device_info_fallback_when_http_unavailable() -> None:
    coordinator = _make_coordinator({"available": True})
    sensor = TplinkPowerlineBinarySensor(coordinator, _make_entry(), None)
    di = sensor.device_info
    assert di["model"] == "Powerline Adapter"
    assert "sw_version" not in di


# --- Remote adapter binary sensor tests (TS-12..15) ---


def test_remote_adapter_connected_when_rates_nonzero() -> None:
    """TS-12: Remote adapter connected when rates non-zero."""
    coordinator = _make_coordinator({
        "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 100, "rx_rate": 200}],
        "connected_count": 1,
    })
    sensor = RemoteAdapterBinarySensor(coordinator, _make_entry(), "58-04-4F-D8-20-2D", "192.168.1.34")
    assert sensor.is_on is True


def test_remote_adapter_disconnected_when_rates_zero() -> None:
    """TS-13: Remote adapter disconnected when rates zero."""
    coordinator = _make_coordinator({
        "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 0, "rx_rate": 0}],
        "connected_count": 0,
    })
    sensor = RemoteAdapterBinarySensor(coordinator, _make_entry(), "58-04-4F-D8-20-2D", "192.168.1.34")
    assert sensor.is_on is False


def test_remote_adapter_unavailable_when_mac_missing() -> None:
    """TS-14: Remote adapter unavailable when MAC missing from data."""
    coordinator = _make_coordinator({"adapters": [], "connected_count": 0})
    sensor = RemoteAdapterBinarySensor(coordinator, _make_entry(), "58-04-4F-D8-20-2D", "192.168.1.34")
    assert sensor.is_on is None


def test_remote_adapter_device_has_via_device() -> None:
    """TS-15: Remote adapter device has via_device to root."""
    coordinator = _make_coordinator({
        "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 100, "rx_rate": 200}],
    })
    sensor = RemoteAdapterBinarySensor(coordinator, _make_entry(), "58-04-4F-D8-20-2D", "192.168.1.34")
    di = sensor.device_info
    assert di["via_device"] == (DOMAIN, "192.168.1.34")
    assert (DOMAIN, "58-04-4F-D8-20-2D") in di["identifiers"]
    assert "58-04-4F-D8-20-2D" in di["name"]
