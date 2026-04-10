"""Binary sensor platform for TP-Link Powerline integration."""

from __future__ import annotations

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
    coordinator: TplinkPowerlineCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TplinkPowerlineBinarySensor(coordinator, entry)])


class TplinkPowerlineBinarySensor(
    CoordinatorEntity[TplinkPowerlineCoordinator], BinarySensorEntity
):
    """Binary sensor representing powerline device connectivity."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: TplinkPowerlineCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.data[CONF_NAME]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_HOST])},
            name=entry.data[CONF_NAME],
            manufacturer="TP-Link",
            model="Powerline Adapter",
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the device is connected."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["available"]
