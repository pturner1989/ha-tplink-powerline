"""DataUpdateCoordinator for TP-Link Powerline integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_SCAN_INTERVAL, FAILURE_THRESHOLD, PING_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class TplinkPowerlineCoordinator(DataUpdateCoordinator[dict[str, bool]]):
    """Coordinator that pings a powerline device and tracks consecutive failures."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.host: str = entry.data[CONF_HOST]
        self.failure_count: int = 0

        super().__init__(
            hass,
            _LOGGER,
            name=f"tplink_powerline_{self.host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, bool]:
        """Ping the device and update failure count."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping",
                "-c",
                "1",
                "-W",
                str(PING_TIMEOUT),
                self.host,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            success = proc.returncode == 0
        except OSError:
            _LOGGER.warning("Failed to execute ping command for %s", self.host)
            success = False

        if success:
            self.failure_count = 0
        else:
            self.failure_count += 1

        return {"available": self.failure_count < FAILURE_THRESHOLD}
