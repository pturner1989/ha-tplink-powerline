# Design: Device Info via HTTP Portal

**Version:** 1.0
**Date:** 2026-04-10
**Status:** Implemented
**Linked Specification** `.sdd/device-info-http/specification.md`

---

# Design Document

---

## Architecture Overview

### Current Architecture Context

The integration has a config flow that collects host and name, a coordinator that pings every 15s, and a binary sensor for connectivity. The device registry entry uses placeholder values for model/manufacturer. There is no HTTP communication with the device.

### Proposed Architecture

```
Config Flow → collects host, name, password (MD5-hashed)
                ↓
async_setup_entry:
  1. Create PowerlineClient(host, password_hash, session)
  2. If password present: client.login() → client.get_device_info()
  3. Store device_info in hass.data alongside coordinator
  4. Create Coordinator (unchanged ping logic)
  5. Forward to binary_sensor + sensor platforms
                ↓
Binary Sensor: reads coordinator data (unchanged)
Sensor: reads device_info from hass.data (static, set once)
```

The HTTP client is a lightweight wrapper around `aiohttp.ClientSession`. It handles login, session token management, data fetching, and re-authentication. Device info is fetched once during setup and stored — it does not participate in the polling cycle.

### Technology Decisions

- **aiohttp via HA's `async_get_clientsession`:** Consistent with HA patterns. The client must explicitly set `Content-Type: application/x-www-form-urlencoded` on every request (no `charset=UTF-8` — the device rejects it).
- **MD5 at config flow time:** The password is hashed immediately in the config flow and only the hash is stored. The plaintext is never persisted.
- **Session maintained for config entry lifetime:** The client stays logged in rather than login/fetch/logout per cycle. This keeps the session available for future features (link quality polling). If the session is invalidated externally (e.g., user opens web UI), the client re-authenticates on next use.
- **Graceful fallback:** If no password is provided or HTTP fails, the integration falls back to ping-only mode with placeholder device info. No errors are raised — the binary sensor still works.

### Quality Attributes

- **Backwards compatibility:** Existing config entries without a password continue to work unchanged.
- **Extensibility:** The client's `get_data` method accepts arbitrary key lists, making it reusable for future features (link quality, satellite devices).
- **Resilience:** HTTP failures don't block the integration — device info is best-effort enrichment on top of the core ping functionality.

---

## Modified Components

### config_flow.py
**Change Description** Currently collects host and name. Adds a password field (optional) that is MD5-hashed before storage. Adds validation that the password authenticates successfully against the device's HTTP portal. If password is empty, skips HTTP validation (ping-only mode).

**Dependants** `__init__.py` (reads password hash from config entry data), `client.py` (uses the hash to login)

**Kind** Module

**Details**
```
STEP_USER_DATA_SCHEMA adds:
  vol.Optional(CONF_PASSWORD, default=""): str

async_step_user changes:
  - After ping validation passes:
    - If password is non-empty:
      - MD5 hash the password
      - Attempt HTTP login via PowerlineClient
      - If login fails with auth error → show "invalid_auth" error
      - If login succeeds → store MD5 hash in entry data as CONF_PASSWORD_HASH
      - Logout/close client (setup will create its own)
    - If password is empty:
      - Skip HTTP validation, don't store password hash
  - Create entry with data including password_hash (if present)
```

**Requirements References**
- [device-info-http:FR-001]: Password field, MD5 hashing, validation, backwards compatibility

**Test Scenarios**

**TS-01: Config flow with valid password**
- Given: Device at host responds to ping and accepts the password
- When: User submits config flow with host, name, and password
- Then: Entry created with password_hash in data, title set to name

**TS-02: Config flow with wrong password**
- Given: Device at host responds to ping but rejects the password
- When: User submits config flow with host, name, and wrong password
- Then: Form redisplayed with "invalid_auth" error

**TS-03: Config flow without password**
- Given: Device at host responds to ping
- When: User submits config flow with host and name, no password
- Then: Entry created without password_hash, title set to name

---

### __init__.py
**Change Description** Currently creates coordinator and forwards to binary_sensor. Now also creates PowerlineClient (if password present), fetches device info, stores it in hass.data, and forwards to the sensor platform additionally.

**Dependants** `binary_sensor.py` (reads device_info for DeviceInfo), `sensor.py` (reads device_info for entity values)

**Kind** Module

**Details**
```
PLATFORMS adds Platform.SENSOR

async_setup_entry changes:
  - If CONF_PASSWORD_HASH in entry.data:
    - Create PowerlineClient(host, password_hash, async_get_clientsession(hass))
    - Try: await client.login()
    - Try: device_info = await client.get_device_info()
    - On failure: device_info = None, log warning
  - Else: device_info = None
  - Store in hass.data[DOMAIN][entry.entry_id]:
    - "coordinator": coordinator
    - "client": client (or None)
    - "device_info": device_info (or None)

async_unload_entry changes:
  - If client exists: await client.logout()
```

**Requirements References**
- [device-info-http:FR-002]: Creates client, manages login/logout lifecycle
- [device-info-http:FR-003]: Fetches device info at setup
- [device-info-http:FR-004]: Stores device_info for binary_sensor DeviceInfo enrichment

**Test Scenarios**

**TS-04: Setup with password fetches device info**
- Given: A config entry with host and password_hash, device reachable and auth succeeds
- When: async_setup_entry is called
- Then: hass.data contains device_info with model, firmware, hardware values

**TS-05: Setup with password but HTTP fails falls back gracefully**
- Given: A config entry with password_hash, device reachable via ping but HTTP login fails
- When: async_setup_entry is called
- Then: hass.data has device_info=None, integration loads successfully, binary sensor works

**TS-06: Setup without password skips HTTP entirely**
- Given: A config entry without password_hash
- When: async_setup_entry is called
- Then: hass.data has client=None, device_info=None, integration loads, binary sensor works

**TS-07: Unload logs out HTTP client**
- Given: A loaded config entry with an active HTTP client
- When: async_unload_entry is called
- Then: client.logout() is called, resources cleaned up

---

### binary_sensor.py
**Change Description** Currently uses hardcoded "Powerline Adapter" for model in DeviceInfo. Now reads device_info from hass.data to populate model, sw_version, and hw_version in DeviceInfo. Falls back to placeholder if device_info is None.

**Dependants** None

**Kind** Module

**Details**
```
async_setup_entry changes:
  - Reads device_info from hass.data[DOMAIN][entry.entry_id]["device_info"]
  - Passes device_info to TplinkPowerlineBinarySensor constructor

TplinkPowerlineBinarySensor.__init__ changes:
  - If device_info is not None:
    - model = device_info["model"]
    - sw_version = device_info["firmware"]
    - hw_version = device_info["hardware"]
  - Else: model = "Powerline Adapter", no sw/hw version
  - Sets self._attr_device_info with these values
```

**Requirements References**
- [device-info-http:FR-004]: Device registry shows real model, firmware, hardware version

**Test Scenarios**

**TS-08: Device info populated from HTTP data**
- Given: device_info with model="PG2400P", firmware="1.0.3 ...", hardware="1.0"
- When: Binary sensor's device_info is read
- Then: model is "PG2400P", sw_version is "1.0.3 ...", hw_version is "1.0"

**TS-09: Device info falls back when HTTP unavailable**
- Given: device_info is None
- When: Binary sensor's device_info is read
- Then: model is "Powerline Adapter", no sw_version or hw_version

---

### const.py
**Change Description** Adds new constants for the password hash config key and HTTP client parameters.

**Dependants** All modules that reference the new constants.

**Kind** Module

**Details**
```
Added constants:
  CONF_PASSWORD_HASH = "password_hash"
  HTTP_TIMEOUT = 10  # seconds
  CONTENT_TYPE = "application/x-www-form-urlencoded"
```

**Requirements References**
- [device-info-http:FR-001]: CONF_PASSWORD_HASH for config entry storage
- [device-info-http:FR-002]: HTTP_TIMEOUT, CONTENT_TYPE for client requests

**Test Scenarios**

No unit tests — static constants.

---

### strings.json / translations/en.json
**Change Description** Adds password field label, description, and new error string for invalid_auth.

**Dependants** Config flow UI rendering.

**Kind** Files (JSON)

**Details**
```
config.step.user.data adds:
  "password": "Password"
config.step.user.data_description adds:
  "password": "The admin password for the device's web portal (optional)"
config.error adds:
  "invalid_auth": "Invalid password. Check the password and try again."
```

**Requirements References**
- [device-info-http:FR-001]: UI strings for password field and auth error

**Test Scenarios**

No unit tests — validated through config flow tests.

---

## Added Components

### client.py
**Description** Async HTTP client for the TP-Link powerline device's local web portal. Handles authentication (login/logout), session token management, and data fetching. Manages the critical `Content-Type` constraint (no charset=UTF-8).

**Users** `__init__.py` (creates client at setup, calls login/get_device_info/logout), `config_flow.py` (creates temporary client to validate password)

**Kind** Module

**Location** `custom_components/tplink_powerline/client.py`

**Details**
```
Exceptions:
  AuthenticationError(Exception)  - wrong password or session full
  DeviceUnavailable(Exception)    - network/connection error
  UnexpectedResponse(Exception)   - response not in expected format

PowerlineClient:
  Properties:
    host: str
    password_hash: str
    session: aiohttp.ClientSession
    token: str | None

  __init__(host, password_hash, session):
    - Stores host, password_hash, session
    - token = None

  async login():
    - POST to http://{host}/ with body TPLINK.GENERAL.LOGIN_PASSWORD={password_hash}
    - Headers: Content-Type: application/x-www-form-urlencoded, Referer: http://{host}/
    - Parse response: ERROR=000 + TOKEN=xxx → store token
    - ERROR=006 → raise AuthenticationError("Wrong password")
    - ERROR=008 → raise AuthenticationError("Session full")
    - Other errors / network failure → raise DeviceUnavailable
    - Timeout: HTTP_TIMEOUT seconds

  async logout():
    - If no token, return
    - POST to http://{host}/ with body _t={token}&COMMAND=logout
    - Clear token regardless of response
    - Swallow exceptions (best-effort cleanup)

  async get_data(keys: list[str]) -> dict[str, str]:
    - If no token, raise DeviceUnavailable
    - GET http://{host}/?_t={token}&KEY1=&KEY2=&KEY3=
    - Headers: Content-Type: application/x-www-form-urlencoded, Referer: http://{host}/
    - Parse response: lines of KEY=value, skip ERROR= line
    - If ERROR != 000 and error is auth-related (003, 004, 005):
      - Try re-login once, retry the GET
    - Return dict of {key: value}
    - Network/timeout → raise DeviceUnavailable
    - Unparseable response → raise UnexpectedResponse

  async get_device_info() -> dict[str, str]:
    - Calls get_data(["SYSTEM.PRODUCTION.HW_PRODUCT", "SYSTEM.PRODUCTION.HW_REVISION", "SYSTEM.GENERAL.FW_VERSION"])
    - Returns {"model": ..., "firmware": ..., "hardware": ...}
```

**Requirements References**
- [device-info-http:FR-002]: Login, session management, re-authentication, Content-Type constraint
- [device-info-http:FR-003]: Data fetching with key list, response parsing, device info retrieval

**Test Scenarios**

**TS-10: Successful login**
- Given: Device accepts the password
- When: client.login() is called
- Then: token is set, no exception raised

**TS-11: Login with wrong password**
- Given: Device rejects the password (ERROR=006)
- When: client.login() is called
- Then: AuthenticationError is raised

**TS-12: Login with device unreachable**
- Given: Device is not reachable
- When: client.login() is called
- Then: DeviceUnavailable is raised

**TS-13: Successful data fetch**
- Given: Client is logged in with a valid token
- When: client.get_data(["KEY1", "KEY2"]) is called
- Then: Returns {"KEY1": "val1", "KEY2": "val2"}

**TS-14: Data fetch with expired session triggers re-auth**
- Given: Client has an expired token (device returns auth error)
- When: client.get_data(keys) is called
- Then: Client re-authenticates and retries, returns data successfully

**TS-15: Data fetch with device unreachable**
- Given: Client is logged in but device becomes unreachable
- When: client.get_data(keys) is called
- Then: DeviceUnavailable is raised

**TS-16: get_device_info returns structured data**
- Given: Client is logged in, device returns valid system info
- When: client.get_device_info() is called
- Then: Returns {"model": "PG2400P", "firmware": "1.0.3 ...", "hardware": "1.0"}

**TS-17: Logout clears token**
- Given: Client is logged in with a valid token
- When: client.logout() is called
- Then: Token is cleared, no exception raised

**TS-18: Content-Type has no charset**
- Given: Any request to the device
- When: The request is sent
- Then: Content-Type header is exactly "application/x-www-form-urlencoded" with no charset suffix

---

### sensor.py
**Description** Sensor platform that creates diagnostic entities for model, firmware version, and hardware version. Entities are static — values are set once at setup from device_info and do not poll.

**Users** HA entity platform framework (loaded via async_setup_entry)

**Kind** Module

**Location** `custom_components/tplink_powerline/sensor.py`

**Details**
```
SENSOR_DESCRIPTIONS = [
  {"key": "model", "name": "Model", "icon": "mdi:router-network"},
  {"key": "firmware", "name": "Firmware Version", "icon": "mdi:memory"},
  {"key": "hardware", "name": "Hardware Version", "icon": "mdi:chip"},
]

async_setup_entry(hass, entry, async_add_entities):
  - Get device_info from hass.data[DOMAIN][entry.entry_id]["device_info"]
  - If device_info is None: return (no sensors to create)
  - Create TplinkPowerlineSensor for each description
  - async_add_entities(sensors)

TplinkPowerlineSensor(SensorEntity):
  _attr_entity_category = EntityCategory.DIAGNOSTIC

  __init__(entry, device_info, description):
    - unique_id = f"{entry.entry_id}_{description['key']}"
    - name = f"{entry.data[CONF_NAME]} {description['name']}"
    - _attr_native_value = device_info[description["key"]]
    - _attr_icon = description["icon"]
    - device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.data[CONF_HOST])},
        ... (same identifiers as binary_sensor to link to same device)
      )
```

**Requirements References**
- [device-info-http:FR-005]: Three diagnostic sensor entities with correct values and entity category

**Test Scenarios**

**TS-19: Sensors created with correct values**
- Given: device_info with model="PG2400P", firmware="1.0.3 ...", hardware="1.0"
- When: Sensor entities are created
- Then: Three sensors exist with correct native_value and entity_category=DIAGNOSTIC

**TS-20: No sensors created when device_info is None**
- Given: device_info is None (no password or HTTP failed)
- When: async_setup_entry for sensor platform is called
- Then: No sensor entities are created

**TS-21: Sensors share device with binary sensor**
- Given: device_info is available
- When: Sensor entities are created
- Then: Sensors have same device identifiers as the binary sensor (linked to same device)

---

## Used Components

### Home Assistant async_get_clientsession
**Location** `homeassistant.helpers.aiohttp_client`

**Provides** Shared aiohttp.ClientSession managed by HA. Handles connection pooling and cleanup.

**Used By** `__init__.py` (passes to PowerlineClient), `config_flow.py` (passes to temporary PowerlineClient for validation)

### Home Assistant SensorEntity
**Location** `homeassistant.components.sensor`

**Provides** Sensor entity base class with native_value, entity_category, icon support.

**Used By** `sensor.py` (TplinkPowerlineSensor subclasses it)

### Home Assistant EntityCategory
**Location** `homeassistant.helpers.entity`

**Provides** Entity category enum with DIAGNOSTIC value for marking entities as diagnostic.

**Used By** `sensor.py` (sets entity_category on diagnostic sensors)

---

## Documentation Considerations

- Update README.md to document the password field and HTTP portal features
- Note the single-session limitation in README

---

## Integration Test Scenarios

**ITS-01: Full setup with password creates device with real info and sensors**
- Given: A mocked HTTP client that returns device info
- When: Config entry with password_hash is loaded
- Then: Device registry shows real model/firmware/hardware, three diagnostic sensors exist with correct values, binary sensor works
- Components Involved: __init__.py, client.py, binary_sensor.py, sensor.py

**ITS-02: Setup with password but HTTP failure falls back gracefully**
- Given: A mocked HTTP client that raises DeviceUnavailable on login
- When: Config entry with password_hash is loaded
- Then: Device registry shows placeholder, no diagnostic sensors, binary sensor works
- Components Involved: __init__.py, client.py, binary_sensor.py, sensor.py

**ITS-03: Setup without password is ping-only**
- Given: A config entry without password_hash
- When: Config entry is loaded
- Then: No HTTP client created, device shows placeholder, no diagnostic sensors, binary sensor works
- Components Involved: __init__.py, binary_sensor.py, sensor.py

---

## Test Data

- Mocked HTTP responses: login success (`ERROR=000\r\nTOKEN=testtoken123\r\n`), login failure (`ERROR=006\r\nLOGIN_TIMES=1\r\n`), device info (`ERROR=000\r\nSYSTEM.PRODUCTION.HW_PRODUCT=PG2400P\r\nSYSTEM.PRODUCTION.HW_REVISION=1.0\r\nSYSTEM.GENERAL.FW_VERSION=1.0.3 Build 20221213 Rel.62540\r\n`)
- Config entry data: `{host: "192.168.1.34", name: "Powerline Network", password_hash: "cc03e747a6afbbcbf8be7668acfebee5"}`

---

## Test Feasibility

- All HTTP interactions mocked via `aioresponses` or patched PowerlineClient methods
- No real device needed for automated tests
- QA scenarios require the real device at 192.168.1.34

---

## Risks and Dependencies

| Risk | Impact | Mitigation |
|------|--------|------------|
| Device firmware update changes API format | HTTP fetch breaks, sensors show incorrect values | Defensive parsing in client.py — return None for unparseable values rather than crashing |
| Device only allows one session — HA login kicks out user from web UI | User frustration | Document in README. Session persists silently — user can re-open web UI which kicks HA out, and HA re-authenticates on next use |
| charset=UTF-8 in Content-Type breaks all requests | 405 errors | Explicit Content-Type on every request in client.py. Unit test verifies no charset |
| aiohttp defaults may add charset to Content-Type | Silent breakage | Test that verifies the exact header value sent |

---

## Feasibility Review

- All QA scenarios are feasible with the designed functionality — no white-box setup required.
- QA-03 (no password) tests backwards compatibility which is fully handled by the optional password field.
- QA-04 (restart) works because async_setup_entry re-creates the client and re-fetches device info on every load.

---

## Task Breakdown

> **CRITICAL: Tests are written WITH implementation, not after.**

### Phase 1: HTTP Client and Config Flow Changes

**Task 1: Add constants and update strings**
- Status: Backlog
- Requirements: [device-info-http:FR-001], [device-info-http:FR-002]
- Test Scenarios: (no unit tests — static constants and JSON)
- Details:
  ```
  Modify:
  - const.py: add CONF_PASSWORD_HASH, HTTP_TIMEOUT, CONTENT_TYPE
  - strings.json: add password field, data_description, invalid_auth error
  - translations/en.json: same changes as strings.json
  ```

**Task 2: Implement HTTP client**
- Status: Backlog
- Requirements: [device-info-http:FR-002], [device-info-http:FR-003]
- Test Scenarios: [device-info-http:client/TS-10], [device-info-http:client/TS-11], [device-info-http:client/TS-12], [device-info-http:client/TS-13], [device-info-http:client/TS-14], [device-info-http:client/TS-15], [device-info-http:client/TS-16], [device-info-http:client/TS-17], [device-info-http:client/TS-18]
- Details:
  ```
  Create:
  - custom_components/tplink_powerline/client.py
  - tests/test_client.py (9 test scenarios)
  
  PowerlineClient with login(), logout(), get_data(), get_device_info().
  Exceptions: AuthenticationError, DeviceUnavailable, UnexpectedResponse.
  All requests use explicit Content-Type without charset.
  Re-authentication on auth errors during get_data.
  ```

**Task 3: Update config flow with password field**
- Status: Backlog
- Requirements: [device-info-http:FR-001]
- Test Scenarios: [device-info-http:config_flow/TS-01], [device-info-http:config_flow/TS-02], [device-info-http:config_flow/TS-03]
- Details:
  ```
  Modify:
  - config_flow.py: add password field, MD5 hashing, HTTP validation
  - tests/test_config_flow.py: add 3 new test scenarios (existing tests updated for schema change)
  ```

### Phase 2: Setup Integration, Sensors, and Device Info

**Task 4: Update setup/teardown for HTTP client and device info**
- Status: Backlog
- Requirements: [device-info-http:FR-002], [device-info-http:FR-003], [device-info-http:FR-004]
- Test Scenarios: [device-info-http:init/TS-04], [device-info-http:init/TS-05], [device-info-http:init/TS-06], [device-info-http:init/TS-07]
- Details:
  ```
  Modify:
  - __init__.py: create client, fetch device_info, store in hass.data, add SENSOR platform, logout on unload
  - tests/test_init.py: add 4 new test scenarios
  ```

**Task 5: Update binary sensor with real device info**
- Status: Backlog
- Requirements: [device-info-http:FR-004]
- Test Scenarios: [device-info-http:binary_sensor/TS-08], [device-info-http:binary_sensor/TS-09]
- Details:
  ```
  Modify:
  - binary_sensor.py: read device_info from hass.data, populate DeviceInfo with real model/sw_version/hw_version
  - tests/test_binary_sensor.py: add 2 new test scenarios
  ```

**Task 6: Implement diagnostic sensor entities and integration tests**
- Status: Backlog
- Requirements: [device-info-http:FR-005]
- Test Scenarios: [device-info-http:sensor/TS-19], [device-info-http:sensor/TS-20], [device-info-http:sensor/TS-21], [device-info-http:ITS-01], [device-info-http:ITS-02], [device-info-http:ITS-03]
- Details:
  ```
  Create:
  - custom_components/tplink_powerline/sensor.py
  - tests/test_sensor.py (3 unit test scenarios)
  - tests/test_integration.py (3 integration test scenarios)
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
- **PowerlineClient:** The HTTP client class that wraps device portal communication
- **device_info:** A dict with keys "model", "firmware", "hardware" — fetched once at setup
- **password_hash:** MD5 hex digest of the user's device password

### References
- [TP-Link device HTTP API](../../../memory/project_device_http_api.md) (project memory)
- [HA aiohttp client helper](https://developers.home-assistant.io/docs/api_lib_auth)
- [HA entity category](https://developers.home-assistant.io/docs/core/entity#entity-category)

### Change History
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-10 | Pete | Initial design |

---
