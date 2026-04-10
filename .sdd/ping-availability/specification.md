# Specification: Ping Availability

**Version:** 1.0
**Date:** 2026-04-10
**Status:** Draft

---

## Problem Statement

Home Assistant has no integration for monitoring TP-Link powerline ethernet adapters. Users with powerline networks have no visibility into whether their powerline devices are online or offline, making it difficult to diagnose network issues. This first iteration establishes the integration skeleton and provides basic ping-based availability monitoring.

## Beneficiaries

**Primary:**
- Home Assistant users with TP-Link powerline networks who want to monitor device availability

**Secondary:**
- Home automation enthusiasts who want to trigger automations based on powerline network status (e.g., alert when the network drops)

---

## Outcomes

**Must Haves**
- A HACS-installable custom integration that registers under the `tplink_powerline` domain
- Users can add a powerline device by entering its IP address and a friendly name through the HA config flow UI
- A binary sensor that reflects whether the configured device responds to ICMP ping
- The binary sensor transitions to unavailable after sustained ping failures, not a single missed poll

**Nice-to-haves**
- Ping round-trip time exposed as a diagnostic attribute on the binary sensor

---

## Explicitly Out of Scope

- HTTP interface scraping for device status, link quality, or satellite device discovery — addressed in a future specification
- YAML-based configuration
- Auto-discovery of powerline devices on the network (mDNS, SSDP, etc.)
- Sensor entities for link rate, firmware version, uptime, or port count
- Any interaction with TP-Link cloud services

---

## Functional Requirements

**FR-001: HACS-compliant integration structure**
- Description: The integration must follow HACS repository conventions with a valid `hacs.json`, `manifest.json` (iot_class `local_polling`), and be installable via HACS as a custom repository
- Acceptance criteria: The repository can be added to HACS as a custom integration repository and installed without errors
- Failure/edge cases: Missing or malformed metadata files cause HACS validation to fail

**FR-002: UI config flow with IP and friendly name**
- Description: The integration provides a config flow that prompts the user for the device IP address (or hostname) and a friendly name. The friendly name field defaults to "Powerline Network". The config flow validates the device is reachable by pinging it before creating the config entry.
- Acceptance criteria: User can add the integration via Settings > Devices & Services, enter an IP and optional name, and a config entry is created after successful ping validation. If the ping fails during setup, the user sees an error and can retry.
- Failure/edge cases: Invalid IP format rejected with a form error. Unreachable IP rejected after ping timeout with a "cannot connect" error. Duplicate IP address rejected if a config entry already exists for that IP.

**FR-003: Binary sensor for ping-based availability**
- Description: Each config entry creates a binary sensor entity representing whether the powerline device responds to ICMP ping. The sensor uses the device class `connectivity`.
- Acceptance criteria: After setup, a binary sensor entity appears under the device. It shows "Connected" when the device responds to ping, "Disconnected" when it does not.
- Failure/edge cases: If the ping subprocess fails for a non-network reason (e.g., permission denied), the sensor should log the error and treat it as a failed ping.

**FR-004: Polling interval and failure threshold**
- Description: The integration pings the device every 15 seconds. The binary sensor transitions to "Disconnected" only after 8 consecutive failed pings (2 minutes of sustained failure). It transitions back to "Connected" on the first successful ping.
- Acceptance criteria: A single dropped ping does not change the sensor state. After 8 consecutive failures the sensor reads "Disconnected". One successful ping after failures immediately restores "Connected".
- Failure/edge cases: If the coordinator itself errors (e.g., event loop blocked), the failure counter should still increment.

**FR-005: Device registry entry**
- Description: Each config entry registers a device in the HA device registry with the friendly name provided during setup, manufacturer "TP-Link", and a model placeholder of "Powerline Adapter".
- Acceptance criteria: The device appears in Settings > Devices & Services under the TP-Link Powerline integration with the correct name and manufacturer.
- Failure/edge cases: N/A

**FR-006: Integration setup and teardown**
- Description: The integration sets up the coordinator and entities when a config entry is loaded, and cleanly tears down (cancels polling) when a config entry is removed or HA shuts down. If the device is unreachable at startup, the integration should raise `ConfigEntryNotReady` so HA retries automatically.
- Acceptance criteria: Adding the integration starts polling. Removing it stops polling. Restarting HA with an unreachable device results in periodic retry until the device comes back.
- Failure/edge cases: Removing a config entry while a ping is in-flight must not raise an unhandled exception.

---

## QA Plan

**QA-01: Successful setup and binary sensor appears**
- Goal: Validate the full setup flow and entity creation
- Steps:
  1. Install the integration via HACS
  2. Go to Settings > Devices & Services > Add Integration
  3. Search for "TP-Link Powerline"
  4. Enter IP address `192.168.1.34` and leave the name as "Powerline Network"
  5. Submit the form
- Expected: Config entry created successfully. A device "Powerline Network" appears with manufacturer "TP-Link". A binary sensor entity shows "Connected".

**QA-02: Setup rejects unreachable device**
- Goal: Validate config flow error handling
- Steps:
  1. Go to Settings > Devices & Services > Add Integration
  2. Search for "TP-Link Powerline"
  3. Enter IP address `192.168.1.99` (an IP with no device)
  4. Submit the form
- Expected: An error message indicates the device could not be reached. The config entry is not created. The user can correct the IP and retry.

**QA-03: Binary sensor reflects device going offline**
- Goal: Validate the failure threshold and recovery behavior
- Steps:
  1. With a working config entry for `192.168.1.34`, observe the binary sensor is "Connected"
  2. Disconnect or block the powerline adapter from the network
  3. Wait at least 2 minutes (8 x 15 second polls)
  4. Observe the binary sensor transitions to "Disconnected"
  5. Reconnect the powerline adapter
  6. Wait up to 15 seconds
- Expected: The sensor stays "Connected" during the first few missed pings. After ~2 minutes it shows "Disconnected". After reconnecting, it returns to "Connected" within one poll cycle.

**QA-04: Duplicate device rejected**
- Goal: Validate uniqueness constraint
- Steps:
  1. With a working config entry for `192.168.1.34`
  2. Attempt to add the integration again with the same IP
- Expected: The config flow rejects the entry, indicating this device is already configured.

---

## Open Questions

None.

---

## Appendix

### Glossary
- **Powerline adapter:** A networking device that transmits Ethernet data over electrical wiring
- **Root device:** The powerline adapter physically connected to the router, typically the only one directly reachable via IP from the LAN
- **Satellite device:** Powerline adapters elsewhere in the electrical network, reachable only through the root device's management portal
- **HACS:** Home Assistant Community Store — a third-party integration manager for Home Assistant

### References
- [HACS custom repository requirements](https://hacs.xyz/docs/publish/integration)
- [HA integration development docs](https://developers.home-assistant.io/docs/creating_integration_manifest)
- [HA DataUpdateCoordinator pattern](https://developers.home-assistant.io/docs/integration_fetching_data)

### Change History
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-10 | Pete | Initial specification |
