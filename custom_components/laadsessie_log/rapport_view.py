"""Rapporten (PDF/CSV) alleen aan ingelogde gebruikers serveren.

De rapporten staan buiten de www-map; /local/... is in Home Assistant voor iedereen
zonder inloggen bereikbaar. Gewone links in de browser sturen geen toegangstoken mee,
daarom krijgt het dashboard tijdelijk ondertekende links (authSig), net als HA zelf
doet voor camera- en mediabestanden.
"""
from __future__ import annotations

import os
import re
import time
from datetime import timedelta
from urllib.parse import quote

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, REPORT_URL, VIEWER_URL

# Alleen eigen rapportbestanden; geen punten of slashes in de naam, dus geen padtrucs.
_BESTAND_RE = re.compile(r"laadrapport_[a-z0-9_-]+\.(pdf|csv)")

LINK_GELDIG = timedelta(hours=2)
LINK_VERNIEUWEN = 3600  # seconden; ruim binnen LINK_GELDIG, de sensor ververst elke minuut


class RapportView(HomeAssistantView):
    url = REPORT_URL + "/{naam}"
    name = f"api:{DOMAIN}:rapport"
    requires_auth = True

    async def get(self, request: web.Request, naam: str) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        log = hass.data.get(DOMAIN)
        if log is None or not _BESTAND_RE.fullmatch(naam):
            raise web.HTTPNotFound
        pad = os.path.join(log.report_dir, naam)
        if not await hass.async_add_executor_job(os.path.isfile, pad):
            raise web.HTTPNotFound
        soort = "attachment" if naam.endswith(".csv") else "inline"
        return web.FileResponse(
            pad,
            headers={
                "Cache-Control": "private, no-store",
                "Content-Disposition": f'{soort}; filename="{naam}"',
                "X-Content-Type-Options": "nosniff",
            },
        )


class Ondertekenaar:
    """Ondertekende links met een cache, zodat de sensor niet elke minuut nieuwe links krijgt."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._cache: dict[str, tuple[str, float]] = {}

    @callback
    def link(self, naam: str, geldig: timedelta = LINK_GELDIG) -> str:
        nu = time.monotonic()
        sleutel = f"{naam}|{geldig.total_seconds()}"
        hit = self._cache.get(sleutel)
        if hit and nu - hit[1] < min(LINK_VERNIEUWEN, geldig.total_seconds() / 2):
            return hit[0]
        url = async_sign_path(self.hass, f"{REPORT_URL}/{naam}", geldig)
        self._cache[sleutel] = (url, nu)
        return url

    @callback
    def viewer(self, naam: str, geldig: timedelta = LINK_GELDIG) -> str:
        return f"{VIEWER_URL}?file={quote(self.link(naam, geldig), safe='')}"
