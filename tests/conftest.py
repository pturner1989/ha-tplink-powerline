"""Common fixtures for TP-Link Powerline tests."""

from __future__ import annotations

from unittest.mock import patch

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
