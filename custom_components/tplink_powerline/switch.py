"""Switch platform for TP-Link Powerline integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up TP-Link Powerline switches."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    network_coordinator: NetworkCoordinator | None = entry_data.get("network_coordinator")
    client: PowerlineClient | None = entry_data.get("client")

    if not network_coordinator or not client:
        return

    host = entry.data[CONF_HOST]
    name = entry.data[CONF_NAME]

    entities: list[SwitchEntity] = []

    if network_coordinator.data and network_coordinator.data.get("led") is not None:
        entities.append(LedSwitch(network_coordinator, client, entry, host, name))
        entities.append(NightModeSwitch(network_coordinator, client, entry, host, name))

    if network_coordinator.data and network_coordinator.data.get("reboot_schedule") is not None:
        entities.append(RebootScheduleSwitch(network_coordinator, client, entry, host, name))

    async_add_entities(entities)


class _BaseSwitch(CoordinatorEntity[NetworkCoordinator], SwitchEntity):
    """Base switch for TP-Link Powerline settings."""

    def __init__(
        self,
        coordinator: NetworkCoordinator,
        client: PowerlineClient,
        entry: ConfigEntry,
        host: str,
        name: str,
        key: str,
        label: str,
        icon_on: str,
        icon_off: str,
        section: str,
        data_key: str,
        write_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._section = section
        self._data_key = data_key
        self._write_key = write_key
        self._icon_on = icon_on
        self._icon_off = icon_off
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = f"{name} {label}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, host)})

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        section = self.coordinator.data.get(self._section)
        if section is None:
            return None
        return section.get(self._data_key)

    @property
    def icon(self) -> str:
        return self._icon_on if self.is_on else self._icon_off

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.set_data({self._write_key: "YES"})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.set_data({self._write_key: "NO"})
        await self.coordinator.async_request_refresh()


class LedSwitch(_BaseSwitch):
    def __init__(self, coordinator, client, entry, host, name):
        super().__init__(
            coordinator, client, entry, host, name,
            key="led_switch", label="LED", icon_on="mdi:led-on", icon_off="mdi:led-off",
            section="led", data_key="enabled", write_key="TPLINK.LEDSCHEDULE.LED_ENABLE",
        )


class NightModeSwitch(_BaseSwitch):
    def __init__(self, coordinator, client, entry, host, name):
        super().__init__(
            coordinator, client, entry, host, name,
            key="night_mode_switch", label="LED Night Mode", icon_on="mdi:weather-night", icon_off="mdi:weather-night",
            section="led", data_key="night_mode", write_key="TPLINK.LEDSCHEDULE.ENABLE",
        )


class RebootScheduleSwitch(_BaseSwitch):
    def __init__(self, coordinator, client, entry, host, name):
        super().__init__(
            coordinator, client, entry, host, name,
            key="reboot_schedule_switch", label="Reboot Schedule", icon_on="mdi:restart-alert", icon_off="mdi:restart-alert",
            section="reboot_schedule", data_key="enabled", write_key="TPLINK.REBOOTSCHEDULE.ENABLE",
        )
