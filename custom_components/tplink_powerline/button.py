"""Button platform for TP-Link Powerline integration."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import PowerlineClient
from .const import DOMAIN
from .device import root_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TP-Link Powerline buttons."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client: PowerlineClient | None = entry_data.get("client")

    if not client:
        return

    async_add_entities([RebootButton(client, entry)])


class RebootButton(ButtonEntity):
    """Button to reboot the powerline device."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_icon = "mdi:restart"

    def __init__(self, client: PowerlineClient, entry: ConfigEntry) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_reboot"
        self._attr_name = f"{entry.data[CONF_NAME]} Reboot"
        self._attr_device_info = root_device_info(entry)

    async def async_press(self) -> None:
        _LOGGER.info("Rebooting powerline device %s", self._client.host)
        try:
            await self._client.send_command("reboot")
        except Exception:
            _LOGGER.warning("Reboot command may have failed (device may already be rebooting)")
