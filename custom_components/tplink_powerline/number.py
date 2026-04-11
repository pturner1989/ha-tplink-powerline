"""Number platform for TP-Link Powerline integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import PowerlineClient
from .const import DOMAIN
from .network_coordinator import NetworkCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TP-Link Powerline number entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    network_coordinator: NetworkCoordinator | None = entry_data.get("network_coordinator")
    client: PowerlineClient | None = entry_data.get("client")

    if not network_coordinator or not client:
        return

    if network_coordinator.data and network_coordinator.data.get("reboot_schedule") is not None:
        async_add_entities([
            RebootDayNumber(network_coordinator, client, entry)
        ])


class RebootDayNumber(CoordinatorEntity[NetworkCoordinator], NumberEntity):
    """Number entity for reboot schedule day."""

    _attr_native_min_value = 1
    _attr_native_max_value = 28
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:calendar-today"

    def __init__(
        self,
        coordinator: NetworkCoordinator,
        client: PowerlineClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_reboot_day"
        self._attr_name = f"{entry.data[CONF_NAME]} Reboot Day"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_HOST])},
        )

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        schedule = self.coordinator.data.get("reboot_schedule")
        if schedule is None:
            return None
        repeat = str(schedule.get("repeat", "1"))
        if repeat == "2":
            return float(schedule.get("weekday", 1))
        if repeat == "3":
            return float(schedule.get("monthday", 1))
        return float(schedule.get("weekday", 1))

    async def async_set_native_value(self, value: float) -> None:
        schedule = self.coordinator.data.get("reboot_schedule", {})
        repeat = str(schedule.get("repeat", "1"))
        int_val = str(int(value))
        if repeat == "2":
            await self._client.set_data({"TPLINK.REBOOTSCHEDULE.WEEKDAY": int_val})
        elif repeat == "3":
            await self._client.set_data({"TPLINK.REBOOTSCHEDULE.MONTHDAY": int_val})
        else:
            await self._client.set_data({"TPLINK.REBOOTSCHEDULE.WEEKDAY": int_val})
        await self.coordinator.async_request_refresh()
