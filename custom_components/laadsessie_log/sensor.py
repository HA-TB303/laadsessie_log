"""Sensoren voor het laadsessie-dashboard."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import CONF_TARIFF, CONF_VOERTUIG, DOMAIN, SIGNAL_UPDATE


def device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="Laadsessie log", manufacturer="Laadsessie log")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    log = entry.runtime_data
    async_add_entities(
        [
            MonthEnergy(log),
            MonthCost(log),
            ActiveSession(log),
            ActiveSessionCost(log),
            Reports(log),
            TariffStatus(log),
        ]
    )


class _Base(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, log) -> None:
        self.log = log
        self._attr_device_info = device_info(log.entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()

    def _this_month(self) -> list[dict]:
        now = datetime.now(self.log.tz)
        return self.log.month_sessions(now.year, now.month)


class MonthEnergy(_Base):
    _attr_name = "Laadsessies energie deze maand"
    _attr_unique_id = f"{DOMAIN}_maand_kwh"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:ev-station"

    @property
    def native_value(self):
        return round(sum(s["kwh"] for s in self._this_month()), 2)

    @property
    def extra_state_attributes(self):
        sessions = self._this_month()
        return {
            "sessies": len(sessions),
            "per_voertuig": self.log.per_voertuig(sessions),
            "per_dag": self.log.per_dag(sessions),
        }


class MonthCost(_Base):
    _attr_name = "Laadsessies kosten deze maand"
    _attr_unique_id = f"{DOMAIN}_maand_kosten"
    _attr_native_unit_of_measurement = "EUR"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:cash-multiple"

    @property
    def native_value(self):
        return round(sum(s["kosten"] for s in self._this_month()), 2)


def _sessie_kosten(t) -> float:
    """Kosten van de lopende sessie tot nu, inclusief het nog niet afgesloten kwartier."""
    cost = sum(r["kwh_vermogen"] * (r["prijs"] or 0) for r in t.session["kwartieren"])
    price = t._live_price(t.q_start) if t.q_start else None
    if price is None and t.timeline:
        price = t.timeline[-1][1]
    return cost + t.q_energy * (price or 0)


class ActiveSession(_Base):
    _attr_name = "Laadsessie actief"
    _attr_unique_id = f"{DOMAIN}_actief"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:car-electric"

    @property
    def native_value(self):
        t = self.log.tracker
        if not t.session:
            return 0
        return round(sum(r["kwh_vermogen"] for r in t.session["kwartieren"]) + t.q_energy, 2)

    @property
    def extra_state_attributes(self):
        t = self.log.tracker
        if not t.session:
            # Altijd een voertuig-attribuut, zodat de dashboardtegel "Voertuig" niet leeg blijft.
            return {"actief": False, "voertuig": "Geen"}
        return {
            "actief": True,
            "start": t.session["start"],
            "kosten_tot_nu": round(_sessie_kosten(t), 2),
            "kwartieren": len(t.session["kwartieren"]),
            "voertuig": t.voertuig,
        }


class ActiveSessionCost(_Base):
    _attr_name = "Laadsessie kosten"
    _attr_unique_id = f"{DOMAIN}_actief_kosten"
    _attr_native_unit_of_measurement = "EUR"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:cash-clock"

    @property
    def native_value(self):
        t = self.log.tracker
        return round(_sessie_kosten(t), 2) if t.session else 0


class Reports(_Base):
    _attr_name = "Laadrapporten"
    _attr_unique_id = f"{DOMAIN}_rapporten"
    _attr_icon = "mdi:file-pdf-box"
    # Ondertekende links zijn tijdelijk geldig en horen niet in de recorder-database.
    _unrecorded_attributes = frozenset({"rapporten", "vorige_maand_pdf"})

    @property
    def native_value(self):
        final = [r for r in self.log.reports if not r["voorlopig"]]
        return final[0]["maand"] if final else "geen"

    @property
    def extra_state_attributes(self):
        links = self.log.links
        rapporten = [
            {**r, "pdf": links.link(r["pdf"]), "csv": links.link(r["csv"]), "viewer": links.viewer(r["pdf"])}
            for r in self.log.reports
        ]
        attrs = {"rapporten": rapporten}
        if not self.log.conf.get(CONF_VOERTUIG):
            # Alleen zinvol zonder losse rapporten per voertuig; anders bestaat dit bestand niet.
            attrs["vorige_maand_pdf"] = links.link("laadrapport_vorige_maand.pdf")
        return attrs


class TariffStatus(_Base):
    _attr_unique_id = f"{DOMAIN}_tarief_status"
    _attr_icon = "mdi:cash-clock"

    def __init__(self, log) -> None:
        super().__init__(log)
        self._attr_name = f"{log.tariff_name} tarief status"

    @property
    def native_value(self):
        if not self.log.ready:
            return None
        st = self.hass.states.get(self.log.conf[CONF_TARIFF])
        try:
            float(st.state)
            live_ok = True
        except (AttributeError, TypeError, ValueError):
            live_ok = False
        return "storing" if self.log.tracker.outage or not live_ok else "ok"

    @property
    def extra_state_attributes(self):
        o = self.log.tracker.outage
        return {"sinds": o["sinds"], "kwartieren_terugval": o["kwartieren"]} if o else {}
