"""Tests for the TP-Link Powerline network coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.tplink_powerline.client import DeviceUnavailable
from custom_components.tplink_powerline.network_coordinator import NetworkCoordinator


def _make_client(network_data: dict | None = None, error: Exception | None = None) -> AsyncMock:
    client = AsyncMock()
    if error:
        client.get_network_data.side_effect = error
    else:
        client.get_network_data.return_value = network_data or {
            "adapters": [{"mac": "58-04-4F-D8-20-2D", "tx_rate": 366, "rx_rate": 317}],
            "connected_count": 1,
            "root_mac": "B8-FB-B3-B6-DD-DF",
        }
    return client


# TS-16: Successful network data fetch
async def test_successful_network_fetch(hass: HomeAssistant) -> None:
    client = _make_client()
    coordinator = NetworkCoordinator(hass, client)

    data = await coordinator._async_update_data()

    assert len(data["adapters"]) == 1
    assert data["connected_count"] == 1
    client.get_network_data.assert_awaited_once()


# TS-17: Network fetch failure raises UpdateFailed
async def test_network_fetch_failure(hass: HomeAssistant) -> None:
    client = _make_client(error=DeviceUnavailable("Connection refused"))
    coordinator = NetworkCoordinator(hass, client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
