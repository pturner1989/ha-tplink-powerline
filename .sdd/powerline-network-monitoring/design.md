# Design: Powerline Network Monitoring

**Version:** 1.0
**Date:** 2026-04-10
**Status:** Draft
**Linked Specification** `.sdd/powerline-network-monitoring/specification.md`

---

# Design Document

---

## Architecture Overview

### Current Architecture Context

The integration has two data paths:
1. **Ping coordinator** (15s) — pings the device, drives the root binary sensor
2. **HTTP client** — logs in at setup, fetches device info once, stays logged in

Remote adapter data requires periodic HTTP fetching, which doesn't fit the current one-shot HTTP fetch model.

### Proposed Architecture

```
async_setup_entry:
  1. Ping coordinator (15s, unchanged)
  2. HTTP client login + device info fetch (unchanged)
  3. NEW: Network coordinator (60s) — fetches adapter list + link rates via HTTP client
  4. Forward to binary_sensor + sensor platforms

Sensor platform reads from:
  - device_info (static, for model/firmware/hardware — unchanged)
  - network_coordinator.data (polled, for link rates + adapter count + network name)

Binary sensor platform reads from:
  - ping_coordinator.data (unchanged, for root device ping)
  - network_coordinator.data (for remote adapter connectivity)
```

The network coordinator is a `DataUpdateCoordinator` that calls `client.get_network_data()` every 60 seconds. Its data is a dict containing the parsed adapter list with link rates, plus root-level network metadata.

### Technology Decisions

- **Separate coordinator for network data:** The 60s poll interval is independent of the 15s ping. Using a separate coordinator keeps concerns isolated and allows independent error handling (ping failures don't affect network data and vice versa).
- **Dynamic entity creation via coordinator data:** Entities for remote adapters are created on first poll and track their adapter by MAC address. If a MAC disappears, the entity returns `None` for its value (becomes unavailable). New MACs on subsequent polls are NOT dynamically added — only initial discovery matters (HA requires entity registration at platform setup time). The coordinator does update existing entities' values.
- **via_device linking:** Remote adapter devices link to the root device via `via_device`, creating a parent-child hierarchy in the device registry.

### Quality Attributes

- **Resilience:** Network coordinator failures don't affect ping monitoring. HTTP re-auth is handled by the client transparently.
- **Extensibility:** The network coordinator data dict can be extended with additional keys (e.g., ethernet status) in future specs without changing the coordinator structure.

---

## Modified Components

### client.py
**Change Description** Add `get_network_data()` method that fetches powerline adapter list, link rates, and network name. Add `get_network_name()` convenience method for the one-time setup fetch.

**Dependants** Network coordinator (calls get_network_data), __init__.py (calls get_network_name at setup)

**Kind** Module

**Details**
```
New method: get_network_data() -> dict
  Fetches keys: DIDMNG.GENERAL.MACS, DIDMNG.GENERAL.RX_BPS, DIDMNG.GENERAL.TX_BPS, 
                SYSTEM.PRODUCTION.MAC_ADDR
  Parses comma-separated values into parallel lists
  Filters out null MACs (00:00:00:00:00:00) and root device MAC
  Returns:
  {
    "adapters": [
      {"mac": "58:04:4F:D8:20:2D", "tx_rate": 366, "rx_rate": 317},
      ...
    ],
    "connected_count": 1,
    "root_mac": "B8:FB:B3:B6:DD:DF",
  }
  Rate conversion: raw_value // 32 = Mbps

New method: get_network_name() -> str
  Fetches NODE.GENERAL.DOMAIN_NAME
  Returns the name string or "Unknown"
```

**Requirements References**
- [powerline-network-monitoring:FR-001]: Fetches and parses adapter data, filters root/null MACs
- [powerline-network-monitoring:FR-003]: Rate conversion (raw // 32)
- [powerline-network-monitoring:FR-006]: Network name fetch

**Test Scenarios**

**TS-01: get_network_data with one remote adapter**
- Given: Device returns MACS with 3 entries (null, remote, root), matching RX/TX arrays
- When: get_network_data() is called
- Then: Returns one adapter with correct MAC and converted rates, connected_count=1

**TS-02: get_network_data with no remote adapters**
- Given: Device returns MACS with only null and root entries, rates all 0
- When: get_network_data() is called
- Then: Returns empty adapters list, connected_count=0

**TS-03: get_network_data with disconnected remote adapter**
- Given: Device returns a remote MAC but TX and RX are both 0
- When: get_network_data() is called
- Then: Returns adapter with rates 0, connected_count=0

**TS-04: get_network_name returns name**
- Given: Device returns NODE.GENERAL.DOMAIN_NAME with a value
- When: get_network_name() is called
- Then: Returns the name string

---

### __init__.py
**Change Description** Creates the network coordinator at setup (when HTTP client is available). Fetches network name at setup alongside device info. Stores network coordinator and network name in hass.data.

**Dependants** sensor.py, binary_sensor.py (read from hass.data)

**Kind** Module

**Details**
```
async_setup_entry changes:
  - After client.login() and get_device_info():
    - network_name = await client.get_network_name()
    - Create NetworkCoordinator(hass, client, update_interval=60s)
    - await network_coordinator.async_config_entry_first_refresh()
      (does NOT raise on failure — wrapped in try/except, network monitoring is best-effort)
  - Store in hass.data[DOMAIN][entry.entry_id]:
    - existing: coordinator, client, device_info
    - new: "network_coordinator", "network_name"
```

**Requirements References**
- [powerline-network-monitoring:FR-006]: Fetches network name at setup
- [powerline-network-monitoring:FR-007]: Creates network coordinator with 60s interval

**Test Scenarios**

**TS-05: Setup creates network coordinator when HTTP available**
- Given: Config entry with password_hash, HTTP login succeeds
- When: async_setup_entry is called
- Then: hass.data contains network_coordinator with adapter data

**TS-06: Setup without password has no network coordinator**
- Given: Config entry without password_hash
- When: async_setup_entry is called
- Then: hass.data has network_coordinator=None

---

### const.py
**Change Description** Add network polling interval constant.

**Kind** Module

**Details**
```
NETWORK_SCAN_INTERVAL = 60  # seconds
```

**Requirements References**
- [powerline-network-monitoring:FR-007]: 60-second interval

---

### sensor.py
**Change Description** Add three new sensor types: TX rate, RX rate (per remote adapter, from network coordinator), connected count (root device, from network coordinator), and network name (root device, static). The existing diagnostic sensors (model/firmware/hardware) remain unchanged.

**Dependants** None

**Kind** Module

**Details**
```
New entities for root device:
  - Connected Adapters Count: reads network_coordinator.data["connected_count"]
    SensorDeviceClass.None, icon mdi:counter, state_class measurement
  - Network Name: reads network_name from hass.data (static, diagnostic)

New entities per remote adapter (created dynamically from network_coordinator.data["adapters"]):
  - TX Rate: reads adapter["tx_rate"], unit "Mbps", icon mdi:upload-network
    SensorDeviceClass.DATA_RATE, state_class measurement
  - RX Rate: reads adapter["rx_rate"], unit "Mbps", icon mdi:download-network
    SensorDeviceClass.DATA_RATE, state_class measurement

Remote adapter sensors:
  - Subclass CoordinatorEntity to auto-update from network_coordinator
  - unique_id: {entry_id}_{mac}_{key} (e.g., "entry123_58044FD8202D_tx_rate")
  - device_info: DeviceInfo with identifiers={(DOMAIN, mac)}, via_device=(DOMAIN, host)
  - name: "Powerline {MAC} TX Rate" / "Powerline {MAC} RX Rate"

Root device sensors (connected count):
  - Subclass CoordinatorEntity to auto-update from network_coordinator
  - Reads connected_count from coordinator data

async_setup_entry:
  - Create existing static sensors (model/firmware/hardware) — unchanged
  - If network_coordinator exists:
    - Create connected count sensor (root device)
    - Create network name sensor (root device, static)
    - For each adapter in network_coordinator.data["adapters"]:
      - Create TX rate sensor
      - Create RX rate sensor
```

**Requirements References**
- [powerline-network-monitoring:FR-003]: TX/RX rate sensors with Mbps unit
- [powerline-network-monitoring:FR-005]: Connected adapters count sensor
- [powerline-network-monitoring:FR-006]: Network name diagnostic sensor
- [powerline-network-monitoring:FR-002]: Remote adapter DeviceInfo with via_device

**Test Scenarios**

**TS-07: TX/RX rate sensors show converted values**
- Given: Network coordinator data with adapter tx_rate=366, rx_rate=317
- When: Sensor state is read
- Then: TX sensor shows 366, RX sensor shows 317, unit is "Mbps"

**TS-08: Connected count sensor reflects adapter count**
- Given: Network coordinator data with connected_count=1
- When: Sensor state is read
- Then: Sensor shows 1

**TS-09: Network name sensor shows name**
- Given: Network name "tJ99snLMMDmuPU7UN6WJ8wa08wdBsSvy" stored at setup
- When: Sensor state is read
- Then: Sensor shows the name, entity_category is DIAGNOSTIC

**TS-10: Remote adapter sensors have via_device to root**
- Given: Remote adapter sensor created
- When: device_info is read
- Then: via_device points to (DOMAIN, host), identifiers contain (DOMAIN, mac)

**TS-11: No network sensors when no HTTP**
- Given: No network_coordinator (no password)
- When: sensor async_setup_entry runs
- Then: Only static sensors created (model/firmware/hardware), no rate or count sensors

---

### binary_sensor.py
**Change Description** Add connectivity binary sensor per remote adapter that reads from the network coordinator. The existing root binary sensor (ping-based) remains unchanged.

**Dependants** None

**Kind** Module

**Details**
```
New entity: RemoteAdapterBinarySensor(CoordinatorEntity, BinarySensorEntity)
  - coordinator: network_coordinator
  - device_class: CONNECTIVITY
  - unique_id: {entry_id}_{mac}_connectivity
  - is_on: True if adapter found in coordinator data AND (tx_rate > 0 OR rx_rate > 0)
           None if adapter MAC not found in latest data (becomes unavailable)
  - device_info: DeviceInfo with identifiers={(DOMAIN, mac)}, via_device=(DOMAIN, host),
                 name="Powerline Adapter {MAC}", manufacturer="TP-Link", model="Powerline Adapter"

async_setup_entry:
  - Create root binary sensor (unchanged)
  - If network_coordinator exists:
    - For each adapter in network_coordinator.data["adapters"]:
      - Create RemoteAdapterBinarySensor
```

**Requirements References**
- [powerline-network-monitoring:FR-004]: Binary connectivity per remote adapter
- [powerline-network-monitoring:FR-002]: Remote adapter device registration with via_device

**Test Scenarios**

**TS-12: Remote adapter connected when rates non-zero**
- Given: Network coordinator data with adapter tx_rate=100, rx_rate=200
- When: Binary sensor state is read
- Then: is_on is True

**TS-13: Remote adapter disconnected when rates zero**
- Given: Network coordinator data with adapter tx_rate=0, rx_rate=0
- When: Binary sensor state is read
- Then: is_on is False

**TS-14: Remote adapter unavailable when MAC missing from data**
- Given: Network coordinator data with no matching MAC
- When: Binary sensor state is read
- Then: is_on is None (entity becomes unavailable)

**TS-15: Remote adapter device has via_device to root**
- Given: Remote adapter binary sensor created
- When: device_info is read
- Then: via_device is (DOMAIN, host), name contains MAC

---

## Added Components

### network_coordinator.py
**Description** DataUpdateCoordinator that fetches powerline network data (adapter list, link rates) every 60 seconds via the HTTP client. Does not raise UpdateFailed — returns last known data on transient failures so entities don't flap.

**Users** `__init__.py` (creates it), `sensor.py` (CoordinatorEntity reads data), `binary_sensor.py` (CoordinatorEntity reads data)

**Kind** Module

**Location** `custom_components/tplink_powerline/network_coordinator.py`

**Details**
```
NetworkCoordinator(DataUpdateCoordinator[dict]):
  __init__(hass, client, update_interval):
    - Stores client reference
    - Sets update_interval to 60s

  async _async_update_data() -> dict:
    - Calls client.get_network_data()
    - Returns the result dict
    - On DeviceUnavailable/UnexpectedResponse: 
      log warning, raise UpdateFailed (coordinator handles backoff)
```

**Requirements References**
- [powerline-network-monitoring:FR-007]: 60-second polling via coordinator
- [powerline-network-monitoring:FR-001]: Coordinator drives adapter discovery

**Test Scenarios**

**TS-16: Successful network data fetch**
- Given: Client returns valid network data
- When: Coordinator updates
- Then: data contains adapters list and connected_count

**TS-17: Network fetch failure raises UpdateFailed**
- Given: Client raises DeviceUnavailable
- When: Coordinator updates
- Then: UpdateFailed is raised (coordinator handles retry)

---

## Used Components

### Home Assistant DataUpdateCoordinator
**Location** `homeassistant.helpers.update_coordinator`

**Provides** Periodic polling, automatic entity update notification, error handling with backoff.

**Used By** network_coordinator.py (subclasses it), sensor.py and binary_sensor.py (CoordinatorEntity auto-subscribes)

### PowerlineClient (existing)
**Location** `custom_components/tplink_powerline/client.py`

**Provides** HTTP session management, data fetching with re-auth.

**Used By** network_coordinator.py (calls get_network_data every 60s)

---

## Documentation Considerations

- Update README to document powerline network monitoring sensors
- Note that remote adapter discovery requires password configuration

---

## Integration Test Scenarios

**ITS-01: Full setup creates root and remote adapter devices with all sensors**
- Given: Mocked HTTP client returns device info, network name, and one remote adapter
- When: Config entry with password is loaded
- Then: Root device has ping sensor, diagnostic sensors, connected count, network name. Remote device has TX, RX, connectivity sensors. Devices are linked via via_device.
- Components Involved: __init__.py, client.py, network_coordinator.py, sensor.py, binary_sensor.py

**ITS-02: Network coordinator updates sensor values**
- Given: Integration loaded, network coordinator refreshes with new rates
- When: Coordinator data changes
- Then: TX/RX rate sensors and connected count reflect new values
- Components Involved: network_coordinator.py, sensor.py

**ITS-03: No password means no network monitoring**
- Given: Config entry without password
- When: Config entry loaded
- Then: No network coordinator, no remote devices, no rate/count sensors
- Components Involved: __init__.py, sensor.py, binary_sensor.py

---

## Test Data

- Mocked network data: `{"adapters": [{"mac": "58:04:4F:D8:20:2D", "tx_rate": 366, "rx_rate": 317}], "connected_count": 1, "root_mac": "B8:FB:B3:B6:DD:DF"}`
- Raw API response: `DIDMNG.GENERAL.MACS=00:00:00:00:00:00,58:04:4f:d8:20:2d,b8:fb:b3:b6:dd:df` etc.
- Network name: `tJ99snLMMDmuPU7UN6WJ8wa08wdBsSvy`

---

## Test Feasibility

- All HTTP and coordinator interactions mocked
- No real device needed for automated tests

---

## Risks and Dependencies

| Risk | Impact | Mitigation |
|------|--------|------------|
| MAC list/rate list length mismatch | Index out of range, parsing crash | Defensive parsing — zip lists, skip mismatched entries |
| Device only allows one HTTP session — network coordinator competes with web UI | User locked out of web UI while HA polls | Documented limitation. Client re-auths if kicked out. |
| Remote adapter discovery only at setup/first poll — new adapters during runtime not added | User must reload integration to discover new adapters | Acceptable for v1. Document in README. |
| Rate values may vary wildly between polls | Noisy sensor data | Accept raw values for now — averaging is out of scope |

---

## Feasibility Review

- All QA scenarios are feasible with the designed functionality.
- QA-03 (offline detection) requires physical access to unplug the remote adapter.
- No missing infrastructure or dependencies.

---

## Task Breakdown

> **CRITICAL: Tests are written WITH implementation, not after.**

### Phase 1: Client Methods and Network Coordinator

**Task 1: Add client methods for network data**
- Status: Backlog
- Requirements: [powerline-network-monitoring:FR-001], [powerline-network-monitoring:FR-003], [powerline-network-monitoring:FR-006]
- Test Scenarios: [powerline-network-monitoring:client/TS-01], [powerline-network-monitoring:client/TS-02], [powerline-network-monitoring:client/TS-03], [powerline-network-monitoring:client/TS-04]
- Details:
  ```
  Modify: client.py — add get_network_data(), get_network_name()
  Create: tests/test_client.py — add 4 test scenarios
  Modify: const.py — add NETWORK_SCAN_INTERVAL
  ```

**Task 2: Implement network coordinator**
- Status: Backlog
- Requirements: [powerline-network-monitoring:FR-007]
- Test Scenarios: [powerline-network-monitoring:network_coordinator/TS-16], [powerline-network-monitoring:network_coordinator/TS-17]
- Details:
  ```
  Create: network_coordinator.py
  Create: tests/test_network_coordinator.py — 2 test scenarios
  ```

### Phase 2: Entities, Setup Wiring, Integration Tests

**Task 3: Update setup to create network coordinator**
- Status: Backlog
- Requirements: [powerline-network-monitoring:FR-006], [powerline-network-monitoring:FR-007]
- Test Scenarios: [powerline-network-monitoring:init/TS-05], [powerline-network-monitoring:init/TS-06]
- Details:
  ```
  Modify: __init__.py — create network coordinator, fetch network name, store in hass.data
  Modify: tests/test_init.py — add 2 test scenarios
  ```

**Task 4: Add remote adapter binary sensors**
- Status: Backlog
- Requirements: [powerline-network-monitoring:FR-004], [powerline-network-monitoring:FR-002]
- Test Scenarios: [powerline-network-monitoring:binary_sensor/TS-12], [powerline-network-monitoring:binary_sensor/TS-13], [powerline-network-monitoring:binary_sensor/TS-14], [powerline-network-monitoring:binary_sensor/TS-15]
- Details:
  ```
  Modify: binary_sensor.py — add RemoteAdapterBinarySensor, update async_setup_entry
  Modify: tests/test_binary_sensor.py — add 4 test scenarios
  ```

**Task 5: Add rate, count, and network name sensors + integration tests**
- Status: Backlog
- Requirements: [powerline-network-monitoring:FR-003], [powerline-network-monitoring:FR-005], [powerline-network-monitoring:FR-006], [powerline-network-monitoring:FR-002]
- Test Scenarios: [powerline-network-monitoring:sensor/TS-07], [powerline-network-monitoring:sensor/TS-08], [powerline-network-monitoring:sensor/TS-09], [powerline-network-monitoring:sensor/TS-10], [powerline-network-monitoring:sensor/TS-11], [powerline-network-monitoring:ITS-01], [powerline-network-monitoring:ITS-02], [powerline-network-monitoring:ITS-03]
- Details:
  ```
  Modify: sensor.py — add rate sensors, connected count, network name, update async_setup_entry
  Modify: tests/test_sensor.py — add 5 unit test scenarios
  Create: tests/test_network_integration.py — 3 integration test scenarios
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
- **NetworkCoordinator:** DataUpdateCoordinator that polls adapter list and link rates every 60s
- **via_device:** HA device registry concept linking a child device to a parent device
- **connected_count:** Number of remote adapters with non-zero TX or RX rates

### References
- [HA DataUpdateCoordinator](https://developers.home-assistant.io/docs/integration_fetching_data)
- [HA Device Registry via_device](https://developers.home-assistant.io/docs/device_registry_index)
- Device API data format documented in specification appendix

### Change History
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-10 | Pete | Initial design |

---
