# Specification: Powerline Network Monitoring

**Version:** 1.0
**Date:** 2026-04-10
**Status:** Implemented

---

## Problem Statement

Users with TP-Link powerline networks have no visibility into the link quality between their powerline adapters or whether remote adapters are connected. The device's HTTP portal exposes real-time TX/RX link rates and MAC addresses for all adapters on the powerline network, but the integration doesn't use this data. Without monitoring, users can't detect degraded powerline performance or dropped adapters until they experience connectivity problems.

## Beneficiaries

**Primary:**
- Home Assistant users who want to monitor the health and performance of their powerline network

**Secondary:**
- Users who want to automate alerts when powerline link quality degrades or a remote adapter goes offline

---

## Outcomes

**Must Haves**
- Each remote powerline adapter is represented as a separate HA device, identified by its MAC address
- TX and RX link rate sensors (in Mbps) for each remote adapter, polled every 60 seconds
- A binary connectivity sensor per remote adapter (connected when link rates are non-zero)
- A sensor on the root device showing the count of connected remote adapters
- A diagnostic sensor on the root device showing the powerline network name

**Nice-to-haves**
- None

---

## Explicitly Out of Scope

- Configuring or renaming remote adapters via the HTTP portal
- Pairing/unpairing powerline adapters
- Ethernet port status on the root device (LAN link speed/duplex)
- Historical link quality trending or averaging
- Changing the powerline network name or password

---

## Functional Requirements

**FR-001: Discover remote powerline adapters**
- Description: The integration fetches `DIDMNG.GENERAL.NUM_DIDS`, `DIDMNG.GENERAL.MACS`, `DIDMNG.GENERAL.RX_BPS`, and `DIDMNG.GENERAL.TX_BPS` from the device portal. It filters out the root device's own MAC (from `SYSTEM.PRODUCTION.MAC_ADDR`) and any null MACs (`00:00:00:00:00:00`) to identify remote adapters. Each remote adapter is identified by its MAC address.
- Acceptance criteria: With one remote adapter connected, the integration discovers it and creates a device for it. With zero remote adapters, no extra devices are created.
- Failure/edge cases: If the HTTP portal is unavailable (no password configured or auth failed), no remote adapter discovery occurs. If NUM_DIDS changes between polls (adapter added/removed), the integration updates the adapter list. MAC arrays and rate arrays are comma-separated and positionally correlated (index N in MACS corresponds to index N in RX_BPS and TX_BPS).

**FR-002: Register remote adapters as HA devices**
- Description: Each discovered remote adapter is registered as a separate device in the HA device registry. The device is identified by its MAC address, named "Powerline Adapter {MAC}", with manufacturer "TP-Link" and model "Powerline Adapter". The remote adapter device is linked to the root device via `via_device`.
- Acceptance criteria: Remote adapter devices appear in Settings > Devices & Services under the TP-Link Powerline integration, linked to the root device. The device name includes the MAC address for identification.
- Failure/edge cases: If a remote adapter disappears from the network (no longer in MACS list), its entities become unavailable but the device remains in the registry (user can manually remove it).

**FR-003: TX and RX link rate sensors per remote adapter**
- Description: Each remote adapter has two sensors: TX link rate and RX link rate, expressed in Mbps. The raw values from the device are divided by 32 to convert to Mbps (matching the device's own web UI conversion). These sensors are polled every 60 seconds.
- Acceptance criteria: For the test device with one remote adapter showing RX ~317 Mbps and TX ~366 Mbps, the sensors display values in that range. Values update every 60 seconds. Unit of measurement is "Mbps".
- Failure/edge cases: If the adapter disconnects, rates drop to 0. If the HTTP fetch fails, sensors become unavailable. Rate values are integers (floor division).

**FR-004: Binary connectivity sensor per remote adapter**
- Description: Each remote adapter has a binary sensor with device class `connectivity` that shows whether the adapter is connected to the powerline network. The adapter is considered connected if either its TX or RX rate is non-zero.
- Acceptance criteria: A connected adapter shows "Connected". An adapter with both TX and RX at 0 shows "Disconnected". Recovery is immediate on the next poll when rates become non-zero.
- Failure/edge cases: If the adapter's MAC disappears entirely from the MACS list, the binary sensor becomes unavailable (not just disconnected).

**FR-005: Connected adapters count sensor on root device**
- Description: A sensor on the root device shows the number of currently connected remote adapters. An adapter is counted as connected if either its TX or RX rate is non-zero.
- Acceptance criteria: With one connected remote adapter, the sensor reads 1. With no remote adapters, it reads 0. The sensor updates every 60 seconds.
- Failure/edge cases: If HTTP fetch fails, the sensor becomes unavailable.

**FR-006: Powerline network name diagnostic sensor**
- Description: A diagnostic sensor on the root device shows the powerline network name from `NODE.GENERAL.DOMAIN_NAME`. This is fetched once at setup (alongside device info), not polled.
- Acceptance criteria: The sensor displays the network name. It uses the diagnostic entity category.
- Failure/edge cases: If the network name is unavailable, the sensor shows "Unknown".

**FR-007: Polling at 60-second interval for link data**
- Description: The powerline network data (adapter list, link rates) is polled every 60 seconds via the existing HTTP client session. This is separate from the 15-second ping polling. If the HTTP session has been invalidated, the client re-authenticates before fetching.
- Acceptance criteria: Link rate sensors update every 60 seconds. The polling does not interfere with the ping-based availability monitoring.
- Failure/edge cases: If the HTTP fetch fails transiently, the coordinator retries on the next cycle. Persistent failures cause entities to become unavailable. The existing ping coordinator continues independently.

---

## QA Plan

**QA-01: Remote adapter discovered and sensors appear**
- Goal: Validate full discovery and entity creation
- Steps:
  1. Set up the integration with IP `192.168.1.34`, password ``<password>``
  2. Wait for setup to complete
  3. Check Settings > Devices & Services
- Expected: Two devices: "Powerline Network" (root) and "Powerline Adapter 58:04:4F:D8:20:2D" (remote). Remote device has TX rate, RX rate, and connectivity sensors. Root device has connected adapters count sensor and network name sensor.

**QA-02: Link rate sensors show correct values**
- Goal: Validate link rate conversion and updates
- Steps:
  1. With both adapters connected, check TX and RX sensors on the remote adapter
  2. Wait 60 seconds for a poll update
- Expected: TX and RX sensors show values in the hundreds of Mbps range (e.g., ~317 and ~366). Values update after 60 seconds.

**QA-03: Remote adapter going offline**
- Goal: Validate offline detection
- Steps:
  1. With a connected remote adapter, unplug it from the electrical outlet
  2. Wait up to 60 seconds
- Expected: Remote adapter's connectivity sensor shows "Disconnected". TX and RX rates drop to 0. Connected adapters count on root device drops by 1.

**QA-04: No password configured (ping-only mode)**
- Goal: Validate no network monitoring without HTTP access
- Steps:
  1. Set up the integration without a password
- Expected: Only the root device with the ping binary sensor. No remote adapter devices, no link rate sensors, no connected count sensor.

---

## Open Questions

None.

---

## Appendix

### Glossary
- **Remote adapter / satellite:** A powerline adapter elsewhere on the electrical network, visible to the root device via the powerline link
- **Root device:** The powerline adapter connected to the router, directly reachable via IP from the LAN
- **TX rate:** Transmission link rate from the root device to the remote adapter, in Mbps
- **RX rate:** Receive link rate from the remote adapter to the root device, in Mbps
- **DID:** Device ID — the device's internal term for a powerline adapter on the network

### Device API Data Format
```
DIDMNG.GENERAL.NUM_DIDS = 2
DIDMNG.GENERAL.MACS = 00:00:00:00:00:00,58:04:4f:d8:20:2d,b8:fb:b3:b6:dd:df
DIDMNG.GENERAL.RX_BPS = 0,10151,0
DIDMNG.GENERAL.TX_BPS = 0,11733,0
SYSTEM.PRODUCTION.MAC_ADDR = b8:fb:b3:b6:dd:df
NODE.GENERAL.DOMAIN_NAME = tJ99snLMMDmuPU7UN6WJ8wa08wdBsSvy
```
- MACS, RX_BPS, TX_BPS are comma-separated, positionally correlated
- Raw BPS values divide by 32 to get Mbps
- NUM_DIDS includes the root device (JS subtracts 1 for display)
- First entry (00:00:00:00:00:00) is a placeholder and should be filtered out
- Root device's own MAC appears in the list and should be filtered out

### References
- Reverse-engineered HTTP API documented in project memory (`project_device_http_api.md`)
- [HA sensor device class](https://developers.home-assistant.io/docs/core/entity/sensor)

### Change History
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-10 | Pete | Initial specification |
