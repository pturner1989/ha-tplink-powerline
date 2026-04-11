# Design: Graceful Compatibility

**Version:** 1.0
**Date:** 2026-04-11
**Status:** Implemented
**Linked Specification** `.sdd/graceful-compatibility/specification.md`

---

# Design Document

---

## Architecture Overview

### Current Architecture Context

The integration assumes the device follows the TP-Link MERProxyNew API pattern. Login failures from non-auth causes silently fall through to ping-only mode in both the config flow and setup. The network coordinator catches `DeviceUnavailable` and `UnexpectedResponse` but not `ValueError`/`KeyError` from data parsing. Individual `_fetch_*` methods catch all exceptions internally, which is already correct for partial degradation.

### Proposed Architecture

Three layers of defence:

1. **Config flow** — probes the portal during setup. If the response is HTML/JSON/unparseable, shows a new `confirm_ping_only` step with a clear explanation. User decides: ping-only or cancel.

2. **Setup** — each feature category (device_info, network_name, network_coordinator) probed independently with its own try/except. Already partially implemented; needs the single broad `except Exception` split into per-feature catches.

3. **Coordinator** — `_async_update_data` catches `Exception` (not just specific types) from `get_network_data`. Individual `_fetch_*` methods already catch all exceptions. `get_network_data` itself is hardened against malformed arrays.

### Technology Decisions

- **New `IncompatibleDevice` exception:** Raised by `login()` when the response is not in the expected format. Distinct from auth and connectivity errors so the config flow can branch appropriately.
- **Login response format detection:** Check for HTML tags (`<html`, `<!DOCTYPE`) and absence of the `ERROR=` pattern. If the response has no `ERROR=` line and isn't empty, it's incompatible.
- **Multi-step config flow:** The `confirm_ping_only` step uses HA's standard form mechanism with a description and submit button. Aborting from this step uses reason `"incompatible_device"`.

---

## Modified Components

### client.py
**Change Description** Add `IncompatibleDevice` exception. Modify `login()` to detect incompatible responses before parsing. Harden `get_network_data()` against malformed arrays.

**Dependants** config_flow.py (catches IncompatibleDevice), __init__.py (catches IncompatibleDevice)

**Kind** Module

**Details**
```
New exception:
  IncompatibleDevice(Exception) — device responded but portal is not compatible

login() changes:
  After receiving response text, before calling _parse_response:
  - If response contains "<html" or "<!DOCTYPE" (case-insensitive): raise IncompatibleDevice
  - If response is empty or _parse_response returns no error_code: raise IncompatibleDevice
  - Existing error_code handling unchanged

get_network_data() changes:
  - Wrap the entire parsing block in try/except (ValueError, KeyError, IndexError)
  - On parse error: return empty result {"adapters": [], "connected_count": 0, "root_mac": ""}
  - Already uses .isdigit() for rate parsing, but add explicit guard for empty split results
```

**Requirements References**
- [graceful-compatibility:FR-005]: IncompatibleDevice exception and login validation
- [graceful-compatibility:FR-003]: Resilient get_network_data parsing

**Test Scenarios**

**TS-01: Login detects HTML response as incompatible**
- Given: Device returns HTML to login POST
- When: client.login() called
- Then: IncompatibleDevice raised

**TS-02: Login detects empty/unparseable response as incompatible**
- Given: Device returns random text with no ERROR= pattern
- When: client.login() called
- Then: IncompatibleDevice raised

**TS-03: Login still works for compatible device**
- Given: Device returns ERROR=000 + TOKEN
- When: client.login() called
- Then: Token set, no exception (regression check)

**TS-04: Login still raises AuthenticationError for wrong password**
- Given: Device returns ERROR=006
- When: client.login() called
- Then: AuthenticationError raised (regression check)

**TS-05: get_network_data handles mismatched array lengths**
- Given: MACS has 3 entries, RX_BPS has 1 entry
- When: get_network_data() called
- Then: Returns adapters with rate 0 for missing entries, no crash

**TS-06: get_network_data handles empty MACS**
- Given: MACS key is empty string
- When: get_network_data() called
- Then: Returns empty adapters list

---

### config_flow.py
**Change Description** Add `async_step_confirm_ping_only` step. Modify `async_step_user` to catch `IncompatibleDevice` from login and redirect to the new step instead of silently continuing.

**Dependants** strings.json, translations/en.json (new step text)

**Kind** Module

**Details**
```
async_step_user changes:
  In the password validation block:
  - except AuthenticationError → errors["base"] = "invalid_auth" (unchanged)
  - except IncompatibleDevice → store user_input in self._user_input,
    return await self.async_step_confirm_ping_only()
  - except Exception → log warning, continue without password (unchanged)

New step: async_step_confirm_ping_only(user_input=None)
  - If user_input is not None (form submitted):
    - Create entry from self._user_input without password_hash (ping-only)
  - If user_input is None (first show):
    - Show form with description explaining incompatibility
    - Submit button = "Continue (ping only)"
    - Menu option to abort (standard HA back button aborts)
```

**Requirements References**
- [graceful-compatibility:FR-001]: Detects incompatible portal, shows warning
- [graceful-compatibility:FR-002]: New confirm_ping_only step with continue/cancel

**Test Scenarios**

**TS-07: Incompatible device triggers confirm_ping_only step**
- Given: Device responds to ping, login raises IncompatibleDevice
- When: User submits config flow with host and password
- Then: Flow shows confirm_ping_only step (not create_entry, not error)

**TS-08: Confirm ping-only creates entry without password**
- Given: User is on confirm_ping_only step
- When: User submits (confirms)
- Then: Entry created without password_hash, title from original input

**TS-09: Compatible device still works normally**
- Given: Device login succeeds
- When: User submits config flow with host and password
- Then: Entry created with password_hash (regression check)

---

### strings.json / translations/en.json
**Change Description** Add text for the new confirm_ping_only step and incompatible_device abort reason.

**Kind** Files (JSON)

**Details**
```
config.step.confirm_ping_only:
  title: "Incompatible Device"
  description: "This device's web portal is not compatible with this integration.
    You can continue with ping-only monitoring (basic availability only)
    or go back to check the device address."
  submit: "Continue (ping only)"

config.abort.incompatible_device:
  "This device's web portal is not compatible."
```

**Requirements References**
- [graceful-compatibility:FR-001]: User-facing incompatibility message
- [graceful-compatibility:FR-002]: Step description text

---

### __init__.py
**Change Description** Split the single broad `except Exception` in setup into per-feature try/except blocks. Each feature (login, device_info, network_name, network_coordinator) fails independently.

**Kind** Module

**Details**
```
async_setup_entry changes:
  if password_hash:
    client = PowerlineClient(...)
    
    # Login
    try:
      await client.login()
    except Exception:
      log warning, client = None
    
    # Device info (only if logged in)
    if client:
      try:
        device_info = await client.get_device_info()
      except Exception:
        log warning, device_info = None
    
    # Network name (only if logged in)
    if client:
      try:
        network_name = await client.get_network_name()
      except Exception:
        log warning, network_name = None
    
    # Network coordinator (only if logged in)
    if client:
      try:
        net_coord = NetworkCoordinator(hass, client)
        await net_coord.async_config_entry_first_refresh()
        network_coordinator = net_coord
      except Exception:
        log warning, network_coordinator = None
```

**Requirements References**
- [graceful-compatibility:FR-004]: Independent feature probing at setup

**Test Scenarios**

**TS-10: Device info failure doesn't block network coordinator**
- Given: get_device_info raises, but network coordinator works
- When: Setup runs
- Then: device_info is None, network_coordinator has data

**TS-11: Network coordinator failure doesn't block device info**
- Given: get_device_info works, network coordinator first refresh fails
- When: Setup runs
- Then: device_info populated, network_coordinator is None

---

### network_coordinator.py
**Change Description** Widen the exception catch in `_async_update_data` to catch `Exception` instead of just `DeviceUnavailable` and `UnexpectedResponse`.

**Kind** Module

**Details**
```
_async_update_data changes:
  try:
    network = await self.client.get_network_data()
  except Exception as err:  # was (DeviceUnavailable, UnexpectedResponse)
    raise UpdateFailed(f"Failed to fetch network data: {err}") from err
```

**Requirements References**
- [graceful-compatibility:FR-006]: Catches ValueError/KeyError/IndexError as UpdateFailed

**Test Scenarios**

**TS-12: ValueError from parsing raises UpdateFailed**
- Given: get_network_data raises ValueError
- When: Coordinator updates
- Then: UpdateFailed raised (not unhandled exception)

---

## Used Components

### Home Assistant ConfigFlow multi-step
**Location** `homeassistant.config_entries`
**Provides** Multi-step config flow with `async_step_<name>` methods, form display, abort handling
**Used By** config_flow.py (new confirm_ping_only step)

---

## Documentation Considerations

- Update README to note that incompatible devices get a config flow warning

---

## Integration Test Scenarios

**ITS-01: Incompatible device full flow to ping-only**
- Given: Mocked client login raises IncompatibleDevice
- When: Config flow completes through confirm_ping_only
- Then: Entry created, loaded, only ping binary sensor exists
- Components Involved: config_flow.py, __init__.py, binary_sensor.py

**ITS-02: Partial feature support creates partial entities**
- Given: Login works, device_info works, network coordinator first refresh fails
- When: Setup runs
- Then: Device info sensors exist, no network/control entities
- Components Involved: __init__.py, sensor.py, binary_sensor.py

---

## Test Data

- Incompatible HTML response: `<!DOCTYPE html><html><body>Not a powerline</body></html>`
- Incompatible JSON response: `{"error": "unknown"}`
- Malformed network data: MACS with 3 entries, RX_BPS with 1 entry

---

## Test Feasibility

- All scenarios fully testable with mocks
- QA-02 (incompatible device) testable against a router or other device on the network

---

## Risks and Dependencies

| Risk | Impact | Mitigation |
|------|--------|------------|
| False positive incompatibility detection for slow devices | User unnecessarily warned | Only trigger on format mismatch, not timeouts (DeviceUnavailable handles those) |
| Some TP-Link models return a slightly different but still valid format | Overly strict format detection rejects valid devices | Check for absence of ERROR= pattern, not strict format matching |

---

## Feasibility Review

- All QA scenarios feasible
- No missing infrastructure

---

## Task Breakdown

> **CRITICAL: Tests are written WITH implementation, not after.**

### Phase 1: Client Hardening and New Exception

**Task 1: Add IncompatibleDevice exception and harden client**
- Status: Backlog
- Requirements: [graceful-compatibility:FR-005], [graceful-compatibility:FR-003]
- Test Scenarios: [graceful-compatibility:client/TS-01], [graceful-compatibility:client/TS-02], [graceful-compatibility:client/TS-03], [graceful-compatibility:client/TS-04], [graceful-compatibility:client/TS-05], [graceful-compatibility:client/TS-06]
- Details:
  ```
  Modify: client.py — add IncompatibleDevice, harden login() and get_network_data()
  Modify: tests/test_client.py — add 6 test scenarios (4 are regression checks)
  ```

**Task 2: Widen coordinator exception catch**
- Status: Backlog
- Requirements: [graceful-compatibility:FR-006]
- Test Scenarios: [graceful-compatibility:network_coordinator/TS-12]
- Details:
  ```
  Modify: network_coordinator.py — catch Exception instead of specific types
  Modify: tests/test_network_coordinator.py — add 1 test scenario
  ```

### Phase 2: Config Flow and Setup Changes

**Task 3: Add confirm_ping_only config flow step**
- Status: Backlog
- Requirements: [graceful-compatibility:FR-001], [graceful-compatibility:FR-002]
- Test Scenarios: [graceful-compatibility:config_flow/TS-07], [graceful-compatibility:config_flow/TS-08], [graceful-compatibility:config_flow/TS-09]
- Details:
  ```
  Modify: config_flow.py — add async_step_confirm_ping_only, catch IncompatibleDevice
  Modify: strings.json, translations/en.json — add step text
  Modify: tests/test_config_flow.py — add 3 test scenarios
  ```

**Task 4: Split setup into per-feature probes + integration tests**
- Status: Backlog
- Requirements: [graceful-compatibility:FR-004]
- Test Scenarios: [graceful-compatibility:init/TS-10], [graceful-compatibility:init/TS-11], [graceful-compatibility:ITS-01], [graceful-compatibility:ITS-02]
- Details:
  ```
  Modify: __init__.py — split broad except into per-feature try/except
  Modify: tests/test_init.py — add 2 test scenarios
  Create: tests/test_compatibility_integration.py — 2 integration tests
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
- **IncompatibleDevice:** Exception raised when the device's HTTP response doesn't match the expected TP-Link MERProxyNew format
- **confirm_ping_only:** Config flow step shown when an incompatible portal is detected

### References
- [HA multi-step config flow](https://developers.home-assistant.io/docs/config_entries_config_flow_handler)

### Change History
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-11 | Pete | Initial design |

---
