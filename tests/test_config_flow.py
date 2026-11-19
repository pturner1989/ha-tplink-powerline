"""Tests for the TP-Link Powerline config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.tplink_powerline.const import CONF_PASSWORD_HASH, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_successful_config_flow(
    hass: HomeAssistant, mock_ping_success
) -> None:
    """Test a successful config flow creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.34", CONF_NAME: "My Powerline"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Powerline"
    assert result["data"] == {CONF_HOST: "192.168.1.34", CONF_NAME: "My Powerline"}


async def test_config_flow_rejects_unreachable_host(
    hass: HomeAssistant, mock_ping_failure
) -> None:
    """Test config flow shows error for unreachable device."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.99", CONF_NAME: "Unreachable"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_rejects_duplicate_host(
    hass: HomeAssistant, mock_ping_success
) -> None:
    """Test config flow aborts when host is already configured."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.34", CONF_NAME: "Powerline Network"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.34", CONF_NAME: "Duplicate"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_config_flow_default_name(
    hass: HomeAssistant, mock_ping_success
) -> None:
    """Test config flow uses default name when not overridden."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.34"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Powerline Network"


# --- New tests for password/HTTP ---


async def test_config_flow_with_valid_password(
    hass: HomeAssistant, mock_ping_success
) -> None:
    """Test config flow with valid password stores MD5 hash."""
    with patch(
        "custom_components.tplink_powerline.config_flow.PowerlineClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.34",
                CONF_NAME: "Powerline",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PASSWORD_HASH] == "e16b2ab8d12314bf4efbd6203906ea6c"
    mock_client.login.assert_awaited_once()
    mock_client.logout.assert_awaited_once()


async def test_config_flow_with_wrong_password(
    hass: HomeAssistant, mock_ping_success
) -> None:
    """Test config flow shows invalid_auth for wrong password."""
    from custom_components.tplink_powerline.client import AuthenticationError

    with patch(
        "custom_components.tplink_powerline.config_flow.PowerlineClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.login.side_effect = AuthenticationError("Wrong password")
        mock_client_cls.return_value = mock_client

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.34",
                CONF_NAME: "Powerline",
                CONF_PASSWORD: "wrongpass",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_without_password(
    hass: HomeAssistant, mock_ping_success
) -> None:
    """Test config flow without password creates entry without password_hash."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "192.168.1.34",
            CONF_NAME: "Powerline",
            CONF_PASSWORD: "",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_PASSWORD_HASH not in result["data"]


# --- Compatibility tests ---


async def test_incompatible_device_triggers_confirm_step(
    hass: HomeAssistant, mock_ping_success
) -> None:
    """TS-07: Incompatible device triggers confirm_ping_only step."""
    from custom_components.tplink_powerline.client import IncompatibleDevice

    with patch(
        "custom_components.tplink_powerline.config_flow.PowerlineClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.login.side_effect = IncompatibleDevice("HTML response")
        mock_client_cls.return_value = mock_client

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.34",
                CONF_NAME: "Powerline",
                CONF_PASSWORD: "somepass",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm_ping_only"


async def test_confirm_ping_only_creates_entry(
    hass: HomeAssistant, mock_ping_success
) -> None:
    """TS-08: Confirm ping-only creates entry without password."""
    from custom_components.tplink_powerline.client import IncompatibleDevice

    with patch(
        "custom_components.tplink_powerline.config_flow.PowerlineClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.login.side_effect = IncompatibleDevice("HTML response")
        mock_client_cls.return_value = mock_client

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.34",
                CONF_NAME: "My Device",
                CONF_PASSWORD: "somepass",
            },
        )
        assert result["step_id"] == "confirm_ping_only"

        # User confirms ping-only
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Device"
    assert CONF_PASSWORD_HASH not in result["data"]


async def test_compatible_device_still_works(
    hass: HomeAssistant, mock_ping_success
) -> None:
    """TS-09: Compatible device still creates entry normally (regression)."""
    with patch(
        "custom_components.tplink_powerline.config_flow.PowerlineClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.34",
                CONF_NAME: "Powerline",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_PASSWORD_HASH in result["data"]


# --- MAC-based identity ---

ROOT_MAC = "b8:fb:b3:b6:dd:df"


def _patch_client(mac: str | None = "B8-FB-B3-B6-DD-DF", device_info_error: Exception | None = None):
    mock_client = AsyncMock()
    if device_info_error:
        mock_client.get_device_info.side_effect = device_info_error
    else:
        mock_client.get_device_info.return_value = {"model": "PG2400P", "mac": mac or ""}
    return mock_client, patch(
        "custom_components.tplink_powerline.config_flow.PowerlineClient",
        return_value=mock_client,
    )


async def _submit_user(hass: HomeAssistant, host: str, password: str = "testpassword"):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: host, CONF_NAME: "Powerline", CONF_PASSWORD: password},
    )


async def test_config_flow_uses_mac_as_unique_id(hass: HomeAssistant, mock_ping_success) -> None:
    mock_client, client_patch = _patch_client()
    with client_patch:
        result = await _submit_user(hass, "192.168.1.34")

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == ROOT_MAC
    mock_client.logout.assert_awaited_once()


async def test_config_flow_known_mac_at_new_ip_updates_existing_entry(
    hass: HomeAssistant, mock_ping_success
) -> None:
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.34", CONF_NAME: "Powerline", CONF_PASSWORD_HASH: "abc"},
        unique_id=ROOT_MAC,
        minor_version=2,
    )
    existing.add_to_hass(hass)

    _, client_patch = _patch_client()
    with client_patch, patch(
        "custom_components.tplink_powerline.async_setup_entry", return_value=True
    ):
        result = await _submit_user(hass, "192.168.1.50")

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert existing.data[CONF_HOST] == "192.168.1.50"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_config_flow_falls_back_to_host_when_mac_unreadable(
    hass: HomeAssistant, mock_ping_success
) -> None:
    _, client_patch = _patch_client(device_info_error=Exception("boom"))
    with client_patch:
        result = await _submit_user(hass, "192.168.1.34")

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "192.168.1.34"
    assert result["data"][CONF_PASSWORD_HASH]


async def test_config_flow_without_password_uses_host_unique_id(
    hass: HomeAssistant, mock_ping_success
) -> None:
    result = await _submit_user(hass, "192.168.1.34", password="")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "192.168.1.34"


async def test_config_flow_new_entries_use_current_minor_version(
    hass: HomeAssistant, mock_ping_success
) -> None:
    result = await _submit_user(hass, "192.168.1.34", password="")
    assert result["result"].minor_version == 2
