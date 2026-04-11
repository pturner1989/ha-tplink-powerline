"""Select platform for TP-Link Powerline integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import PowerlineClient
from .const import DOMAIN, QOS_MODES_REVERSE, REBOOT_CYCLES, REBOOT_CYCLES_REVERSE

WEEKDAYS = {
    "1": "Monday", "2": "Tuesday", "3": "Wednesday", "4": "Thursday",
    "5": "Friday", "6": "Saturday", "7": "Sunday",
}
WEEKDAYS_REVERSE = {v: k for k, v in WEEKDAYS.items()}

MONTH_DAYS = {str(i): f"{i}" for i in range(1, 29)}
MONTH_DAYS_REVERSE = {v: k for k, v in MONTH_DAYS.items()}
from .network_coordinator import NetworkCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TP-Link Powerline select entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    network_coordinator: NetworkCoordinator | None = entry_data.get("network_coordinator")
    client: PowerlineClient | None = entry_data.get("client")

    if not network_coordinator or not client:
        return

    host = entry.data[CONF_HOST]
    name = entry.data[CONF_NAME]
    entities: list[SelectEntity] = []

    if network_coordinator.data and network_coordinator.data.get("qos_mode") is not None:
        entities.append(QosModeSelect(network_coordinator, client, entry, host, name))

    if network_coordinator.data and network_coordinator.data.get("reboot_schedule") is not None:
        entities.append(RebootCycleSelect(network_coordinator, client, entry, host, name))
        entities.append(RebootWeekdaySelect(network_coordinator, client, entry, host, name))
        entities.append(RebootMonthdaySelect(network_coordinator, client, entry, host, name))

    async_add_entities(entities)


class QosModeSelect(CoordinatorEntity[NetworkCoordinator], SelectEntity):
    """Select entity for QoS priority mode."""

    _attr_options = ["Fair", "Gaming", "Streaming", "Voice"]
    _attr_icon = "mdi:quality-high"

    def __init__(self, coordinator, client, entry, host, name):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_qos_mode"
        self._attr_name = f"{name} QoS Mode"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, host)})

    @property
    def current_option(self) -> str | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("qos_mode")

    async def async_select_option(self, option: str) -> None:
        mode_num = QOS_MODES_REVERSE.get(option, "1")
        await self._client.send_command(f"set qos {mode_num}")
        await self.coordinator.async_request_refresh()


class RebootCycleSelect(CoordinatorEntity[NetworkCoordinator], SelectEntity):
    """Select entity for reboot schedule repeat cycle."""

    _attr_options = ["Daily", "Weekly", "Monthly"]
    _attr_icon = "mdi:calendar-refresh"

    def __init__(self, coordinator, client, entry, host, name):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_reboot_cycle"
        self._attr_name = f"{name} Reboot Cycle"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, host)})

    @property
    def current_option(self) -> str | None:
        if not self.coordinator.data:
            return None
        schedule = self.coordinator.data.get("reboot_schedule")
        if schedule is None:
            return None
        return REBOOT_CYCLES.get(str(schedule["repeat"]), "Daily")

    async def async_select_option(self, option: str) -> None:
        cycle_num = REBOOT_CYCLES_REVERSE.get(option, "1")
        await self._client.set_data({"TPLINK.REBOOTSCHEDULE.REPEAT": cycle_num})
        await self.coordinator.async_request_refresh()


class RebootWeekdaySelect(CoordinatorEntity[NetworkCoordinator], SelectEntity):
    """Select entity for reboot schedule weekday (when cycle is Weekly)."""

    _attr_options = list(WEEKDAYS.values())
    _attr_icon = "mdi:calendar-week"

    def __init__(self, coordinator, client, entry, host, name):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_reboot_weekday"
        self._attr_name = f"{name} Reboot Weekday"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, host)})

    @property
    def current_option(self) -> str | None:
        if not self.coordinator.data:
            return None
        schedule = self.coordinator.data.get("reboot_schedule")
        if schedule is None or str(schedule.get("repeat")) != "2":
            return None
        return WEEKDAYS.get(str(schedule.get("weekday", 1)), "Monday")

    async def async_select_option(self, option: str) -> None:
        day_num = WEEKDAYS_REVERSE.get(option, "1")
        await self._client.set_data({"TPLINK.REBOOTSCHEDULE.WEEKDAY": day_num})
        await self.coordinator.async_request_refresh()


class RebootMonthdaySelect(CoordinatorEntity[NetworkCoordinator], SelectEntity):
    """Select entity for reboot schedule day of month (when cycle is Monthly)."""

    _attr_options = [str(i) for i in range(1, 29)]
    _attr_icon = "mdi:calendar-month"

    def __init__(self, coordinator, client, entry, host, name):
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_reboot_monthday"
        self._attr_name = f"{name} Reboot Day of Month"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, host)})

    @property
    def current_option(self) -> str | None:
        if not self.coordinator.data:
            return None
        schedule = self.coordinator.data.get("reboot_schedule")
        if schedule is None or str(schedule.get("repeat")) != "3":
            return None
        return str(schedule.get("monthday", 1))

    async def async_select_option(self, option: str) -> None:
        await self._client.set_data({"TPLINK.REBOOTSCHEDULE.MONTHDAY": option})
        await self.coordinator.async_request_refresh()
