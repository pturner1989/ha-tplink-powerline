"""Binary sensor platform for TP-Link Powerline integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TplinkPowerlineCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TP-Link Powerline binary sensor from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TplinkPowerlineCoordinator = entry_data["coordinator"]
    device_info: dict[str, str] | None = entry_data.get("device_info")
    async_add_entities(
        [TplinkPowerlineBinarySensor(coordinator, entry, device_info)]
    )


class TplinkPowerlineBinarySensor(
    CoordinatorEntity[TplinkPowerlineCoordinator], BinarySensorEntity
):
    """Binary sensor representing powerline device connectivity."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: TplinkPowerlineCoordinator,
        entry: ConfigEntry,
        device_info: dict[str, str] | None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.data[CONF_NAME]

        model = "Powerline Adapter"
        sw_version = None
        hw_version = None
        if device_info:
            model = device_info.get("model", model)
            sw_version = device_info.get("firmware")
            hw_version = device_info.get("hardware")

        di_kwargs: dict[str, Any] = {
            "identifiers": {(DOMAIN, entry.data[CONF_HOST])},
            "name": entry.data[CONF_NAME],
            "manufacturer": "TP-Link",
            "model": model,
        }
        if sw_version:
            di_kwargs["sw_version"] = sw_version
        if hw_version:
            di_kwargs["hw_version"] = hw_version

        self._attr_device_info = DeviceInfo(**di_kwargs)

    @property
    def is_on(self) -> bool | None:
        """Return True if the device is connected."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["available"]
