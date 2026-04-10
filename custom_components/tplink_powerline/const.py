"""Constants for the TP-Link Powerline integration."""

DOMAIN = "tplink_powerline"
DEFAULT_NAME = "Powerline Network"
DEFAULT_SCAN_INTERVAL = 15  # seconds
PING_TIMEOUT = 5  # seconds per ping attempt
FAILURE_THRESHOLD = 8  # consecutive failures before unavailable

CONF_PASSWORD_HASH = "password_hash"
HTTP_TIMEOUT = 10  # seconds
CONTENT_TYPE = "application/x-www-form-urlencoded"
