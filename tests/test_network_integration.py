"""Integration tests for powerline network monitoring."""

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
    client = AsyncMock()
    client.get_device_info.return_value = {
        "model": "PG2400P",
        "firmware": "1.0.3 Build 20221213 Rel.62540",
        "hardware": "1.0",
    }
    client.get_network_name.return_value = "MyPowerline"
    client.get_network_data.return_value = SAMPLE_NETWORK_DATA
    return client


# ITS-01: Full setup creates root and remote adapter devices with all sensors
async def test_full_setup_with_network_monitoring(hass: HomeAssistant) -> None:
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

    # Root device sensors
    assert hass.states.get("binary_sensor.powerline_network") is not None
    assert hass.states.get("binary_sensor.powerline_network").state == "on"
    assert hass.states.get("sensor.powerline_network_model").state == "PG2400P"
    assert hass.states.get("sensor.powerline_network_connected_adapters").state == "1"
    assert hass.states.get("sensor.powerline_network_network_name").state == "MyPowerline"

    # Remote adapter sensors
    assert hass.states.get("binary_sensor.powerline_58_04_4f_d8_20_2d") is not None
    tx = hass.states.get("sensor.powerline_58_04_4f_d8_20_2d_tx_rate")
    rx = hass.states.get("sensor.powerline_58_04_4f_d8_20_2d_rx_rate")
    assert tx is not None
    assert rx is not None
    assert int(tx.state) == 366
    assert int(rx.state) == 317


# ITS-02: Network coordinator updates sensor values
async def test_network_coordinator_updates_sensors(hass: HomeAssistant) -> None:
    entry = _make_config_entry(password_hash="cc03e747a6afbbcbf8be7668acfebee5")
    entry.add_to_hass(hass)
    mock_client = _mock_http_client()

    with (
        patch("custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec", return_value=_mock_process(0)),
        patch("custom_components.tplink_powerline.PowerlineClient", return_value=mock_client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Update with new rates
    mock_client.get_network_data.return_value = {
        "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 200, "rx_rate": 150}],
        "connected_count": 1,
        "root_mac": "B8-FB-B3-B6-DD-DF",
    }
    network_coordinator = hass.data[DOMAIN][entry.entry_id]["network_coordinator"]
    await network_coordinator.async_refresh()
    await hass.async_block_till_done()

    tx = hass.states.get("sensor.powerline_58_04_4f_d8_20_2d_tx_rate")
    assert int(tx.state) == 200


# ITS-03: No password means no network monitoring
async def test_no_password_no_network(hass: HomeAssistant) -> None:
    entry = _make_config_entry()  # no password
    entry.add_to_hass(hass)

    with patch("custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec", return_value=_mock_process(0)):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    # Root ping sensor exists
    assert hass.states.get("binary_sensor.powerline_network") is not None
    # No network sensors
    assert hass.states.get("sensor.powerline_network_connected_adapters") is None
    assert hass.states.get("sensor.powerline_network_network_name") is None
    assert hass.states.get("binary_sensor.powerline_58_04_4f_d8_20_2d") is None
