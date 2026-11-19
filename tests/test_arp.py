"""Tests for resolving the adapter MAC from the ARP table (no password needed)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from custom_components.tplink_powerline.client import IncompatibleDevice
from custom_components.tplink_powerline.const import CONF_PASSWORD_HASH, DOMAIN
from custom_components.tplink_powerline.device import async_mac_from_arp

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_init import _mock_http_client, _mock_process

OLD_HOST = "192.168.1.34"
NEW_HOST = "192.168.1.50"
ROOT_MAC = "b8:fb:b3:b6:dd:df"
OTHER_MAC = "58:04:4f:d8:20:2d"


# --- Lookup helper ---


@pytest.mark.parametrize(
    ("host", "kwarg"),
    [("192.168.1.34", "ip"), ("fd00::34", "ip6"), ("powerline.lan", "hostname")],
)
async def test_lookup_passes_host_kind(
    hass: HomeAssistant, mock_arp: MagicMock, host: str, kwarg: str
) -> None:
    mock_arp.return_value = "B8:FB:B3:B6:DD:DF"
    assert await async_mac_from_arp(hass, host) == ROOT_MAC
    mock_arp.assert_called_once_with(**{kwarg: host})


@pytest.mark.parametrize("raw", [None, "", "00:00:00:00:00:00", "garbage"])
async def test_lookup_rejects_missing_or_invalid(
    hass: HomeAssistant, mock_arp: MagicMock, raw
) -> None:
    mock_arp.return_value = raw
    assert await async_mac_from_arp(hass, OLD_HOST) is None


async def test_lookup_swallows_errors(hass: HomeAssistant, mock_arp: MagicMock) -> None:
    mock_arp.side_effect = OSError("no arp table")
    assert await async_mac_from_arp(hass, OLD_HOST) is None


# --- Setup ---


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, client=None) -> None:
    with (
        patch(
            "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
            return_value=_mock_process(0),
        ),
        patch(
            "custom_components.tplink_powerline.PowerlineClient",
            return_value=client or _mock_http_client(),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def _entry(hass: HomeAssistant, *, unique_id: str = OLD_HOST, password: bool = False, host: str = OLD_HOST) -> MockConfigEntry:
    data = {CONF_HOST: host, CONF_NAME: "Powerline"}
    if password:
        data[CONF_PASSWORD_HASH] = "e16b2ab8d12314bf4efbd6203906ea6c"
    entry = MockConfigEntry(domain=DOMAIN, data=data, unique_id=unique_id, minor_version=2, title="Powerline")
    entry.add_to_hass(hass)
    return entry


async def test_ping_only_setup_uses_arp_mac(hass: HomeAssistant, mock_arp: MagicMock) -> None:
    mock_arp.return_value = "b8:fb:b3:b6:dd:df"
    entry = _entry(hass)

    await _setup(hass, entry)

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert (dr.CONNECTION_NETWORK_MAC, ROOT_MAC) in device.connections
    assert entry.unique_id == ROOT_MAC


async def test_http_setup_prefers_portal_mac(hass: HomeAssistant, mock_arp: MagicMock) -> None:
    entry = _entry(hass, password=True)
    await _setup(hass, entry)
    assert entry.unique_id == ROOT_MAC
    mock_arp.assert_not_called()


async def test_http_setup_falls_back_to_arp(hass: HomeAssistant, mock_arp: MagicMock) -> None:
    mock_arp.return_value = "b8:fb:b3:b6:dd:df"
    client = _mock_http_client()
    client.get_device_info.return_value = {"model": "PG2400P", "firmware": "1", "hardware": "1", "mac": ""}
    entry = _entry(hass, password=True)

    await _setup(hass, entry, client)

    assert entry.unique_id == ROOT_MAC


# --- User flow ---


async def _user_flow(hass: HomeAssistant, host: str, password: str = ""):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host, CONF_NAME: "Powerline", CONF_PASSWORD: password}
    )


async def test_user_flow_ping_only_uses_arp_mac(
    hass: HomeAssistant, mock_ping_success, mock_arp: MagicMock
) -> None:
    mock_arp.return_value = "b8:fb:b3:b6:dd:df"
    result = await _user_flow(hass, OLD_HOST)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == ROOT_MAC


async def test_user_flow_ping_only_known_mac_updates_existing(
    hass: HomeAssistant, mock_ping_success, mock_arp: MagicMock, mock_setup
) -> None:
    mock_arp.return_value = "b8:fb:b3:b6:dd:df"
    existing = _entry(hass, unique_id=ROOT_MAC)

    result = await _user_flow(hass, NEW_HOST)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert existing.data[CONF_HOST] == NEW_HOST


async def test_incompatible_portal_uses_arp_mac(
    hass: HomeAssistant, mock_ping_success, mock_arp: MagicMock
) -> None:
    mock_arp.return_value = "b8:fb:b3:b6:dd:df"
    client = AsyncMock()
    client.login.side_effect = IncompatibleDevice("old firmware")
    with patch("custom_components.tplink_powerline.config_flow.PowerlineClient", return_value=client):
        result = await _user_flow(hass, OLD_HOST, password="secret")
    assert result["step_id"] == "confirm_ping_only"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == ROOT_MAC


async def test_user_flow_http_does_not_query_arp(
    hass: HomeAssistant, mock_ping_success, mock_arp: MagicMock, mock_setup
) -> None:
    client = AsyncMock()
    client.get_device_info.return_value = {"mac": "B8-FB-B3-B6-DD-DF"}
    with patch("custom_components.tplink_powerline.config_flow.PowerlineClient", return_value=client):
        result = await _user_flow(hass, OLD_HOST, password="secret")
    assert result["result"].unique_id == ROOT_MAC
    mock_arp.assert_not_called()


# --- Reconfigure ---


async def _reconfigure(hass: HomeAssistant, entry: MockConfigEntry, host: str):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: host})
    await hass.async_block_till_done()
    return result


async def test_reconfigure_ping_only_same_arp_mac(
    hass: HomeAssistant, mock_ping_success, mock_arp: MagicMock, mock_setup
) -> None:
    mock_arp.return_value = "b8:fb:b3:b6:dd:df"
    entry = _entry(hass, unique_id=ROOT_MAC)
    result = await _reconfigure(hass, entry, NEW_HOST)
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == NEW_HOST
    assert entry.unique_id == ROOT_MAC


async def test_reconfigure_ping_only_different_arp_mac(
    hass: HomeAssistant, mock_ping_success, mock_arp: MagicMock, mock_setup
) -> None:
    mock_arp.return_value = OTHER_MAC
    entry = _entry(hass, unique_id=ROOT_MAC)
    result = await _reconfigure(hass, entry, NEW_HOST)
    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_HOST] == OLD_HOST


async def test_reconfigure_ping_only_arp_unavailable_trusts_user(
    hass: HomeAssistant, mock_ping_success, mock_setup
) -> None:
    entry = _entry(hass, unique_id=ROOT_MAC)
    result = await _reconfigure(hass, entry, NEW_HOST)
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == NEW_HOST
    assert entry.unique_id == ROOT_MAC


async def test_reconfigure_http_portal_mac_missing_uses_arp(
    hass: HomeAssistant, mock_ping_success, mock_arp: MagicMock, mock_setup
) -> None:
    mock_arp.return_value = "b8:fb:b3:b6:dd:df"
    client = AsyncMock()
    client.get_device_info.return_value = {"mac": ""}
    entry = _entry(hass, unique_id=ROOT_MAC, password=True)
    with patch("custom_components.tplink_powerline.config_flow.PowerlineClient", return_value=client):
        result = await _reconfigure(hass, entry, NEW_HOST)
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == NEW_HOST


# --- DHCP for ping-only entries ---


async def test_dhcp_follows_ping_only_entry_keyed_by_arp_mac(
    hass: HomeAssistant, mock_setup
) -> None:
    entry = _entry(hass, unique_id=ROOT_MAC)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DhcpServiceInfo(ip=NEW_HOST, hostname="pg2400p", macaddress="b8fbb3b6dddf"),
    )
    await hass.async_block_till_done()

    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == NEW_HOST
