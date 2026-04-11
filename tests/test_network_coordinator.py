"""Tests for the TP-Link Powerline network coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.tplink_powerline.client import DeviceUnavailable
from custom_components.tplink_powerline.network_coordinator import NetworkCoordinator


def _make_client(
    network_data: dict | None = None,
    led_data: dict | None = None,
    reboot_data: dict | None = None,
    qos_result: dict | None = None,
    ethernet_result: dict | None = None,
    error: Exception | None = None,
) -> AsyncMock:
    client = AsyncMock()
    if error:
        client.get_network_data.side_effect = error
    else:
        client.get_network_data.return_value = network_data or {
            "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 366, "rx_rate": 317}],
            "connected_count": 1,
            "root_mac": "B8-FB-B3-B6-DD-DF",
        }

    # get_data returns different things depending on which keys are requested
    async def mock_get_data(keys):
        if "TPLINK.LEDSCHEDULE.LED_ENABLE" in keys:
            return led_data or {
                "TPLINK.LEDSCHEDULE.LED_ENABLE": "YES",
                "TPLINK.LEDSCHEDULE.ENABLE": "YES",
                "TPLINK.LEDSCHEDULE.START_HOUR": "21",
                "TPLINK.LEDSCHEDULE.START_MINUTE": "0",
                "TPLINK.LEDSCHEDULE.END_HOUR": "6",
                "TPLINK.LEDSCHEDULE.END_MINUTE": "0",
            }
        if "TPLINK.REBOOTSCHEDULE.ENABLE" in keys:
            return reboot_data or {
                "TPLINK.REBOOTSCHEDULE.ENABLE": "NO",
                "TPLINK.REBOOTSCHEDULE.HOUR": "3",
                "TPLINK.REBOOTSCHEDULE.MINUTE": "0",
                "TPLINK.REBOOTSCHEDULE.REPEAT": "1",
                "TPLINK.REBOOTSCHEDULE.WEEKDAY": "0",
                "TPLINK.REBOOTSCHEDULE.MONTHDAY": "1",
            }
        return {}

    client.get_data = AsyncMock(side_effect=mock_get_data)

    async def mock_send_command(cmd):
        if cmd == "get qos":
            return qos_result or {"RESULT": "1"}
        if cmd == "lan link speed":
            return ethernet_result or {"PORT1": "0", "PORT2": "6"}
        return {}

    client.send_command = AsyncMock(side_effect=mock_send_command)

    return client


# TS-05: Coordinator fetches all data sections
async def test_coordinator_fetches_all_sections(hass: HomeAssistant) -> None:
    client = _make_client()
    coordinator = NetworkCoordinator(hass, client)

    data = await coordinator._async_update_data()

    assert len(data["adapters"]) == 1
    assert data["connected_count"] == 1
    assert data["led"]["enabled"] is True
    assert data["led"]["night_mode"] is True
    assert data["led"]["start_hour"] == 21
    assert data["reboot_schedule"]["enabled"] is False
    assert data["reboot_schedule"]["hour"] == 3
    assert data["qos_mode"] == "Fair"
    assert len(data["ethernet_ports"]) == 2
    assert data["ethernet_ports"][0]["connected"] is False
    assert data["ethernet_ports"][1]["connected"] is True
    assert data["ethernet_ports"][1]["speed"] == 1000


# TS-06: Partial fetch failure doesn't break coordinator
async def test_partial_fetch_failure(hass: HomeAssistant) -> None:
    client = _make_client()
    # Make QoS command fail
    original_side_effect = client.send_command.side_effect

    async def failing_send_command(cmd):
        if cmd == "get qos":
            raise DeviceUnavailable("QoS not supported")
        return await original_side_effect(cmd)

    client.send_command = AsyncMock(side_effect=failing_send_command)

    coordinator = NetworkCoordinator(hass, client)
    data = await coordinator._async_update_data()

    assert data["qos_mode"] is None
    assert data["led"]["enabled"] is True
    assert len(data["ethernet_ports"]) == 2


# Original tests
async def test_successful_network_fetch(hass: HomeAssistant) -> None:
    client = _make_client()
    coordinator = NetworkCoordinator(hass, client)
    data = await coordinator._async_update_data()
    assert len(data["adapters"]) == 1
    assert data["connected_count"] == 1


async def test_network_fetch_failure(hass: HomeAssistant) -> None:
    client = _make_client(error=DeviceUnavailable("Connection refused"))
    coordinator = NetworkCoordinator(hass, client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


# TS-12: ValueError from parsing raises UpdateFailed
async def test_value_error_raises_update_failed(hass: HomeAssistant) -> None:
    client = _make_client(error=ValueError("invalid literal"))
    coordinator = NetworkCoordinator(hass, client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
