"""Tests for following an adapter to a new address via DHCP discovery."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_DHCP
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.loader import async_get_dhcp

from custom_components.tplink_powerline.const import CONF_PASSWORD_HASH, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

OLD_HOST = "192.168.1.34"
NEW_HOST = "192.168.1.50"
ROOT_MAC = "b8:fb:b3:b6:dd:df"


async def _loaded_entry(
    hass: HomeAssistant, *, host: str = OLD_HOST, unique_id: str = ROOT_MAC
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: host, CONF_NAME: "Powerline", CONF_PASSWORD_HASH: "abc"},
        unique_id=unique_id,
        minor_version=2,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _discover(hass: HomeAssistant, ip: str, mac: str = "b8fbb3b6dddf"):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DhcpServiceInfo(ip=ip, hostname="pg2400p", macaddress=mac),
    )
    await hass.async_block_till_done()
    return result


async def test_manifest_registers_dhcp_matcher_for_known_devices(
    hass: HomeAssistant,
) -> None:
    matchers = await async_get_dhcp(hass)
    assert {"domain": DOMAIN, "registered_devices": True} in matchers


async def test_known_mac_at_new_ip_updates_host_and_reloads(
    hass: HomeAssistant, mock_setup
) -> None:
    entry = await _loaded_entry(hass)

    result = await _discover(hass, NEW_HOST)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == NEW_HOST
    assert entry.data[CONF_PASSWORD_HASH] == "abc"
    assert mock_setup.call_count == 2  # initial setup + reload


async def test_known_mac_at_same_ip_does_not_reload(
    hass: HomeAssistant, mock_setup
) -> None:
    entry = await _loaded_entry(hass)

    result = await _discover(hass, OLD_HOST)

    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == OLD_HOST
    assert mock_setup.call_count == 1


async def test_hostname_configured_entry_is_not_overwritten(
    hass: HomeAssistant, mock_setup
) -> None:
    entry = await _loaded_entry(hass, host="powerline.lan")

    result = await _discover(hass, NEW_HOST)

    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "powerline.lan"
    assert mock_setup.call_count == 1


async def test_ipv6_configured_entry_is_updated(hass: HomeAssistant, mock_setup) -> None:
    entry = await _loaded_entry(hass, host="fd00::34")
    await _discover(hass, NEW_HOST)
    assert entry.data[CONF_HOST] == NEW_HOST


async def test_unknown_mac_is_not_offered(hass: HomeAssistant, mock_setup) -> None:
    entry = await _loaded_entry(hass)

    result = await _discover(hass, NEW_HOST, mac="58044fd8202d")

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"
    assert entry.data[CONF_HOST] == OLD_HOST
    assert not hass.config_entries.flow.async_progress()


async def test_entry_still_keyed_by_host_is_not_matched(
    hass: HomeAssistant, mock_setup
) -> None:
    """Ping-only and not-yet-migrated entries have no MAC to match."""
    entry = await _loaded_entry(hass, unique_id=OLD_HOST)

    result = await _discover(hass, NEW_HOST)

    assert result["reason"] == "not_supported"
    assert entry.data[CONF_HOST] == OLD_HOST


async def test_invalid_mac_is_rejected(hass: HomeAssistant, mock_setup) -> None:
    result = await _discover(hass, NEW_HOST, mac="")
    assert result["reason"] == "not_supported"
