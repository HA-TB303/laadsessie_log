"""Ingebouwd Lovelace-dashboard 'Laadsessies' in de zijbalk."""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any

from homeassistant.components import frontend
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.json import json_bytes, json_fragment

from .const import (
    CONF_KENTEKEN,
    CONF_STATUS,
    CONF_TARIEF_INTERVAL,
    CONF_TARIFF,
    CONF_TARIFF_NAME,
    CONF_VOERTUIG,
    DASHBOARD_URL,
    DEFAULT_TARIEF_INTERVAL,
    DEFAULT_TARIFF_NAME,
    DOMAIN,
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
}


def _own_entities(hass: HomeAssistant) -> dict[str, str]:
    """Actuele entity_id's van de eigen entiteiten opzoeken (de gebruiker kan ze hernoemd hebben)."""
    registry = er.async_get(hass)
    out = {}
    for key, default in _OWN_ENTITIES.items():
        domain = default.split(".", 1)[0]
        out[key] = registry.async_get_entity_id(domain, DOMAIN, f"{DOMAIN}_{key}") or default
    return out


def _has_apexcharts(hass: HomeAssistant) -> bool:
    """Is de (HACS-)kaart apexcharts-card beschikbaar? Zo niet, dan valt de grafiek terug op tekst."""
    try:
        items = hass.data[LOVELACE_DATA].resources.async_items() or []
    except Exception:  # noqa: BLE001 - resources nog niet geladen of in YAML-modus
        items = []
    if any("apexcharts-card" in (i.get("url") or "") for i in items):
        return True
    return os.path.isdir(hass.config.path("www", "community", "apexcharts-card"))


def _apex_grafiek(entity: str) -> dict[str, Any]:
    """Staafgrafiek: dagen van de maand op de x-as, geladen kWh op de y-as."""
    return {
        "type": "custom:apexcharts-card",
        "graph_span": "1month",
        "span": {"start": "month"},
        "header": {"show": False},
        "now": {"show": False},
        "yaxis": [{"min": 0, "decimals": 1, "apex_config": {"title": {"text": "kWh"}}}],
        "apex_config": {
            "chart": {"height": 300},
            "xaxis": {"labels": {"datetimeFormatter": {"day": "d"}}},
            "tooltip": {"x": {"format": "d MMMM"}},
            "plotOptions": {"bar": {"columnWidth": "70%"}},
            "legend": {"show": False},
        },
        "series": [
            {
                "entity": entity,
                "name": "Geladen",
                "type": "column",
                "unit": "kWh",
                "float_precision": 2,
                "show": {"in_header": False, "legend_value": False},
                # Staaf midden op de dag (12:00) zodat hij netjes boven het daglabel staat.
                "data_generator": (
                    "const n = new Date();\n"
                    "return (entity.attributes.per_dag || []).map("
                    "d => [new Date(n.getFullYear(), n.getMonth(), d.dag, 12).getTime(), d.kwh]);"
                ),
            }
        ],
    }


def build_config(hass: HomeAssistant, conf: dict[str, Any]) -> dict[str, Any]:
    """Dashboardconfiguratie opbouwen op basis van de ingestelde sensoren."""
    e = _own_entities(hass)
    tariff_name = conf.get(CONF_TARIFF_NAME) or DEFAULT_TARIFF_NAME
    reports = e["rapporten"]
    per_voertuig = bool(conf.get(CONF_VOERTUIG))

    tiles = [
        {"type": "tile", "entity": e["maand_kwh"], "name": "Geladen"},
        {"type": "tile", "entity": e["maand_kosten"], "name": "Kosten"},
    ]
    # Laadpaal en aangesloten voertuig als paar naast elkaar (elk een halve rij breed).
    if conf.get(CONF_STATUS):
        tiles.append({"type": "tile", "entity": conf[CONF_STATUS], "name": "Laadpaal"})
    if per_voertuig or not conf.get(CONF_KENTEKEN):
        # Zodra er per voertuig wordt gerapporteerd is een vast kenteken toch niet meer zinvol
        # (zie ook _info() in __init__.py); toon dan altijd welk voertuig nu is aangesloten.
        tiles.append(
            {
                "type": "tile",
                "entity": e["actief"],
                "name": "Voertuig",
                "icon": "mdi:car",
                "state_content": "voertuig",
            }
        )
    tiles.append({"type": "tile", "entity": e["actief"], "name": "Actieve sessie"})
    tiles.append({"type": "tile", "entity": e["tarief_status"], "name": f"{tariff_name} tarief"})
    if conf.get(CONF_TARIFF):
        interval = conf.get(CONF_TARIEF_INTERVAL) or DEFAULT_TARIEF_INTERVAL
        tegel_naam = TARIEF_INTERVAL_TEGEL.get(interval, TARIEF_INTERVAL_TEGEL[DEFAULT_TARIEF_INTERVAL])
        tiles.append({"type": "tile", "entity": conf[CONF_TARIFF], "name": tegel_naam})

    # Als HTML-tabel i.p.v. markdown: alleen zo kan hij de volle breedte van de kaart vullen
    # (de markdown-kaart laat het width-attribuut door, maar geen CSS).
    kolommen = [("Maand", "left")]
    if per_voertuig:
        kolommen.append(("Voertuig", "left"))
    kolommen += [("Sessies", "right"), ("kWh", "right"), ("Kosten", "right")]
    kolommen += [("Bekijk", "center"), ("PDF", "center"), ("CSV", "center")]
    kop = "<tr>" + "".join(f'<th align="{al}">{naam}</th>' for naam, al in kolommen) + "</tr>\n"
    voertuig_cel = "<td>{{ x.voertuig or '' }}</td>" if per_voertuig else ""
    table = (
        f"{{% set r = state_attr('{reports}','rapporten') or [] %}}\n"
        "{% if r %}\n"
        f'<table width="100%">\n{kop}'
        "{% for x in r %}<tr>"
        "<td>{{ x.maand }}{{ ' <i>(voorlopig)</i>' if x.voorlopig }}</td>"
        f"{voertuig_cel}"
        '<td align="right">{{ x.sessies }}</td>'
        "<td align=\"right\">{{ '%.2f'|format(x.kwh) | replace('.',',') }}</td>"
        "<td align=\"right\">€\u00a0{{ '%.2f'|format(x.kosten) | replace('.',',') }}</td>"
        '<td align="center"><a href="{{ x.viewer }}" '
        'target="_blank" rel="noopener" title="Bekijken"><ha-icon icon="mdi:eye"></ha-icon></a></td>'
        '<td align="center"><a href="{{ x.pdf }}" target="_blank" rel="noopener" title="PDF openen">'
        '<ha-icon icon="mdi:file-pdf-box"></ha-icon></a></td>'
        '<td align="center"><a href="{{ x.csv }}" target="_blank" rel="noopener" download title="CSV downloaden">'
        '<ha-icon icon="mdi:file-delimited"></ha-icon></a></td>'
        "</tr>\n{% endfor %}</table>\n"
        "{% else %}Nog geen rapporten.{% endif %}"
    )

    apex = _has_apexcharts(hass)
    # Zonder apexcharts-card: blokjes-sparkline als gewone (grote) markdown-tekst. Een code-blok
    # kreeg in de praktijk een kleurthema waarin de tekens onzichtbaar bleken.
    sparkline = (
        ""
        if apex
        else "##### {% for d in dagen %}"
        "{{ '▁▂▃▄▅▆▇█'"
        "[ ((d.kwh / max_kwh * 7) | round(0) | int) if max_kwh else 0 ] }}"
        "{% endfor %}\n\n"
    )
    grafiek = (
        f"{{% set dagen = state_attr('{e['maand_kwh']}','per_dag') or [] %}}\n"
        "{% set totaal = dagen | sum(attribute='kwh') %}\n"
        "{% if totaal > 0 %}\n"
        "{% set max_kwh = dagen | map(attribute='kwh') | max %}\n"
        f"{sparkline}"
        "Dag 1 t/m {{ dagen | length }} — totaal {{ '%.1f'|format(totaal)|replace('.',',') }} kWh, "
        "piek {{ '%.1f'|format(max_kwh)|replace('.',',') }} kWh op dag "
        "{{ (dagen | selectattr('kwh','equalto',max_kwh) | first).dag }}"
        "{% else %}Nog geen laadsessies deze maand.{% endif %}"
    )

    grafiek_kaarten = [
        {"type": "heading", "heading": "Laadsessies deze maand", "icon": "mdi:chart-bar"},
        {"type": "markdown", "grid_options": {"columns": "full"}, "content": grafiek},
    ]
    if apex:
        grafiek_kaarten.insert(1, {**_apex_grafiek(e["maand_kwh"]), "grid_options": {"columns": "full"}})

    rapporten_kaarten = [
        {"type": "heading", "heading": "Rapporten", "icon": "mdi:file-document-multiple"},
        {"type": "markdown", "grid_options": {"columns": "full"}, "content": table},
    ]
    if not per_voertuig:
        # Bij losse rapporten per voertuig bestaat er geen eenduidig "vorige maand"-bestand meer;
        # de kolom Bekijk in de tabel hierboven ontsluit dan elk rapport afzonderlijk.
        rapporten_kaarten += [
            {"type": "heading", "heading": "Rapport vorige maand", "icon": "mdi:file-pdf-box"},
            {
                "type": "iframe",
                # Ondertekend bij het ophalen van het dashboard; ruim geldig omdat de frontend
                # de dashboardconfiguratie lang in het geheugen houdt.
                "url": hass.data[DOMAIN].links.viewer("laadrapport_vorige_maand.pdf", timedelta(hours=24)),
                "grid_options": {"columns": "full", "rows": 24},
            },
        ]

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
                                "type": "button",
                                "entity": reports,
                                "name": "Alle rapporten opnieuw maken",
                                "icon": "mdi:file-refresh",
                                "show_state": False,
                                "tap_action": {
                                    "action": "perform-action",
                                    "perform_action": f"{DOMAIN}.genereer_rapport",
                                    "data": {"alle": True},
                                },
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "column_span": 3,
                        "cards": grafiek_kaarten,
                    },
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": rapporten_kaarten,
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
