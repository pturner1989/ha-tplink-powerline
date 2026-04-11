"""Time platform for TP-Link Powerline integration."""

from __future__ import annotations

from datetime import time as dt_time
import logging
from typing import Any

from homeassistant.components.time import TimeEntity
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
    """Set up TP-Link Powerline time entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    network_coordinator: NetworkCoordinator | None = entry_data.get("network_coordinator")
    client: PowerlineClient | None = entry_data.get("client")

    if not network_coordinator or not client:
        return

    host = entry.data[CONF_HOST]
    name = entry.data[CONF_NAME]
    entities: list[TimeEntity] = []

    if network_coordinator.data and network_coordinator.data.get("led") is not None:
        entities.append(NightModeStartTime(network_coordinator, client, entry, host, name))
        entities.append(NightModeEndTime(network_coordinator, client, entry, host, name))

    if network_coordinator.data and network_coordinator.data.get("reboot_schedule") is not None:
        entities.append(RebootScheduleTime(network_coordinator, client, entry, host, name))

    async_add_entities(entities)


class _BaseTime(CoordinatorEntity[NetworkCoordinator], TimeEntity):
    """Base time entity."""

    def __init__(
        self,
        coordinator: NetworkCoordinator,
        client: PowerlineClient,
        entry: ConfigEntry,
        host: str,
        name: str,
        key: str,
        label: str,
        icon: str,
        section: str,
        hour_data_key: str,
        minute_data_key: str,
        hour_write_key: str,
        minute_write_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._section = section
        self._hour_data_key = hour_data_key
        self._minute_data_key = minute_data_key
        self._hour_write_key = hour_write_key
        self._minute_write_key = minute_write_key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = f"{name} {label}"
        self._attr_icon = icon
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, host)})

    @property
    def native_value(self) -> dt_time | None:
        if not self.coordinator.data:
            return None
        section = self.coordinator.data.get(self._section)
        if section is None:
            return None
        return dt_time(section[self._hour_data_key], section[self._minute_data_key])

    async def async_set_value(self, value: dt_time) -> None:
        await self._client.set_data({
            self._hour_write_key: str(value.hour),
            self._minute_write_key: str(value.minute),
        })
        await self.coordinator.async_request_refresh()


class NightModeStartTime(_BaseTime):
    def __init__(self, coordinator, client, entry, host, name):
        super().__init__(
            coordinator, client, entry, host, name,
            key="night_mode_start", label="LED Night Mode Start",
            icon="mdi:weather-sunset-down",
            section="led", hour_data_key="start_hour", minute_data_key="start_minute",
            hour_write_key="TPLINK.LEDSCHEDULE.START_HOUR",
            minute_write_key="TPLINK.LEDSCHEDULE.START_MINUTE",
        )


class NightModeEndTime(_BaseTime):
    def __init__(self, coordinator, client, entry, host, name):
        super().__init__(
            coordinator, client, entry, host, name,
            key="night_mode_end", label="LED Night Mode End",
            icon="mdi:weather-sunset-up",
            section="led", hour_data_key="end_hour", minute_data_key="end_minute",
            hour_write_key="TPLINK.LEDSCHEDULE.END_HOUR",
            minute_write_key="TPLINK.LEDSCHEDULE.END_MINUTE",
        )


class RebootScheduleTime(_BaseTime):
    def __init__(self, coordinator, client, entry, host, name):
        super().__init__(
            coordinator, client, entry, host, name,
            key="reboot_schedule_time", label="Reboot Schedule Time",
            icon="mdi:clock-outline",
            section="reboot_schedule", hour_data_key="hour", minute_data_key="minute",
            hour_write_key="TPLINK.REBOOTSCHEDULE.HOUR",
            minute_write_key="TPLINK.REBOOTSCHEDULE.MINUTE",
        )
