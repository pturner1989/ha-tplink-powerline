# Project Guidelines — ha-tplink-powerline

## Overview

HACS-compatible Home Assistant custom integration for monitoring TP-Link powerline ethernet adapters (initially PG2400P, extensible to other models). Combines ICMP ping for basic availability with reverse-engineered local HTTP interface scraping for device status and link quality metrics.

## Language & Runtime

- Python 3.13+
- Target Home Assistant 2024.12+ (current stable)
- No external native dependencies — pure Python only so HACS installs work everywhere

## Project Structure

```
custom_components/tplink_powerline/
  __init__.py           # Integration setup, coordinator
  manifest.json         # HACS/HA metadata
  config_flow.py        # UI-based configuration
  coordinator.py        # DataUpdateCoordinator for polling
  sensor.py             # Sensor entities (link rate, status, etc.)
  binary_sensor.py      # Online/offline availability
  device.py             # Device abstraction per powerline adapter
  client.py             # HTTP client for local device API
  const.py              # Domain, defaults, keys
  strings.json          # UI strings
  translations/
    en.json
```

Top-level repo also contains:
```
hacs.json              # HACS repository metadata
README.md              # User-facing docs
LICENSE
```

## Home Assistant Conventions

### Integration Domain

`tplink_powerline`

### Config Flow

- UI-based config flow only (no YAML configuration)
- User provides device IP/hostname
- Validation step pings device and attempts HTTP connection
- Support for multiple devices (each is a config entry)

### DataUpdateCoordinator

- Single coordinator per config entry
- Default polling interval: 30 seconds
- Combines ping check + HTTP status fetch in one update cycle
- Raise `UpdateFailed` on transient errors
- Raise `ConfigEntryNotReady` during setup if device unreachable

### Entities

- Each physical powerline adapter = one HA device
- Binary sensor: device availability (ping-based)
- Sensors: TX/RX link rate, connected port count, uptime, firmware version (as applicable — depends on what the HTTP interface exposes)
- Entity IDs follow `<platform>.tplink_powerline_<device>_<metric>` pattern

## Error Handling

- Use `HomeAssistantError` subclasses for user-facing errors
- `ConfigEntryNotReady` when device is unreachable at startup
- `UpdateFailed` for transient polling failures (coordinator handles backoff)
- HTTP client raises specific exceptions: `DeviceUnavailable`, `AuthenticationError`, `UnexpectedResponse`
- Never swallow exceptions silently — always log before re-raising or handling

## Logging

- `_LOGGER = logging.getLogger(__name__)` in every module
- `DEBUG`: raw HTTP responses, ping RTT, parsing details
- `INFO`: device discovered, config entry loaded/unloaded
- `WARNING`: transient failures, unexpected response formats (device still functional)
- `ERROR`: persistent failures, device unreachable after retries

## HTTP Client (`client.py`)

- Use `aiohttp.ClientSession` (HA provides one via `async_get_clientsession`)
- All I/O is async
- Timeout: 10 seconds per request
- Parse HTML/JSON responses defensively — device firmware may vary
- Document every discovered endpoint and its response format in docstrings
- Keep authentication/session handling isolated in the client class

## Naming Conventions

- Files: `snake_case.py`
- Classes: `PascalCase` (e.g., `TplinkPowerlineCoordinator`, `PowerlineDevice`)
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE` in `const.py`
- Prefix integration-specific constants with `DOMAIN` or descriptive scope

## Testing

- Framework: `pytest` with `pytest-homeassistant-custom-component`
- Test files mirror source: `tests/test_<module>.py`
- Mock HTTP responses with `aioresponses` or fixture files
- Mock ping with patched subprocess/icmp calls
- Test config flow happy path + error paths
- Test coordinator update cycle with mocked client

## HACS Compliance

- `hacs.json` with correct metadata
- `manifest.json` includes `version`, `documentation`, `issue_tracker`, `iot_class: "local_polling"`
- Repository follows default HACS structure (integration in `custom_components/`)
