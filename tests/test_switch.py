"""Tests for TP-Link Powerline switch entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.tplink_powerline.const import DOMAIN
from custom_components.tplink_powerline.switch import LedSwitch, NightModeSwitch, RebootScheduleSwitch


SAMPLE_DATA = {
    "led": {"enabled": True, "night_mode": True, "start_hour": 21, "start_minute": 0, "end_hour": 6, "end_minute": 0},
    "reboot_schedule": {"enabled": False, "hour": 0, "minute": 0, "repeat": "1", "weekday": 0, "monthday": 1},
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


# TS-07: LED switch reflects state
def test_led_switch_state() -> None:
    coordinator = _make_coordinator()
    switch = LedSwitch(coordinator, AsyncMock(), _make_entry(), "Powerline Network")
    assert switch.is_on is True


# TS-08: LED switch writes on toggle
async def test_led_switch_toggle() -> None:
    client = AsyncMock()
    coordinator = _make_coordinator()
    switch = LedSwitch(coordinator, client, _make_entry(), "Powerline Network")

    await switch.async_turn_off()

    client.set_data.assert_awaited_once_with({"TPLINK.LEDSCHEDULE.LED_ENABLE": "NO"})
    coordinator.async_request_refresh.assert_awaited_once()


# TS-09: Night mode switch
async def test_night_mode_switch() -> None:
    client = AsyncMock()
    coordinator = _make_coordinator()
    switch = NightModeSwitch(coordinator, client, _make_entry(), "Powerline Network")
    assert switch.is_on is True

    await switch.async_turn_off()
    client.set_data.assert_awaited_once_with({"TPLINK.LEDSCHEDULE.ENABLE": "NO"})


# TS-10: Reboot schedule switch
async def test_reboot_schedule_switch() -> None:
    client = AsyncMock()
    coordinator = _make_coordinator()
    switch = RebootScheduleSwitch(coordinator, client, _make_entry(), "Powerline Network")
    assert switch.is_on is False

    await switch.async_turn_on()
    client.set_data.assert_awaited_once_with({"TPLINK.REBOOTSCHEDULE.ENABLE": "YES"})
