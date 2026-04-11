# TP-Link Powerline for Home Assistant

A Home Assistant custom integration for monitoring and controlling TP-Link powerline ethernet adapters via their local HTTP portal. Initially developed for the PG2400P but designed to work with other TP-Link powerline models that share the same web interface.

## Features

### Ping Availability
- Binary sensor for device connectivity (ICMP ping every 15 seconds)
- Configurable failure threshold (unavailable after 8 consecutive failures)
- Works without a password (ping-only mode)

### Device Information (requires password)
- Fetches real model name, firmware version, and hardware version from the device
- Populates the HA device registry with accurate device info
- Diagnostic sensors for model, firmware, and hardware version

### Powerline Network Monitoring (requires password)
- Discovers remote powerline adapters on the network
- Each remote adapter registered as a separate HA device linked to the root
- TX and RX link rate sensors per adapter (Mbps, polled every 60 seconds)
- Binary connectivity sensor per remote adapter
- Connected adapters count sensor on the root device
- Powerline network name diagnostic sensor

### Device Controls (requires password)
- **LED Switch** - Toggle device LEDs on/off
- **LED Night Mode** - Enable/disable scheduled LED off period with configurable start and end times
- **Reboot Button** - Trigger an immediate device reboot
- **Reboot Schedule** - Enable/disable scheduled reboots with configurable time, cycle (daily/weekly/monthly), weekday, and day of month
- **QoS Mode** - Select between Fair, Gaming, Streaming, and Voice priority modes
- **Ethernet Port Status** - Per-port binary sensors showing connected/disconnected with link speed and duplex attributes

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations**
3. Click the three dots in the top right and select **Custom repositories**
4. Add this repository URL and select **Integration** as the category
5. Click **Add**
6. Search for "TP-Link Powerline" and install it
7. Restart Home Assistant

### Manual

1. Copy the `custom_components/tplink_powerline` directory to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for "TP-Link Powerline"
3. Enter the IP address of your powerline adapter
4. Optionally enter the device's web portal password to enable HTTP features (device info, network monitoring, controls)
5. Enter a friendly name (defaults to "Powerline Network")

### Password

The password is the same one used to log in to the device's web portal (typically accessed at `http://<device-ip>/`). Without a password, the integration operates in ping-only mode - you still get availability monitoring but no device info, network monitoring, or controls.

## Known Limitations

- **Single session:** The device only allows one active HTTP session at a time. While the integration is connected, logging into the device's web UI will invalidate the integration's session (it re-authenticates automatically on the next poll). Conversely, the integration's login will end any active web UI session.
- **Remote adapter discovery:** Remote adapters are discovered at integration setup and on each poll. New adapters appearing between restarts are picked up on the next 60-second poll cycle.
- **Content-Type constraint:** The device's embedded web server rejects requests with `charset=UTF-8` in the Content-Type header. The integration handles this automatically.

## Supported Devices

Tested with:
- **TP-Link PG2400P**

Should work with other TP-Link powerline adapters that use the same web portal interface (jQuery-based SPA with MERProxyNew API pattern).

## Development

### Running Tests

```bash
python -m venv .venv
.venv/bin/pip install pytest pytest-homeassistant-custom-component
.venv/bin/python -m pytest tests/ -v
```

## License

This project is licensed under the MIT License.
