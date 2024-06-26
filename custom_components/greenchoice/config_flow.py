"""Config flow for Greenchoice Sensor integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode, SelectOptionDict

from . import GreenchoiceApi, GreenchoiceError, DEFAULT_SCAN_INTERVAL_MINUTES
from .const import (
    CONF_OVEREENKOMST_ID,
    CONFIGFLOW_VERSION,
    DOMAIN,
    CONF_METERSTAND_STROOM_ENABLED,
    CONF_METERSTAND_GAS_ENABLED,
    CONF_TARIEVEN_ENABLED,
    DEFAULT_METERSTAND_STROOM_ENABLED,
    DEFAULT_METERSTAND_GAS_ENABLED,
    DEFAULT_TARIEVEN_ENABLED,
)


class GreenchoiceFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for Greenchoice Sensor."""

    VERSION = CONFIGFLOW_VERSION

    data = None
    api = None

    @staticmethod
    @callback
    def async_get_options_flow(
            config_entry: ConfigEntry,
    ) -> GreenchoiceSensorOptionsFlowHandler:
        """Get the options flow for this handler."""
        return GreenchoiceSensorOptionsFlowHandler(config_entry)

    async def async_step_user(
            self, user_input=None, errors: dict[str, str] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""

        errors = {}
        if user_input is not None:
            try:
                api = GreenchoiceApi(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
                await self.hass.async_add_executor_job(api.login)
            except GreenchoiceError:
                errors["base"] = "login_failure"
            else:
                self.data = user_input
                self.data[CONF_OVEREENKOMST_ID] = None
                self.api = api
                return await self.async_step_setup_overeenkomst()

        schema = vol.Schema({
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_setup_overeenkomst(
            self,
            user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle setup flow Greenchoice sensor."""
        errors = {}

        if user_input is not None:
            self.data[CONF_OVEREENKOMST_ID] = user_input[CONF_OVEREENKOMST_ID]
            await self.async_set_unique_id(user_input[CONF_OVEREENKOMST_ID])
            self._abort_if_unique_id_configured()
            products = await self.hass.async_add_executor_job(self.api.get_products, int(user_input[CONF_OVEREENKOMST_ID]))
            self.data["has_power"] = products.has_power
            self.data["has_gas"] = products.has_gas
            default_options = {
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MINUTES,
                CONF_METERSTAND_STROOM_ENABLED: self.data["has_power"],
                CONF_METERSTAND_GAS_ENABLED: self.data["has_gas"],
                CONF_TARIEVEN_ENABLED: True,
            }
            return self.async_create_entry(title=f"Greenchoice ({user_input[CONF_OVEREENKOMST_ID]})", data=self.data, options=default_options)

        overeenkomsten = await self.hass.async_add_executor_job(self.api.get_overeenkomsten)
        options = list[SelectOptionDict]()

        existing_configurations = [int(config_entry.data[CONF_OVEREENKOMST_ID]) for config_entry in self.hass.config_entries.async_entries(self.handler)]

        for overeenkomst in overeenkomsten:
            if overeenkomst.overeenkomst_id in existing_configurations:
                continue
            options.append(SelectOptionDict(value=str(overeenkomst.overeenkomst_id), label=str(overeenkomst)))

        if not len(options):
            return self.async_abort(reason="no_available_contracts")

        schema = vol.Schema({
            vol.Required(CONF_OVEREENKOMST_ID): SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN))
        })
        return self.async_show_form(step_id="setup_overeenkomst", data_schema=schema, errors=errors)


class GreenchoiceSensorOptionsFlowHandler(OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Convert scan interval to integer
            options_data = {
                CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                CONF_METERSTAND_STROOM_ENABLED: user_input.get(CONF_METERSTAND_STROOM_ENABLED, False),
                CONF_METERSTAND_GAS_ENABLED: user_input.get(CONF_METERSTAND_GAS_ENABLED, False),
                CONF_TARIEVEN_ENABLED: user_input[CONF_TARIEVEN_ENABLED]
            }
            return self.async_create_entry(title="", data=options_data)

        options = list[SelectOptionDict]()
        options.append(SelectOptionDict(value="60", label="elk uur"))
        options.append(SelectOptionDict(value="1440", label="elke dag"))
        options.append(SelectOptionDict(value="10080", label="elke week"))

        schema = {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=str(self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES))
            ): SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST))
        }
        data = self.config_entry.data
        if data["has_power"]:
            schema[vol.Required(CONF_METERSTAND_STROOM_ENABLED, default=self.config_entry.options.get(CONF_METERSTAND_STROOM_ENABLED, DEFAULT_METERSTAND_STROOM_ENABLED))] = bool
        if data["has_gas"]:
            schema[vol.Required(CONF_METERSTAND_GAS_ENABLED, default=self.config_entry.options.get(CONF_METERSTAND_GAS_ENABLED, DEFAULT_METERSTAND_GAS_ENABLED))] = bool
        schema[vol.Required(CONF_TARIEVEN_ENABLED, default=self.config_entry.options.get(CONF_TARIEVEN_ENABLED, DEFAULT_TARIEVEN_ENABLED))] = bool

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
        )
