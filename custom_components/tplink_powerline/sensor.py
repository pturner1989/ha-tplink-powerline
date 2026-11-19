"""Sensor platform for TP-Link Powerline integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, EntityCategory, UnitOfDataRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .device import root_device_identifier, root_device_info
from .network_coordinator import NetworkCoordinator

STATIC_SENSOR_DESCRIPTIONS = [
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
    entry_data = hass.data[DOMAIN][entry.entry_id]
    device_info: dict[str, str] | None = entry_data.get("device_info")
    network_coordinator: NetworkCoordinator | None = entry_data.get("network_coordinator")
    network_name: str | None = entry_data.get("network_name")
    name = entry.data[CONF_NAME]

    entities: list[SensorEntity] = []

    # Static device info sensors (model, firmware, hardware)
    if device_info:
        for desc in STATIC_SENSOR_DESCRIPTIONS:
            entities.append(StaticDiagnosticSensor(entry, device_info, desc))

    # Network name sensor (static, diagnostic)
    if network_name:
        entities.append(NetworkNameSensor(entry, network_name))

    # Network coordinator-driven sensors
    if network_coordinator and network_coordinator.data:
        # Connected adapters count on root device
        entities.append(
            ConnectedCountSensor(network_coordinator, entry, name)
        )

        # Per-adapter TX/RX rate sensors
        for adapter in network_coordinator.data.get("adapters", []):
            mac = adapter["mac"]
            entities.append(
                AdapterRateSensor(network_coordinator, entry, mac, "tx_rate", "TX Rate", "mdi:upload-network")
            )
            entities.append(
                AdapterRateSensor(network_coordinator, entry, mac, "rx_rate", "RX Rate", "mdi:download-network")
            )

    async_add_entities(entities)


class StaticDiagnosticSensor(SensorEntity):
    """Diagnostic sensor for static device information."""

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
        self._attr_device_info = root_device_info(entry)


class NetworkNameSensor(SensorEntity):
    """Diagnostic sensor for the powerline network name."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:network"

    def __init__(
        self, entry: ConfigEntry, network_name: str
    ) -> None:
        """Initialize the sensor."""
        self._attr_unique_id = f"{entry.entry_id}_network_name"
        self._attr_name = f"{entry.data[CONF_NAME]} Network Name"
        self._attr_native_value = network_name
        self._attr_device_info = root_device_info(entry)


class ConnectedCountSensor(CoordinatorEntity[NetworkCoordinator], SensorEntity):
    """Sensor showing the number of connected remote adapters."""

    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: NetworkCoordinator,
        entry: ConfigEntry,
        name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_connected_count"
        self._attr_name = f"{name} Connected Adapters"
        self._attr_device_info = root_device_info(entry)

    @property
    def native_value(self) -> int | None:
        """Return the number of connected adapters."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("connected_count", 0)


class AdapterRateSensor(CoordinatorEntity[NetworkCoordinator], SensorEntity):
    """Sensor for a remote adapter's TX or RX link rate."""

    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: NetworkCoordinator,
        entry: ConfigEntry,
        mac: str,
        rate_key: str,
        rate_label: str,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._mac = mac
        self._rate_key = rate_key
        self._attr_unique_id = f"{entry.entry_id}_{mac.replace('-', '')}_{rate_key}"
        self._attr_name = f"Powerline {mac} {rate_label}"
        self._attr_icon = icon
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
    def native_value(self) -> int | None:
        """Return the link rate in Mbps."""
        adapter = self._find_adapter()
        if adapter is None:
            return None
        return adapter.get(self._rate_key, 0)
