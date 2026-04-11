# Specification: Device Controls and Status

**Version:** 1.0
**Date:** 2026-04-10
**Status:** Draft

---

## Problem Statement

The integration provides monitoring but no control over the powerline device. Users cannot toggle LEDs, reboot the device, change QoS priority, or check ethernet port status from Home Assistant. These are all available through the device's local HTTP portal but not exposed to HA, forcing users to open the web UI for basic device management.

## Beneficiaries

**Primary:**
- Home Assistant users who want to control their powerline adapter and automate device management (e.g., turn off LEDs at night, reboot on a schedule, switch QoS mode based on activity)

**Secondary:**
- Users diagnosing network issues who need to check ethernet port status without opening the device web UI

---

## Outcomes

**Must Haves**
- LED on/off switch entity that toggles the device's LEDs
- LED night mode controls: enable/disable switch and start/end time configuration
- Reboot button entity to trigger an immediate device reboot
- Reboot schedule controls: enable/disable, time, and repeat cycle configuration
- QoS mode select entity with fair/gaming/streaming/voice options
- Per-ethernet-port binary sensors showing connected/disconnected status with link speed attributes

**Nice-to-haves**
- None

---

## Explicitly Out of Scope

- Firmware update functionality
- Changing the device login password
- Factory reset
- Powerline pairing/unpairing (soft pair)
- Compatibility mode (MIMO/SISO) settings
- Power saving mode settings
- Changing LAN IP settings

---

## Functional Requirements

**FR-001: LED on/off switch**
- Description: A switch entity that controls the device's LED enable state via `TPLINK.LEDSCHEDULE.LED_ENABLE`. When turned off, all LEDs on the device are disabled. When turned on, LEDs resume normal operation.
- Acceptance criteria: Toggling the switch in HA changes the LED state on the physical device. The switch reflects the current state when polled.
- Failure/edge cases: If the HTTP write fails, the switch state should revert. The switch should read the current state at setup and on each poll.

**FR-002: LED night mode switch**
- Description: A switch entity that controls the LED night mode schedule via `TPLINK.LEDSCHEDULE.ENABLE`. When enabled, LEDs turn off automatically during the scheduled time window.
- Acceptance criteria: Toggling the switch enables/disables the night mode schedule on the device.
- Failure/edge cases: The night mode schedule times (start/end) are independent of the enable toggle. Disabling night mode does not clear the schedule times.

**FR-003: LED night mode start and end time**
- Description: Two time entities for the night mode start time and end time. The start time is when LEDs turn off, the end time is when they turn back on. Times are stored as hour + minute on the device (`TPLINK.LEDSCHEDULE.START_HOUR`, `TPLINK.LEDSCHEDULE.START_MINUTE`, `TPLINK.LEDSCHEDULE.END_HOUR`, `TPLINK.LEDSCHEDULE.END_MINUTE`).
- Acceptance criteria: Setting the time in HA updates the device. For the test device, current values are 21:00 start, 06:00 end. The time entities display in HH:MM format.
- Failure/edge cases: Times are 24-hour format. The end time can be earlier than start time (overnight schedule, e.g., 21:00-06:00).

**FR-004: Reboot button**
- Description: A button entity that triggers an immediate device reboot when pressed. Sends `COMMAND=reboot` to the device. After pressing, the device will be unreachable for approximately 30-60 seconds.
- Acceptance criteria: Pressing the button causes the device to reboot. The ping binary sensor transitions to unavailable during reboot and recovers when the device comes back.
- Failure/edge cases: If the HTTP session is lost during reboot, the client re-authenticates when the device comes back. The button should require confirmation in the HA UI (standard HA button behavior). Multiple rapid presses should not cause issues (device ignores commands while rebooting).

**FR-005: Reboot schedule controls**
- Description: A switch to enable/disable scheduled reboot (`TPLINK.REBOOTSCHEDULE.ENABLE`), a time entity for the reboot time (`TPLINK.REBOOTSCHEDULE.HOUR`, `TPLINK.REBOOTSCHEDULE.MINUTE`), and a select entity for the repeat cycle (`TPLINK.REBOOTSCHEDULE.REPEAT`: 1=daily, 2=weekly, 3=monthly). When weekly or monthly, a number entity for the day (weekday 1-7 or month day 1-28).
- Acceptance criteria: Enabling the schedule and setting the time/cycle on HA updates the device. The current schedule settings are read at setup and reflected in the entities.
- Failure/edge cases: Day entity only applies when cycle is weekly or monthly. Daily cycle ignores the day value.

**FR-006: QoS mode select**
- Description: A select entity that shows and controls the QoS priority mode. The device supports four modes: fair (1), gaming (2), streaming (3), voice (4). Read via `COMMAND=get qos`, write via `COMMAND=set qos <mode_number>`.
- Acceptance criteria: Selecting a mode in HA sends the command to the device and the selection persists. The current mode is read at setup. For the test device, current mode is "fair" (1).
- Failure/edge cases: If the command fails, the select should revert to the previous value.

**FR-007: Ethernet port status sensors**
- Description: Binary sensor entities for each ethernet port on the device, showing connected/disconnected. Read via `COMMAND=lan link speed` which returns `PORT<N>=<status_code>`. Status codes: 0=disconnected, 1=10M half, 2=10M full, 3=100M half, 4=100M full, 5=1000M half, 6=1000M full. The link speed and duplex are exposed as attributes on the binary sensor.
- Acceptance criteria: For the test device, PORT1 shows disconnected, PORT2 shows connected with speed=1000 and duplex=full. Sensors update when cables are plugged/unplugged (on next poll).
- Failure/edge cases: The number of ports varies by model. The PG2400P has 2 ports. The integration should create sensors for all ports returned by the command. Port count is discovered dynamically.

**FR-008: Polling controls and settings state**
- Description: LED settings, QoS mode, ethernet port status, and reboot schedule are polled every 60 seconds alongside the existing network data. All control/status entities require HTTP access (password configured). Without a password, none of these entities are created.
- Acceptance criteria: Control entities reflect the current device state after each poll. Changes made via the device's web UI are picked up within 60 seconds.
- Failure/edge cases: If HTTP polling fails, control entities become unavailable but ping monitoring continues independently.

---

## QA Plan

**QA-01: LED controls**
- Goal: Validate LED switch and night mode controls
- Steps:
  1. Set up integration with IP `192.168.1.34`, password `test123`
  2. Find the LED switch entity and toggle it off
  3. Observe LEDs on the physical device turn off
  4. Toggle it back on
  5. Check the night mode switch and time entities show 21:00-06:00
- Expected: LED switch toggles the physical LEDs. Night mode shows current schedule.

**QA-02: QoS mode**
- Goal: Validate QoS select entity
- Steps:
  1. Find the QoS mode select entity, currently showing "Fair"
  2. Change it to "Gaming"
  3. Open the device web UI and verify QoS shows Gaming
  4. Change it back to "Fair"
- Expected: QoS mode changes on the device and is reflected in HA.

**QA-03: Ethernet port status**
- Goal: Validate per-port binary sensors
- Steps:
  1. Check ethernet port sensors
  2. PORT2 should show connected with speed 1000 Mbps
  3. PORT1 should show disconnected
- Expected: Port status matches physical connections. Speed/duplex in attributes.

**QA-04: Reboot button**
- Goal: Validate reboot triggers
- Steps:
  1. Press the reboot button entity
  2. Wait 30-60 seconds
  3. Observe device comes back online
- Expected: Device reboots. Ping sensor shows unavailable during reboot, then recovers.

**QA-05: No controls without password**
- Goal: Validate no control entities without HTTP access
- Steps:
  1. Set up integration without a password
- Expected: Only ping binary sensor exists. No LED, QoS, ethernet, or reboot entities.

---

## Open Questions

None.

---

## Appendix

### Glossary
- **Night mode:** LED schedule that turns off LEDs during a time window (e.g., 21:00-06:00)
- **QoS:** Quality of Service — prioritizes certain types of network traffic
- **Duplex:** Full duplex means simultaneous send/receive; half duplex means one direction at a time

### Device API Reference

**Standard key read/write (POST to `/` with `_t=TOKEN&KEY=VALUE`):**
| Key | Values | R/W |
|-----|--------|-----|
| TPLINK.LEDSCHEDULE.LED_ENABLE | YES/NO | R/W |
| TPLINK.LEDSCHEDULE.ENABLE | YES/NO | R/W |
| TPLINK.LEDSCHEDULE.START_HOUR | 0-23 | R/W |
| TPLINK.LEDSCHEDULE.START_MINUTE | 0-59 | R/W |
| TPLINK.LEDSCHEDULE.END_HOUR | 0-23 | R/W |
| TPLINK.LEDSCHEDULE.END_MINUTE | 0-59 | R/W |
| TPLINK.REBOOTSCHEDULE.ENABLE | YES/NO | R/W |
| TPLINK.REBOOTSCHEDULE.HOUR | 0-23 | R/W |
| TPLINK.REBOOTSCHEDULE.MINUTE | 0-59 | R/W |
| TPLINK.REBOOTSCHEDULE.REPEAT | 1=daily, 2=weekly, 3=monthly | R/W |
| TPLINK.REBOOTSCHEDULE.WEEKDAY | 1-7 (Mon-Sun) | R/W |
| TPLINK.REBOOTSCHEDULE.MONTHDAY | 1-28 | R/W |

**Command format (POST to `/` with `_t=TOKEN&COMMAND=<cmd>`):**
| Command | Response |
|---------|----------|
| `get qos` | `ERROR=000\r\nRESULT=<1-4>` |
| `set qos <1-4>` | `ERROR=000\r\nRESULT=0` |
| `lan link speed` | `ERROR=000\r\nPORT1=<0-6>\r\nPORT2=<0-6>\r\n...` |
| `reboot` | `ERROR=000` (then device reboots) |

**Ethernet port status codes:**
| Code | Status | Speed | Duplex |
|------|--------|-------|--------|
| 0 | Disconnected | — | — |
| 1 | Connected | 10 Mbps | Half |
| 2 | Connected | 10 Mbps | Full |
| 3 | Connected | 100 Mbps | Half |
| 4 | Connected | 100 Mbps | Full |
| 5 | Connected | 1000 Mbps | Half |
| 6 | Connected | 1000 Mbps | Full |

### References
- Reverse-engineered HTTP API documented in project memory
- Device JS models: `modules/advanced/system/led/models.js`, `modules/qos/models.js`, `modules/advanced/system/reboot/models.js`, `modules/networkMap/mapRepeater/controllers.js`

### Change History
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-10 | Pete | Initial specification |
