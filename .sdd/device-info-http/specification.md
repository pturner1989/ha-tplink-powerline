# Specification: Device Info via HTTP Portal

**Version:** 1.0
**Date:** 2026-04-10
**Status:** Implemented

---

## Problem Statement

The integration currently registers powerline devices with a placeholder model name ("Powerline Adapter") and no firmware or hardware version information. The device's local HTTP portal exposes the actual model, firmware version, and hardware version, but the integration doesn't use it. Users have no way to see what firmware their powerline adapter is running or confirm the exact hardware revision.

## Beneficiaries

**Primary:**
- Home Assistant users who want to see accurate device information for their powerline adapters (model, firmware, hardware version)

**Secondary:**
- Users managing multiple TP-Link powerline models who need to distinguish between them
- Users tracking firmware versions to know when updates are available

---

## Outcomes

**Must Haves**
- The integration authenticates with the device's local HTTP portal using a password provided during setup
- The device registry entry shows the real model name, firmware version, and hardware version instead of placeholders
- Model, firmware version, and hardware version are exposed as diagnostic sensor entities

**Nice-to-haves**
- None

---

## Explicitly Out of Scope

- Fetching link quality, TX/RX rates, or satellite device information from the HTTP portal — addressed in a future specification
- Periodic re-fetching of device info (model/firmware/hardware rarely change)
- Firmware update functionality
- Changing device settings via the HTTP portal
- Logging out after data fetch (integration maintains a persistent session)

---

## Functional Requirements

**FR-001: Config flow collects device password**
- Description: The config flow adds a password field so the integration can authenticate with the device's HTTP portal. The password is stored as its MD5 hash (the format the device API requires). The password field is required.
- Acceptance criteria: The config flow shows a password field alongside the existing IP and name fields. The password is MD5-hashed and stored in the config entry data. Existing config entries without a password continue to work (ping-only mode).
- Failure/edge cases: Empty password rejected with a form error. Incorrect password (authentication fails during setup) shows an "invalid_auth" error and lets the user retry.

**FR-002: HTTP client authenticates with the device portal**
- Description: The integration logs in to the device's local HTTP portal at setup time using the MD5-hashed password. The login is a POST to `/` with `TPLINK.GENERAL.LOGIN_PASSWORD=<md5_hash>`. The device returns a session token used for subsequent requests. The integration maintains this session for the lifetime of the config entry.
- Acceptance criteria: After setup, the integration holds an active session token. The token is used for all subsequent HTTP requests. If the session expires or becomes invalid, the integration re-authenticates automatically.
- Failure/edge cases: Login failure returns an error code (e.g., ERROR=006 for wrong password, ERROR=008 for session full). The device only allows one active session at a time — a new login invalidates any previous session. If another client (e.g., the web UI) logs in, the integration's session is invalidated and must re-authenticate on the next use. The `Content-Type` header must be exactly `application/x-www-form-urlencoded` without `charset=UTF-8` — the device rejects requests with charset in the Content-Type.

**FR-003: Fetch device model, firmware version, and hardware version**
- Description: After authenticating, the integration fetches three data keys from the HTTP portal via a GET request: `SYSTEM.PRODUCTION.HW_PRODUCT` (model), `SYSTEM.GENERAL.FW_VERSION` (firmware version), and `SYSTEM.PRODUCTION.HW_REVISION` (hardware version). This fetch happens once during integration setup, not on every poll cycle.
- Acceptance criteria: The integration retrieves the correct values for all three keys. For the PG2400P test device: model="PG2400P", firmware="1.0.3 Build 20221213 Rel.62540", hardware="1.0".
- Failure/edge cases: If the HTTP fetch fails (device doesn't support the portal, network error, auth failure), the integration falls back to the placeholder values and continues operating in ping-only mode. The GET request must include `Content-Type: application/x-www-form-urlencoded` and `Referer: http://<host>/` headers.

**FR-004: Device registry shows real device information**
- Description: The device registry entry uses the fetched model name, firmware version, and hardware version instead of the placeholder "Powerline Adapter". The manufacturer remains "TP-Link".
- Acceptance criteria: In Settings > Devices & Services, the device shows the real model (e.g., "PG2400P"), firmware version, and hardware version.
- Failure/edge cases: If HTTP fetch failed, device registry shows "Powerline Adapter" as before (graceful fallback).

**FR-005: Diagnostic sensor entities for model, firmware, and hardware version**
- Description: Three diagnostic sensor entities are created for each device: model, firmware version, and hardware version. These use the `diagnostic` entity category so they don't pollute the default entity list.
- Acceptance criteria: After setup with a valid password, three sensor entities appear under the device with correct values. The sensors are categorised as diagnostic.
- Failure/edge cases: If HTTP data is unavailable, the sensors show "Unknown" or are unavailable. The sensors do not poll — their values are set once at setup and remain static until the next restart.

---

## QA Plan

**QA-01: Setup with password and device info appears**
- Goal: Validate the full setup flow with HTTP authentication
- Steps:
  1. Remove any existing TP-Link Powerline config entry
  2. Add the integration via Settings > Devices & Services
  3. Enter IP `192.168.1.34`, password ``<password>``, name "Powerline Network"
  4. Submit the form
- Expected: Config entry created. Device shows model "PG2400P", firmware "1.0.3 Build 20221213 Rel.62540", hardware "1.0". Three diagnostic sensors appear with these values.

**QA-02: Setup with wrong password**
- Goal: Validate authentication error handling
- Steps:
  1. Add the integration
  2. Enter IP `192.168.1.34`, password `wrongpassword`
  3. Submit the form
- Expected: An "invalid_auth" error is shown. The user can correct the password and retry.

**QA-03: Setup without password (ping-only fallback)**
- Goal: Validate backwards compatibility
- Steps:
  1. Add the integration
  2. Enter IP `192.168.1.34`, leave password empty
  3. Submit the form
- Expected: Config entry created. Device shows placeholder "Powerline Adapter" model. No diagnostic sensors for model/firmware/hardware. Ping binary sensor works normally.

**QA-04: Device info survives restart**
- Goal: Validate that device info is re-fetched on restart
- Steps:
  1. With a working config entry that has device info
  2. Restart Home Assistant
  3. Check the device info and diagnostic sensors
- Expected: After restart, device info and diagnostic sensors show the correct values (re-fetched from device).

---

## Open Questions

None.

---

## Appendix

### Glossary
- **Session token:** A 32-character string returned by the device after successful login, used as the `_t` query parameter for authenticated requests
- **MD5 hash:** The device expects the password as an MD5 hex digest, not plaintext
- **Diagnostic entity:** An HA entity category for information that is useful for debugging but not for automations

### References
- Reverse-engineered HTTP API documented in project memory (`project_device_http_api.md`)
- [HA diagnostic entity category](https://developers.home-assistant.io/docs/core/entity#entity-category)

### Change History
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-10 | Pete | Initial specification |
