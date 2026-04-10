"""Tests for the TP-Link Powerline coordinator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.tplink_powerline.coordinator import TplinkPowerlineCoordinator


def _make_entry(host: str = "192.168.1.34") -> MagicMock:
    """Create a mock config entry."""
    entry = MagicMock()
    entry.data = {CONF_HOST: host, CONF_NAME: "Powerline Network"}
    return entry


def _mock_process(returncode: int) -> AsyncMock:
    """Create a mock subprocess with a given return code."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.wait = AsyncMock()
    return proc


async def test_successful_ping_resets_failure_count(hass: HomeAssistant) -> None:
    """Test that a successful ping resets the failure counter."""
    coordinator = TplinkPowerlineCoordinator(hass, _make_entry())
    coordinator.failure_count = 3

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        data = await coordinator._async_update_data()

    assert coordinator.failure_count == 0
    assert data["available"] is True


async def test_failed_ping_increments_failure_count(hass: HomeAssistant) -> None:
    """Test that a failed ping increments the failure counter."""
    coordinator = TplinkPowerlineCoordinator(hass, _make_entry())
    coordinator.failure_count = 0

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(1),
    ):
        data = await coordinator._async_update_data()

    assert coordinator.failure_count == 1
    assert data["available"] is True


async def test_failure_threshold_reached(hass: HomeAssistant) -> None:
    """Test that reaching the failure threshold marks device unavailable."""
    coordinator = TplinkPowerlineCoordinator(hass, _make_entry())
    coordinator.failure_count = 7

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(1),
    ):
        data = await coordinator._async_update_data()

    assert coordinator.failure_count == 8
    assert data["available"] is False


async def test_recovery_after_threshold(hass: HomeAssistant) -> None:
    """Test that a successful ping after threshold immediately recovers."""
    coordinator = TplinkPowerlineCoordinator(hass, _make_entry())
    coordinator.failure_count = 8

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        return_value=_mock_process(0),
    ):
        data = await coordinator._async_update_data()

    assert coordinator.failure_count == 0
    assert data["available"] is True


async def test_subprocess_exception_treated_as_failure(
    hass: HomeAssistant,
) -> None:
    """Test that an OSError from subprocess is treated as a failed ping."""
    coordinator = TplinkPowerlineCoordinator(hass, _make_entry())
    coordinator.failure_count = 0

    with patch(
        "custom_components.tplink_powerline.coordinator.asyncio.create_subprocess_exec",
        side_effect=OSError("Permission denied"),
    ):
        data = await coordinator._async_update_data()

    assert coordinator.failure_count == 1
    assert data["available"] is True
