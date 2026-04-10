# Design: Ping Availability

**Version:** 1.0
**Date:** 2026-04-10
**Status:** Implemented
**Linked Specification** `.sdd/ping-availability/specification.md`

---

# Design Document

---

## Architecture Overview

### Current Architecture Context

This is a greenfield project — no existing code. The integration will be a standard Home Assistant custom component following the `DataUpdateCoordinator` pattern for periodic polling.

### Proposed Architecture

The integration follows the standard HA custom component structure:

```
Config Flow → creates Config Entry
                ↓
async_setup_entry → creates Coordinator → starts polling loop (15s)
                                              ↓
                                         ping device
                                              ↓
                                     update failure counter
                                              ↓
                                     Binary Sensor reads coordinator data
                                     (is_on based on failure_count < 8)
```

Each config entry (one per powerline device) gets its own coordinator. The coordinator runs an ICMP ping via subprocess every 15 seconds and maintains a consecutive failure counter. The binary sensor reads this counter to determine connectivity state.

### Technology Decisions

- **Ping method:** `asyncio.create_subprocess_exec` calling the system `ping` command with a single packet and 5-second timeout. This avoids requiring raw socket privileges (which `icmplib` would need) and works on all HA installation types.
- **No external dependencies:** The integration uses only HA core and Python stdlib. No pip requirements beyond `homeassistant`.
- **Failure counting in coordinator data:** The coordinator's `data` dict holds both `ping_success` (bool) and `failure_count` (int). The coordinator itself manages the counter rather than the binary sensor, keeping state centralized.

### Quality Attributes

- **Maintainability:** Clean separation — ping logic in coordinator, presentation in binary sensor, config in config flow. Future HTTP scraping plugs into the coordinator without touching the binary sensor.
- **Extensibility:** The coordinator data dict can be extended with HTTP-sourced fields in a future iteration without changing the binary sensor's interface.

---

## Added Components

### const.py
**Description** Central constants for the integration: domain name, config keys, default values, and polling parameters.

**Users** All other modules in the integration.

**Kind** Module

**Location** `custom_components/tplink_powerline/const.py`

**Details**
```
DOMAIN = "tplink_powerline"
CONF_HOST = "host"               # reuse HA's CONF_HOST key name
CONF_NAME = "name"
DEFAULT_NAME = "Powerline Network"
DEFAULT_SCAN_INTERVAL = 15       # seconds
PING_TIMEOUT = 5                 # seconds per ping attempt
FAILURE_THRESHOLD = 8            # consecutive failures before unavailable
```

**Requirements References**
- [ping-availability:FR-004]: Defines the polling interval (15s) and failure threshold (8) as named constants

**Test Scenarios**

No unit tests needed — these are static constants validated by integration tests.

---

### config_flow.py
**Description** UI-based config flow that collects the device IP/hostname and friendly name, validates reachability via ping, and prevents duplicate entries.

**Users** Home Assistant config flow framework (called when user adds the integration via UI).

**Kind** Module

**Location** `custom_components/tplink_powerline/config_flow.py`

**Details**
```
TplinkPowerlineConfigFlow(ConfigFlow)
  domain = DOMAIN

  async_step_user(user_input):
    - Shows form with fields: host (string, required), name (string, default "Powerline Network")
    - On submit:
      1. Check host not already configured (abort "already_configured")
      2. Ping the host with single ICMP packet, 5s timeout
      3. If ping fails → show form again with error "cannot_connect"
      4. If ping succeeds → create entry with title = user-provided name, unique_id = host
    - Returns: ConfigEntry with data {host, name}
```

**Requirements References**
- [ping-availability:FR-002]: Config flow with IP, friendly name, ping validation, duplicate rejection
- [ping-availability:FR-001]: Config flow is part of the integration structure HA requires

**Test Scenarios**

**TS-01: Successful config flow**
- Given: No existing config entries, device at the given IP responds to ping
- When: User submits the config flow with a valid host and name
- Then: A config entry is created with the provided host and name, titled with the name

**TS-02: Config flow rejects unreachable host**
- Given: No device responds at the given IP
- When: User submits the config flow with an unreachable host
- Then: The form is redisplayed with a "cannot_connect" error, no entry created

**TS-03: Config flow rejects duplicate host**
- Given: A config entry already exists for host "192.168.1.34"
- When: User submits the config flow with host "192.168.1.34"
- Then: The flow aborts with "already_configured"

**TS-04: Config flow uses default name**
- Given: No existing config entries, device responds to ping
- When: User submits the config flow with a host but no name override
- Then: The config entry title is "Powerline Network"

---

### coordinator.py
**Description** DataUpdateCoordinator subclass that pings the device on each update cycle and maintains a consecutive failure counter. Exposes the current ping result and failure count in its data dict.

**Users** `__init__.py` (creates the coordinator), `binary_sensor.py` (reads coordinator data).

**Kind** Module

**Location** `custom_components/tplink_powerline/coordinator.py`

**Details**
```
TplinkPowerlineCoordinator(DataUpdateCoordinator)
  Properties:
    host: str
    failure_count: int (starts at 0)

  __init__(hass, entry):
    - Sets update_interval = timedelta(seconds=15)
    - Stores host from entry.data

  async _async_update_data():
    - Runs ping via asyncio.create_subprocess_exec("ping", "-c", "1", "-W", "5", host)
    - If return code == 0: reset failure_count to 0, return {available: True}
    - If return code != 0: increment failure_count, return {available: failure_count < FAILURE_THRESHOLD}
    - If subprocess raises exception: increment failure_count, log warning, return {available: failure_count < FAILURE_THRESHOLD}
    - Never raises UpdateFailed — the binary sensor should always reflect state, not go unavailable from HA's perspective
```

The coordinator does NOT raise `UpdateFailed` because the ping failing is expected data, not an error. The failure counter is the data. The binary sensor interprets it.

**Requirements References**
- [ping-availability:FR-004]: 15-second polling, 8-failure threshold, immediate recovery on success
- [ping-availability:FR-003]: Provides the availability data the binary sensor consumes
- [ping-availability:FR-006]: Coordinator lifecycle — created at setup, cancelled at teardown

**Test Scenarios**

**TS-05: Successful ping resets failure count**
- Given: A coordinator with failure_count at 3
- When: The ping succeeds
- Then: failure_count resets to 0, data.available is True

**TS-06: Failed ping increments failure count**
- Given: A coordinator with failure_count at 0
- When: The ping fails
- Then: failure_count is 1, data.available is True (below threshold)

**TS-07: Failure threshold reached**
- Given: A coordinator with failure_count at 7
- When: The ping fails
- Then: failure_count is 8, data.available is False

**TS-08: Recovery after threshold**
- Given: A coordinator with failure_count at 8 (data.available is False)
- When: The ping succeeds
- Then: failure_count resets to 0, data.available is True

**TS-09: Subprocess exception treated as failure**
- Given: A coordinator with failure_count at 0
- When: The ping subprocess raises an OSError
- Then: failure_count is 1, data.available is True, a warning is logged

---

### binary_sensor.py
**Description** Binary sensor entity that reflects the powerline device's connectivity state based on the coordinator's data. Registers the device in the HA device registry.

**Users** Home Assistant entity platform framework (loaded via `async_setup_entry`).

**Kind** Module

**Location** `custom_components/tplink_powerline/binary_sensor.py`

**Details**
```
async_setup_entry(hass, entry, async_add_entities):
  - Gets coordinator from hass.data[DOMAIN][entry.entry_id]
  - Creates TplinkPowerlineBinarySensor(coordinator, entry)
  - Calls async_add_entities

TplinkPowerlineBinarySensor(CoordinatorEntity, BinarySensorEntity)
  _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

  Properties:
    unique_id: entry.entry_id
    name: entry.data[CONF_NAME]
    is_on: coordinator.data["available"] (True = connected)

    device_info: DeviceInfo(
      identifiers={(DOMAIN, entry.data[CONF_HOST])},
      name=entry.data[CONF_NAME],
      manufacturer="TP-Link",
      model="Powerline Adapter"
    )
```

**Requirements References**
- [ping-availability:FR-003]: Binary sensor with connectivity device class, showing Connected/Disconnected
- [ping-availability:FR-005]: Device registry entry with friendly name, manufacturer, model

**Test Scenarios**

**TS-10: Binary sensor shows connected when available**
- Given: Coordinator data has available=True
- When: The binary sensor state is read
- Then: is_on is True (shown as "Connected")

**TS-11: Binary sensor shows disconnected when unavailable**
- Given: Coordinator data has available=False
- When: The binary sensor state is read
- Then: is_on is False (shown as "Disconnected")

**TS-12: Device info is correct**
- Given: A config entry with host "192.168.1.34" and name "Powerline Network"
- When: The binary sensor's device_info is read
- Then: manufacturer is "TP-Link", model is "Powerline Adapter", name is "Powerline Network", identifiers contain (DOMAIN, "192.168.1.34")

---

### __init__.py
**Description** Integration setup and teardown. Creates the coordinator on entry load, forwards to the binary_sensor platform, and cleans up on unload.

**Users** Home Assistant integration loader.

**Kind** Module

**Location** `custom_components/tplink_powerline/__init__.py`

**Details**
```
PLATFORMS = [Platform.BINARY_SENSOR]

async_setup_entry(hass, entry):
  - Create TplinkPowerlineCoordinator(hass, entry)
  - Call await coordinator.async_config_entry_first_refresh()
    (raises ConfigEntryNotReady if first ping fails)
  - Store coordinator in hass.data[DOMAIN][entry.entry_id]
  - Forward entry setup to PLATFORMS

async_unload_entry(hass, entry):
  - Call await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
  - Remove coordinator from hass.data[DOMAIN]
  - Return True
```

**Requirements References**
- [ping-availability:FR-006]: Setup creates coordinator and starts polling; teardown stops polling; ConfigEntryNotReady on unreachable device
- [ping-availability:FR-001]: __init__.py is a required part of integration structure

**Test Scenarios**

**TS-13: Setup creates coordinator and forwards platforms**
- Given: A valid config entry with a reachable host
- When: async_setup_entry is called
- Then: A coordinator is stored in hass.data, binary_sensor platform is loaded, coordinator is polling

**TS-14: Setup raises ConfigEntryNotReady on unreachable device**
- Given: A config entry with an unreachable host
- When: async_setup_entry is called
- Then: ConfigEntryNotReady is raised

**TS-15: Unload cleans up coordinator**
- Given: A loaded config entry with an active coordinator
- When: async_unload_entry is called
- Then: Coordinator is removed from hass.data, platforms are unloaded, returns True

---

### manifest.json
**Description** Home Assistant integration manifest declaring the domain, dependencies, and HACS metadata.

**Users** HA integration loader, HACS.

**Kind** File (JSON)

**Location** `custom_components/tplink_powerline/manifest.json`

**Details**
```
{
  "domain": "tplink_powerline",
  "name": "TP-Link Powerline",
  "codeowners": [],
  "config_flow": true,
  "dependencies": [],
  "documentation": "https://github.com/<owner>/ha-tplink-powerline",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/<owner>/ha-tplink-powerline/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

**Requirements References**
- [ping-availability:FR-001]: Required for HACS compliance and HA integration registration

**Test Scenarios**

No unit tests — validated by HACS and HA loader at install time. Covered by QA-01.

---

### hacs.json
**Description** HACS repository metadata file.

**Users** HACS.

**Kind** File (JSON)

**Location** `hacs.json` (repository root)

**Details**
```
{
  "name": "TP-Link Powerline",
  "render_readme": true
}
```

**Requirements References**
- [ping-availability:FR-001]: Required for HACS repository compliance

**Test Scenarios**

No unit tests — validated by HACS. Covered by QA-01.

---

### strings.json and translations/en.json
**Description** UI strings for the config flow: form labels, error messages, abort reasons.

**Users** HA frontend (config flow UI).

**Kind** Files (JSON)

**Location** `custom_components/tplink_powerline/strings.json` and `custom_components/tplink_powerline/translations/en.json`

**Details**
```
{
  "config": {
    "step": {
      "user": {
        "title": "TP-Link Powerline",
        "description": "Enter the IP address of your powerline adapter.",
        "data": {
          "host": "IP Address",
          "name": "Device Name"
        },
        "data_description": {
          "host": "The IP address or hostname of the powerline adapter",
          "name": "A friendly name for this powerline network"
        }
      }
    },
    "error": {
      "cannot_connect": "Could not reach the device. Check the IP address and try again."
    },
    "abort": {
      "already_configured": "This device is already configured."
    }
  }
}
```

Both files have identical content (strings.json is the source, translations/en.json is the English translation).

**Requirements References**
- [ping-availability:FR-002]: Provides the UI text for config flow form, errors, and abort messages

**Test Scenarios**

No unit tests — validated through config flow integration tests (TS-01 through TS-04).

---

## Used Components

### Home Assistant DataUpdateCoordinator
**Location** `homeassistant.helpers.update_coordinator`

**Provides** Periodic polling framework with automatic scheduling, error handling, and entity update notifications. Provides `async_config_entry_first_refresh()` which raises `ConfigEntryNotReady` on initial failure.

**Used By** coordinator.py (subclasses it), binary_sensor.py (CoordinatorEntity base), __init__.py (creates and triggers first refresh)

### Home Assistant ConfigFlow
**Location** `homeassistant.config_entries`

**Provides** UI-based configuration framework with form rendering, validation, error display, unique ID management, and abort handling.

**Used By** config_flow.py (subclasses it)

### Home Assistant BinarySensorEntity / CoordinatorEntity
**Location** `homeassistant.components.binary_sensor`, `homeassistant.helpers.update_coordinator`

**Provides** Binary sensor entity with device class support. CoordinatorEntity auto-subscribes to coordinator updates and triggers state writes.

**Used By** binary_sensor.py (subclasses both)

---

## Documentation Considerations

- `README.md` at repo root: installation via HACS, configuration steps, what the integration provides
- No developer docs needed at this stage

---

## Integration Test Scenarios

**ITS-01: Full setup to entity state flow**
- Given: A mocked ping that succeeds
- When: A config entry is loaded via async_setup_entry
- Then: Coordinator is created, binary sensor platform is set up, binary sensor reads "Connected"
- Components Involved: __init__.py, coordinator.py, binary_sensor.py

**ITS-02: Config entry not ready on unreachable device**
- Given: A mocked ping that fails
- When: A config entry is loaded via async_setup_entry
- Then: ConfigEntryNotReady is raised, no entities are created
- Components Involved: __init__.py, coordinator.py

**ITS-03: Failure threshold causes state transition**
- Given: A loaded integration with a coordinator at failure_count 7
- When: The coordinator polls and ping fails
- Then: The binary sensor transitions from "Connected" to "Disconnected"
- Components Involved: coordinator.py, binary_sensor.py

---

## Test Data

- Mocked ping responses: success (return code 0) and failure (return code 1 or exception)
- Config entry data: `{"host": "192.168.1.34", "name": "Powerline Network"}`
- No external test data sources required

---

## Test Feasibility

- **pytest-homeassistant-custom-component** must be available in the test environment for HA test fixtures
- Ping subprocess must be mocked in all tests — no real network calls in CI

---

## Risks and Dependencies

| Risk | Impact | Mitigation |
|------|--------|------------|
| System `ping` command unavailable or different flags across OS | Ping fails on some HA installations | Use platform-aware ping flags (Linux vs macOS). HA Docker images are Linux-based, so target Linux flags as primary. |
| ICMP blocked by firewall between HA host and powerline device | Device appears offline despite being reachable | Document in README that ICMP must be allowed. This is inherent to ping-based monitoring. |
| HA `async_config_entry_first_refresh` behavior changes | Setup logic may break on HA updates | Pin minimum HA version in manifest. Follow HA deprecation notices. |

---

## Feasibility Review

- No blocking dependencies. All required HA framework components exist and are stable.
- QA-01 through QA-04 are all feasible with the designed functionality — no white-box setup required.

---

## Task Breakdown

> **CRITICAL: Tests are written WITH implementation, not after.**

### Phase 1: Integration Skeleton and Config Flow

**Task 1: Create integration metadata and constants**
- Status: Backlog
- Requirements: [ping-availability:FR-001]
- Test Scenarios: (no unit tests — static files validated by HA/HACS loaders)
- Details:
  ```
  Create:
  - custom_components/tplink_powerline/const.py with all constants
  - custom_components/tplink_powerline/manifest.json
  - custom_components/tplink_powerline/strings.json
  - custom_components/tplink_powerline/translations/en.json
  - hacs.json at repo root
  ```

**Task 2: Implement config flow with ping validation**
- Status: Backlog
- Requirements: [ping-availability:FR-002]
- Test Scenarios: [ping-availability:config_flow/TS-01], [ping-availability:config_flow/TS-02], [ping-availability:config_flow/TS-03], [ping-availability:config_flow/TS-04]
- Details:
  ```
  Create:
  - custom_components/tplink_powerline/config_flow.py
  - tests/conftest.py (pytest fixtures for HA test harness)
  - tests/test_config_flow.py (all 4 test scenarios)
  
  Config flow: single step "user" with host + name fields.
  Ping validation via asyncio subprocess.
  Unique ID set to host to prevent duplicates.
  ```

### Phase 2: Coordinator and Binary Sensor

**Task 3: Implement coordinator with ping polling and failure counting**
- Status: Backlog
- Requirements: [ping-availability:FR-004], [ping-availability:FR-003], [ping-availability:FR-006]
- Test Scenarios: [ping-availability:coordinator/TS-05], [ping-availability:coordinator/TS-06], [ping-availability:coordinator/TS-07], [ping-availability:coordinator/TS-08], [ping-availability:coordinator/TS-09]
- Details:
  ```
  Create:
  - custom_components/tplink_powerline/coordinator.py
  - tests/test_coordinator.py (all 5 test scenarios)
  
  Coordinator subclasses DataUpdateCoordinator.
  _async_update_data runs ping subprocess, manages failure_count.
  Returns dict with "available" key.
  ```

**Task 4: Implement binary sensor and device registration**
- Status: Backlog
- Requirements: [ping-availability:FR-003], [ping-availability:FR-005]
- Test Scenarios: [ping-availability:binary_sensor/TS-10], [ping-availability:binary_sensor/TS-11], [ping-availability:binary_sensor/TS-12]
- Details:
  ```
  Create:
  - custom_components/tplink_powerline/binary_sensor.py
  - tests/test_binary_sensor.py (all 3 test scenarios)
  
  Entity subclasses CoordinatorEntity + BinarySensorEntity.
  device_class = CONNECTIVITY. is_on reads coordinator.data["available"].
  device_info returns DeviceInfo with TP-Link manufacturer.
  ```

**Task 5: Implement integration setup/teardown and integration tests**
- Status: Backlog
- Requirements: [ping-availability:FR-006], [ping-availability:FR-001]
- Test Scenarios: [ping-availability:init/TS-13], [ping-availability:init/TS-14], [ping-availability:init/TS-15], [ping-availability:ITS-01], [ping-availability:ITS-02], [ping-availability:ITS-03]
- Details:
  ```
  Create:
  - custom_components/tplink_powerline/__init__.py
  - tests/test_init.py (TS-13, TS-14, TS-15 + ITS-01, ITS-02, ITS-03)
  
  async_setup_entry: create coordinator, first refresh, store in hass.data, forward platforms.
  async_unload_entry: unload platforms, remove from hass.data.
  ```

---

## Intermediate Dead Code Tracking

No dead code expected — all components are used within the same phase they are introduced.

---

## Intermediate Stub Tracking

No stubs expected — all functionality is implemented in full.

---

## Appendix

### Glossary
- **Coordinator:** HA's `DataUpdateCoordinator` — manages periodic data fetching and notifies entities of updates
- **Config entry:** A persisted configuration record in HA, created by the config flow
- **CoordinatorEntity:** HA entity base class that auto-subscribes to a coordinator's updates

### References
- [HA DataUpdateCoordinator docs](https://developers.home-assistant.io/docs/integration_fetching_data)
- [HA Config Flow docs](https://developers.home-assistant.io/docs/config_entries_config_flow_handler)
- [HA Binary Sensor docs](https://developers.home-assistant.io/docs/core/entity/binary-sensor)
- [HACS repository structure](https://hacs.xyz/docs/publish/integration)

### Change History
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-10 | Pete | Initial design |

---
