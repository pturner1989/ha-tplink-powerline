"""Common fixtures for TP-Link Powerline tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.loader import DATA_CUSTOM_COMPONENTS


@pytest.fixture(autouse=True)
def enable_custom_integrations(hass: HomeAssistant) -> None:
    """Enable custom integrations in the test HA instance."""
    hass.data.pop(DATA_CUSTOM_COMPONENTS)


@pytest.fixture
def mock_ping_success():
    """Mock a successful ping."""
    with patch(
        "custom_components.tplink_powerline.config_flow.async_ping",
        return_value=True,
    ) as mock:
        yield mock


@pytest.fixture
def mock_ping_failure():
    """Mock a failed ping."""
    with patch(
        "custom_components.tplink_powerline.config_flow.async_ping",
        return_value=False,
    ) as mock:
        yield mock


@pytest.fixture
def mock_setup() -> Generator[MagicMock]:
    """Stub entry setup/unload so reloads can be observed without I/O."""
    with (
        patch(
            "custom_components.tplink_powerline.async_setup_entry",
            return_value=True,
        ) as setup,
        patch(
            "custom_components.tplink_powerline.async_unload_entry",
            return_value=True,
        ),
    ):
        yield setup


@pytest.fixture(autouse=True)
def mock_arp() -> Generator[MagicMock]:
    """Keep tests off the real ARP table; returns no MAC unless a test sets one."""
    with patch(
        "custom_components.tplink_powerline.device.get_mac_address",
        return_value=None,
    ) as mock:
        yield mock
