"""Tests for TP-Link Powerline integration setup and teardown."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.tplink_powerline.const import CONF_PASSWORD_HASH, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

SAMPLE_NETWORK_DATA = {
    "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 366, "rx_rate": 317}],
    "connected_count": 1,
    "root_mac": "B8-FB-B3-B6-DD-DF",
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
    """Create a mock HTTP client that returns valid device and network data."""
    client = AsyncMock()
    client.get_device_info.return_value = {
        "model": "PG2400P",
        "firmware": "1.0.3 Build 20221213 Rel.62540",
        "hardware": "1.0",
    }
    client.get_network_name.return_value = "MyPowerline"
    client.get_network_data.return_value = SAMPLE_NETWORK_DATA

    async def mock_get_data(keys):
        if "TPLINK.LEDSCHEDULE.LED_ENABLE" in keys:
            return {"TPLINK.LEDSCHEDULE.LED_ENABLE": "YES", "TPLINK.LEDSCHEDULE.ENABLE": "NO",
                    "TPLINK.LEDSCHEDULE.START_HOUR": "21", "TPLINK.LEDSCHEDULE.START_MINUTE": "0",
                    "TPLINK.LEDSCHEDULE.END_HOUR": "6", "TPLINK.LEDSCHEDULE.END_MINUTE": "0"}
        if "TPLINK.REBOOTSCHEDULE.ENABLE" in keys:
            return {"TPLINK.REBOOTSCHEDULE.ENABLE": "NO", "TPLINK.REBOOTSCHEDULE.HOUR": "0",
                    "TPLINK.REBOOTSCHEDULE.MINUTE": "0", "TPLINK.REBOOTSCHEDULE.REPEAT": "1",
                    "TPLINK.REBOOTSCHEDULE.WEEKDAY": "0", "TPLINK.REBOOTSCHEDULE.MONTHDAY": "1"}
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


# --- Core setup tests ---


async def test_setup_creates_coordinator(hass: HomeAssistant) -> None:
    entry = _make_config_entry()
    entry.add_to_hass(hass)
    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert "coordinator" in hass.data[DOMAIN][entry.entry_id]


async def test_setup_raises_config_entry_not_ready(hass: HomeAssistant) -> None:
    entry = _make_config_entry()
    entry.add_to_hass(hass)
    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(1),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_cleans_up(hass: HomeAssistant) -> None:
    entry = _make_config_entry()
    entry.add_to_hass(hass)
    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_full_setup_to_entity_state(hass: HomeAssistant) -> None:
    entry = _make_config_entry()
    entry.add_to_hass(hass)
    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.powerline_network")
    assert state is not None
    assert state.state == "on"


async def test_config_entry_not_ready_no_entities(hass: HomeAssistant) -> None:
    entry = _make_config_entry()
    entry.add_to_hass(hass)
    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(1),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.states.get("binary_sensor.powerline_network") is None


async def test_failure_threshold_causes_state_transition(hass: HomeAssistant) -> None:
    entry = _make_config_entry()
    entry.add_to_hass(hass)
    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.powerline_network")
    assert state.state == "on"
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.failure_count = 7
    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(1),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.powerline_network")
    assert state.state == "off"


# --- HTTP client tests ---


async def test_setup_with_password_fetches_device_info(hass: HomeAssistant) -> None:
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
    ed = hass.data[DOMAIN][entry.entry_id]
    assert ed["device_info"]["model"] == "PG2400P"
    mock_client.login.assert_awaited_once()


async def test_setup_with_password_http_fails_gracefully(hass: HomeAssistant) -> None:
    from custom_components.tplink_powerline.client import DeviceUnavailable
    entry = _make_config_entry(password_hash="cc03e747a6afbbcbf8be7668acfebee5")
    entry.add_to_hass(hass)
    mock_client = AsyncMock()
    mock_client.login.side_effect = DeviceUnavailable("Connection refused")
    with (
        patch("custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec", return_value=_mock_process(0)),
        patch("custom_components.tplink_powerline.PowerlineClient", return_value=mock_client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    ed = hass.data[DOMAIN][entry.entry_id]
    assert ed["device_info"] is None
    assert ed["client"] is None
    assert ed["network_coordinator"] is None


async def test_setup_without_password_skips_http(hass: HomeAssistant) -> None:
    entry = _make_config_entry()
    entry.add_to_hass(hass)
    with patch("custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec", return_value=_mock_process(0)):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    ed = hass.data[DOMAIN][entry.entry_id]
    assert ed["client"] is None
    assert ed["device_info"] is None
    assert ed["network_coordinator"] is None


async def test_unload_logs_out_http_client(hass: HomeAssistant) -> None:
    entry = _make_config_entry(password_hash="cc03e747a6afbbcbf8be7668acfebee5")
    entry.add_to_hass(hass)
    mock_client = _mock_http_client()
    with (
        patch("custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec", return_value=_mock_process(0)),
        patch("custom_components.tplink_powerline.PowerlineClient", return_value=mock_client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    mock_client.logout.assert_awaited_once()


# --- Network coordinator setup tests (TS-05, TS-06) ---


async def test_setup_creates_network_coordinator(hass: HomeAssistant) -> None:
    """TS-05: Setup with password creates network coordinator."""
    entry = _make_config_entry(password_hash="cc03e747a6afbbcbf8be7668acfebee5")
    entry.add_to_hass(hass)
    mock_client = _mock_http_client()
    with (
        patch("custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec", return_value=_mock_process(0)),
        patch("custom_components.tplink_powerline.PowerlineClient", return_value=mock_client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    ed = hass.data[DOMAIN][entry.entry_id]
    assert ed["network_coordinator"] is not None
    assert ed["network_coordinator"].data["adapters"] == SAMPLE_NETWORK_DATA["adapters"]
    assert ed["network_coordinator"].data["connected_count"] == 1
    assert ed["network_coordinator"].data["led"] is not None
    assert ed["network_coordinator"].data["qos_mode"] is not None
    assert ed["network_name"] == "MyPowerline"


async def test_setup_without_password_no_network_coordinator(hass: HomeAssistant) -> None:
    """TS-06: Setup without password has no network coordinator."""
    entry = _make_config_entry()
    entry.add_to_hass(hass)
    with patch("custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec", return_value=_mock_process(0)):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    ed = hass.data[DOMAIN][entry.entry_id]
    assert ed["network_coordinator"] is None
    assert ed["network_name"] is None
