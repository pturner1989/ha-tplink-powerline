"""Config flow for TP-Link Powerline integration."""

from __future__ import annotations

import asyncio
import hashlib
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .client import (
    AuthenticationError,
    DeviceUnavailable,
    IncompatibleDevice,
    PowerlineClient,
)
from .const import CONF_PASSWORD_HASH, DEFAULT_NAME, DOMAIN, PING_TIMEOUT
from .device import async_mac_from_arp, is_ip_address, normalize_mac

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
                        await self._async_set_identity(
                            host, await async_mac_from_arp(self.hass, host)
                        )
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
                    if mac is None:
                        mac = await async_mac_from_arp(self.hass, host)
                    await self._async_set_identity(host, mac)
                    return self.async_create_entry(
                        title=entry_data[CONF_NAME],
                        data=entry_data,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Follow a configured adapter to the address HA's DHCP watcher saw.

        The manifest only matches MACs already registered to this domain, so
        this updates existing entries and never offers new ones.
        """
        mac = normalize_mac(discovery_info.macaddress)
        if mac is None:
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(mac)
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN, mac
        )
        if entry is not None and not is_ip_address(entry.data[CONF_HOST]):
            # The user chose a hostname, which already follows the adapter.
            self._abort_if_unique_id_configured()
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: discovery_info.ip}
        )
        return self.async_abort(reason="not_supported")

    async def async_step_reconfigure(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Point an existing entry at the adapter's new address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if self._host_used_by_other_entry(host, entry.entry_id):
                errors["base"] = "host_in_use"
            elif not await async_ping(host):
                errors["base"] = "cannot_connect"
            else:
                unique_id, error = await self._async_verify_reconfigure_host(
                    entry, host
                )
                if error:
                    errors["base"] = error
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=unique_id,
                        data_updates={CONF_HOST: host},
                    )

        current_host = user_input[CONF_HOST] if user_input else entry.data[CONF_HOST]
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=current_host): str}
            ),
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    async def _async_set_identity(self, host: str, mac: str | None) -> None:
        """Set the flow's unique ID, aborting if the adapter is already set up.

        A known adapter (by MAC) at a new address updates the existing entry's
        host instead of creating a duplicate.
        """
        if mac:
            await self.async_set_unique_id(mac)
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        else:
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

    def _host_used_by_other_entry(self, host: str, entry_id: str) -> bool:
        """Return True if another entry already uses this host."""
        return any(
            other.entry_id != entry_id
            and (other.data.get(CONF_HOST) == host or other.unique_id == host)
            for other in self._async_current_entries(include_ignore=True)
        )

    async def _async_verify_reconfigure_host(
        self, entry: ConfigEntry, host: str
    ) -> tuple[str | None, str | None]:
        """Check the new host is this entry's adapter.

        Returns (unique_id, error). Aborts with ``wrong_device`` if the
        adapter at the new host has a different MAC. The MAC comes from the
        web portal when a password is stored, falling back to the ARP table.
        """
        entry_mac = normalize_mac(entry.unique_id)
        password_hash = entry.data.get(CONF_PASSWORD_HASH)
        mac: str | None = None

        if password_hash:
            client = PowerlineClient(
                host, password_hash, async_get_clientsession(self.hass)
            )
            try:
                await client.login()
            except AuthenticationError:
                return None, "invalid_auth"
            except Exception:  # noqa: BLE001 - any portal failure means unreachable
                _LOGGER.debug(
                    "Reconfigure login failed for %s", host, exc_info=True
                )
                return None, "cannot_connect"
            try:
                mac = await self._async_fetch_mac(client)
            finally:
                await client.logout()

        if entry_mac is None:
            # Entry not yet keyed by MAC; setup adopts it once the MAC is read.
            return host, None
        if mac is None:
            mac = await async_mac_from_arp(self.hass, host)
        if mac is None:
            if password_hash:
                return None, "cannot_verify"
            # Ping-only identity can only be checked via ARP, which doesn't
            # work across subnets; trust the user's explicit choice.
            return entry.unique_id, None

        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_mismatch(reason="wrong_device")
        return mac, None

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
