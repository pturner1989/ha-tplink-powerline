# CLAUDE.md — ha-tplink-powerline

## Development Methodology

This project follows **Spec Driven Development (SDD)**. All feature work must go through the SDD workflow:

1. **Specification** — Define requirements in `.sdd/<feature>/specification.md`
2. **Design** — Create design document in `.sdd/<feature>/design.md`
3. **Implementation** — Implement from the design, task by task
4. **Review** — Review against specification and design

### SDD Rules

- Never skip phases. No implementation without a design. No design without a specification.
- Read `.sdd/project-guidelines.md` before any SDD phase.
- Use `/sdd:sdd` skill for all SDD workflow operations.
- All SDD artifacts live in the `.sdd/` directory.
- Keep `.sdd/index.md` updated when creating new features.
- No SDD artifact references (FR-XXX, TS-XX) in code or test names.
- Tests are written WITH implementation tasks, never deferred to separate phases.

## Project Context

- **Type:** HACS custom integration for Home Assistant
- **Domain:** `tplink_powerline`
- **Target devices:** TP-Link PG2400P powerline adapters (extensible to others)
- **Data sources:** ICMP ping (availability) + local HTTP interface (device status, link quality)
- **IoT class:** `local_polling`

## Tech Stack

- Python 3.13+
- Home Assistant 2024.12+
- aiohttp for async HTTP (via HA's client session)
- pytest + pytest-homeassistant-custom-component for testing

## Key Conventions

- All I/O is async
- One DataUpdateCoordinator per config entry
- UI config flow only (no YAML)
- See `.sdd/project-guidelines.md` for full conventions
