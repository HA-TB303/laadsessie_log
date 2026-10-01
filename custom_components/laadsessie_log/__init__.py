"""Laadsessie log: logt laadsessies per kwartier met een dynamisch tarief en maakt maandrapporten (PDF)."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from calendar import monthrange
from datetime import datetime, timedelta
from functools import partial

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.components.recorder import get_instance, history
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall, State, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from . import dashboard
from .const import (
    CONF_DASHBOARD,
    CONF_DISCONNECTED,
    CONF_INFO,
    CONF_POWER,
    CONF_SESSION_ENERGY,
    CONF_STATUS,
    CONF_TARIEF_INTERVAL,
    CONF_TARIFF,
    CONF_TARIFF_NAME,
    CONF_VOERTUIG,
    DEFAULT_DISCONNECTED,
    DEFAULT_TARIEF_INTERVAL,
    DEFAULT_TARIFF_NAME,
    DOMAIN,
    ONBEKEND_VOERTUIG,
    REPORT_URL,
    SIGNAL_UPDATE,
    TARIEF_INTERVAL_LABEL,
    TARIEF_INTERVAL_UREN,
)
from .pdf import MONTHS, build_report, num
from .rapport_view import Ondertekenaar, RapportView
from .tracker import SOURCE_LIVE, SessionTracker

_LOGGER = logging.getLogger(__name__)

NOTIFICATION_ID = f"{DOMAIN}_zonneplan"
REPORT_DIR = "laadsessies/rapporten"
OUDE_REPORT_DIR = "www/laadrapporten"  # tot en met 1.4.0: openbaar via /local
VIEWER_DIR = "www/laadrapporten/viewer"
FIRST_RUN_DAYS = 10
RETENTION_MONTHS = 15  # naast de lopende maand
PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def parse_states(value: str) -> set[str]:
    return {v.strip().lower() for v in value.split(",") if v.strip()}


def _float(state: State | None) -> float | None:
    if state is None:
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, path)


def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


def _write_bytes(path: str, data: bytes, copies: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for p in [path, *copies]:
        tmp = p + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, p)


def _install_viewer(src_dir: str, dest_dir: str) -> None:
    """PDF-viewer (pdf.js) naar de www-map kopiëren als die ontbreekt of verouderd is."""
    os.makedirs(dest_dir, exist_ok=True)
    for name in os.listdir(src_dir):
        src = os.path.join(src_dir, name)
        dest = os.path.join(dest_dir, name)
        with open(src, "rb") as fh:
            data = fh.read()
        try:
            with open(dest, "rb") as fh:
                if fh.read() == data:
                    continue
        except FileNotFoundError:
            pass
        _write_bytes(dest, data, [])


def _verplaats_oude_rapporten(oud: str, nieuw: str) -> int:
    """Rapporten uit de openbare www-map naar de afgeschermde rapportmap verplaatsen."""
    if not os.path.isdir(oud):
        return 0
    os.makedirs(nieuw, exist_ok=True)
    aantal = 0
    for name in os.listdir(oud):
        src = os.path.join(oud, name)
        if not os.path.isfile(src) or not name.endswith((".pdf", ".csv", ".html")):
            continue
        dest = os.path.join(nieuw, name)
        if os.path.exists(dest):
            os.remove(src)
        else:
            shutil.move(src, dest)
        aantal += 1
    return aantal


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _slug(naam: str) -> str:
    """Bestandsnaamveilige, kleine-letters-versie van een voertuignaam."""
    s = re.sub(r"[^a-z0-9]+", "-", naam.strip().lower()).strip("-")
    return s or "onbekend"


# Matcht "laadrapport_2024-05.pdf" en, bij CONF_VOERTUIG, "laadrapport_2024-05_<slug>.pdf".
# "laadrapport_vorige_maand(_<slug>).pdf" matcht hier bewust niet (geen \d{4}-\d{2}).
_REPORT_RE = re.compile(r"^laadrapport_(\d{4})-(\d{2})(?:_(.+))?\.(pdf|csv)$")


async def _migreer_rapportgegevens(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Eenmalig: naam/adres/kenteken van de oude tekstvelden naar de integratie-instellingen migreren."""
    path = os.path.join(hass.config.path("laadsessies"), "gegevens.json")
    oud = await hass.async_add_executor_job(_read_json, path, None)
    if not oud:
        return
    aanvulling = {
        k: v for k, v in oud.items() if k in CONF_INFO and v and not (entry.data.get(k) or entry.options.get(k))
    }
    if aanvulling:
        hass.config_entries.async_update_entry(entry, options={**entry.options, **aanvulling})
        _LOGGER.info(
            "Laadsessie log: %s gemigreerd van tekstvelden naar integratie-instellingen",
            ", ".join(aanvulling),
        )
    # Bestand aan de kant zetten zodat dit echt maar één keer gebeurt; anders vult een
    # latere herstart een veld dat de gebruiker daarna weer heeft leeggemaakt opnieuw aan.
    await hass.async_add_executor_job(os.replace, path, path + ".gemigreerd")


class LaadLog:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.conf = conf = {**entry.data, **entry.options}
        self.tariff_name = conf.get(CONF_TARIFF_NAME) or DEFAULT_TARIFF_NAME
        self.disconnected = parse_states(conf.get(CONF_DISCONNECTED) or DEFAULT_DISCONNECTED)
        self.tarief_interval = conf.get(CONF_TARIEF_INTERVAL) or DEFAULT_TARIEF_INTERVAL
        self.tariff_stale = timedelta(
            hours=TARIEF_INTERVAL_UREN.get(self.tarief_interval, TARIEF_INTERVAL_UREN[DEFAULT_TARIEF_INTERVAL])
        )
        self.tarief_label = TARIEF_INTERVAL_LABEL.get(
            self.tarief_interval, TARIEF_INTERVAL_LABEL[DEFAULT_TARIEF_INTERVAL]
        )
        self._unsubs: list = []
        self._units: dict[str, str] = {}
        self.tz = dt_util.get_default_time_zone()
        self.data_dir = hass.config.path("laadsessies")
        self.report_dir = hass.config.path(REPORT_DIR)
        self.links = Ondertekenaar(hass)
        self.state_path = os.path.join(self.data_dir, "state.json")
        self.sessions_path = os.path.join(self.data_dir, "sessies.json")
        self.tracker = SessionTracker(self.tz, self.disconnected, self.tariff_stale)
        self.sessions: list[dict] = []
        self.reports: list[dict] = []
        self.ready = False
        self.entities = {}
        for key, kind in (
            (CONF_POWER, "power"),
            (CONF_STATUS, "status"),
            (CONF_SESSION_ENERGY, "energy"),
            (CONF_TARIFF, "tariff"),
            (CONF_VOERTUIG, "voertuig"),
        ):
            if conf.get(key):
                self.entities[conf[key]] = kind

    # ------------------------------------------------------------- opstarten
    async def async_load(self) -> None:
        state = await self.hass.async_add_executor_job(_read_json, self.state_path, None)
        self.sessions = await self.hass.async_add_executor_job(_read_json, self.sessions_path, [])
        if state:
            self.tracker = SessionTracker.from_dict(state, self.tz, self.disconnected, self.tariff_stale)
        verplaatst = await self.hass.async_add_executor_job(
            _verplaats_oude_rapporten, self.hass.config.path(OUDE_REPORT_DIR), self.report_dir
        )
        if verplaatst:
            _LOGGER.info("Laadsessie log: %d rapportbestanden uit www/ naar %s verplaatst", verplaatst, REPORT_DIR)
        self.reports = await self.hass.async_add_executor_job(self._scan_reports)
        await self.hass.async_add_executor_job(
            _install_viewer,
            os.path.join(os.path.dirname(__file__), "viewer"),
            self.hass.config.path(VIEWER_DIR),
        )

    async def async_regenerate_all(self) -> int:
        """Alle bestaande rapporten (plus vorige en huidige maand) opnieuw maken."""
        now = dt_util.now()
        months = {(r["jaar"], r["maand_nr"]) for r in self.reports}
        months |= {_prev_month(now.year, now.month), (now.year, now.month)}
        totaal = 0
        for ym in sorted(months):
            totaal += len(await self.async_generate_voertuigen(*ym))
        return totaal

    async def async_start(self) -> None:
        now = dt_util.utcnow()
        start = self.tracker.last_ts or now - timedelta(days=FIRST_RUN_DAYS)
        start = min(start, now)
        _LOGGER.info("Laadsessie log: historie naspelen vanaf %s", start)
        try:
            hist = await get_instance(self.hass).async_add_executor_job(
                partial(
                    history.get_significant_states,
                    self.hass,
                    start,
                    now,
                    list(self.entities),
                    include_start_time_state=True,
                    significant_changes_only=False,
                    minimal_response=False,
                    no_attributes=True,
                )
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Laadsessie log: historie ophalen mislukt")
            hist = {}

        events = []
        for entity_id, states in hist.items():
            for st in states:
                if isinstance(st, State):
                    events.append((st.last_updated, entity_id, st))
        events.sort(key=lambda e: e[0])
        # Tijdens het naspelen geen notificaties per gebeurtenis; alleen de eindtoestand telt.
        for ts, entity_id, st in events:
            self._feed(entity_id, st, ts)
        for entity_id in self.entities:
            st = self.hass.states.get(entity_id)
            if st:
                self._feed(entity_id, st, st.last_updated)
        self.tracker.tick(dt_util.utcnow())
        await self._handle_outputs(replay=True)

        self.ready = True
        self._unsubs += [
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._on_stop),
            async_track_state_change_event(self.hass, list(self.entities), self._on_state),
            async_track_time_change(self.hass, self._on_tick, second=5),
            async_track_time_change(self.hass, self._on_month, hour=0, minute=5, second=30),
        ]

        await self._save_state()
        await self.async_purge()
        await self._ensure_reports()
        self._notify_update()

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self.ready:
            await self._save_state()

    # --------------------------------------------------------------- invoer
    def _value(self, entity_id: str, st: State) -> float | None:
        """Numerieke waarde, omgerekend naar kW of kWh (W en Wh worden ondersteund)."""
        value = _float(st)
        unit = st.attributes.get("unit_of_measurement")
        if unit:
            self._units[entity_id] = unit
        else:
            live = self.hass.states.get(entity_id)
            unit = self._units.get(entity_id) or (live and live.attributes.get("unit_of_measurement"))
        if value is not None and unit in ("W", "Wh"):
            value /= 1000
        return value

    def _feed(self, entity_id: str, st: State, ts: datetime) -> None:
        kind = self.entities[entity_id]
        if kind == "power":
            self.tracker.feed_power(ts, self._value(entity_id, st))
        elif kind == "status":
            self.tracker.feed_status(ts, st.state)
        elif kind == "energy":
            self.tracker.feed_session_energy(ts, self._value(entity_id, st))
        elif kind == "voertuig":
            self.tracker.feed_voertuig(ts, st.state)
        else:
            self.tracker.feed_tariff(ts, _float(st))

    @callback
    def _on_state(self, event: Event) -> None:
        st: State | None = event.data.get("new_state")
        if st is None:
            return
        self._feed(event.data["entity_id"], st, st.last_updated)
        if self.tracker.outputs:
            self.hass.async_create_task(self._handle_outputs())
        if self.entities[event.data["entity_id"]] in ("status", "tariff", "voertuig"):
            self._notify_update()

    async def _on_tick(self, now: datetime) -> None:
        self.tracker.tick(dt_util.utcnow())
        changed = await self._handle_outputs()
        if not changed and now.minute % 15 == 1:
            await self._save_state()
        self._notify_update()

    async def _on_month(self, now: datetime) -> None:
        if now.day != 1:
            return
        year, month = _prev_month(now.year, now.month)
        await self.async_generate_voertuigen(year, month)
        await self.async_purge()

    async def _on_stop(self, _event: Event) -> None:
        await self._save_state()

    # ------------------------------------------------------------ uitvoer
    async def _handle_outputs(self, replay: bool = False) -> bool:
        outputs = self.tracker.pop_outputs()
        if not outputs:
            return False
        months = set()
        for kind, data in outputs:
            if kind == "session_finished":
                self._add_session(data)
                end = datetime.fromisoformat(data["einde"]).astimezone(self.tz)
                months.add((end.year, end.month))
                _LOGGER.info("Laadsessie afgerond: %s, %.2f kWh, EUR %.2f", data["start"], data["kwh"], data["kosten"])
            elif kind == "tariff_outage" and not replay:
                self._notify_outage(data)
            elif kind == "tariff_restored" and not replay:
                self._notify_restored(data)
        if replay and self.tracker.outage:
            self._notify_outage(self.tracker.outage)
        await self.hass.async_add_executor_job(_write_json, self.sessions_path, self.sessions)
        await self._save_state()
        for year, month in sorted(months):
            await self.async_generate_voertuigen(year, month)
        self._notify_update()
        return True

    def _add_session(self, session: dict) -> None:
        start = datetime.fromisoformat(session["start"])
        for i, s in enumerate(self.sessions):
            if abs((datetime.fromisoformat(s["start"]) - start).total_seconds()) < 60:
                self.sessions[i] = session
                break
        else:
            self.sessions.append(session)
        self.sessions.sort(key=lambda s: s["start"])

    async def _save_state(self) -> None:
        await self.hass.async_add_executor_job(_write_json, self.state_path, self.tracker.to_dict())

    def _local(self, ts: str) -> datetime:
        return datetime.fromisoformat(ts).astimezone(self.tz)

    def _notify_outage(self, data: dict) -> None:
        since = self._local(data["sinds"])
        persistent_notification.async_create(
            self.hass,
            (
                f"De {self.tariff_name}-tariefsensor (`{self.conf[CONF_TARIFF]}`) levert sinds "
                f"**{since:%d-%m-%Y %H:%M}** geen tarief.\n\n"
                "Laadsessies worden in de tussentijd berekend met het tarief van de meest recente dag "
                "waarop op hetzelfde kwartier wel een tarief bekend was (terugvaltarief). "
                f"Controleer de {self.tariff_name}-integratie."
            ),
            title=f"{self.tariff_name}-tarief niet beschikbaar",
            notification_id=NOTIFICATION_ID,
        )

    def _notify_restored(self, data: dict) -> None:
        since = self._local(data["sinds"])
        restored = self._local(data["hersteld"])
        persistent_notification.async_create(
            self.hass,
            (
                f"De {self.tariff_name}-tariefsensor was niet beschikbaar van **{since:%d-%m-%Y %H:%M}** tot "
                f"**{restored:%d-%m-%Y %H:%M}** ({data['kwartieren']} kwartieren). "
                "Laden in die periode is berekend met terugvaltarieven en staat in het rapport gemarkeerd met T."
            ),
            title=f"{self.tariff_name}-tarief weer beschikbaar",
            notification_id=NOTIFICATION_ID,
        )

    @callback
    def _notify_update(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    # ------------------------------------------------------------- rapporten
    def month_sessions(self, year: int, month: int, voertuig: str | None = None) -> list[dict]:
        out = []
        for s in self.sessions:
            end = self._local(s["einde"])
            if end.year == year and end.month == month:
                if voertuig is None or (s.get("voertuig") or ONBEKEND_VOERTUIG) == voertuig:
                    out.append(s)
        return out

    def per_voertuig(self, sessions: list[dict]) -> dict[str, dict]:
        """Totalen per voertuig, voor op de sensor (alleen zinvol als CONF_VOERTUIG is ingesteld)."""
        out: dict[str, dict] = {}
        for s in sessions:
            naam = s.get("voertuig") or ONBEKEND_VOERTUIG
            totaal = out.setdefault(naam, {"sessies": 0, "kwh": 0.0, "kosten": 0.0})
            totaal["sessies"] += 1
            totaal["kwh"] += s["kwh"]
            totaal["kosten"] += s["kosten"]
        return out

    def _voertuigen_in(self, sessions: list[dict]) -> set[str]:
        return {s.get("voertuig") or ONBEKEND_VOERTUIG for s in sessions}

    def per_dag(self, sessions: list[dict]) -> list[dict]:
        """kWh per dag van de maand, voor de grafiek op het dashboard."""
        ref = self._local(sessions[0]["start"]) if sessions else dt_util.now()
        laatste_dag = monthrange(ref.year, ref.month)[1]
        totalen = {dag: 0.0 for dag in range(1, laatste_dag + 1)}
        for s in sessions:
            for q in s["kwartieren"]:
                dag = self._local(q["start"]).day
                if dag in totalen:
                    totalen[dag] += q["kwh"]
        return [{"dag": dag, "kwh": round(kwh, 2)} for dag, kwh in totalen.items()]

    def _info(self, voertuig: str | None = None) -> dict:
        st = self.hass.states.get(self.conf.get(CONF_STATUS, ""))
        info = {}
        for key in CONF_INFO:
            info[key.capitalize()] = self.conf.get(key)
        if st:
            name = st.attributes.get("friendly_name", "Laadpaal").removesuffix(" Status")
            cid = st.attributes.get("id")
            info["Laadpaal"] = f"{name} ({cid})" if cid else name
            info["Locatie"] = info.get("Adres") or st.attributes.get("site_name")
            info.pop("Adres", None)
        if voertuig is not None:
            # Eén kenteken slaat nergens meer op zodra er per voertuig wordt gerapporteerd.
            info.pop("Kenteken", None)
            info["Voertuig"] = voertuig
        info["Tariefbron"] = f"{self.tariff_name} ({self.tarief_label})"
        return info

    async def async_generate(self, year: int, month: int, voertuig: str | None = None) -> dict:
        """Genereert één rapport. Bij CONF_VOERTUIG hoort hier een specifiek voertuig bij."""
        now = dt_util.now()
        provisional = (now.year, now.month) <= (year, month)
        sessions = self.month_sessions(year, month, voertuig)
        data = build_report(
            sessions,
            year,
            month,
            self.tz,
            self._info(voertuig),
            provisional,
            self.tariff_name,
            self.tarief_label,
            self.tarief_interval == "maand",
        )
        suffix = f"_{_slug(voertuig)}" if voertuig is not None else ""
        naam = f"laadrapport_{year}-{month:02d}{suffix}"
        base = os.path.join(self.report_dir, naam)
        copies = []
        if (year, month) == _prev_month(now.year, now.month):
            copies.append(os.path.join(self.report_dir, f"laadrapport_vorige_maand{suffix}.pdf"))
        await self.hass.async_add_executor_job(_write_bytes, base + ".pdf", data, copies)
        await self.hass.async_add_executor_job(
            _write_bytes, base + ".csv", self._csv(sessions).encode("utf-8-sig"), []
        )
        _LOGGER.info(
            "Laadrapport %d-%02d%s gegenereerd (%d sessies)",
            year,
            month,
            f" [{voertuig}]" if voertuig is not None else "",
            len(sessions),
        )
        self.reports = await self.hass.async_add_executor_job(self._scan_reports)
        self._notify_update()
        return {"pdf": f"{REPORT_URL}/{naam}.pdf"}

    async def async_generate_voertuigen(self, year: int, month: int) -> list[dict]:
        """Genereert het rapport voor een maand; bij CONF_VOERTUIG één rapport per voertuig."""
        if self.conf.get(CONF_VOERTUIG):
            # Alleen voertuigen die die maand echt geladen hebben; lege rapporten zeggen niets.
            voertuigen = sorted(self._voertuigen_in(self.month_sessions(year, month)))
            return [await self.async_generate(year, month, v) for v in voertuigen]
        return [await self.async_generate(year, month)]

    async def _ensure_reports(self) -> None:
        now = dt_util.now()
        months = {(now.year, now.month), _prev_month(now.year, now.month)}
        for s in self.sessions:
            end = self._local(s["einde"])
            months.add((end.year, end.month))
        for year, month in sorted(months):
            if self.conf.get(CONF_VOERTUIG):
                voertuigen = sorted(self._voertuigen_in(self.month_sessions(year, month)))
            else:
                voertuigen = [None]
            for voertuig in voertuigen:
                await self._ensure_report(year, month, voertuig)

    async def _ensure_report(self, year: int, month: int, voertuig: str | None) -> None:
        now = dt_util.now()
        bestaand = next(
            (
                r
                for r in self.reports
                if (r["jaar"], r["maand_nr"], r.get("voertuig")) == (year, month, voertuig)
            ),
            None,
        )
        # Voorlopige rapporten van afgesloten maanden opnieuw maken als definitief.
        stale = bool(bestaand) and bestaand["voorlopig"] and (year, month) < (now.year, now.month)
        prev = _prev_month(now.year, now.month)
        suffix = f"_{_slug(voertuig)}" if voertuig is not None else ""
        prev_copy = os.path.join(self.report_dir, f"laadrapport_vorige_maand{suffix}.pdf")
        prev_ok = await self.hass.async_add_executor_job(os.path.exists, prev_copy)
        if (
            bestaand is None
            or stale
            or (year, month) == (now.year, now.month)
            or ((year, month) == prev and not prev_ok)
        ):
            await self.async_generate(year, month, voertuig)

    def _retention_cutoff(self) -> tuple[int, int]:
        now = dt_util.now()
        idx = now.year * 12 + now.month - 1 - RETENTION_MONTHS
        return idx // 12, idx % 12 + 1

    async def async_purge(self) -> None:
        """Sessies en rapportbestanden ouder dan de bewaartermijn verwijderen."""
        cutoff = self._retention_cutoff()
        keep = []
        for s in self.sessions:
            end = self._local(s["einde"])
            if (end.year, end.month) >= cutoff:
                keep.append(s)
        removed_sessions = len(self.sessions) - len(keep)
        if removed_sessions:
            self.sessions = keep
            await self.hass.async_add_executor_job(_write_json, self.sessions_path, self.sessions)
        removed_files = await self.hass.async_add_executor_job(self._purge_files, cutoff)
        if removed_sessions or removed_files:
            _LOGGER.info(
                "Laadsessie log: %d sessies en %d rapportbestanden ouder dan %d-%02d verwijderd",
                removed_sessions,
                len(removed_files),
                *cutoff,
            )
            self.reports = await self.hass.async_add_executor_job(self._scan_reports)
            self._notify_update()

    def _purge_files(self, cutoff: tuple[int, int]) -> list[str]:
        removed = []
        if not os.path.isdir(self.report_dir):
            return removed
        for name in os.listdir(self.report_dir):
            m = _REPORT_RE.match(name)
            if not m:
                continue
            year, month = int(m.group(1)), int(m.group(2))
            if (year, month) < cutoff:
                os.remove(os.path.join(self.report_dir, name))
                removed.append(name)
        return removed

    def _csv(self, sessions: list[dict]) -> str:
        lines = [
            "sessie_start;sessie_einde;voertuig;kwartier;kwh;tarief_eur_per_kwh;kosten_eur;tariefbron;terugval_datum"
        ]
        for s in sessions:
            st = self._local(s["start"]).strftime("%Y-%m-%d %H:%M")
            en = self._local(s["einde"]).strftime("%Y-%m-%d %H:%M")
            voertuig = s.get("voertuig") or ""
            for q in s["kwartieren"]:
                price = num(q["prijs"], 7).replace(".", "") if q["prijs"] is not None else ""
                lines.append(
                    ";".join(
                        [
                            st,
                            en,
                            voertuig,
                            self._local(q["start"]).strftime("%Y-%m-%d %H:%M"),
                            num(q["kwh"], 4).replace(".", ""),
                            price,
                            num(q["kosten"], 4).replace(".", ""),
                            self.tariff_name.lower() if q["bron"] == SOURCE_LIVE else q["bron"],
                            q.get("terugval_datum", ""),
                        ]
                    )
                )
        return "\n".join(lines) + "\n"

    def _scan_reports(self) -> list[dict]:
        out = []
        if not os.path.isdir(self.report_dir):
            return out
        per_voertuig = bool(self.conf.get(CONF_VOERTUIG))
        for name in sorted(os.listdir(self.report_dir), reverse=True):
            if not name.endswith(".pdf"):
                continue
            m = _REPORT_RE.match(name)
            if not m:
                continue
            year, month, slug = int(m.group(1)), int(m.group(2)), m.group(3)
            if per_voertuig != (slug is not None):
                # Oude niet-opgesplitste rapporten (of, na uitschakelen, oude per-voertuig-
                # rapporten) horen niet bij de huidige modus; negeren voorkomt dubbele rijen.
                continue
            voertuig = None
            if slug is not None:
                # Slugs zijn lossy; herleid de echte naam via de sessies van die maand.
                kandidaten = self._voertuigen_in(self.month_sessions(year, month)) | {ONBEKEND_VOERTUIG}
                voertuig = next((v for v in kandidaten if _slug(v) == slug), slug)
            sessions = self.month_sessions(year, month, voertuig)
            kwh = round(sum(s["kwh"] for s in sessions), 2)
            kosten = round(sum(s["kosten"] for s in sessions), 2)
            if not kwh and not kosten:
                # Rapporten zonder geladen energie en kosten niet tonen.
                continue
            mtime = datetime.fromtimestamp(os.path.getmtime(os.path.join(self.report_dir, name)), self.tz)
            out.append(
                {
                    "jaar": year,
                    "maand_nr": month,
                    "maand": f"{MONTHS[month - 1]} {year}",
                    "voertuig": voertuig,
                    # Bestandsnamen; de sensor maakt er ondertekende links van (zie rapport_view.py).
                    "pdf": name,
                    "csv": f"{name[:-4]}.csv",
                    "sessies": len(sessions),
                    "kwh": kwh,
                    "kosten": kosten,
                    "voorlopig": mtime < datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=self.tz),
                }
            )
        return out


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    def _log() -> LaadLog:
        log = hass.data.get(DOMAIN)
        if log is None:
            raise HomeAssistantError("Laadsessie log is niet ingesteld")
        return log

    async def _generate(call: ServiceCall) -> dict:
        log = _log()
        if call.data.get("alle"):
            count = await log.async_regenerate_all()
            return {"aantal": count}
        now = dt_util.now()
        year, month = _prev_month(now.year, now.month)
        year = call.data.get("jaar", year)
        month = call.data.get("maand", month)
        resultaten = await log.async_generate_voertuigen(year, month)
        if len(resultaten) == 1:
            return resultaten[0]
        return {"rapporten": resultaten}

    hass.http.register_view(RapportView())
    hass.services.async_register(
        DOMAIN,
        "genereer_rapport",
        _generate,
        schema=vol.Schema(
            {
                vol.Optional("jaar"): vol.All(vol.Coerce(int), vol.Range(min=2020, max=2100)),
                vol.Optional("maand"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
                vol.Optional("alle", default=False): cv.boolean,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await _migreer_rapportgegevens(hass, entry)
    log = LaadLog(hass, entry)
    await log.async_load()
    hass.data[DOMAIN] = log
    entry.runtime_data = log

    async def _started(_hass: HomeAssistant) -> None:
        await log.async_start()

    entry.async_on_unload(async_at_started(hass, _started))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if log.conf.get(CONF_DASHBOARD, True) and dashboard.async_register(hass, log.conf):
        entry.async_on_unload(lambda: dashboard.async_unregister(hass))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_stop()
        hass.data.pop(DOMAIN, None)
    return ok
