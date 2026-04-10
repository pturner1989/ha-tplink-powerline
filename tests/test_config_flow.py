"""Tests for the TP-Link Powerline config flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.tplink_powerline.const import DOMAIN


async def test_successful_config_flow(
    hass: HomeAssistant, mock_ping_success
) -> None:
    """Test a successful config flow creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

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
    # Create first entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.34", CONF_NAME: "Powerline Network"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    # Attempt duplicate
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
