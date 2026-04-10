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
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: host, CONF_NAME: name}
    return entry


def _make_coordinator(data: dict | None = None) -> MagicMock:
    """Create a mock coordinator with given data."""
    coordinator = MagicMock()
    coordinator.data = data
    return coordinator


def test_binary_sensor_connected_when_available() -> None:
    """Test binary sensor shows connected when coordinator reports available."""
    coordinator = _make_coordinator({"available": True})
    entry = _make_entry()
    sensor = TplinkPowerlineBinarySensor(coordinator, entry)

    assert sensor.is_on is True


def test_binary_sensor_disconnected_when_unavailable() -> None:
    """Test binary sensor shows disconnected when coordinator reports unavailable."""
    coordinator = _make_coordinator({"available": False})
    entry = _make_entry()
    sensor = TplinkPowerlineBinarySensor(coordinator, entry)

    assert sensor.is_on is False


def test_device_info_is_correct() -> None:
    """Test device info contains correct manufacturer, model, and identifiers."""
    coordinator = _make_coordinator({"available": True})
    entry = _make_entry(host="192.168.1.34", name="Powerline Network")
    sensor = TplinkPowerlineBinarySensor(coordinator, entry)

    device_info = sensor.device_info
    assert device_info["manufacturer"] == "TP-Link"
    assert device_info["model"] == "Powerline Adapter"
    assert device_info["name"] == "Powerline Network"
    assert (DOMAIN, "192.168.1.34") in device_info["identifiers"]
