"""Tests for TP-Link Powerline time entities."""

from __future__ import annotations

from datetime import time as dt_time
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.tplink_powerline.time import (
    NightModeEndTime,
    NightModeStartTime,
    RebootScheduleTime,
)

SAMPLE_DATA = {
    "led": {"enabled": True, "night_mode": True, "start_hour": 21, "start_minute": 0, "end_hour": 6, "end_minute": 0},
    "reboot_schedule": {"enabled": False, "hour": 3, "minute": 0, "repeat": "1", "weekday": 0, "monthday": 1},
}


def _make_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {CONF_HOST: "192.168.1.34", CONF_NAME: "Powerline Network"}
    return entry


def _make_coordinator(data=None):
    c = MagicMock()
    c.data = data or SAMPLE_DATA
    c.async_request_refresh = AsyncMock()
    return c


# TS-12: Night mode start time reads from coordinator
def test_night_mode_start_time() -> None:
    coordinator = _make_coordinator()
    entity = NightModeStartTime(coordinator, AsyncMock(), _make_entry(), "Powerline Network")
    assert entity.native_value == dt_time(21, 0)


# TS-13: Night mode time writes to device
async def test_night_mode_start_time_write() -> None:
    client = AsyncMock()
    coordinator = _make_coordinator()
    entity = NightModeStartTime(coordinator, client, _make_entry(), "Powerline Network")

    await entity.async_set_value(dt_time(22, 30))

    client.set_data.assert_awaited_once_with({
        "TPLINK.LEDSCHEDULE.START_HOUR": "22",
        "TPLINK.LEDSCHEDULE.START_MINUTE": "30",
    })
    coordinator.async_request_refresh.assert_awaited_once()


# TS-14: Reboot schedule time
def test_reboot_schedule_time() -> None:
    coordinator = _make_coordinator()
    entity = RebootScheduleTime(coordinator, AsyncMock(), _make_entry(), "Powerline Network")
    assert entity.native_value == dt_time(3, 0)
