"""Tests for TP-Link Powerline button entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_HOST, CONF_NAME

from custom_components.tplink_powerline.button import RebootButton


def _make_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {CONF_HOST: "192.168.1.34", CONF_NAME: "Powerline Network"}
    return entry


# TS-11: Reboot button sends command
async def test_reboot_button_press() -> None:
    client = AsyncMock()
    button = RebootButton(client, _make_entry())

    await button.async_press()

    client.send_command.assert_awaited_once_with("reboot")
