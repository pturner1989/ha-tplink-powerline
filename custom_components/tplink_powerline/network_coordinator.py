"""Network data coordinator for TP-Link Powerline integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import DeviceUnavailable, PowerlineClient, UnexpectedResponse
from .const import NETWORK_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


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
        """Fetch network data from the device."""
        try:
            return await self.client.get_network_data()
        except (DeviceUnavailable, UnexpectedResponse) as err:
            raise UpdateFailed(f"Failed to fetch network data: {err}") from err
