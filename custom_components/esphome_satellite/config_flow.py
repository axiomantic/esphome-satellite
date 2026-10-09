"""Config flow for ESPHome Satellite Gatekeeper integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DEFAULT_THRESHOLD,
    CONF_DOWNSTREAM_AGENT,
    CONF_FALLBACK_BEHAVIOR,
    CONF_SLOT1_ENABLED,
    CONF_SLOT1_THRESHOLD,
    CONF_SLOT2_ENABLED,
    CONF_SLOT2_THRESHOLD,
    CONF_SYSTEMONE_TOKEN,
    CONF_SYSTEMONE_URL,
    CONF_TIMEOUT_SECONDS,
    DEFAULT_FALLBACK,
    DEFAULT_SYSTEMONE_TOKEN,
    DEFAULT_SYSTEMONE_URL,
    DEFAULT_THRESHOLD,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

class ESPHomeSatelliteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ESPHome Satellite Gatekeeper."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title="ESPHome Satellite Gatekeeper",
                data=user_input,
            )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_DOWNSTREAM_AGENT,
                    default="conversation.home_assistant",
                ): selector.ConversationAgentSelector(),
                vol.Required(
                    CONF_SYSTEMONE_URL,
                    default=DEFAULT_SYSTEMONE_URL,
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                ),
                vol.Optional(
                    CONF_SYSTEMONE_TOKEN,
                    default=DEFAULT_SYSTEMONE_TOKEN,
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_DEFAULT_THRESHOLD,
                    default=DEFAULT_THRESHOLD,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.10,
                        max=0.95,
                        step=0.01,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return ESPHomeSatelliteOptionsFlow()


class ESPHomeSatelliteOptionsFlow(config_entries.OptionsFlow):
    """Handle per-slot and operational options for the Gatekeeper."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        super().__init__()

    @property
    def config_entry(self) -> config_entries.ConfigEntry:
        """Return the config entry."""
        if self._config_entry is not None:
            return self._config_entry
        return super().config_entry

    async def async_step_init(self, user_input=None):
        """Manage the Gatekeeper options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_DOWNSTREAM_AGENT,
                    default=options.get(CONF_DOWNSTREAM_AGENT, data.get(CONF_DOWNSTREAM_AGENT, "conversation.home_assistant")),
                ): selector.ConversationAgentSelector(),
                vol.Required(
                    CONF_SYSTEMONE_URL,
                    default=options.get(CONF_SYSTEMONE_URL, data.get(CONF_SYSTEMONE_URL, DEFAULT_SYSTEMONE_URL)),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                ),
                vol.Optional(
                    CONF_SYSTEMONE_TOKEN,
                    description={"suggested_value": options.get(CONF_SYSTEMONE_TOKEN, data.get(CONF_SYSTEMONE_TOKEN, DEFAULT_SYSTEMONE_TOKEN))},
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_SLOT1_ENABLED,
                    default=options.get(CONF_SLOT1_ENABLED, True),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_SLOT1_THRESHOLD,
                    default=options.get(CONF_SLOT1_THRESHOLD, DEFAULT_THRESHOLD),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.10, max=0.95, step=0.01, mode=selector.NumberSelectorMode.SLIDER)
                ),
                vol.Required(
                    CONF_SLOT2_ENABLED,
                    default=options.get(CONF_SLOT2_ENABLED, True),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_SLOT2_THRESHOLD,
                    default=options.get(CONF_SLOT2_THRESHOLD, DEFAULT_THRESHOLD),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.10, max=0.95, step=0.01, mode=selector.NumberSelectorMode.SLIDER)
                ),
                vol.Required(
                    CONF_TIMEOUT_SECONDS,
                    default=options.get(CONF_TIMEOUT_SECONDS, data.get(CONF_TIMEOUT_SECONDS, DEFAULT_TIMEOUT)),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.5, max=10.0, step=0.1, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_FALLBACK_BEHAVIOR,
                    default=options.get(CONF_FALLBACK_BEHAVIOR, DEFAULT_FALLBACK),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"label": "Fail-Open (Allow Command)", "value": "allow"},
                            {"label": "Fail-Closed (Drop Command)", "value": "drop"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
