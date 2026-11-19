"""Device identity helpers for the TP-Link Powerline integration.

The root device is keyed by the config entry ID rather than the host, so the
adapter keeps its device (and entity history) when its IP address changes.
The MAC address, when known, is attached as a network connection so Home
Assistant's DHCP watcher can recognise the adapter at a new address.
"""

from __future__ import annotations

from string import hexdigits

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo, format_mac

from .const import DOMAIN

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
