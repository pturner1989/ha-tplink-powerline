"""Binary sensor platform for TP-Link Powerline integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TplinkPowerlineCoordinator
from .device import root_device_identifier, root_device_info
from .network_coordinator import NetworkCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TP-Link Powerline binary sensors from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TplinkPowerlineCoordinator = entry_data["coordinator"]
    network_coordinator: NetworkCoordinator | None = entry_data.get("network_coordinator")

    entities: list[BinarySensorEntity] = [
        TplinkPowerlineBinarySensor(coordinator, entry)
    ]

    if network_coordinator and network_coordinator.data:
        name = entry.data[CONF_NAME]
        for adapter in network_coordinator.data.get("adapters", []):
            entities.append(
                RemoteAdapterBinarySensor(
                    network_coordinator, entry, adapter["mac"]
                )
            )
        for port in network_coordinator.data.get("ethernet_ports", []) or []:
            entities.append(
                EthernetPortBinarySensor(
                    network_coordinator, entry, port["port"], name
                )
            )

    async_add_entities(entities)


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
        # Name, model and versions are set when the device is registered in setup.
        self._attr_device_info = root_device_info(entry)

    @property
    def is_on(self) -> bool | None:
        """Return True if the device is connected."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["available"]


class RemoteAdapterBinarySensor(
    CoordinatorEntity[NetworkCoordinator], BinarySensorEntity
):
    """Binary sensor for remote powerline adapter connectivity."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: NetworkCoordinator,
        entry: ConfigEntry,
        mac: str,
    ) -> None:
        """Initialize the remote adapter binary sensor."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{entry.entry_id}_{mac.replace('-', '')}_connectivity"
        self._attr_name = f"Powerline {mac}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=f"Powerline Adapter {mac}",
            manufacturer="TP-Link",
            model="Powerline Adapter",
            via_device=root_device_identifier(entry),
        )

    def _find_adapter(self) -> dict[str, Any] | None:
        """Find this adapter in the coordinator data."""
        if not self.coordinator.data:
            return None
        for adapter in self.coordinator.data.get("adapters", []):
            if adapter["mac"] == self._mac:
                return adapter
        return None

    @property
    def is_on(self) -> bool | None:
        """Return True if the remote adapter is connected."""
        adapter = self._find_adapter()
        if adapter is None:
            return None
        return adapter["tx_rate"] > 0 or adapter["rx_rate"] > 0


class EthernetPortBinarySensor(
    CoordinatorEntity[NetworkCoordinator], BinarySensorEntity
):
    """Binary sensor for an ethernet port on the root device."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: NetworkCoordinator,
        entry: ConfigEntry,
        port_num: int,
        name: str,
    ) -> None:
        """Initialize the ethernet port binary sensor."""
        super().__init__(coordinator)
        self._port_num = port_num
        self._attr_unique_id = f"{entry.entry_id}_ethernet_port_{port_num}"
        self._attr_name = f"{name} Ethernet Port {port_num}"
        self._attr_icon = "mdi:ethernet"
        self._attr_device_info = root_device_info(entry)

    def _find_port(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        ports = self.coordinator.data.get("ethernet_ports")
        if not ports:
            return None
        for port in ports:
            if port["port"] == self._port_num:
                return port
        return None

    @property
    def is_on(self) -> bool | None:
        port = self._find_port()
        if port is None:
            return None
        return port["connected"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        port = self._find_port()
        if port is None:
            return {}
        return {
            "speed": port["speed"],
            "duplex": port["duplex"],
        }
