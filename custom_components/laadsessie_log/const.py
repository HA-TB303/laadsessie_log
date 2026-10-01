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
CONF_VOERTUIG = "voertuig"
CONF_NAAM = "naam"
CONF_ADRES = "adres"
CONF_KENTEKEN = "kenteken"
CONF_INFO = (CONF_NAAM, CONF_ADRES, CONF_KENTEKEN)

ONBEKEND_VOERTUIG = "Onbekend"

DASHBOARD_URL = "laadsessie-log"
# Rapporten alleen via een geauthenticeerd endpoint (zie rapport_view.py), niet via /local.
REPORT_URL = f"/api/{DOMAIN}/rapport"
# De PDF-viewer zelf bevat geen gegevens en mag dus in de (openbare) www-map staan.
VIEWER_URL = "/local/laadrapporten/viewer/viewer.html"

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

# Omschrijving van het tariefsoort, gebruikt in rapporten en op het dashboard.
TARIEF_INTERVAL_LABEL = {
    "kwartier": "dynamisch kwartiertarief",
    "dag": "dagtarief",
    "maand": "vast maandtarief",
}
TARIEF_INTERVAL_TEGEL = {
    "kwartier": "Huidig kwartiertarief",
    "dag": "Huidig dagtarief",
    "maand": "Huidig tarief",
}
