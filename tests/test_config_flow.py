"""Tests for the TP-Link Powerline config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.tplink_powerline.const import CONF_PASSWORD_HASH, DOMAIN


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
