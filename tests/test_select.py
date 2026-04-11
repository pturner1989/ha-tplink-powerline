"""Tests for TP-Link Powerline select entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.tplink_powerline.select import (
    QosModeSelect,
    RebootCycleSelect,
    RebootMonthdaySelect,
    RebootWeekdaySelect,
)

SAMPLE_DATA = {
    "qos_mode": "Fair",
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


# TS-15: QoS select shows current mode
def test_qos_select_current() -> None:
    select = QosModeSelect(_make_coordinator(), AsyncMock(), _make_entry(), "192.168.1.34", "Powerline Network")
    assert select.current_option == "Fair"


# TS-16: QoS select writes command
async def test_qos_select_write() -> None:
    client = AsyncMock()
    coordinator = _make_coordinator()
    select = QosModeSelect(coordinator, client, _make_entry(), "192.168.1.34", "Powerline Network")

    await select.async_select_option("Gaming")

    client.send_command.assert_awaited_once_with("set qos 2")
    coordinator.async_request_refresh.assert_awaited_once()


# TS-17: Reboot cycle select
def test_reboot_cycle_select() -> None:
    select = RebootCycleSelect(_make_coordinator(), AsyncMock(), _make_entry(), "192.168.1.34", "Powerline Network")
    assert select.current_option == "Daily"


# Reboot weekday select — shows value when cycle is weekly
def test_reboot_weekday_shows_day_when_weekly() -> None:
    data = {**SAMPLE_DATA, "reboot_schedule": {**SAMPLE_DATA["reboot_schedule"], "repeat": "2", "weekday": 5}}
    select = RebootWeekdaySelect(_make_coordinator(data), AsyncMock(), _make_entry(), "192.168.1.34", "Powerline Network")
    assert select.current_option == "Friday"


# Reboot weekday select — unavailable when cycle is not weekly
def test_reboot_weekday_unavailable_when_daily() -> None:
    select = RebootWeekdaySelect(_make_coordinator(), AsyncMock(), _make_entry(), "192.168.1.34", "Powerline Network")
    assert select.current_option is None


# Reboot weekday writes correct key
async def test_reboot_weekday_write() -> None:
    client = AsyncMock()
    data = {**SAMPLE_DATA, "reboot_schedule": {**SAMPLE_DATA["reboot_schedule"], "repeat": "2", "weekday": 1}}
    coordinator = _make_coordinator(data)
    select = RebootWeekdaySelect(coordinator, client, _make_entry(), "192.168.1.34", "Powerline Network")

    await select.async_select_option("Wednesday")

    client.set_data.assert_awaited_once_with({"TPLINK.REBOOTSCHEDULE.WEEKDAY": "3"})


# Reboot monthday select — shows value when cycle is monthly
def test_reboot_monthday_shows_day_when_monthly() -> None:
    data = {**SAMPLE_DATA, "reboot_schedule": {**SAMPLE_DATA["reboot_schedule"], "repeat": "3", "monthday": 15}}
    select = RebootMonthdaySelect(_make_coordinator(data), AsyncMock(), _make_entry(), "192.168.1.34", "Powerline Network")
    assert select.current_option == "15"


# Reboot monthday select — unavailable when cycle is not monthly
def test_reboot_monthday_unavailable_when_daily() -> None:
    select = RebootMonthdaySelect(_make_coordinator(), AsyncMock(), _make_entry(), "192.168.1.34", "Powerline Network")
    assert select.current_option is None
