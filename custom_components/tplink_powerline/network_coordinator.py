"""Network data coordinator for TP-Link Powerline integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import DeviceUnavailable, PowerlineClient, UnexpectedResponse
from .const import ETHERNET_PORT_STATUS, NETWORK_SCAN_INTERVAL, QOS_MODES

_LOGGER = logging.getLogger(__name__)

_LED_KEYS = [
    "TPLINK.LEDSCHEDULE.LED_ENABLE",
    "TPLINK.LEDSCHEDULE.ENABLE",
    "TPLINK.LEDSCHEDULE.START_HOUR",
    "TPLINK.LEDSCHEDULE.START_MINUTE",
    "TPLINK.LEDSCHEDULE.END_HOUR",
    "TPLINK.LEDSCHEDULE.END_MINUTE",
]

_REBOOT_KEYS = [
    "TPLINK.REBOOTSCHEDULE.ENABLE",
    "TPLINK.REBOOTSCHEDULE.HOUR",
    "TPLINK.REBOOTSCHEDULE.MINUTE",
    "TPLINK.REBOOTSCHEDULE.REPEAT",
    "TPLINK.REBOOTSCHEDULE.WEEKDAY",
    "TPLINK.REBOOTSCHEDULE.MONTHDAY",
]


class NetworkCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches powerline network data every 60 seconds."""

    def __init__(self, hass: HomeAssistant, client: PowerlineClient) -> None:
        """Initialize the network coordinator."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            name="tplink_powerline_network",
            update_interval=timedelta(seconds=NETWORK_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all network and device status data."""
        try:
            network = await self.client.get_network_data()
        except (DeviceUnavailable, UnexpectedResponse) as err:
            raise UpdateFailed(f"Failed to fetch network data: {err}") from err

        result: dict[str, Any] = {
            "adapters": network["adapters"],
            "connected_count": network["connected_count"],
            "root_mac": network["root_mac"],
        }

        # LED settings
        result["led"] = await self._fetch_led()

        # Reboot schedule
        result["reboot_schedule"] = await self._fetch_reboot_schedule()

        # QoS mode
        result["qos_mode"] = await self._fetch_qos()

        # Ethernet port status
        result["ethernet_ports"] = await self._fetch_ethernet()

        return result

    async def _fetch_led(self) -> dict[str, Any] | None:
        try:
            data = await self.client.get_data(_LED_KEYS)
            return {
                "enabled": data.get("TPLINK.LEDSCHEDULE.LED_ENABLE") == "YES",
                "night_mode": data.get("TPLINK.LEDSCHEDULE.ENABLE") == "YES",
                "start_hour": int(data.get("TPLINK.LEDSCHEDULE.START_HOUR", 0)),
                "start_minute": int(data.get("TPLINK.LEDSCHEDULE.START_MINUTE", 0)),
                "end_hour": int(data.get("TPLINK.LEDSCHEDULE.END_HOUR", 0)),
                "end_minute": int(data.get("TPLINK.LEDSCHEDULE.END_MINUTE", 0)),
            }
        except Exception:
            _LOGGER.debug("Failed to fetch LED settings", exc_info=True)
            return None

    async def _fetch_reboot_schedule(self) -> dict[str, Any] | None:
        try:
            data = await self.client.get_data(_REBOOT_KEYS)
            return {
                "enabled": data.get("TPLINK.REBOOTSCHEDULE.ENABLE") == "YES",
                "hour": int(data.get("TPLINK.REBOOTSCHEDULE.HOUR", 0)),
                "minute": int(data.get("TPLINK.REBOOTSCHEDULE.MINUTE", 0)),
                "repeat": data.get("TPLINK.REBOOTSCHEDULE.REPEAT", "1"),
                "weekday": int(data.get("TPLINK.REBOOTSCHEDULE.WEEKDAY", 0)),
                "monthday": int(data.get("TPLINK.REBOOTSCHEDULE.MONTHDAY", 1)),
            }
        except Exception:
            _LOGGER.debug("Failed to fetch reboot schedule", exc_info=True)
            return None

    async def _fetch_qos(self) -> str | None:
        try:
            data = await self.client.send_command("get qos")
            mode_num = data.get("RESULT", "1")
            return QOS_MODES.get(mode_num, "Fair")
        except Exception:
            _LOGGER.debug("Failed to fetch QoS mode", exc_info=True)
            return None

    async def _fetch_ethernet(self) -> list[dict[str, Any]] | None:
        try:
            data = await self.client.send_command("lan link speed")
            ports = []
            for key, value in sorted(data.items()):
                if not key.startswith("PORT"):
                    continue
                port_num = int(key[4:])
                status_code = int(value)
                status = ETHERNET_PORT_STATUS.get(
                    status_code,
                    {"connected": False, "speed": 0, "duplex": ""},
                )
                ports.append({"port": port_num, **status})
            return ports
        except Exception:
            _LOGGER.debug("Failed to fetch ethernet status", exc_info=True)
            return None
