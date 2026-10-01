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
    CONF_POWER,
    CONF_STATUS,
    CONF_TARIEF_INTERVAL,
    CONF_TARIFF,
    CONF_TARIFF_NAME,
    CONF_VOERTUIG,
    DASHBOARD_URL,
    DEFAULT_TARIEF_INTERVAL,
    DEFAULT_TARIFF_NAME,
    DOMAIN,
    ONBEKEND_VOERTUIG,
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
    "actief_kosten": "sensor.laadsessie_kosten",
    "rapporten": "sensor.laadrapporten",
    "tarief_status": "sensor.zonneplan_tarief_status",
}


# Vaste kleurvolgorde per voertuig (HA-themakleuren); zelfde kleur in tegel en grafiek.
_VOERTUIG_KLEUREN = ["#2196f3", "#ff9800", "#9c27b0", "#009688", "#e91e63", "#3f51b5"]
_ONBEKEND_KLEUR = "#9e9e9e"


def _voertuig_kleuren(hass: HomeAssistant, conf: dict[str, Any]) -> dict[str, str]:
    """Bekende voertuigen (uit de sessies en de voertuig-sensor) met elk een vaste kleur."""
    namen: set[str] = set()
    log = hass.data.get(DOMAIN)
    if log is not None:
        namen |= {s.get("voertuig") for s in log.sessions if s.get("voertuig")}
    st = hass.states.get(conf.get(CONF_VOERTUIG) or "")
    if st and st.state not in ("unknown", "unavailable", ""):
        namen.add(st.state)
    namen.discard(ONBEKEND_VOERTUIG)
    kleuren = {n: _VOERTUIG_KLEUREN[i % len(_VOERTUIG_KLEUREN)] for i, n in enumerate(sorted(namen))}
    kleuren[ONBEKEND_VOERTUIG] = _ONBEKEND_KLEUR
    return kleuren


def _own_entities(hass: HomeAssistant) -> dict[str, str]:
    """Actuele entity_id's van de eigen entiteiten opzoeken (de gebruiker kan ze hernoemd hebben)."""
    registry = er.async_get(hass)
    out = {}
    for key, default in _OWN_ENTITIES.items():
        domain = default.split(".", 1)[0]
        out[key] = registry.async_get_entity_id(domain, DOMAIN, f"{DOMAIN}_{key}") or default
    return out


def _heeft_kaart(hass: HomeAssistant, bestand: str, hacs_map: str) -> bool:
    """Is een (HACS-)kaart beschikbaar? Zo niet, dan valt de grafiek terug op een alternatief."""
    try:
        items = hass.data[LOVELACE_DATA].resources.async_items() or []
    except Exception:  # noqa: BLE001 - resources nog niet geladen of in YAML-modus
        items = []
    if any(bestand in (i.get("url") or "") for i in items):
        return True
    return os.path.isdir(hass.config.path("www", "community", hacs_map))


def _plotly_grafiek(entity: str, kleuren: dict[str, str] | None = None) -> dict[str, Any]:
    """Staafgrafiek met alleen de dagen waarop geladen is (categorie-as, dus geen lege dagen).

    Met ``kleuren`` (voertuig -> kleur) worden de staven per voertuig gestapeld.
    """
    dagen = f"(hass.states['{entity}']?.attributes.per_dag || []).filter(d => d.kwh > 0)"
    x = (
        f"$ex {dagen}.map(d => new Date(new Date().getFullYear(), new Date().getMonth(), d.dag)"
        ".toLocaleDateString('nl-NL', {day: 'numeric', month: 'short'}))"
    )
    # Themakleuren van HA uitlezen; raw_plotly_config zet de standaardopmaak van de kaart uit.
    kleur = "$ex getComputedStyle(document.body).getPropertyValue('{var}').trim() || '{terugval}'"
    tekst = kleur.format(var="--secondary-text-color", terugval="#888")
    hover = "%{x}: %{y:.2f} kWh<extra>%{fullData.name}</extra>"
    if kleuren:
        traces = [
            {
                "entity": "",
                "name": naam,
                "type": "bar",
                "x": x,
                "y": f"$ex {dagen}.map(d => (d.voertuigen || {{}})[{naam!r}] || 0)",
                "marker": {"color": k},
                "hovertemplate": hover,
            }
            for naam, k in kleuren.items()
        ]
        # Totaal boven de gestapelde staaf als losse tekstlaag.
        traces.append(
            {
                "entity": "",
                "name": "Totaal",
                "type": "scatter",
                "mode": "text",
                "x": x,
                "y": f"$ex {dagen}.map(d => d.kwh)",
                "text": f"$ex {dagen}.map(d => d.kwh.toFixed(1).replace('.', ','))",
                "textposition": "top center",
                "cliponaxis": False,
                "hoverinfo": "skip",
                "showlegend": False,
            }
        )
    else:
        traces = [
            {
                "entity": "",
                "name": "Geladen",
                "type": "bar",
                "x": x,
                "y": f"$ex {dagen}.map(d => d.kwh)",
                "marker": {"color": kleur.format(var="--primary-color", terugval="#03a9f4")},
                "texttemplate": "%{y:.1f}",
                "textposition": "outside",
                "cliponaxis": False,
                "hovertemplate": hover,
            }
        ]
    return {
        "type": "custom:plotly-graph",
        "raw_plotly_config": True,
        "hours_to_show": "current_month",
        "entities": traces,
        "layout": {
            "height": 280 if kleuren else 260,
            "margin": {"t": 32, "b": 36, "l": 44, "r": 12},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"family": "Roboto, Noto, sans-serif", "size": 12, "color": tekst},
            "separators": ",.",  # decimale komma
            "barmode": "stack",
            "bargap": 0.35,
            "showlegend": bool(kleuren),
            "legend": {"orientation": "h", "x": 0, "y": -0.18, "traceorder": "normal", "font": {"size": 11}},
            "xaxis": {"type": "category", "fixedrange": True, "showgrid": False},
            "yaxis": {
                "title": {"text": "kWh"},
                "rangemode": "tozero",
                "fixedrange": True,
                "gridcolor": "rgba(127,127,127,0.2)",
                "zeroline": False,
            },
        },
        "config": {"displayModeBar": False, "responsive": True},
    }


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

    kleuren = _voertuig_kleuren(hass, conf) if per_voertuig else {}

    tiles = [
        {"type": "tile", "entity": e["maand_kwh"], "name": "Geladen", "icon": "mdi:lightning-bolt", "color": "green"},
        {"type": "tile", "entity": e["maand_kosten"], "name": "Kosten", "icon": "mdi:currency-eur", "color": "orange"},
    ]
    # Laadpaal en aangesloten voertuig als paar naast elkaar (elk een halve rij breed).
    if conf.get(CONF_STATUS):
        tiles.append(
            {"type": "tile", "entity": conf[CONF_STATUS], "name": "Laadpaal", "icon": "mdi:ev-plug-type2", "color": "blue"}
        )
    voertuig_tegel = {
        "type": "tile",
        "entity": e["actief"],
        "name": "Aangesloten voertuig",
        "icon": "mdi:car-electric",
        "state_content": "voertuig",
    }
    if per_voertuig:
        # Eén tegel per bekend voertuig in de eigen kleur (dezelfde als in de grafiek); de
        # zichtbaarheid volgt de voertuig-sensor. Anders een grijze tegel ("Geen"/onbekend).
        bekend = [n for n in kleuren if n != ONBEKEND_VOERTUIG]
        for naam in bekend:
            tiles.append(
                {
                    **voertuig_tegel,
                    "color": kleuren[naam],
                    "visibility": [{"condition": "state", "entity": conf[CONF_VOERTUIG], "state": naam}],
                }
            )
        tiles.append(
            {
                **voertuig_tegel,
                "icon": "mdi:car-off",
                "color": "disabled",
                "visibility": [{"condition": "state", "entity": conf[CONF_VOERTUIG], "state_not": bekend}]
                if bekend
                else [],
            }
        )
    elif not conf.get(CONF_KENTEKEN):
        # Zonder vast kenteken altijd tonen welk voertuig nu is aangesloten.
        tiles.append({**voertuig_tegel, "color": "purple"})

    # Lopende sessie alleen tonen zolang er geladen wordt (of de sessie al energie heeft).
    laden = [{"condition": "numeric_state", "entity": e["actief"], "above": 0}]
    if conf.get(CONF_POWER):
        laden.append({"condition": "numeric_state", "entity": conf[CONF_POWER], "above": 0})
    tijdens_laden = [{"condition": "or", "conditions": laden}]
    tiles += [
        {
            "type": "tile",
            "entity": e["actief"],
            "name": "Actieve sessie",
            "icon": "mdi:battery-charging",
            "color": "green",
            "visibility": tijdens_laden,
        },
        {
            "type": "tile",
            "entity": e["actief_kosten"],
            "name": "Kosten sessie",
            "icon": "mdi:cash-clock",
            "color": "orange",
            "visibility": tijdens_laden,
        },
    ]
    if conf.get(CONF_TARIFF):
        interval = conf.get(CONF_TARIEF_INTERVAL) or DEFAULT_TARIEF_INTERVAL
        tegel_naam = TARIEF_INTERVAL_TEGEL.get(interval, TARIEF_INTERVAL_TEGEL[DEFAULT_TARIEF_INTERVAL])
        tiles.append(
            {"type": "tile", "entity": conf[CONF_TARIFF], "name": tegel_naam, "icon": "mdi:cash", "color": "amber"}
        )
    # Tariefstatus alleen als waarschuwing bij een storing.
    tiles.append(
        {
            "type": "tile",
            "entity": e["tarief_status"],
            "name": f"{tariff_name} tarief: storing",
            "icon": "mdi:alert",
            "color": "red",
            "grid_options": {"columns": "full"},
            "visibility": [{"condition": "state", "entity": e["tarief_status"], "state": "storing"}],
        }
    )

    # Als HTML-tabel i.p.v. markdown: alleen zo kan hij de volle breedte van de kaart vullen
    # (de markdown-kaart laat het width-attribuut door, maar geen CSS).
    kolommen = [("Maand", "left")]
    if per_voertuig:
        kolommen.append(("Voertuig", "left"))
    kolommen += [("Sessies", "right"), ("kWh", "right"), ("Kosten", "right"), ("Rapport", "center")]
    kop = "<tr>" + "".join(f'<th align="{al}">{naam}</th>' for naam, al in kolommen) + "</tr>\n"
    voertuig_cel = "<td>{{ x.voertuig or '' }}</td>" if per_voertuig else ""
    leeg_cel = "<td></td>" if per_voertuig else ""
    bedrag = "€\u00a0{{{{ '%.2f'|format({0}) | replace('.',',') }}}}"
    totaal_kosten = bedrag.format("r | sum(attribute='kosten')")
    table = (
        f"{{% set r = state_attr('{reports}','rapporten') or [] %}}\n"
        "{% if r %}\n"
        f'<table width="100%">\n{kop}'
        "{% for x in r %}<tr>"
        "<td>{{ x.maand | capitalize }}"
        "{% if x.voorlopig %} <small><font color=\"#ff9800\">● voorlopig</font></small>{% endif %}</td>"
        f"{voertuig_cel}"
        '<td align="right">{{ x.sessies }}</td>'
        "<td align=\"right\">{{ '%.2f'|format(x.kwh) | replace('.',',') }}</td>"
        f'<td align="right">{bedrag.format("x.kosten")}</td>'
        '<td align="center" width="96">'
        '<a href="{{ x.viewer }}" target="_blank" rel="noopener" title="Bekijken">'
        '<ha-icon icon="mdi:eye"></ha-icon></a>&nbsp;'
        '<a href="{{ x.pdf }}" target="_blank" rel="noopener" title="PDF openen">'
        '<ha-icon icon="mdi:file-pdf-box"></ha-icon></a>&nbsp;'
        '<a href="{{ x.csv }}" target="_blank" rel="noopener" title="CSV downloaden">'
        '<ha-icon icon="mdi:file-delimited"></ha-icon></a></td>'
        "</tr>\n{% endfor %}"
        "<tr><td><b>Totaal</b></td>"
        f"{leeg_cel}"
        "<td align=\"right\"><b>{{ r | sum(attribute='sessies') }}</b></td>"
        "<td align=\"right\"><b>{{ '%.2f'|format(r | sum(attribute='kwh')) | replace('.',',') }}</b></td>"
        f'<td align="right"><b>{totaal_kosten}</b></td>'
        "<td></td></tr>\n</table>\n"
        "{% else %}Nog geen rapporten.{% endif %}"
    )

    # Voorkeur: Plotly (alleen laaddagen), dan ApexCharts (hele maand), anders een tekstgrafiek.
    plotly = _heeft_kaart(hass, "plotly-graph-card", "lovelace-plotly-graph-card")
    apex = not plotly and _heeft_kaart(hass, "apexcharts-card", "apexcharts-card")
    # Zonder apexcharts-card: blokjes-sparkline als gewone (grote) markdown-tekst. Een code-blok
    # kreeg in de praktijk een kleurthema waarin de tekens onzichtbaar bleken.
    sparkline = (
        ""
        if plotly or apex
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
    if plotly:
        # Alleen voertuigen die deze maand geladen hebben (plus het nu aangesloten voertuig);
        # stapelen heeft pas zin bij meer dan één voertuig.
        st_maand = hass.states.get(e["maand_kwh"])
        geladen = set(((st_maand and st_maand.attributes.get("per_voertuig")) or {}).keys())
        st_v = hass.states.get(conf.get(CONF_VOERTUIG) or "")
        if st_v:
            geladen.add(st_v.state)
        grafiek_kleuren = {n: k for n, k in kleuren.items() if n in geladen}
        plotly_kaart = _plotly_grafiek(e["maand_kwh"], grafiek_kleuren if len(grafiek_kleuren) > 1 else None)
        grafiek_kaarten.insert(1, {**plotly_kaart, "grid_options": {"columns": "full"}})
    elif apex:
        grafiek_kaarten.insert(1, {**_apex_grafiek(e["maand_kwh"]), "grid_options": {"columns": "full"}})

    # Grafiek alleen zo breed als nodig: bij weinig laaddagen een smalle kolom.
    st = hass.states.get(e["maand_kwh"])
    laaddagen = sum(1 for d in ((st and st.attributes.get("per_dag")) or []) if d.get("kwh"))
    grafiek_breedte = 3 if apex else (1 if laaddagen <= 8 else 2 if laaddagen <= 16 else 3)

    rapporten_kaarten = [
        {
            "type": "heading",
            "heading": "Rapporten",
            "icon": "mdi:file-document-multiple",
            # Klein recycle-icoon rechts in de kop i.p.v. een grote knop bovenaan het dashboard.
            "badges": [
                {
                    "type": "entity",
                    "entity": reports,
                    "name": "Rapporten opnieuw genereren...",  # tooltip van het icoon
                    "icon": "mdi:recycle",
                    "show_state": False,
                    "show_icon": True,
                    "tap_action": {
                        "action": "perform-action",
                        "perform_action": f"{DOMAIN}.genereer_rapport",
                        "data": {"alle": True},
                        "confirmation": {"text": "Alle rapporten opnieuw maken?"},
                    },
                }
            ],
        },
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
                        ],
                    },
                    {
                        "type": "grid",
                        "column_span": grafiek_breedte,
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
