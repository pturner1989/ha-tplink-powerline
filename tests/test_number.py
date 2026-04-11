"""Tests for TP-Link Powerline number entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.tplink_powerline.number import RebootDayNumber


def _make_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {CONF_HOST: "192.168.1.34", CONF_NAME: "Powerline Network"}
    return entry


def _make_coordinator(data=None):
    c = MagicMock()
    c.data = data or {
        "reboot_schedule": {"enabled": False, "hour": 0, "minute": 0, "repeat": "2", "weekday": 5, "monthday": 1},
    }
    c.async_request_refresh = AsyncMock()
    return c


# TS-18: Reboot day reads from coordinator (weekly)
def test_reboot_day_weekly() -> None:
    entity = RebootDayNumber(_make_coordinator(), AsyncMock(), _make_entry())
    assert entity.native_value == 5.0


# TS-19: Reboot day writes correct key
async def test_reboot_day_write_weekly() -> None:
    client = AsyncMock()
    coordinator = _make_coordinator()
    entity = RebootDayNumber(coordinator, client, _make_entry())

    await entity.async_set_native_value(3.0)

    client.set_data.assert_awaited_once_with({"TPLINK.REBOOTSCHEDULE.WEEKDAY": "3"})
    coordinator.async_request_refresh.assert_awaited_once()
