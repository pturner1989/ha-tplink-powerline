"""Tests for the TP-Link Powerline diagnostic sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import CONF_HOST, CONF_NAME, EntityCategory

from custom_components.tplink_powerline.const import DOMAIN
from custom_components.tplink_powerline.sensor import (
    SENSOR_DESCRIPTIONS,
    TplinkPowerlineSensor,
)


def _make_entry(
    host: str = "192.168.1.34", name: str = "Powerline Network"
) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: host, CONF_NAME: name}
    return entry


SAMPLE_DEVICE_INFO = {
    "model": "PG2400P",
    "firmware": "1.0.3 Build 20221213 Rel.62540",
    "hardware": "1.0",
}


# TS-19: Sensors created with correct values
def test_sensors_have_correct_values() -> None:
    entry = _make_entry()
    for desc in SENSOR_DESCRIPTIONS:
        sensor = TplinkPowerlineSensor(entry, SAMPLE_DEVICE_INFO, desc)
        assert sensor.native_value == SAMPLE_DEVICE_INFO[desc["key"]]
        assert sensor.entity_category is EntityCategory.DIAGNOSTIC


# TS-20: No sensors created when device_info is None is handled by async_setup_entry
# (tested in integration tests)


# TS-21: Sensors share device with binary sensor
def test_sensors_share_device_identifiers() -> None:
    entry = _make_entry()
    for desc in SENSOR_DESCRIPTIONS:
        sensor = TplinkPowerlineSensor(entry, SAMPLE_DEVICE_INFO, desc)
        di = sensor.device_info
        assert (DOMAIN, "192.168.1.34") in di["identifiers"]
