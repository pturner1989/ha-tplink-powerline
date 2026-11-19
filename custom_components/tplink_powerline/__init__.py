"""The TP-Link Powerline integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import PowerlineClient
from .const import CONF_PASSWORD_HASH, DOMAIN
from .coordinator import TplinkPowerlineCoordinator
from .device import normalize_mac, root_device_identifier
from .network_coordinator import NetworkCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TP-Link Powerline from a config entry."""
    coordinator = TplinkPowerlineCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    client = None
    device_info = None
    network_name = None
    network_coordinator = None

    password_hash = entry.data.get(CONF_PASSWORD_HASH)
    if password_hash:
        host = entry.data[CONF_HOST]
        session = async_get_clientsession(hass)
        client = PowerlineClient(host, password_hash, session)

        # Login
        try:
            await client.login()
        except Exception:
            _LOGGER.warning(
                "HTTP login failed for %s, continuing in ping-only mode",
                host,
                exc_info=True,
            )
            client = None

        # Device info
        if client:
            try:
                device_info = await client.get_device_info()
                _LOGGER.info("Fetched device info for %s: %s", host, device_info)
            except Exception:
                _LOGGER.warning(
                    "Failed to fetch device info for %s", host, exc_info=True
                )

        # Network name
        if client:
            try:
                network_name = await client.get_network_name()
            except Exception:
                _LOGGER.warning(
                    "Failed to fetch network name for %s", host, exc_info=True
                )

        # Network coordinator
        if client:
            try:
                net_coord = NetworkCoordinator(hass, client)
                await net_coord.async_config_entry_first_refresh()
                network_coordinator = net_coord
            except Exception:
                _LOGGER.warning(
                    "Failed to start network monitoring for %s", host, exc_info=True
                )

    mac = normalize_mac(device_info.get("mac")) if device_info else None
    _register_root_device(hass, entry, device_info, mac)
    if mac:
        _adopt_mac_unique_id(hass, entry, mac)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "device_info": device_info,
        "network_name": network_name,
        "network_coordinator": network_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _register_root_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_info: dict[str, str] | None,
    mac: str | None,
) -> None:
    """Create or update the root adapter's device registry entry."""
    info = device_info or {}
    kwargs = {}
    if info.get("firmware"):
        kwargs["sw_version"] = info["firmware"]
    if info.get("hardware"):
        kwargs["hw_version"] = info["hardware"]
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={root_device_identifier(entry)},
        connections={(dr.CONNECTION_NETWORK_MAC, mac)} if mac else set(),
        name=entry.data[CONF_NAME],
        manufacturer="TP-Link",
        model=info.get("model", "Powerline Adapter"),
        **kwargs,
    )


def _adopt_mac_unique_id(hass: HomeAssistant, entry: ConfigEntry, mac: str) -> None:
    """Switch the entry's unique ID to the adapter MAC once it is known."""
    if entry.unique_id == mac:
        return
    existing = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, mac)
    if existing is not None:
        _LOGGER.warning(
            "Adapter %s (MAC %s) is also configured as '%s'; "
            "keeping unique ID %s for this entry",
            entry.data[CONF_HOST],
            mac,
            existing.title,
            entry.unique_id,
        )
        return
    hass.config_entries.async_update_entry(entry, unique_id=mac)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry."""
    if entry.version > 1:
        return False

    if entry.minor_version < 2:
        # 1.2: root device keyed by entry_id instead of host.
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get_device(
            identifiers={(DOMAIN, entry.data[CONF_HOST])}
        )
        if device is not None and entry.entry_id in device.config_entries:
            dev_reg.async_update_device(
                device.id, new_identifiers={root_device_identifier(entry)}
            )
        hass.config_entries.async_update_entry(entry, minor_version=2)
        _LOGGER.debug("Migrated %s to version 1.2", entry.title)

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
