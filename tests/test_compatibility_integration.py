"""Integration tests for graceful compatibility."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.tplink_powerline.const import CONF_PASSWORD_HASH, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _make_config_entry(**kwargs) -> MockConfigEntry:
    data = {CONF_HOST: "192.168.1.34", CONF_NAME: "Powerline Network"}
    data.update(kwargs)
    return MockConfigEntry(domain=DOMAIN, data=data, unique_id="192.168.1.34")


def _mock_process(returncode: int) -> AsyncMock:
    proc = AsyncMock()
    proc.returncode = returncode
    proc.wait = AsyncMock()
    return proc


# ITS-01: Incompatible device config flow to ping-only results in only ping sensor
async def test_ping_only_entry_has_only_ping_sensor(hass: HomeAssistant) -> None:
    """Entry without password_hash (from incompatible flow) creates only ping sensor."""
    entry = _make_config_entry()  # no password_hash = ping-only
    entry.add_to_hass(hass)

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("binary_sensor.powerline_network") is not None
    assert hass.states.get("binary_sensor.powerline_network").state == "on"

    # No HTTP entities
    assert hass.states.get("sensor.powerline_network_model") is None
    assert hass.states.get("switch.powerline_network_led") is None
    assert hass.states.get("select.powerline_network_qos_mode") is None


# ITS-02: Partial feature support creates partial entities
async def test_partial_features_create_partial_entities(hass: HomeAssistant) -> None:
    """Device info works but network coordinator fails — only device info sensors appear."""
    entry = _make_config_entry(password_hash="e16b2ab8d12314bf4efbd6203906ea6c")
    entry.add_to_hass(hass)

    mock_client = AsyncMock()
    mock_client.get_device_info.return_value = {
        "model": "PG2400P", "firmware": "1.0.3", "hardware": "1.0",
    }
    mock_client.get_network_name.return_value = "MyPowerline"
    mock_client.get_network_data.side_effect = Exception("Not supported")

    with (
        patch("custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec", return_value=_mock_process(0)),
        patch("custom_components.tplink_powerline.PowerlineClient", return_value=mock_client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Ping works
    assert hass.states.get("binary_sensor.powerline_network").state == "on"

    # Device info sensors exist
    assert hass.states.get("sensor.powerline_network_model").state == "PG2400P"

    # No network/control entities (coordinator failed)
    assert hass.states.get("sensor.powerline_network_connected_adapters") is None
    assert hass.states.get("switch.powerline_network_led") is None
    assert hass.states.get("select.powerline_network_qos_mode") is None
