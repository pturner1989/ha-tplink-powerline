"""Tests for TP-Link Powerline integration setup and teardown."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.tplink_powerline.const import CONF_PASSWORD_HASH, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _make_config_entry(**kwargs) -> MockConfigEntry:
    """Create a mock config entry for testing."""
    data = {CONF_HOST: "192.168.1.34", CONF_NAME: "Powerline Network"}
    data.update(kwargs)
    return MockConfigEntry(
        domain=DOMAIN,
        data=data,
        unique_id="192.168.1.34",
    )


def _mock_process(returncode: int) -> AsyncMock:
    proc = AsyncMock()
    proc.returncode = returncode
    proc.wait = AsyncMock()
    return proc


# --- Existing tests (updated for new hass.data structure) ---


async def test_setup_creates_coordinator_and_forwards_platforms(
    hass: HomeAssistant,
) -> None:
    entry = _make_config_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.entry_id in hass.data[DOMAIN]
    assert "coordinator" in hass.data[DOMAIN][entry.entry_id]


async def test_setup_raises_config_entry_not_ready(
    hass: HomeAssistant,
) -> None:
    entry = _make_config_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(1),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_cleans_up(
    hass: HomeAssistant,
) -> None:
    entry = _make_config_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data[DOMAIN]


# --- Existing integration tests (updated) ---


async def test_full_setup_to_entity_state(
    hass: HomeAssistant,
) -> None:
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


async def test_config_entry_not_ready_no_entities(
    hass: HomeAssistant,
) -> None:
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


async def test_failure_threshold_causes_state_transition(
    hass: HomeAssistant,
) -> None:
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

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.failure_count = 7

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(1),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.powerline_network")
    assert state is not None
    assert state.state == "off"


# --- New tests for HTTP client integration (TS-04..07) ---


async def test_setup_with_password_fetches_device_info(
    hass: HomeAssistant,
) -> None:
    """TS-04: Setup with password fetches device info."""
    entry = _make_config_entry(password_hash="cc03e747a6afbbcbf8be7668acfebee5")
    entry.add_to_hass(hass)

    mock_client = AsyncMock()
    mock_client.get_device_info.return_value = {
        "model": "PG2400P",
        "firmware": "1.0.3 Build 20221213 Rel.62540",
        "hardware": "1.0",
    }

    with (
        patch(
            "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
            return_value=_mock_process(0),
        ),
        patch(
            "custom_components.tplink_powerline.PowerlineClient",
            return_value=mock_client,
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    assert device_info["model"] == "PG2400P"
    assert device_info["firmware"] == "1.0.3 Build 20221213 Rel.62540"
    assert device_info["hardware"] == "1.0"
    mock_client.login.assert_awaited_once()


async def test_setup_with_password_http_fails_gracefully(
    hass: HomeAssistant,
) -> None:
    """TS-05: Setup with password but HTTP fails falls back gracefully."""
    from custom_components.tplink_powerline.client import DeviceUnavailable

    entry = _make_config_entry(password_hash="cc03e747a6afbbcbf8be7668acfebee5")
    entry.add_to_hass(hass)

    mock_client = AsyncMock()
    mock_client.login.side_effect = DeviceUnavailable("Connection refused")

    with (
        patch(
            "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
            return_value=_mock_process(0),
        ),
        patch(
            "custom_components.tplink_powerline.PowerlineClient",
            return_value=mock_client,
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.data[DOMAIN][entry.entry_id]["device_info"] is None
    assert hass.data[DOMAIN][entry.entry_id]["client"] is None


async def test_setup_without_password_skips_http(
    hass: HomeAssistant,
) -> None:
    """TS-06: Setup without password skips HTTP entirely."""
    entry = _make_config_entry()  # no password_hash
    entry.add_to_hass(hass)

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.data[DOMAIN][entry.entry_id]["client"] is None
    assert hass.data[DOMAIN][entry.entry_id]["device_info"] is None


async def test_unload_logs_out_http_client(
    hass: HomeAssistant,
) -> None:
    """TS-07: Unload logs out HTTP client."""
    entry = _make_config_entry(password_hash="cc03e747a6afbbcbf8be7668acfebee5")
    entry.add_to_hass(hass)

    mock_client = AsyncMock()
    mock_client.get_device_info.return_value = {
        "model": "PG2400P",
        "firmware": "1.0.3",
        "hardware": "1.0",
    }

    with (
        patch(
            "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
            return_value=_mock_process(0),
        ),
        patch(
            "custom_components.tplink_powerline.PowerlineClient",
            return_value=mock_client,
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    mock_client.logout.assert_awaited_once()
