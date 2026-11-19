"""Tests for the reconfigure flow (changing an adapter's address)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.tplink_powerline.client import (
    AuthenticationError,
    DeviceUnavailable,
)
from custom_components.tplink_powerline.const import CONF_PASSWORD_HASH, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

OLD_HOST = "192.168.1.34"
NEW_HOST = "192.168.1.50"
ROOT_MAC = "b8:fb:b3:b6:dd:df"


def _client(mac: str = "B8-FB-B3-B6-DD-DF", login_error: Exception | None = None):
    client = AsyncMock()
    if login_error:
        client.login.side_effect = login_error
    client.get_device_info.return_value = {"model": "PG2400P", "mac": mac}
    return client, patch(
        "custom_components.tplink_powerline.config_flow.PowerlineClient",
        return_value=client,
    )


async def _loaded_entry(
    hass: HomeAssistant, *, unique_id: str, password: bool = True
) -> MockConfigEntry:
    data = {CONF_HOST: OLD_HOST, CONF_NAME: "Powerline"}
    if password:
        data[CONF_PASSWORD_HASH] = "e16b2ab8d12314bf4efbd6203906ea6c"
    entry = MockConfigEntry(
        domain=DOMAIN, data=data, unique_id=unique_id, minor_version=2, title="Powerline"
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _submit(hass: HomeAssistant, entry: MockConfigEntry, host: str):
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host}
    )
    await hass.async_block_till_done()
    return result


async def test_form_defaults_to_current_host(
    hass: HomeAssistant, mock_setup
) -> None:
    entry = await _loaded_entry(hass, unique_id=ROOT_MAC)
    result = await entry.start_reconfigure_flow(hass)
    schema_keys = {str(k): k for k in result["data_schema"].schema}
    assert schema_keys[CONF_HOST].default() == OLD_HOST
    assert result["description_placeholders"] == {"name": "Powerline"}


async def test_reconfigure_same_mac_updates_host_and_reloads(
    hass: HomeAssistant, mock_ping_success, mock_setup
) -> None:
    entry = await _loaded_entry(hass, unique_id=ROOT_MAC)
    client, client_patch = _client()
    with client_patch:
        result = await _submit(hass, entry, NEW_HOST)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == NEW_HOST
    assert entry.data[CONF_PASSWORD_HASH] == "e16b2ab8d12314bf4efbd6203906ea6c"
    assert entry.unique_id == ROOT_MAC
    assert mock_setup.call_count == 2  # initial setup + reload
    client.logout.assert_awaited_once()


async def test_reconfigure_strips_whitespace(
    hass: HomeAssistant, mock_ping_success, mock_setup
) -> None:
    entry = await _loaded_entry(hass, unique_id=ROOT_MAC)
    _, client_patch = _client()
    with client_patch:
        await _submit(hass, entry, f"  {NEW_HOST} ")
    assert entry.data[CONF_HOST] == NEW_HOST


async def test_reconfigure_different_mac_aborts_wrong_device(
    hass: HomeAssistant, mock_ping_success, mock_setup
) -> None:
    entry = await _loaded_entry(hass, unique_id=ROOT_MAC)
    _, client_patch = _client(mac="58-04-4F-D8-20-2D")
    with client_patch:
        result = await _submit(hass, entry, NEW_HOST)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_HOST] == OLD_HOST
    assert entry.unique_id == ROOT_MAC
    assert mock_setup.call_count == 1


async def test_reconfigure_unreadable_mac_shows_cannot_verify(
    hass: HomeAssistant, mock_ping_success, mock_setup
) -> None:
    entry = await _loaded_entry(hass, unique_id=ROOT_MAC)
    _, client_patch = _client(mac="")
    with client_patch:
        result = await _submit(hass, entry, NEW_HOST)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_verify"}
    assert entry.data[CONF_HOST] == OLD_HOST


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (AuthenticationError("bad password"), "invalid_auth"),
        (DeviceUnavailable("refused"), "cannot_connect"),
    ],
)
async def test_reconfigure_portal_errors(
    hass: HomeAssistant, mock_ping_success, mock_setup, error, expected
) -> None:
    entry = await _loaded_entry(hass, unique_id=ROOT_MAC)
    _, client_patch = _client(login_error=error)
    with client_patch:
        result = await _submit(hass, entry, NEW_HOST)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    assert entry.data[CONF_HOST] == OLD_HOST


async def test_reconfigure_unreachable_host(
    hass: HomeAssistant, mock_ping_failure, mock_setup
) -> None:
    entry = await _loaded_entry(hass, unique_id=ROOT_MAC)
    result = await _submit(hass, entry, NEW_HOST)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data[CONF_HOST] == OLD_HOST


async def test_reconfigure_recovers_after_error(
    hass: HomeAssistant, mock_setup
) -> None:
    entry = await _loaded_entry(hass, unique_id=ROOT_MAC)
    result = await entry.start_reconfigure_flow(hass)
    with patch(
        "custom_components.tplink_powerline.config_flow.async_ping",
        return_value=False,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "10.0.0.99"}
        )
    assert result["errors"] == {"base": "cannot_connect"}

    _, client_patch = _client()
    with client_patch, patch(
        "custom_components.tplink_powerline.config_flow.async_ping",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: NEW_HOST}
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == NEW_HOST


async def test_reconfigure_ping_only_updates_host_and_unique_id(
    hass: HomeAssistant, mock_ping_success, mock_setup
) -> None:
    entry = await _loaded_entry(hass, unique_id=OLD_HOST, password=False)
    with patch(
        "custom_components.tplink_powerline.config_flow.PowerlineClient"
    ) as client_cls:
        result = await _submit(hass, entry, NEW_HOST)

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == NEW_HOST
    assert entry.unique_id == NEW_HOST
    client_cls.assert_not_called()


async def test_reconfigure_entry_not_yet_keyed_by_mac(
    hass: HomeAssistant, mock_ping_success, mock_setup
) -> None:
    """An HTTP entry still keyed by host follows the host; setup adopts the MAC later."""
    entry = await _loaded_entry(hass, unique_id=OLD_HOST)
    _, client_patch = _client()
    with client_patch:
        result = await _submit(hass, entry, NEW_HOST)

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == NEW_HOST
    assert entry.unique_id == NEW_HOST


@pytest.mark.parametrize("other_uses", ["host", "unique_id"])
async def test_reconfigure_rejects_host_used_by_other_entry(
    hass: HomeAssistant, mock_ping_success, mock_setup, other_uses
) -> None:
    other = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: NEW_HOST if other_uses == "host" else "10.0.0.5", CONF_NAME: "Other"},
        unique_id="aa:bb:cc:dd:ee:ff" if other_uses == "host" else NEW_HOST,
    )
    other.add_to_hass(hass)
    entry = await _loaded_entry(hass, unique_id=OLD_HOST, password=False)

    result = await _submit(hass, entry, NEW_HOST)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "host_in_use"}
    assert entry.data[CONF_HOST] == OLD_HOST


async def test_reconfigure_same_host_is_allowed(
    hass: HomeAssistant, mock_ping_success, mock_setup
) -> None:
    """Re-submitting the current address just reloads the entry."""
    entry = await _loaded_entry(hass, unique_id=ROOT_MAC)
    _, client_patch = _client()
    with client_patch:
        result = await _submit(hass, entry, OLD_HOST)

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == OLD_HOST
