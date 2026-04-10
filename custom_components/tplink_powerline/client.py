"""HTTP client for TP-Link powerline device local web portal."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import CONTENT_TYPE, HTTP_TIMEOUT

_LOGGER = logging.getLogger(__name__)

# Device API error codes
_ERROR_AUTH = ("003", "004", "005")
_ERROR_WRONG_PASSWORD = "006"
_ERROR_SESSION_FULL = "008"


class AuthenticationError(Exception):
    """Raised when authentication fails."""


class DeviceUnavailable(Exception):
    """Raised when the device is unreachable."""


class UnexpectedResponse(Exception):
    """Raised when the device returns an unparseable response."""


def _parse_response(text: str) -> tuple[str, dict[str, str]]:
    """Parse a device response into error code and key-value data."""
    data: dict[str, str] = {}
    error_code = ""
    for line in text.strip().split("\n"):
        line = line.strip().rstrip("\r")
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "ERROR":
            error_code = value
        else:
            data[key] = value
    return error_code, data


class PowerlineClient:
    """Client for the TP-Link powerline device HTTP portal."""

    def __init__(
        self,
        host: str,
        password_hash: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the client."""
        self.host = host
        self.password_hash = password_hash
        self._session = session
        self.token: str | None = None

    @property
    def _base_url(self) -> str:
        return f"http://{self.host}/"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": CONTENT_TYPE,
            "Referer": self._base_url,
        }

    async def login(self) -> None:
        """Authenticate with the device and obtain a session token."""
        body = f"TPLINK.GENERAL.LOGIN_PASSWORD={self.password_hash}"
        try:
            async with self._session.post(
                self._base_url,
                data=body.encode("ascii"),
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                text = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise DeviceUnavailable(
                f"Cannot connect to {self.host}"
            ) from err

        error_code, data = _parse_response(text)

        if error_code == "000":
            self.token = data.get("TOKEN")
            if not self.token:
                raise UnexpectedResponse("Login succeeded but no token returned")
            _LOGGER.debug("Logged in to %s", self.host)
            return

        if error_code == _ERROR_WRONG_PASSWORD:
            raise AuthenticationError("Wrong password")
        if error_code == _ERROR_SESSION_FULL:
            raise AuthenticationError("Session full")

        raise DeviceUnavailable(f"Login failed with error code {error_code}")

    async def logout(self) -> None:
        """End the session with the device."""
        if not self.token:
            return
        try:
            async with self._session.post(
                self._base_url,
                data=f"_t={self.token}&COMMAND=logout".encode("ascii"),
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                await resp.text()
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.debug("Logout request failed for %s", self.host)
        finally:
            self.token = None

    async def get_data(self, keys: list[str]) -> dict[str, str]:
        """Fetch data keys from the device."""
        if not self.token:
            raise DeviceUnavailable("Not logged in")

        data = await self._do_get(keys)
        return data

    async def _do_get(
        self, keys: list[str], *, retry_auth: bool = True
    ) -> dict[str, str]:
        """Execute a GET request for the given keys, with optional re-auth retry."""
        query_params = f"_t={self.token}&" + "&".join(f"{k}=" for k in keys)
        url = f"{self._base_url}?{query_params}"

        try:
            async with self._session.get(
                url,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                text = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise DeviceUnavailable(
                f"Cannot connect to {self.host}"
            ) from err

        if "<html" in text.lower():
            raise UnexpectedResponse("Device returned HTML instead of data")

        error_code, data = _parse_response(text)

        if error_code == "000":
            return data

        if error_code in _ERROR_AUTH and retry_auth:
            _LOGGER.debug("Session expired for %s, re-authenticating", self.host)
            await self.login()
            return await self._do_get(keys, retry_auth=False)

        raise UnexpectedResponse(
            f"Data fetch failed with error code {error_code}"
        )

    async def get_device_info(self) -> dict[str, str]:
        """Fetch device model, firmware, and hardware version."""
        data = await self.get_data([
            "SYSTEM.PRODUCTION.HW_PRODUCT",
            "SYSTEM.PRODUCTION.HW_REVISION",
            "SYSTEM.GENERAL.FW_VERSION",
        ])
        return {
            "model": data.get("SYSTEM.PRODUCTION.HW_PRODUCT", "Unknown"),
            "firmware": data.get("SYSTEM.GENERAL.FW_VERSION", "Unknown"),
            "hardware": data.get("SYSTEM.PRODUCTION.HW_REVISION", "Unknown"),
        }

    async def get_network_name(self) -> str:
        """Fetch the powerline network name."""
        data = await self.get_data(["NODE.GENERAL.DOMAIN_NAME"])
        return data.get("NODE.GENERAL.DOMAIN_NAME", "Unknown")

    async def get_network_data(self) -> dict[str, Any]:
        """Fetch powerline adapter list and link rates."""
        data = await self.get_data([
            "DIDMNG.GENERAL.MACS",
            "DIDMNG.GENERAL.RX_BPS",
            "DIDMNG.GENERAL.TX_BPS",
            "SYSTEM.PRODUCTION.MAC_ADDR",
        ])

        root_mac = data.get("SYSTEM.PRODUCTION.MAC_ADDR", "").upper().replace(":", "-")
        macs_raw = data.get("DIDMNG.GENERAL.MACS", "")
        rx_raw = data.get("DIDMNG.GENERAL.RX_BPS", "")
        tx_raw = data.get("DIDMNG.GENERAL.TX_BPS", "")

        macs = [m.strip().upper().replace(":", "-") for m in macs_raw.split(",") if m.strip()]
        rx_vals = [int(v) if v.strip().isdigit() else 0 for v in rx_raw.split(",")]
        tx_vals = [int(v) if v.strip().isdigit() else 0 for v in tx_raw.split(",")]

        null_mac = "00-00-00-00-00-00"
        adapters = []
        connected_count = 0

        for i, mac in enumerate(macs):
            if mac == null_mac or mac == root_mac or not mac:
                continue
            rx = rx_vals[i] // 32 if i < len(rx_vals) else 0
            tx = tx_vals[i] // 32 if i < len(tx_vals) else 0
            adapters.append({"mac": mac, "tx_rate": tx, "rx_rate": rx})
            if tx > 0 or rx > 0:
                connected_count += 1

        return {
            "adapters": adapters,
            "connected_count": connected_count,
            "root_mac": root_mac,
        }
