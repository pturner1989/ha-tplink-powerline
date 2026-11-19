"""Config flow for TP-Link Powerline integration."""

from __future__ import annotations

import asyncio
import hashlib
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import (
    AuthenticationError,
    DeviceUnavailable,
    IncompatibleDevice,
    PowerlineClient,
)
from .const import CONF_PASSWORD_HASH, DEFAULT_NAME, DOMAIN, PING_TIMEOUT
from .device import normalize_mac

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
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._user_input: dict[str, str] | None = None

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            self._async_abort_entries_match({CONF_HOST: host})
            mac: str | None = None

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
                        mac = await self._async_fetch_mac(client)
                        await client.logout()
                        entry_data[CONF_PASSWORD_HASH] = password_hash
                    except AuthenticationError:
                        errors["base"] = "invalid_auth"
                    except IncompatibleDevice:
                        _LOGGER.warning(
                            "Device at %s has an incompatible web portal",
                            host,
                        )
                        await self.async_set_unique_id(host)
                        self._abort_if_unique_id_configured()
                        self._user_input = entry_data
                        return await self.async_step_confirm_ping_only()
                    except Exception:
                        _LOGGER.warning(
                            "HTTP validation failed for %s, "
                            "continuing without HTTP features",
                            host,
                            exc_info=True,
                        )

                if not errors:
                    if mac:
                        # A known adapter at a new address updates the
                        # existing entry instead of creating a duplicate.
                        await self.async_set_unique_id(mac)
                        self._abort_if_unique_id_configured(
                            updates={CONF_HOST: host}
                        )
                    else:
                        await self.async_set_unique_id(host)
                        self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=entry_data[CONF_NAME],
                        data=entry_data,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    async def _async_fetch_mac(client: PowerlineClient) -> str | None:
        """Read the adapter MAC; failures fall back to host-based identity."""
        try:
            info = await client.get_device_info()
        except Exception:  # noqa: BLE001 - MAC is optional at this stage
            _LOGGER.debug("Could not read MAC from %s", client.host, exc_info=True)
            return None
        if not isinstance(info, dict):
            return None
        return normalize_mac(info.get("mac"))

    async def async_step_confirm_ping_only(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Handle the incompatible device confirmation step."""
        if user_input is not None:
            # User confirmed — create entry in ping-only mode (no password hash)
            return self.async_create_entry(
                title=self._user_input[CONF_NAME],
                data=self._user_input,
            )

        return self.async_show_form(step_id="confirm_ping_only")
