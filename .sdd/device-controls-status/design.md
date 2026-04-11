# Design: Device Controls and Status

**Version:** 1.0
**Date:** 2026-04-10
**Status:** Implemented
**Linked Specification** `.sdd/device-controls-status/specification.md`

---

# Design Document

---

## Architecture Overview

### Current Architecture Context

The integration has a network coordinator that polls adapter data every 60s via the HTTP client. Control entities (switches, selects, buttons, times, numbers) don't exist yet. The client has `get_data()` for reading keys and `_do_get()` for GET requests, but no method for writing keys or sending commands.

### Proposed Architecture

```
Network Coordinator (60s) — expanded to also fetch:
  - LED settings (6 keys)
  - Reboot schedule settings (6 keys)
  - QoS mode (COMMAND=get qos)
  - Ethernet port status (COMMAND=lan link speed)

Control entities write to device on user action:
  switch.turn_on/off → client.set_data({key: value})
  select.select_option → client.send_command("set qos N")
  button.press → client.send_command("reboot")
  time.set_value → client.set_data({hour_key: H, minute_key: M})
  number.set_value → client.set_data({key: value})

All control entities also subscribe to network coordinator
for state reads (CoordinatorEntity pattern).
```

The network coordinator's data dict is expanded to include `led`, `reboot_schedule`, `qos_mode`, and `ethernet_ports` alongside the existing `adapters` and `connected_count`.

### Technology Decisions

- **Single coordinator for all HTTP data:** Rather than creating separate coordinators, the existing network coordinator fetches everything in one update cycle. This avoids multiple concurrent HTTP sessions and keeps the polling synchronized.
- **Write-then-refresh pattern:** When a control entity writes to the device, it calls `await coordinator.async_request_refresh()` after the write to immediately update all entities with the new state, rather than waiting for the next 60s poll.
- **New HA platforms:** `switch`, `button`, `time`, `select`, `number` — each in its own module file per HA convention.

### Quality Attributes

- **Consistency:** All control entities subscribe to the same coordinator, so state is always in sync.
- **Responsiveness:** Write-then-refresh means the UI updates immediately after a control action.
- **Graceful degradation:** If a COMMAND fails (e.g., device doesn't support QoS), that entity becomes unavailable without affecting others.

---

## Modified Components

### client.py
**Change Description** Add `set_data()` for writing key-value pairs and `send_command()` for COMMAND-style requests. Both use POST to `/` with the session token in the body.

**Dependants** All control entity modules (switch, button, select, time, number)

**Kind** Module

**Details**
```
New method: set_data(data: dict[str, str]) -> None
  POST to http://{host}/ with body _t={token}&KEY1=VALUE1&KEY2=VALUE2
  Parse response: ERROR=000 → success
  Auth errors → re-auth and retry (same pattern as get_data)
  Other errors → raise UnexpectedResponse

New method: send_command(command: str) -> dict[str, str]
  POST to http://{host}/ with body _t={token}&COMMAND={command}
  Parse response: return data dict (e.g., {"RESULT": "1"})
  Auth errors → re-auth and retry
  Other errors → raise UnexpectedResponse
```

**Requirements References**
- [device-controls-status:FR-001]: set_data for LED toggle
- [device-controls-status:FR-004]: send_command for reboot
- [device-controls-status:FR-006]: send_command for QoS get/set
- [device-controls-status:FR-007]: send_command for ethernet status

**Test Scenarios**

**TS-01: set_data writes keys successfully**
- Given: Client logged in
- When: set_data({"KEY": "VALUE"}) called
- Then: POST sent with _t=token&KEY=VALUE, no exception

**TS-02: set_data re-auths on expired session**
- Given: Client session expired
- When: set_data called
- Then: Re-authenticates and retries successfully

**TS-03: send_command returns result**
- Given: Client logged in
- When: send_command("get qos") called
- Then: Returns {"RESULT": "1"}

**TS-04: send_command re-auths on expired session**
- Given: Client session expired
- When: send_command called
- Then: Re-authenticates and retries

---

### network_coordinator.py
**Change Description** Expand `_async_update_data` to also fetch LED settings, reboot schedule, QoS mode, and ethernet port status. The data dict grows to include these additional sections.

**Dependants** All new entity modules read from this coordinator's data

**Kind** Module

**Details**
```
_async_update_data changes:
  Existing: calls client.get_network_data() → adapters, connected_count
  New: additionally fetches:
    - LED keys via client.get_data([6 LED keys])
    - Reboot schedule keys via client.get_data([6 reboot keys])
    - QoS via client.send_command("get qos")
    - Ethernet via client.send_command("lan link speed")
  
  Returns expanded dict:
  {
    "adapters": [...],  # existing
    "connected_count": N,  # existing
    "root_mac": "...",  # existing
    "led": {
      "enabled": True/False,
      "night_mode": True/False,
      "start_hour": 21, "start_minute": 0,
      "end_hour": 6, "end_minute": 0,
    },
    "reboot_schedule": {
      "enabled": True/False,
      "hour": 0, "minute": 0,
      "repeat": 1,  # 1=daily, 2=weekly, 3=monthly
      "weekday": 0, "monthday": 1,
    },
    "qos_mode": "fair",  # fair/gaming/streaming/voice
    "ethernet_ports": [
      {"port": 1, "connected": False, "speed": 0, "duplex": ""},
      {"port": 2, "connected": True, "speed": 1000, "duplex": "full"},
    ],
  }

  Each sub-fetch is wrapped in try/except — if one fails, others still work.
  Failed sections are set to None in the data dict.
```

**Requirements References**
- [device-controls-status:FR-008]: Polls all settings at 60s

**Test Scenarios**

**TS-05: Coordinator fetches all data sections**
- Given: Client returns valid data for all sections
- When: Coordinator updates
- Then: Data contains adapters, led, reboot_schedule, qos_mode, ethernet_ports

**TS-06: Partial fetch failure doesn't break coordinator**
- Given: QoS command fails but other fetches succeed
- When: Coordinator updates
- Then: qos_mode is None, other sections have valid data

---

### __init__.py
**Change Description** Add new platforms to PLATFORMS list: SWITCH, BUTTON, TIME, SELECT, NUMBER.

**Dependants** All new platform modules

**Kind** Module

**Details**
```
PLATFORMS adds: Platform.SWITCH, Platform.BUTTON, Platform.TIME, Platform.SELECT, Platform.NUMBER
```

**Requirements References**
- [device-controls-status:FR-008]: Platforms registration

**Test Scenarios**

No additional tests — covered by integration tests.

---

### const.py
**Change Description** Add QoS mode mapping constants and ethernet port status mapping.

**Kind** Module

**Details**
```
QOS_MODES = {"1": "Fair", "2": "Gaming", "3": "Streaming", "4": "Voice"}
QOS_MODES_REVERSE = {v: k for k, v in QOS_MODES.items()}

ETHERNET_PORT_STATUS = {
    0: {"connected": False, "speed": 0, "duplex": ""},
    1: {"connected": True, "speed": 10, "duplex": "half"},
    2: {"connected": True, "speed": 10, "duplex": "full"},
    3: {"connected": True, "speed": 100, "duplex": "half"},
    4: {"connected": True, "speed": 100, "duplex": "full"},
    5: {"connected": True, "speed": 1000, "duplex": "half"},
    6: {"connected": True, "speed": 1000, "duplex": "full"},
}
```

**Requirements References**
- [device-controls-status:FR-006]: QoS mode mapping
- [device-controls-status:FR-007]: Ethernet port status mapping

---

## Added Components

### switch.py
**Description** Switch entities for LED on/off, LED night mode, and reboot schedule enable/disable. Each reads state from the network coordinator and writes via the HTTP client.

**Users** HA switch platform

**Kind** Module

**Location** `custom_components/tplink_powerline/switch.py`

**Details**
```
async_setup_entry:
  If network_coordinator exists:
    Create LedSwitch, NightModeSwitch, RebootScheduleSwitch

Base pattern for all switches:
  Subclass CoordinatorEntity[NetworkCoordinator] + SwitchEntity
  Read is_on from coordinator.data[section][key]
  turn_on/turn_off → client.set_data({key: "YES"/"NO"})
    → coordinator.async_request_refresh()

LedSwitch:
  is_on: coordinator.data["led"]["enabled"]
  write key: TPLINK.LEDSCHEDULE.LED_ENABLE
  icon: mdi:led-on / mdi:led-off

NightModeSwitch:
  is_on: coordinator.data["led"]["night_mode"]
  write key: TPLINK.LEDSCHEDULE.ENABLE
  icon: mdi:weather-night

RebootScheduleSwitch:
  is_on: coordinator.data["reboot_schedule"]["enabled"]
  write key: TPLINK.REBOOTSCHEDULE.ENABLE
  icon: mdi:restart-alert
```

**Requirements References**
- [device-controls-status:FR-001]: LED switch
- [device-controls-status:FR-002]: Night mode switch
- [device-controls-status:FR-005]: Reboot schedule switch

**Test Scenarios**

**TS-07: LED switch reflects state from coordinator**
- Given: Coordinator data has led.enabled=True
- When: Switch state read
- Then: is_on is True

**TS-08: LED switch writes to device on toggle**
- Given: LED switch is on
- When: turn_off called
- Then: client.set_data called with LED_ENABLE=NO, coordinator refreshed

**TS-09: Night mode switch works independently**
- Given: Night mode is disabled
- When: turn_on called
- Then: client.set_data called with ENABLE=YES

**TS-10: Reboot schedule switch**
- Given: Reboot schedule disabled
- When: turn_on called
- Then: client.set_data called with REBOOTSCHEDULE.ENABLE=YES

---

### button.py
**Description** Button entity that triggers an immediate device reboot.

**Users** HA button platform

**Kind** Module

**Location** `custom_components/tplink_powerline/button.py`

**Details**
```
async_setup_entry:
  If client exists:
    Create RebootButton

RebootButton(ButtonEntity):
  icon: mdi:restart
  device_class: ButtonDeviceClass.RESTART
  async_press: client.send_command("reboot")
  DeviceInfo: root device identifiers
```

**Requirements References**
- [device-controls-status:FR-004]: Reboot button

**Test Scenarios**

**TS-11: Reboot button sends command**
- Given: Client is logged in
- When: Button pressed
- Then: client.send_command("reboot") called

---

### time.py
**Description** Time entities for LED night mode start/end and reboot schedule time.

**Users** HA time platform

**Kind** Module

**Location** `custom_components/tplink_powerline/time.py`

**Details**
```
async_setup_entry:
  If network_coordinator exists:
    Create NightModeStartTime, NightModeEndTime, RebootScheduleTime

Base pattern:
  Subclass CoordinatorEntity[NetworkCoordinator] + TimeEntity
  Read native_value from coordinator.data as time(hour, minute)
  set_value → client.set_data({hour_key: H, minute_key: M})
    → coordinator.async_request_refresh()

NightModeStartTime:
  reads: led.start_hour, led.start_minute
  writes: TPLINK.LEDSCHEDULE.START_HOUR, START_MINUTE

NightModeEndTime:
  reads: led.end_hour, led.end_minute
  writes: TPLINK.LEDSCHEDULE.END_HOUR, END_MINUTE

RebootScheduleTime:
  reads: reboot_schedule.hour, reboot_schedule.minute
  writes: TPLINK.REBOOTSCHEDULE.HOUR, MINUTE
```

**Requirements References**
- [device-controls-status:FR-003]: Night mode times
- [device-controls-status:FR-005]: Reboot schedule time

**Test Scenarios**

**TS-12: Night mode start time reads from coordinator**
- Given: Coordinator data has led.start_hour=21, start_minute=0
- When: Time entity state read
- Then: native_value is time(21, 0)

**TS-13: Night mode time writes to device**
- Given: Start time entity
- When: set_value(time(22, 30)) called
- Then: client.set_data called with START_HOUR=22, START_MINUTE=30

**TS-14: Reboot schedule time**
- Given: Coordinator data has reboot_schedule.hour=3, minute=0
- When: Time entity state read
- Then: native_value is time(3, 0)

---

### select.py
**Description** Select entities for QoS mode and reboot schedule repeat cycle.

**Users** HA select platform

**Kind** Module

**Location** `custom_components/tplink_powerline/select.py`

**Details**
```
async_setup_entry:
  If network_coordinator exists:
    Create QosModeSelect, RebootCycleSelect

QosModeSelect(CoordinatorEntity, SelectEntity):
  options: ["Fair", "Gaming", "Streaming", "Voice"]
  current_option: QOS_MODES[coordinator.data["qos_mode"]] (mapped from number)
  select_option → client.send_command(f"set qos {QOS_MODES_REVERSE[option]}")
    → coordinator.async_request_refresh()
  icon: mdi:quality-high

RebootCycleSelect(CoordinatorEntity, SelectEntity):
  options: ["Daily", "Weekly", "Monthly"]
  current_option: mapped from coordinator.data["reboot_schedule"]["repeat"]
  select_option → client.set_data({REBOOTSCHEDULE.REPEAT: value})
    → coordinator.async_request_refresh()
  icon: mdi:calendar-refresh
```

**Requirements References**
- [device-controls-status:FR-006]: QoS mode select
- [device-controls-status:FR-005]: Reboot cycle select

**Test Scenarios**

**TS-15: QoS select shows current mode**
- Given: Coordinator data has qos_mode="fair"
- When: Select state read
- Then: current_option is "Fair"

**TS-16: QoS select writes command**
- Given: QoS select
- When: select_option("Gaming") called
- Then: client.send_command("set qos 2") called

**TS-17: Reboot cycle select**
- Given: Coordinator data has repeat=1
- When: Select state read
- Then: current_option is "Daily"

---

### number.py
**Description** Number entity for the reboot schedule day (weekday 1-7 or month day 1-28).

**Users** HA number platform

**Kind** Module

**Location** `custom_components/tplink_powerline/number.py`

**Details**
```
async_setup_entry:
  If network_coordinator exists:
    Create RebootDayNumber

RebootDayNumber(CoordinatorEntity, NumberEntity):
  native_min_value: 1
  native_max_value: 28
  native_step: 1
  mode: NumberMode.BOX
  native_value: coordinator.data["reboot_schedule"]["weekday"] or ["monthday"]
    depending on current repeat cycle
  set_native_value → client.set_data({appropriate key: value})
    → coordinator.async_request_refresh()
  icon: mdi:calendar-today
```

**Requirements References**
- [device-controls-status:FR-005]: Reboot day number

**Test Scenarios**

**TS-18: Reboot day reads from coordinator**
- Given: Coordinator data has repeat=2 (weekly), weekday=5
- When: Number state read
- Then: native_value is 5

**TS-19: Reboot day writes correct key**
- Given: Repeat is weekly
- When: set_native_value(3) called
- Then: client.set_data with REBOOTSCHEDULE.WEEKDAY=3

---

### binary_sensor.py (modified)
**Change Description** Add ethernet port binary sensors that read from the network coordinator.

**Kind** Module

**Details**
```
async_setup_entry adds:
  If network_coordinator and coordinator.data has ethernet_ports:
    For each port in ethernet_ports:
      Create EthernetPortBinarySensor

EthernetPortBinarySensor(CoordinatorEntity, BinarySensorEntity):
  device_class: CONNECTIVITY
  is_on: port["connected"]
  extra_state_attributes: {"speed": port["speed"], "duplex": port["duplex"]}
  unique_id: {entry_id}_ethernet_port_{N}
  name: "{device_name} Ethernet Port {N}"
  DeviceInfo: root device identifiers
```

**Requirements References**
- [device-controls-status:FR-007]: Ethernet port sensors

**Test Scenarios**

**TS-20: Ethernet port connected with attributes**
- Given: Coordinator data has port 2 connected, speed=1000, duplex=full
- When: Binary sensor state read
- Then: is_on=True, attributes contain speed=1000, duplex=full

**TS-21: Ethernet port disconnected**
- Given: Coordinator data has port 1 disconnected
- When: Binary sensor state read
- Then: is_on=False, speed=0

---

## Used Components

### Home Assistant SwitchEntity
**Location** `homeassistant.components.switch`
**Provides** Switch entity with turn_on/turn_off methods
**Used By** switch.py

### Home Assistant ButtonEntity
**Location** `homeassistant.components.button`
**Provides** Button entity with async_press method and RESTART device class
**Used By** button.py

### Home Assistant TimeEntity
**Location** `homeassistant.components.time`
**Provides** Time entity with native_value as datetime.time and set_value method
**Used By** time.py

### Home Assistant SelectEntity
**Location** `homeassistant.components.select`
**Provides** Select entity with options list and select_option method
**Used By** select.py

### Home Assistant NumberEntity
**Location** `homeassistant.components.number`
**Provides** Number entity with min/max/step and set_native_value method
**Used By** number.py

---

## Documentation Considerations

- Update README with control entities documentation
- Note that all controls require password configuration

---

## Integration Test Scenarios

**ITS-01: Full setup creates all control entities**
- Given: Mocked client returns all data sections
- When: Config entry with password loaded
- Then: LED switches, night mode times, reboot controls, QoS select, ethernet port sensors, and reboot button all exist
- Components Involved: __init__.py, switch.py, button.py, time.py, select.py, number.py, binary_sensor.py

**ITS-02: No controls without password**
- Given: Config entry without password
- When: Config entry loaded
- Then: No switch, button, time, select, or number entities exist. No ethernet port sensors.
- Components Involved: __init__.py, all platform modules

---

## Test Data

- LED data: `{"enabled": True, "night_mode": True, "start_hour": 21, "start_minute": 0, "end_hour": 6, "end_minute": 0}`
- Reboot schedule: `{"enabled": False, "hour": 0, "minute": 0, "repeat": 1, "weekday": 0, "monthday": 1}`
- QoS: `"fair"`
- Ethernet: `[{"port": 1, "connected": False, "speed": 0, "duplex": ""}, {"port": 2, "connected": True, "speed": 1000, "duplex": "full"}]`

---

## Test Feasibility

- All HTTP interactions mocked
- QA scenarios require real device

---

## Risks and Dependencies

| Risk | Impact | Mitigation |
|------|--------|------------|
| Reboot command makes device temporarily unreachable | HTTP client loses session, coordinator fails until device returns | Client re-auths automatically. Ping coordinator handles unavailability. |
| Writing settings while web UI is open | Potential conflict if user edits from both sides simultaneously | Accepted risk — last write wins. 60s poll syncs state. |
| Different device models may not support all commands | Entity creation fails or returns errors | Each sub-fetch is try/except wrapped. Unsupported features set to None. |

---

## Feasibility Review

- All QA scenarios feasible with designed functionality
- No missing infrastructure

---

## Task Breakdown

> **CRITICAL: Tests are written WITH implementation, not after.**

### Phase 1: Client Write Methods and Coordinator Expansion

**Task 1: Add client set_data and send_command methods**
- Status: Backlog
- Requirements: [device-controls-status:FR-001], [device-controls-status:FR-004], [device-controls-status:FR-006], [device-controls-status:FR-007]
- Test Scenarios: [device-controls-status:client/TS-01], [device-controls-status:client/TS-02], [device-controls-status:client/TS-03], [device-controls-status:client/TS-04]
- Details:
  ```
  Modify: client.py — add set_data(), send_command()
  Modify: tests/test_client.py — add 4 test scenarios
  Modify: const.py — add QOS_MODES, ETHERNET_PORT_STATUS
  ```

**Task 2: Expand network coordinator to fetch all data**
- Status: Backlog
- Requirements: [device-controls-status:FR-008]
- Test Scenarios: [device-controls-status:network_coordinator/TS-05], [device-controls-status:network_coordinator/TS-06]
- Details:
  ```
  Modify: network_coordinator.py — expand _async_update_data
  Modify: tests/test_network_coordinator.py — add 2 test scenarios
  ```

### Phase 2: Switch, Button, Time Entities

**Task 3: Implement switch entities (LED, night mode, reboot schedule)**
- Status: Backlog
- Requirements: [device-controls-status:FR-001], [device-controls-status:FR-002], [device-controls-status:FR-005]
- Test Scenarios: [device-controls-status:switch/TS-07], [device-controls-status:switch/TS-08], [device-controls-status:switch/TS-09], [device-controls-status:switch/TS-10]
- Details:
  ```
  Create: switch.py
  Create: tests/test_switch.py — 4 test scenarios
  Modify: __init__.py — add Platform.SWITCH
  ```

**Task 4: Implement button and time entities**
- Status: Backlog
- Requirements: [device-controls-status:FR-004], [device-controls-status:FR-003], [device-controls-status:FR-005]
- Test Scenarios: [device-controls-status:button/TS-11], [device-controls-status:time/TS-12], [device-controls-status:time/TS-13], [device-controls-status:time/TS-14]
- Details:
  ```
  Create: button.py, time.py
  Create: tests/test_button.py, tests/test_time.py
  Modify: __init__.py — add Platform.BUTTON, Platform.TIME
  ```

### Phase 3: Select, Number, Ethernet Ports, Integration Tests

**Task 5: Implement select and number entities**
- Status: Backlog
- Requirements: [device-controls-status:FR-006], [device-controls-status:FR-005]
- Test Scenarios: [device-controls-status:select/TS-15], [device-controls-status:select/TS-16], [device-controls-status:select/TS-17], [device-controls-status:number/TS-18], [device-controls-status:number/TS-19]
- Details:
  ```
  Create: select.py, number.py
  Create: tests/test_select.py, tests/test_number.py
  Modify: __init__.py — add Platform.SELECT, Platform.NUMBER
  ```

**Task 6: Add ethernet port sensors and integration tests**
- Status: Backlog
- Requirements: [device-controls-status:FR-007]
- Test Scenarios: [device-controls-status:binary_sensor/TS-20], [device-controls-status:binary_sensor/TS-21], [device-controls-status:ITS-01], [device-controls-status:ITS-02]
- Details:
  ```
  Modify: binary_sensor.py — add EthernetPortBinarySensor
  Modify: tests/test_binary_sensor.py — add 2 test scenarios
  Create: tests/test_controls_integration.py — 2 integration tests
  ```

---

## Intermediate Dead Code Tracking

No dead code expected.

---

## Intermediate Stub Tracking

No stubs expected.

---

## Appendix

### Glossary
- **set_data:** HTTP client method for writing key-value pairs to the device
- **send_command:** HTTP client method for COMMAND-style requests
- **write-then-refresh:** Pattern where a control entity writes to the device then triggers an immediate coordinator refresh

### References
- Device API reference in specification appendix
- [HA Switch Entity](https://developers.home-assistant.io/docs/core/entity/switch)
- [HA Button Entity](https://developers.home-assistant.io/docs/core/entity/button)
- [HA Time Entity](https://developers.home-assistant.io/docs/core/entity/time)
- [HA Select Entity](https://developers.home-assistant.io/docs/core/entity/select)
- [HA Number Entity](https://developers.home-assistant.io/docs/core/entity/number)

### Change History
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-10 | Pete | Initial design |

---
