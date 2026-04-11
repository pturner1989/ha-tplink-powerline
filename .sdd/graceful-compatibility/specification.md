# Specification: Graceful Compatibility

**Version:** 1.0
**Date:** 2026-04-11
**Status:** Implemented

---

## Problem Statement

When a user adds a TP-Link powerline device with a different or incompatible HTTP portal, the integration either silently falls back to ping-only mode (if login fails) or crashes when individual features return unexpected data. Users get no feedback about why HTTP features are missing, and there's no way to distinguish "password wrong" from "device incompatible". The integration should detect incompatible portals, warn users, and gracefully degrade to whatever features the specific device supports.

## Beneficiaries

**Primary:**
- Users with TP-Link powerline models that have a different or partial HTTP portal implementation

**Secondary:**
- Users who accidentally enter the wrong IP (e.g., a router instead of a powerline adapter) and need clear feedback

---

## Outcomes

**Must Haves**
- Config flow detects incompatible HTTP portals and warns the user with an option to continue in ping-only mode or cancel
- Each feature category (device info, network monitoring, LED, QoS, reboot schedule, ethernet ports) is independently probed and only available features create entities
- The network coordinator handles malformed or missing data without crashing
- Features that fail on first poll but succeed later are picked up on integration reload (documented behaviour, not dynamic)

**Nice-to-haves**
- None

---

## Explicitly Out of Scope

- Hardening entity write paths (switch/select/time error handling) — separate spec
- Dynamic entity registration when features become available after initial setup
- Auto-detecting the device model to pre-select a known capability profile
- Supporting non-TP-Link devices

---

## Functional Requirements

**FR-001: Config flow detects incompatible HTTP portal**
- Description: After a successful ping and password entry, the config flow attempts to log in to the HTTP portal. If the login response is not in the expected key=value format (e.g., HTML, JSON, or no TOKEN in the response), the config flow shows a new "incompatible_device" error explaining the device's web portal is not compatible. The user is presented with two options: continue setup in ping-only mode (without storing the password hash) or cancel and go back.
- Acceptance criteria: When adding a device whose HTTP portal returns an unexpected format, the user sees a clear message like "This device's web portal is not compatible with this integration. You can continue with ping-only monitoring or go back to check the device." Two buttons: "Continue (ping only)" and "Back".
- Failure/edge cases: If the device is just temporarily unavailable (network error / timeout), the existing "cannot_connect"-style handling applies — not the incompatible device flow. The incompatible detection only triggers when the device responds but the response is not parseable as the expected format. `AuthenticationError` (wrong password) still shows "invalid_auth" as before.

**FR-002: Config flow incompatible device step**
- Description: A new config flow step `async_step_confirm_ping_only` that is shown when the portal is detected as incompatible. This step has a description explaining the situation and allows the user to either create the entry in ping-only mode or abort.
- Acceptance criteria: The step shows an explanation message. Submitting creates the entry without a password hash (ping-only). The abort reason is "incompatible_device".
- Failure/edge cases: If the user goes back and enters a different IP, the flow restarts from the user step.

**FR-003: Network coordinator resilient to malformed data**
- Description: The `get_network_data()` method in `client.py` handles malformed MAC/rate arrays without raising uncaught exceptions. Specifically: mismatched array lengths (MACS has more entries than RX_BPS), non-numeric rate values, and empty/missing fields all produce safe defaults rather than crashes. The coordinator's `_async_update_data` catches all exceptions from `get_network_data` (not just `DeviceUnavailable` and `UnexpectedResponse`).
- Acceptance criteria: A device that returns `DIDMNG.GENERAL.MACS=aa:bb:cc:dd:ee:ff` with `DIDMNG.GENERAL.RX_BPS=notanumber` does not crash the coordinator. Instead, the adapter gets rate 0 and the coordinator continues.
- Failure/edge cases: Completely empty responses (no MACS key at all) should result in an empty adapters list, not a crash.

**FR-004: Feature probing at setup**
- Description: During `async_setup_entry`, after HTTP login succeeds, the integration probes each feature category independently. Each probe is wrapped in its own try/except. If device info fails, it falls back to placeholders. If network data fails, no remote adapter entities are created. If individual coordinator sections (LED, QoS, ethernet, reboot) fail, only those entities are omitted. The integration loads successfully as long as the ping coordinator works.
- Acceptance criteria: A device that supports login and device info but not QoS commands creates device info sensors but no QoS select. A device that supports nothing but ping creates only the ping binary sensor. No combination of feature failures prevents the integration from loading.
- Failure/edge cases: If the network coordinator's first refresh fails entirely (all features unsupported), the coordinator is still created but with no data — entity platform setup functions handle None data by creating no entities.

**FR-005: Client login response validation**
- Description: The `login()` method in `client.py` validates that the response is in the expected format before parsing. If the response contains HTML (indicating a different portal type) or doesn't match the `ERROR=XXX` pattern, it raises a new `IncompatibleDevice` exception (distinct from `AuthenticationError` and `DeviceUnavailable`). The config flow uses this to trigger the incompatible device step.
- Acceptance criteria: A device that returns JSON or HTML to the login POST triggers `IncompatibleDevice`. A device that returns `ERROR=006` (wrong password) still triggers `AuthenticationError`. A device that returns `ERROR=000\nTOKEN=xxx` still succeeds normally.
- Failure/edge cases: A device that returns an empty response or a timeout still triggers `DeviceUnavailable`, not `IncompatibleDevice`.

**FR-006: Coordinator catches all exceptions from network data fetch**
- Description: The `_async_update_data` method wraps the `get_network_data()` call to catch any exception type (not just `DeviceUnavailable` and `UnexpectedResponse`), including `ValueError`, `KeyError`, `IndexError` from malformed data parsing. These are raised as `UpdateFailed` so the coordinator handles backoff properly.
- Acceptance criteria: A `ValueError` from `int()` parsing inside `get_network_data()` results in `UpdateFailed`, not an unhandled exception in the HA event loop.
- Failure/edge cases: N/A

---

## QA Plan

**QA-01: Compatible device works as before**
- Goal: Verify no regression for the PG2400P
- Steps:
  1. Add integration with IP `192.168.1.34`, password `<password>`
- Expected: All entities created as before — device info, network monitoring, controls, ethernet ports.

**QA-02: Incompatible device shows warning in config flow**
- Goal: Verify incompatible portal detection
- Steps:
  1. Add integration with the IP of a non-powerline device (e.g., a router) that has a different web portal
  2. Enter a password
- Expected: After ping succeeds and login fails with an unexpected response, the user sees a message explaining the portal is incompatible. They can choose to continue with ping-only or go back.

**QA-03: Ping-only fallback from incompatible device flow**
- Goal: Verify the ping-only continuation path
- Steps:
  1. On the incompatible device warning step, click "Continue (ping only)"
- Expected: Config entry created without password hash. Only ping binary sensor exists. No HTTP-derived entities.

**QA-04: Malformed network data doesn't crash**
- Goal: Verify resilience to bad data
- Steps:
  1. (Unit test) Mock `get_network_data` to return malformed arrays
- Expected: Coordinator returns safe defaults, no unhandled exceptions.

---

## Open Questions

None.

---

## Appendix

### Glossary
- **Incompatible portal:** A device HTTP interface that doesn't follow the TP-Link MERProxyNew API pattern (key=value responses, `ERROR=000` success format, `TOKEN=` login)
- **Feature probing:** Testing each feature category independently to determine device capabilities
- **Ping-only mode:** Integration operates with only ICMP ping availability monitoring, no HTTP features

### References
- Current error handling audit in conversation context
- [HA config flow multi-step documentation](https://developers.home-assistant.io/docs/config_entries_config_flow_handler)

### Change History
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-11 | Pete | Initial specification |
