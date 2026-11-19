"""Tests for the TP-Link Powerline binary sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.tplink_powerline.binary_sensor import (
    EthernetPortBinarySensor,
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
    sensor = TplinkPowerlineBinarySensor(coordinator, _make_entry())
    assert sensor.is_on is True


def test_binary_sensor_disconnected_when_unavailable() -> None:
    coordinator = _make_coordinator({"available": False})
    sensor = TplinkPowerlineBinarySensor(coordinator, _make_entry())
    assert sensor.is_on is False


def test_device_info_links_to_root_device() -> None:
    coordinator = _make_coordinator({"available": True})
    sensor = TplinkPowerlineBinarySensor(coordinator, _make_entry())
    assert sensor.device_info["identifiers"] == {(DOMAIN, "test_entry_id")}


# --- Remote adapter binary sensor tests (TS-12..15) ---


def test_remote_adapter_connected_when_rates_nonzero() -> None:
    """TS-12: Remote adapter connected when rates non-zero."""
    coordinator = _make_coordinator({
        "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 100, "rx_rate": 200}],
        "connected_count": 1,
    })
    sensor = RemoteAdapterBinarySensor(coordinator, _make_entry(), "58-04-4F-D8-20-2D")
    assert sensor.is_on is True


def test_remote_adapter_disconnected_when_rates_zero() -> None:
    """TS-13: Remote adapter disconnected when rates zero."""
    coordinator = _make_coordinator({
        "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 0, "rx_rate": 0}],
        "connected_count": 0,
    })
    sensor = RemoteAdapterBinarySensor(coordinator, _make_entry(), "58-04-4F-D8-20-2D")
    assert sensor.is_on is False


def test_remote_adapter_unavailable_when_mac_missing() -> None:
    """TS-14: Remote adapter unavailable when MAC missing from data."""
    coordinator = _make_coordinator({"adapters": [], "connected_count": 0})
    sensor = RemoteAdapterBinarySensor(coordinator, _make_entry(), "58-04-4F-D8-20-2D")
    assert sensor.is_on is None


def test_remote_adapter_device_has_via_device() -> None:
    """TS-15: Remote adapter device has via_device to root."""
    coordinator = _make_coordinator({
        "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 100, "rx_rate": 200}],
    })
    sensor = RemoteAdapterBinarySensor(coordinator, _make_entry(), "58-04-4F-D8-20-2D")
    di = sensor.device_info
    assert di["via_device"] == (DOMAIN, "test_entry_id")
    assert (DOMAIN, "58-04-4F-D8-20-2D") in di["identifiers"]
    assert "58-04-4F-D8-20-2D" in di["name"]


# --- Ethernet port tests (TS-20, TS-21) ---


def test_ethernet_port_connected_with_attributes() -> None:
    """TS-20: Ethernet port connected with speed/duplex attributes."""
    coordinator = _make_coordinator({
        "ethernet_ports": [
            {"port": 1, "connected": False, "speed": 0, "duplex": ""},
            {"port": 2, "connected": True, "speed": 1000, "duplex": "full"},
        ],
    })
    sensor = EthernetPortBinarySensor(coordinator, _make_entry(), 2, "Powerline Network")
    assert sensor.is_on is True
    attrs = sensor.extra_state_attributes
    assert attrs["speed"] == 1000
    assert attrs["duplex"] == "full"


def test_ethernet_port_disconnected() -> None:
    """TS-21: Ethernet port disconnected."""
    coordinator = _make_coordinator({
        "ethernet_ports": [
            {"port": 1, "connected": False, "speed": 0, "duplex": ""},
        ],
    })
    sensor = EthernetPortBinarySensor(coordinator, _make_entry(), 1, "Powerline Network")
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["speed"] == 0
