"""Integration tests for device controls and status."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.tplink_powerline.const import CONF_PASSWORD_HASH, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

SAMPLE_FULL_DATA = {
    "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 366, "rx_rate": 317}],
    "connected_count": 1,
    "root_mac": "B8-FB-B3-B6-DD-DF",
    "led": {"enabled": True, "night_mode": True, "start_hour": 21, "start_minute": 0, "end_hour": 6, "end_minute": 0},
    "reboot_schedule": {"enabled": False, "hour": 3, "minute": 0, "repeat": "1", "weekday": 0, "monthday": 1},
    "qos_mode": "Fair",
    "ethernet_ports": [
        {"port": 1, "connected": False, "speed": 0, "duplex": ""},
        {"port": 2, "connected": True, "speed": 1000, "duplex": "full"},
    ],
}


def _make_config_entry(**kwargs) -> MockConfigEntry:
    data = {CONF_HOST: "192.168.1.34", CONF_NAME: "Powerline Network"}
    data.update(kwargs)
    return MockConfigEntry(domain=DOMAIN, data=data, unique_id="192.168.1.34")


def _mock_process(returncode: int) -> AsyncMock:
    proc = AsyncMock()
    proc.returncode = returncode
    proc.wait = AsyncMock()
    return proc


def _mock_http_client() -> AsyncMock:
    client = AsyncMock()
    client.get_device_info.return_value = {
        "model": "PG2400P", "firmware": "1.0.3", "hardware": "1.0",
    }
    client.get_network_name.return_value = "MyPowerline"
    client.get_network_data.return_value = {
        "adapters": SAMPLE_FULL_DATA["adapters"],
        "connected_count": 1,
        "root_mac": "B8-FB-B3-B6-DD-DF",
    }

    async def mock_get_data(keys):
        if "TPLINK.LEDSCHEDULE.LED_ENABLE" in keys:
            return {
                "TPLINK.LEDSCHEDULE.LED_ENABLE": "YES",
                "TPLINK.LEDSCHEDULE.ENABLE": "YES",
                "TPLINK.LEDSCHEDULE.START_HOUR": "21",
                "TPLINK.LEDSCHEDULE.START_MINUTE": "0",
                "TPLINK.LEDSCHEDULE.END_HOUR": "6",
                "TPLINK.LEDSCHEDULE.END_MINUTE": "0",
            }
        if "TPLINK.REBOOTSCHEDULE.ENABLE" in keys:
            return {
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
            return {"RESULT": "1"}
        if cmd == "lan link speed":
            return {"PORT1": "0", "PORT2": "6"}
        return {}

    client.send_command = AsyncMock(side_effect=mock_send_command)
    return client


# ITS-01: Full setup creates all control entities
async def test_full_setup_creates_all_controls(hass: HomeAssistant) -> None:
    entry = _make_config_entry(password_hash="cc03e747a6afbbcbf8be7668acfebee5")
    entry.add_to_hass(hass)
    mock_client = _mock_http_client()

    with (
        patch("custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec", return_value=_mock_process(0)),
        patch("custom_components.tplink_powerline.PowerlineClient", return_value=mock_client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Switches
    assert hass.states.get("switch.powerline_network_led") is not None
    assert hass.states.get("switch.powerline_network_led").state == "on"
    assert hass.states.get("switch.powerline_network_led_night_mode") is not None
    assert hass.states.get("switch.powerline_network_reboot_schedule") is not None

    # Button
    assert hass.states.get("button.powerline_network_reboot") is not None

    # Time
    assert hass.states.get("time.powerline_network_led_night_mode_start") is not None
    assert hass.states.get("time.powerline_network_led_night_mode_end") is not None
    assert hass.states.get("time.powerline_network_reboot_schedule_time") is not None

    # Select
    assert hass.states.get("select.powerline_network_qos_mode") is not None
    assert hass.states.get("select.powerline_network_qos_mode").state == "Fair"
    assert hass.states.get("select.powerline_network_reboot_cycle") is not None

    # Number
    assert hass.states.get("number.powerline_network_reboot_day") is not None

    # Ethernet ports
    assert hass.states.get("binary_sensor.powerline_network_ethernet_port_1") is not None
    assert hass.states.get("binary_sensor.powerline_network_ethernet_port_1").state == "off"
    assert hass.states.get("binary_sensor.powerline_network_ethernet_port_2") is not None
    assert hass.states.get("binary_sensor.powerline_network_ethernet_port_2").state == "on"


# ITS-02: No controls without password
async def test_no_controls_without_password(hass: HomeAssistant) -> None:
    entry = _make_config_entry()  # no password
    entry.add_to_hass(hass)

    with patch("custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec", return_value=_mock_process(0)):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    # Root ping works
    assert hass.states.get("binary_sensor.powerline_network") is not None

    # No controls
    assert hass.states.get("switch.powerline_network_led") is None
    assert hass.states.get("button.powerline_network_reboot") is None
    assert hass.states.get("select.powerline_network_qos_mode") is None
    assert hass.states.get("binary_sensor.powerline_network_ethernet_port_1") is None
