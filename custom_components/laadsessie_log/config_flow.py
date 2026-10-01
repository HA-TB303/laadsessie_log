"""Config flow voor Laadsessie log."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ADRES,
    CONF_DASHBOARD,
    CONF_DISCONNECTED,
    CONF_KENTEKEN,
    CONF_NAAM,
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
    TARIEF_INTERVAL_UREN,
)


def _schema(values: dict[str, Any]) -> vol.Schema:
    def suggested(key: str, default: Any = None) -> dict:
        value = values.get(key, default)
        return {"suggested_value": value} if value else {}

    sensor = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
    return vol.Schema(
        {
            vol.Required(CONF_POWER, description=suggested(CONF_POWER)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Required(CONF_STATUS, description=suggested(CONF_STATUS)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
            ),
            vol.Optional(CONF_SESSION_ENERGY, description=suggested(CONF_SESSION_ENERGY)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy")
            ),
            vol.Optional(CONF_VOERTUIG, description=suggested(CONF_VOERTUIG)): sensor,
            vol.Required(CONF_TARIFF, description=suggested(CONF_TARIFF)): sensor,
            vol.Required(
                CONF_TARIFF_NAME, default=values.get(CONF_TARIFF_NAME, DEFAULT_TARIFF_NAME)
            ): selector.TextSelector(),
            vol.Required(
                CONF_DISCONNECTED, default=values.get(CONF_DISCONNECTED, DEFAULT_DISCONNECTED)
            ): selector.TextSelector(),
            vol.Required(
                CONF_TARIEF_INTERVAL, default=values.get(CONF_TARIEF_INTERVAL, DEFAULT_TARIEF_INTERVAL)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(TARIEF_INTERVAL_UREN),
                    translation_key=CONF_TARIEF_INTERVAL,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_DASHBOARD, default=values.get(CONF_DASHBOARD, True)): selector.BooleanSelector(),
            vol.Optional(CONF_NAAM, description=suggested(CONF_NAAM)): selector.TextSelector(),
            vol.Optional(CONF_ADRES, description=suggested(CONF_ADRES)): selector.TextSelector(),
            vol.Optional(CONF_KENTEKEN, description=suggested(CONF_KENTEKEN)): selector.TextSelector(),
        }
    )


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data.setdefault(CONF_SESSION_ENERGY, "")
    data.setdefault(CONF_VOERTUIG, "")
    data.setdefault(CONF_NAAM, "")
    data.setdefault(CONF_ADRES, "")
    data.setdefault(CONF_KENTEKEN, "")
    return data


class LaadsessieLogConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Laadsessie log", data=_clean(user_input))
        return self.async_show_form(step_id="user", data_schema=_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return LaadsessieLogOptionsFlow()


class LaadsessieLogOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_clean(user_input))
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(current))
