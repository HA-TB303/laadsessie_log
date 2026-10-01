"""Invulbare gegevens voor het laadrapport (naam, kenteken, adres laadpaal)."""
from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_UPDATE
from .sensor import device_info

FIELDS = {
    "naam": ("Laadrapport naam", "mdi:account"),
    "kenteken": ("Laadrapport kenteken", "mdi:car"),
    "adres": ("Laadrapport adres laadpaal", "mdi:home-map-marker"),
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    log = entry.runtime_data
    async_add_entities([ReportDetail(log, key) for key in FIELDS])


class ReportDetail(TextEntity):
    _attr_should_poll = False
    _attr_native_max = 100

    def __init__(self, log, key: str) -> None:
        self.log = log
        self._attr_device_info = device_info(log.entry)
        self.key = key
        self._attr_name, self._attr_icon = FIELDS[key]
        self._attr_unique_id = f"{DOMAIN}_{key}"

    @property
    def native_value(self) -> str:
        return self.log.details.get(self.key, "")

    async def async_set_value(self, value: str) -> None:
        await self.log.async_set_detail(self.key, value)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()
