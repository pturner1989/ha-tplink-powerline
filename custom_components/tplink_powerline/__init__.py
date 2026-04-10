"""The TP-Link Powerline integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import PowerlineClient
from .const import CONF_PASSWORD_HASH, DOMAIN
from .coordinator import TplinkPowerlineCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TP-Link Powerline from a config entry."""
    coordinator = TplinkPowerlineCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    client = None
    device_info = None

    password_hash = entry.data.get(CONF_PASSWORD_HASH)
    if password_hash:
        host = entry.data[CONF_HOST]
        session = async_get_clientsession(hass)
        client = PowerlineClient(host, password_hash, session)
        try:
            await client.login()
            device_info = await client.get_device_info()
            _LOGGER.info(
                "Fetched device info for %s: %s", host, device_info
            )
        except Exception:
            _LOGGER.warning(
                "Failed to fetch device info via HTTP for %s, "
                "continuing in ping-only mode",
                host,
                exc_info=True,
            )
            client = None
            device_info = None

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "device_info": device_info,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        client = entry_data.get("client")
        if client:
            await client.logout()
    return unload_ok
