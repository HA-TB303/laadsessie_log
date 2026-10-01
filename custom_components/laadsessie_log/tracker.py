"""Logica voor laadsessies en kwartiertarieven, zonder Home Assistant-afhankelijkheden.

De tracker krijgt tijdgestempelde gebeurtenissen (vermogen, status, sessie-energie,
tarief) en bouwt daaruit laadsessies op met per kwartier de energie en het tarief.
Dezelfde code wordt gebruikt voor live verwerking en voor het naspelen van historie.
"""
from __future__ import annotations

from datetime import datetime, timedelta, tzinfo

QUARTER = timedelta(minutes=15)
END_GRACE = timedelta(minutes=2)
PRICE_PROBE = timedelta(seconds=60)
TARIFF_STALE_DEFAULT = timedelta(hours=3)
MIN_SESSION_KWH = 0.05

# Statussen die niets zeggen over wel/niet aangesloten (glitches bij herverbinden)
IGNORED_STATUS = {"", "unknown", "unavailable", "unknown 0", "offline", "none"}

SOURCE_LIVE = "zonneplan"
SOURCE_FALLBACK = "terugval"
SOURCE_NONE = "onbekend"


def floor_quarter(ts: datetime) -> datetime:
    return ts.replace(minute=ts.minute - ts.minute % 15, second=0, microsecond=0)


def _iso(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SessionTracker:
    def __init__(
        self,
        tz: tzinfo,
        disconnected: set[str] | None = None,
        tariff_stale: timedelta | None = None,
    ) -> None:
        self.tz = tz
        self.disconnected = disconnected or {"disconnected"}
        self.tariff_stale = tariff_stale or TARIFF_STALE_DEFAULT
        self.slots: dict[str, dict] = {}  # "HH:MM" -> {"prijs", "datum"}
        self.timeline: list[tuple[datetime, float | None]] = []
        self.last_ts: datetime | None = None
        self.q_start: datetime | None = None
        self.q_energy = 0.0
        self.power: float | None = None
        self.status_seen = False
        self.session: dict | None = None
        self.pending_end: datetime | None = None
        self.session_energy: tuple[datetime, float] | None = None
        self.voertuig: str | None = None
        self.q_voertuig: str | None = None
        self.outage: dict | None = None
        self.outputs: list[tuple[str, dict]] = []

    # ------------------------------------------------------------------ input
    def feed_power(self, ts: datetime, value: float | None) -> None:
        self._advance(ts)
        self.power = value

    def feed_status(self, ts: datetime, value: str | None) -> None:
        ts = self._advance(ts)
        value = (value or "").strip().lower()
        if value in IGNORED_STATUS:
            return
        first = not self.status_seen
        self.status_seen = True
        if value in self.disconnected:
            if self.session and not self.pending_end:
                self.pending_end = ts
            return
        self.pending_end = None
        if self.session is None:
            self.session = {
                "start": _iso(ts),
                "kwartieren": [],
                "onvolledig": first,
            }
            self.q_energy = 0.0
            # Voertuig van een vorige sessie niet laten doorlekken; wordt (opnieuw)
            # vastgesteld via feed_voertuig() zodra de herkenning een resultaat geeft.
            self.voertuig = None
            self.q_voertuig = None

    def feed_session_energy(self, ts: datetime, value: float | None) -> None:
        ts = self._advance(ts)
        if value is not None:
            self.session_energy = (ts, value)

    def feed_voertuig(self, ts: datetime, value: str | None) -> None:
        self._advance(ts)
        value = (value or "").strip()
        if value and value.lower() not in IGNORED_STATUS:
            self.voertuig = value

    def feed_tariff(self, ts: datetime, value: float | None) -> None:
        ts = self._advance(ts)
        self.timeline.append((ts, value))
        cutoff = (self.q_start or ts) - QUARTER
        while len(self.timeline) > 1 and self.timeline[1][0] <= cutoff:
            self.timeline.pop(0)

    def tick(self, ts: datetime) -> None:
        self._advance(ts)

    def pop_outputs(self) -> list[tuple[str, dict]]:
        out, self.outputs = self.outputs, []
        return out

    # ---------------------------------------------------------------- interne
    def _advance(self, ts: datetime) -> datetime:
        if self.last_ts and ts < self.last_ts:
            ts = self.last_ts
        if self.q_start is None:
            self.q_start = floor_quarter(ts)
        if self.last_ts is None:
            self.last_ts = ts
        while ts >= self.q_start + QUARTER:
            boundary = self.q_start + QUARTER
            self._maybe_finalize(boundary)
            self._integrate(boundary)
            self._close_quarter(boundary)
            self.q_start = boundary
        self._maybe_finalize(ts)
        self._integrate(ts)
        return ts

    def _integrate(self, ts: datetime) -> None:
        if self.session and self.power and self.power > 0 and ts > self.last_ts:
            self.q_energy += self.power * (ts - self.last_ts).total_seconds() / 3600
            # Voertuig vastleggen op het moment dat er echt energie bijkomt, niet pas
            # bij het wegschrijven van het kwartier of afsluiten van de sessie: na het
            # loskoppelen van de kabel kan de herkenningssensor sneller terugvallen op
            # "onbekend" dan de aansluitstatus zelf bijwerkt.
            self.q_voertuig = self.voertuig
        if ts > self.last_ts:
            self.last_ts = ts

    def _maybe_finalize(self, ts: datetime) -> None:
        if self.session and self.pending_end and ts >= self.pending_end + END_GRACE:
            self._integrate(self.pending_end + END_GRACE)
            self._finalize(self.pending_end, ts)

    def _tariff_at(self, ts: datetime) -> tuple[datetime, float | None] | None:
        found = None
        for entry in self.timeline:
            if entry[0] <= ts:
                found = entry
            else:
                break
        return found

    def _live_price(self, q_start: datetime) -> float | None:
        probe = q_start + PRICE_PROBE
        entry = self._tariff_at(probe)
        if entry and entry[1] is not None and probe - entry[0] <= self.tariff_stale:
            return entry[1]
        for ts, value in self.timeline:
            if q_start <= ts < q_start + QUARTER and value is not None:
                return value
        return None

    def _price(self, q_start: datetime, update: bool) -> dict:
        local = q_start.astimezone(self.tz)
        slot = local.strftime("%H:%M")
        price = self._live_price(q_start)
        if price is not None:
            if update:
                self.slots[slot] = {"prijs": price, "datum": local.date().isoformat()}
                if self.outage:
                    self.outputs.append(("tariff_restored", {**self.outage, "hersteld": _iso(q_start)}))
                    self.outage = None
            return {"prijs": price, "bron": SOURCE_LIVE}
        if update:
            if self.outage is None:
                self.outage = {"sinds": _iso(q_start), "kwartieren": 0}
                self.outputs.append(("tariff_outage", dict(self.outage)))
            self.outage["kwartieren"] += 1
        fb = self.slots.get(slot)
        if fb:
            return {"prijs": fb["prijs"], "bron": SOURCE_FALLBACK, "terugval_datum": fb["datum"]}
        return {"prijs": None, "bron": SOURCE_NONE}

    def _add_row(self, q_start: datetime, price: dict) -> None:
        if self.session is not None and self.q_energy > 0.0001:
            self.session["kwartieren"].append(
                {"start": _iso(q_start), "kwh_vermogen": self.q_energy, "voertuig": self.q_voertuig, **price}
            )
        self.q_energy = 0.0
        self.q_voertuig = None

    def _close_quarter(self, boundary: datetime) -> None:
        price = self._price(self.q_start, update=True)
        self._add_row(self.q_start, price)

    def _finalize(self, end: datetime, now: datetime) -> None:
        session = self.session
        q_start = self.q_start
        if self.q_energy > 0.0001:
            self._add_row(q_start, self._price(q_start, update=False))
        self.session = None
        self.pending_end = None
        self.q_energy = 0.0

        start = _dt(session["start"])
        rows = session["kwartieren"]
        integrated = sum(r["kwh_vermogen"] for r in rows)
        meter = None
        if self.session_energy and self.session_energy[0] >= start - timedelta(seconds=60):
            meter = self.session_energy[1] if self.session_energy[1] > 0 else None

        if meter is not None and integrated <= 0:
            q = floor_quarter(start)
            voertuig = self.q_voertuig or self.voertuig
            rows.append(
                {"start": _iso(q), "kwh_vermogen": 0.0, "voertuig": voertuig, **self._price_from_slots(q)}
            )
        total_kwh = meter if meter is not None else integrated
        if total_kwh < MIN_SESSION_KWH:
            return

        for r in rows:
            if integrated > 0:
                r["kwh"] = r["kwh_vermogen"] * total_kwh / integrated
            else:
                r["kwh"] = total_kwh / len(rows)
            r["kosten"] = r["kwh"] * r["prijs"] if r["prijs"] is not None else 0.0

        # Voertuig van de sessie: het voertuig met de meeste geladen energie over de
        # kwartieren heen (vastgelegd tijdens het laden zelf, zie _integrate), niet het
        # mogelijk inmiddels teruggevallen self.voertuig op het moment van afsluiten.
        voertuig_kwh: dict[str, float] = {}
        for r in rows:
            v = r.get("voertuig")
            if v:
                voertuig_kwh[v] = voertuig_kwh.get(v, 0.0) + r["kwh_vermogen"]
        sessie_voertuig = max(voertuig_kwh, key=voertuig_kwh.get) if voertuig_kwh else None

        session.update(
            {
                "einde": _iso(end),
                "kwh": total_kwh,
                "kwh_vermogen": integrated,
                "kwh_bron": "laadpaal" if meter is not None else "vermogen",
                "kosten": sum(r["kosten"] for r in rows),
                "terugval": any(r["bron"] != SOURCE_LIVE for r in rows),
                "voertuig": sessie_voertuig,
            }
        )
        self.outputs.append(("session_finished", session))

    def _price_from_slots(self, q_start: datetime) -> dict:
        slot = q_start.astimezone(self.tz).strftime("%H:%M")
        fb = self.slots.get(slot)
        if fb:
            return {"prijs": fb["prijs"], "bron": SOURCE_FALLBACK, "terugval_datum": fb["datum"]}
        return {"prijs": None, "bron": SOURCE_NONE}

    # ------------------------------------------------------------ persistentie
    def to_dict(self) -> dict:
        return {
            "slots": self.slots,
            "timeline": [[_iso(t), v] for t, v in self.timeline],
            "last_ts": _iso(self.last_ts),
            "q_start": _iso(self.q_start),
            "q_energy": self.q_energy,
            "status_seen": self.status_seen,
            "session": self.session,
            "pending_end": _iso(self.pending_end),
            "session_energy": [_iso(self.session_energy[0]), self.session_energy[1]] if self.session_energy else None,
            "voertuig": self.voertuig,
            "q_voertuig": self.q_voertuig,
            "outage": self.outage,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        tz: tzinfo,
        disconnected: set[str] | None = None,
        tariff_stale: timedelta | None = None,
    ) -> SessionTracker:
        t = cls(tz, disconnected, tariff_stale)
        t.slots = data.get("slots", {})
        t.timeline = [(_dt(ts), v) for ts, v in data.get("timeline", [])]
        t.last_ts = _dt(data.get("last_ts"))
        t.q_start = _dt(data.get("q_start"))
        t.q_energy = data.get("q_energy", 0.0)
        t.status_seen = data.get("status_seen", False)
        t.session = data.get("session")
        t.pending_end = _dt(data.get("pending_end"))
        se = data.get("session_energy")
        t.session_energy = (_dt(se[0]), se[1]) if se else None
        t.voertuig = data.get("voertuig")
        t.q_voertuig = data.get("q_voertuig")
        t.outage = data.get("outage")
        # Vermogen is na een herstart onbekend tot de eerste nieuwe meting.
        t.power = None
        return t
