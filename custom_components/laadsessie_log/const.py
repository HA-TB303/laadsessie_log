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
CONF_TARIEF_INTERVAL = "tarief_interval"
CONF_INFO = ("naam", "adres", "kenteken")

DASHBOARD_URL = "laadsessie-log"
REPORT_URL = "/local/laadrapporten"

DEFAULT_TARIFF_NAME = "Zonneplan"
DEFAULT_DISCONNECTED = "disconnected, off, not_connected, unplugged"
DEFAULT_TARIEF_INTERVAL = "kwartier"

# Hoe lang een tariefwaarde als "vers" geldt voordat terugvaltarieven worden gebruikt
# en een storingsmelding verschijnt. Moet ruim boven de werkelijke update-frequentie
# van de tariefsensor liggen (bijv. een vaste maandprijs wijzigt zelf niet elk kwartier).
TARIEF_INTERVAL_UREN = {
    "kwartier": 3,
    "dag": 30,
    "maand": 32 * 24,
}
