"""Sensor platform for TP-Link Powerline integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

SENSOR_DESCRIPTIONS = [
    {"key": "model", "name": "Model", "icon": "mdi:router-network"},
    {"key": "firmware", "name": "Firmware Version", "icon": "mdi:memory"},
    {"key": "hardware", "name": "Hardware Version", "icon": "mdi:chip"},
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TP-Link Powerline sensors from a config entry."""
    device_info: dict[str, str] | None = hass.data[DOMAIN][entry.entry_id].get(
        "device_info"
    )
    if device_info is None:
        return

    async_add_entities(
        TplinkPowerlineSensor(entry, device_info, desc)
        for desc in SENSOR_DESCRIPTIONS
    )


class TplinkPowerlineSensor(SensorEntity):
    """Diagnostic sensor for powerline device information."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        entry: ConfigEntry,
        device_info: dict[str, str],
        description: dict[str, str],
    ) -> None:
        """Initialize the sensor."""
        self._attr_unique_id = f"{entry.entry_id}_{description['key']}"
        self._attr_name = f"{entry.data[CONF_NAME]} {description['name']}"
        self._attr_native_value = device_info.get(description["key"])
        self._attr_icon = description["icon"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_HOST])},
        )
