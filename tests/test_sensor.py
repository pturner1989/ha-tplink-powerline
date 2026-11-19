"""Tests for the TP-Link Powerline sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import CONF_HOST, CONF_NAME, EntityCategory, UnitOfDataRate

from custom_components.tplink_powerline.const import DOMAIN
from custom_components.tplink_powerline.sensor import (
    STATIC_SENSOR_DESCRIPTIONS,
    AdapterRateSensor,
    ConnectedCountSensor,
    NetworkNameSensor,
    StaticDiagnosticSensor,
)


def _make_entry(host: str = "192.168.1.34", name: str = "Powerline Network") -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: host, CONF_NAME: name}
    return entry


def _make_coordinator(data: dict | None = None) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = data
    return coordinator


SAMPLE_DEVICE_INFO = {
    "model": "PG2400P",
    "firmware": "1.0.3 Build 20221213 Rel.62540",
    "hardware": "1.0",
}

SAMPLE_NETWORK_DATA = {
    "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 366, "rx_rate": 317}],
    "connected_count": 1,
    "root_mac": "B8-FB-B3-B6-DD-DF",
}


# --- Static sensor tests ---


def test_static_sensors_have_correct_values() -> None:
    entry = _make_entry()
    for desc in STATIC_SENSOR_DESCRIPTIONS:
        sensor = StaticDiagnosticSensor(entry, SAMPLE_DEVICE_INFO, desc)
        assert sensor.native_value == SAMPLE_DEVICE_INFO[desc["key"]]
        assert sensor.entity_category is EntityCategory.DIAGNOSTIC


def test_static_sensors_share_device_identifiers() -> None:
    entry = _make_entry()
    for desc in STATIC_SENSOR_DESCRIPTIONS:
        sensor = StaticDiagnosticSensor(entry, SAMPLE_DEVICE_INFO, desc)
        assert (DOMAIN, "test_entry_id") in sensor.device_info["identifiers"]


# --- Rate sensor tests (TS-07) ---


def test_rate_sensors_show_converted_values() -> None:
    """TS-07: TX/RX rate sensors show converted values."""
    coordinator = _make_coordinator(SAMPLE_NETWORK_DATA)
    entry = _make_entry()
    tx = AdapterRateSensor(coordinator, entry, "58-04-4F-D8-20-2D", "tx_rate", "TX Rate", "mdi:upload-network")
    rx = AdapterRateSensor(coordinator, entry, "58-04-4F-D8-20-2D", "rx_rate", "RX Rate", "mdi:download-network")
    assert tx.native_value == 366
    assert rx.native_value == 317
    assert tx.native_unit_of_measurement == UnitOfDataRate.MEGABITS_PER_SECOND


# --- Connected count sensor test (TS-08) ---


def test_connected_count_sensor() -> None:
    """TS-08: Connected count sensor reflects adapter count."""
    coordinator = _make_coordinator(SAMPLE_NETWORK_DATA)
    entry = _make_entry()
    sensor = ConnectedCountSensor(coordinator, entry, "Powerline Network")
    assert sensor.native_value == 1


# --- Network name sensor test (TS-09) ---


def test_network_name_sensor() -> None:
    """TS-09: Network name sensor shows name."""
    entry = _make_entry()
    sensor = NetworkNameSensor(entry, "MyPowerline")
    assert sensor.native_value == "MyPowerline"
    assert sensor.entity_category is EntityCategory.DIAGNOSTIC


# --- Remote adapter device linking (TS-10) ---


def test_remote_adapter_sensor_has_via_device() -> None:
    """TS-10: Remote adapter sensors have via_device to root."""
    coordinator = _make_coordinator(SAMPLE_NETWORK_DATA)
    entry = _make_entry()
    sensor = AdapterRateSensor(coordinator, entry, "58-04-4F-D8-20-2D", "tx_rate", "TX Rate", "mdi:upload-network")
    di = sensor.device_info
    assert di["via_device"] == (DOMAIN, "test_entry_id")
    assert (DOMAIN, "58-04-4F-D8-20-2D") in di["identifiers"]


# --- No network sensors without HTTP (TS-11) ---
# Tested via integration tests (async_setup_entry with no network_coordinator)
