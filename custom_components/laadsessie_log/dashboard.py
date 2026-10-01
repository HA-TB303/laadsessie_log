"""Ingebouwd Lovelace-dashboard 'Laadsessies' in de zijbalk."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import frontend
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.json import json_bytes, json_fragment

from .const import (
    CONF_STATUS,
    CONF_TARIEF_INTERVAL,
    CONF_TARIFF,
    CONF_TARIFF_NAME,
    DASHBOARD_URL,
    DEFAULT_TARIEF_INTERVAL,
    DEFAULT_TARIFF_NAME,
    DOMAIN,
    REPORT_URL,
    TARIEF_INTERVAL_TEGEL,
)

_LOGGER = logging.getLogger(__name__)

TITLE = "Laadsessies"
ICON = "mdi:ev-station"

# unique_id-achtervoegsel -> standaard entity_id (als de entiteit nog niet in het register staat)
_OWN_ENTITIES = {
    "maand_kwh": "sensor.laadsessies_energie_deze_maand",
    "maand_kosten": "sensor.laadsessies_kosten_deze_maand",
    "actief": "sensor.laadsessie_actief",
    "rapporten": "sensor.laadrapporten",
    "tarief_status": "sensor.zonneplan_tarief_status",
    "naam": "text.laadrapport_naam",
    "kenteken": "text.laadrapport_kenteken",
    "adres": "text.laadrapport_adres_laadpaal",
}


def _own_entities(hass: HomeAssistant) -> dict[str, str]:
    """Actuele entity_id's van de eigen entiteiten opzoeken (de gebruiker kan ze hernoemd hebben)."""
    registry = er.async_get(hass)
    out = {}
    for key, default in _OWN_ENTITIES.items():
        domain = default.split(".", 1)[0]
        out[key] = registry.async_get_entity_id(domain, DOMAIN, f"{DOMAIN}_{key}") or default
    return out


def build_config(hass: HomeAssistant, conf: dict[str, Any]) -> dict[str, Any]:
    """Dashboardconfiguratie opbouwen op basis van de ingestelde sensoren."""
    e = _own_entities(hass)
    tariff_name = conf.get(CONF_TARIFF_NAME) or DEFAULT_TARIFF_NAME
    reports = e["rapporten"]

    tiles = [
        {"type": "tile", "entity": e["maand_kwh"], "name": "Geladen"},
        {"type": "tile", "entity": e["maand_kosten"], "name": "Kosten"},
        {"type": "tile", "entity": e["actief"], "name": "Actieve sessie"},
    ]
    if conf.get(CONF_STATUS):
        tiles.append({"type": "tile", "entity": conf[CONF_STATUS], "name": "Laadpaal"})
    tiles.append({"type": "tile", "entity": e["tarief_status"], "name": f"{tariff_name} tarief"})
    if conf.get(CONF_TARIFF):
        interval = conf.get(CONF_TARIEF_INTERVAL) or DEFAULT_TARIEF_INTERVAL
        tegel_naam = TARIEF_INTERVAL_TEGEL.get(interval, TARIEF_INTERVAL_TEGEL[DEFAULT_TARIEF_INTERVAL])
        tiles.append({"type": "tile", "entity": conf[CONF_TARIFF], "name": tegel_naam})

    table = (
        f"{{% set r = state_attr('{reports}','rapporten') or [] %}}\n"
        "{% if r %}\n"
        "| Maand | Sessies | kWh | Kosten | Bekijk | PDF | CSV |\n"
        "|:--|--:|--:|--:|:-:|:-:|:-:|\n"
        "{% for x in r %}| {{ x.maand }}{{ ' *(voorlopig)*' if x.voorlopig }} | {{ x.sessies }} "
        "| {{ '%.2f'|format(x.kwh) | replace('.',',') }} "
        "| €\u00a0{{ '%.2f'|format(x.kosten) | replace('.',',') }} "
        f"| <a href=\"{REPORT_URL}/viewer/viewer.html?file={{{{ x.pdf.split('/') | last }}}}\" "
        "target=\"_blank\" rel=\"noopener\" title=\"Bekijken\"><ha-icon icon=\"mdi:eye\"></ha-icon></a> "
        "| <a href=\"{{ x.pdf }}\" target=\"_blank\" rel=\"noopener\" title=\"PDF openen\">"
        "<ha-icon icon=\"mdi:file-pdf-box\"></ha-icon></a> "
        "| <a href=\"{{ x.csv }}\" target=\"_blank\" rel=\"noopener\" download title=\"CSV downloaden\">"
        "<ha-icon icon=\"mdi:file-delimited\"></ha-icon></a> |\n"
        "{% endfor %}\n"
        "{% else %}Nog geen rapporten.{% endif %}"
    )

    return {
        "title": TITLE,
        "views": [
            {
                "title": TITLE,
                "path": "laadsessies",
                "icon": ICON,
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    {
                        "type": "grid",
                        "cards": [
                            {"type": "heading", "heading": "Laden deze maand", "icon": ICON},
                            *tiles,
                            {
                                "type": "entities",
                                "title": "Gegevens op het rapport",
                                "entities": [
                                    {"entity": e["naam"], "name": "Naam"},
                                    {"entity": e["kenteken"], "name": "Kenteken"},
                                    {"entity": e["adres"], "name": "Adres laadpaal"},
                                ],
                                "footer": {
                                    "type": "buttons",
                                    "entities": [
                                        {
                                            "entity": reports,
                                            "name": "Alle rapporten opnieuw maken",
                                            "icon": "mdi:file-refresh",
                                            "show_icon": True,
                                            "show_name": True,
                                            "tap_action": {
                                                "action": "perform-action",
                                                "perform_action": f"{DOMAIN}.genereer_rapport",
                                                "data": {"alle": True},
                                            },
                                        }
                                    ],
                                },
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": [
                            {"type": "heading", "heading": "Rapporten", "icon": "mdi:file-document-multiple"},
                            {"type": "markdown", "grid_options": {"columns": "full"}, "content": table},
                            {"type": "heading", "heading": "Rapport vorige maand", "icon": "mdi:file-pdf-box"},
                            {
                                "type": "iframe",
                                "url": f"{REPORT_URL}/viewer/viewer.html?file=laadrapport_vorige_maand.pdf",
                                "grid_options": {"columns": "full", "rows": 24},
                            },
                        ],
                    },
                ],
            }
        ],
    }


class LaadsessieDashboard(LovelaceConfig):
    """Alleen-lezen dashboard dat telkens uit de actuele instellingen wordt opgebouwd."""

    def __init__(self, hass: HomeAssistant, conf: dict[str, Any]) -> None:
        super().__init__(
            hass,
            DASHBOARD_URL,
            {"mode": "yaml", "title": TITLE, "icon": ICON, "show_in_sidebar": True, "require_admin": False},
        )
        self._conf = conf

    @property
    def mode(self) -> str:
        return "yaml"

    async def async_get_info(self) -> dict[str, Any]:
        return {"mode": self.mode, "views": 1}

    async def async_load(self, force: bool) -> dict[str, Any]:
        return build_config(self.hass, self._conf)

    async def async_json(self, force: bool) -> json_fragment:
        return json_fragment(json_bytes(build_config(self.hass, self._conf)))


def async_register(hass: HomeAssistant, conf: dict[str, Any]) -> bool:
    """Dashboard registreren; False als de URL al door een ander dashboard wordt gebruikt."""
    dashboards = hass.data[LOVELACE_DATA].dashboards
    if DASHBOARD_URL in dashboards or frontend.async_panel_exists(hass, DASHBOARD_URL):
        _LOGGER.warning("Dashboard /%s bestaat al; ingebouwd dashboard niet toegevoegd", DASHBOARD_URL)
        return False
    dashboards[DASHBOARD_URL] = LaadsessieDashboard(hass, conf)
    frontend.async_register_built_in_panel(
        hass,
        "lovelace",
        sidebar_title=TITLE,
        sidebar_icon=ICON,
        frontend_url_path=DASHBOARD_URL,
        config={"mode": "yaml"},
        require_admin=False,
    )
    return True


def async_unregister(hass: HomeAssistant) -> None:
    frontend.async_remove_panel(hass, DASHBOARD_URL, warn_if_unknown=False)
    hass.data[LOVELACE_DATA].dashboards.pop(DASHBOARD_URL, None)
