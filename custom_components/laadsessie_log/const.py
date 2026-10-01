"""Constanten voor Laadsessie log."""

DOMAIN = "laadsessie_log"
SIGNAL_UPDATE = f"{DOMAIN}_update"

CONF_POWER = "vermogen"
CONF_STATUS = "status"
CONF_SESSION_ENERGY = "sessie_energie"
CONF_TARIFF = "tarief"
CONF_TARIFF_NAME = "tarief_naam"
CONF_DISCONNECTED = "status_niet_aangesloten"
CONF_DASHBOARD = "dashboard"
CONF_INFO = ("naam", "adres", "kenteken")

DASHBOARD_URL = "laadsessie-log"
REPORT_URL = "/local/laadrapporten"

DEFAULT_TARIFF_NAME = "Zonneplan"
DEFAULT_DISCONNECTED = "disconnected, off, not_connected, unplugged"
