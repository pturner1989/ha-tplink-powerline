"""Config flow for TP-Link Powerline integration."""

from __future__ import annotations

import asyncio
import hashlib
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import AuthenticationError, DeviceUnavailable, PowerlineClient
from .const import CONF_PASSWORD_HASH, DEFAULT_NAME, DOMAIN, PING_TIMEOUT

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_PASSWORD, default=""): str,
    }
)


async def async_ping(host: str) -> bool:
    """Ping a host and return True if reachable."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping",
            "-c",
            "1",
            "-W",
            str(PING_TIMEOUT),
            host,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0
    except OSError:
        _LOGGER.warning("Failed to execute ping command for %s", host)
        return False


class TplinkPowerlineConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TP-Link Powerline."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            if not await async_ping(host):
                errors["base"] = "cannot_connect"
            else:
                password = user_input.get(CONF_PASSWORD, "")
                entry_data = {
                    CONF_HOST: host,
                    CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                }

                if password:
                    password_hash = hashlib.md5(
                        password.encode()
                    ).hexdigest()
                    client = PowerlineClient(
                        host,
                        password_hash,
                        async_get_clientsession(self.hass),
                    )
                    try:
                        await client.login()
                        await client.logout()
                        entry_data[CONF_PASSWORD_HASH] = password_hash
                    except AuthenticationError:
                        errors["base"] = "invalid_auth"
                    except (DeviceUnavailable, Exception):
                        _LOGGER.warning(
                            "HTTP validation failed for %s, "
                            "continuing without HTTP features",
                            host,
                        )

                if not errors:
                    return self.async_create_entry(
                        title=entry_data[CONF_NAME],
                        data=entry_data,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
