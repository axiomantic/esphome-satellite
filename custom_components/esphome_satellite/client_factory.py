"""Factory for instantiating Gatekeeper clients based on configuration."""
from __future__ import annotations

from typing import Union
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_GATEKEEPER_ENGINE,
    CONF_LLM_MODEL,
    CONF_LLM_TOKEN,
    CONF_LLM_URL,
    CONF_SYSTEMONE_TOKEN,
    CONF_SYSTEMONE_URL,
    CONF_TIMEOUT_SECONDS,
    DEFAULT_GATEKEEPER_ENGINE,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TOKEN,
    DEFAULT_LLM_URL,
    DEFAULT_SYSTEMONE_TOKEN,
    DEFAULT_SYSTEMONE_URL,
    DEFAULT_TIMEOUT,
    GATEKEEPER_ENGINE_LLM,
)
from .llm_client import GatekeeperLlmClient
from .systemone_client import SystemOneClient

GatekeeperClient = Union[GatekeeperLlmClient, SystemOneClient]


def create_gatekeeper_client(hass: HomeAssistant, entry: ConfigEntry) -> GatekeeperClient:
    """Create the appropriate Gatekeeper client based on config entry options/data."""
    options = entry.options
    data = entry.data

    engine = options.get(
        CONF_GATEKEEPER_ENGINE,
        data.get(CONF_GATEKEEPER_ENGINE, DEFAULT_GATEKEEPER_ENGINE),
    )

    timeout = options.get(
        CONF_TIMEOUT_SECONDS,
        data.get(CONF_TIMEOUT_SECONDS, DEFAULT_TIMEOUT),
    )

    if engine == GATEKEEPER_ENGINE_LLM:
        endpoint = options.get(
            CONF_LLM_URL,
            data.get(CONF_LLM_URL, DEFAULT_LLM_URL),
        )
        token = options.get(
            CONF_LLM_TOKEN,
            data.get(CONF_LLM_TOKEN, DEFAULT_LLM_TOKEN),
        )
        model = options.get(
            CONF_LLM_MODEL,
            data.get(CONF_LLM_MODEL, DEFAULT_LLM_MODEL),
        )
        return GatekeeperLlmClient(
            hass=hass,
            endpoint_url=endpoint,
            auth_token=token or None,
            model=model,
            timeout_seconds=timeout,
        )

    endpoint = options.get(
        CONF_SYSTEMONE_URL,
        data.get(CONF_SYSTEMONE_URL, DEFAULT_SYSTEMONE_URL),
    )
    token = options.get(
        CONF_SYSTEMONE_TOKEN,
        data.get(CONF_SYSTEMONE_TOKEN, DEFAULT_SYSTEMONE_TOKEN),
    )
    return SystemOneClient(
        hass=hass,
        endpoint_url=endpoint,
        auth_token=token or None,
        timeout_seconds=timeout,
    )
