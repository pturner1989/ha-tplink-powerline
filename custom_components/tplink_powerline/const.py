"""Constants for the TP-Link Powerline integration."""

DOMAIN = "tplink_powerline"
DEFAULT_NAME = "Powerline Network"
DEFAULT_SCAN_INTERVAL = 15  # seconds
PING_TIMEOUT = 5  # seconds per ping attempt
FAILURE_THRESHOLD = 8  # consecutive failures before unavailable

CONF_PASSWORD_HASH = "password_hash"
HTTP_TIMEOUT = 10  # seconds
CONTENT_TYPE = "application/x-www-form-urlencoded"
NETWORK_SCAN_INTERVAL = 60  # seconds

QOS_MODES = {"1": "Fair", "2": "Gaming", "3": "Streaming", "4": "Voice"}
QOS_MODES_REVERSE = {v: k for k, v in QOS_MODES.items()}

REBOOT_CYCLES = {"1": "Daily", "2": "Weekly", "3": "Monthly"}
REBOOT_CYCLES_REVERSE = {v: k for k, v in REBOOT_CYCLES.items()}

ETHERNET_PORT_STATUS = {
    0: {"connected": False, "speed": 0, "duplex": ""},
    1: {"connected": True, "speed": 10, "duplex": "half"},
    2: {"connected": True, "speed": 10, "duplex": "full"},
    3: {"connected": True, "speed": 100, "duplex": "half"},
    4: {"connected": True, "speed": 100, "duplex": "full"},
    5: {"connected": True, "speed": 1000, "duplex": "half"},
    6: {"connected": True, "speed": 1000, "duplex": "full"},
}
