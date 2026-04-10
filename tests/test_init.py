"""Tests for TP-Link Powerline integration setup and teardown."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.tplink_powerline.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _make_config_entry() -> MockConfigEntry:
    """Create a mock config entry for testing."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.34", CONF_NAME: "Powerline Network"},
        unique_id="192.168.1.34",
    )


def _mock_process(returncode: int) -> AsyncMock:
    """Create a mock subprocess with a given return code."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.wait = AsyncMock()
    return proc


# --- Unit tests (TS-13, TS-14, TS-15) ---


async def test_setup_creates_coordinator_and_forwards_platforms(
    hass: HomeAssistant,
) -> None:
    """Test that setup creates a coordinator and loads the binary sensor platform."""
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


async def test_setup_raises_config_entry_not_ready(
    hass: HomeAssistant,
) -> None:
    """Test that setup raises ConfigEntryNotReady when device is unreachable."""
    entry = _make_config_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(1),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_cleans_up_coordinator(
    hass: HomeAssistant,
) -> None:
    """Test that unloading removes the coordinator from hass.data."""
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


# --- Integration tests (ITS-01, ITS-02, ITS-03) ---


async def test_full_setup_to_entity_state(
    hass: HomeAssistant,
) -> None:
    """Test the full flow from setup to binary sensor showing connected."""
    entry = _make_config_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(f"binary_sensor.powerline_network")
    assert state is not None
    assert state.state == "on"


async def test_config_entry_not_ready_no_entities(
    hass: HomeAssistant,
) -> None:
    """Test that no entities are created when device is unreachable at setup."""
    entry = _make_config_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(1),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.states.get(f"binary_sensor.powerline_network") is None


async def test_failure_threshold_causes_state_transition(
    hass: HomeAssistant,
) -> None:
    """Test that reaching failure threshold transitions sensor to disconnected."""
    entry = _make_config_entry()
    entry.add_to_hass(hass)

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Verify initial state
    state = hass.states.get("binary_sensor.powerline_network")
    assert state is not None
    assert state.state == "on"

    # Simulate 8 consecutive failures by setting failure count and triggering update
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.failure_count = 7  # Next failure will be #8

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(1),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.powerline_network")
    assert state is not None
    assert state.state == "off"
