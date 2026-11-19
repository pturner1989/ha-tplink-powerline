"""Device identity helpers for the TP-Link Powerline integration.

The root device is keyed by the config entry ID rather than the host, so the
adapter keeps its device (and entity history) when its IP address changes.
The MAC address, when known, is attached as a network connection so Home
Assistant's DHCP watcher can recognise the adapter at a new address. It comes
from the web portal when a password is configured, otherwise from the host's
ARP table (which only works when HA and the adapter share a network segment).
"""

from __future__ import annotations

from functools import partial
from ipaddress import IPv6Address, ip_address
import logging
from string import hexdigits

from getmac import get_mac_address

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, format_mac

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_NULL_MAC = "00:00:00:00:00:00"


def root_device_identifier(entry: ConfigEntry) -> tuple[str, str]:
    """Return the device registry identifier for an entry's root adapter."""
    return (DOMAIN, entry.entry_id)


def root_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return DeviceInfo linking an entity to the entry's root adapter."""
    return DeviceInfo(identifiers={root_device_identifier(entry)})


def normalize_mac(raw: object) -> str | None:
    """Normalise a MAC address to HA's lowercase colon form, or None if invalid."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    mac = format_mac(raw.strip())
    octets = mac.split(":")
    if (
        len(octets) != 6
        or any(len(o) != 2 or not all(c in hexdigits for c in o) for o in octets)
        or mac == _NULL_MAC
    ):
        return None
    return mac


def is_ip_address(host: str) -> bool:
    """Return True if host is an IP literal rather than a hostname."""
    try:
        ip_address(host)
    except ValueError:
        return False
    return True


async def async_mac_from_arp(hass: HomeAssistant, host: str) -> str | None:
    """Look up the adapter's MAC in the ARP/neighbour table, or None.

    Only works when the adapter is on the same network segment as Home
    Assistant; across subnets/VLANs or from a bridged container it finds
    nothing and callers fall back to host-based identity.
    """
    try:
        addr = ip_address(host)
    except ValueError:
        kwargs = {"hostname": host}
    else:
        kwargs = {"ip6": host} if isinstance(addr, IPv6Address) else {"ip": host}
    try:
        raw = await hass.async_add_executor_job(partial(get_mac_address, **kwargs))
    except Exception:  # noqa: BLE001 - getmac failures just mean "unknown"
        _LOGGER.debug("ARP lookup failed for %s", host, exc_info=True)
        return None
    return normalize_mac(raw)
