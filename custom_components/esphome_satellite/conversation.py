"""Gatekeeper Conversation Entity for ESPHome Voice Satellites."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import conversation
from homeassistant.components.conversation import (
    ConversationEntity,
    ConversationInput,
    ConversationResult,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CHOICE_AMBIENT,
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
    DEFAULT_SYSTEMONE_TOKEN,
    DEFAULT_SYSTEMONE_URL,
    DEFAULT_THRESHOLD,
    DEFAULT_TIMEOUT,
    DOMAIN,
    QUESTION_TEMPLATE_CLEMENS,
    QUESTION_TEMPLATE_GENERAL,
)
from .systemone_client import SystemOneClient, SystemOneClientError

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ESPHome Satellite Gatekeeper entity from a config entry."""
    client = SystemOneClient(
        hass=hass,
        endpoint_url=entry.options.get(
            CONF_SYSTEMONE_URL, entry.data.get(CONF_SYSTEMONE_URL, DEFAULT_SYSTEMONE_URL)
        ),
        auth_token=entry.options.get(
            CONF_SYSTEMONE_TOKEN, entry.data.get(CONF_SYSTEMONE_TOKEN, DEFAULT_SYSTEMONE_TOKEN)
        ),
        timeout_seconds=entry.options.get(
            CONF_TIMEOUT_SECONDS, entry.data.get(CONF_TIMEOUT_SECONDS, DEFAULT_TIMEOUT)
        ),
    )

    async_add_entities([ESPHomeSatelliteGatekeeperEntity(hass, entry, client)])

class ESPHomeSatelliteGatekeeperEntity(ConversationEntity):
    """Conversation entity that guards downstream agents against ambient speech."""

    _attr_has_entity_name = True
    _attr_name = "Gatekeeper"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SystemOneClient,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_gatekeeper"

    @property
    def supported_languages(self) -> list[str]:
        """Return supported languages."""
        return ["en", "*"]

    async def async_process(self, user_input: ConversationInput) -> ConversationResult:
        """Process an incoming conversational turn with System 1 gating."""
        text = user_input.text.strip()
        satellite_id = getattr(user_input, "satellite_id", None)
        
        # Bypass gatekeeper for non-satellite inputs (e.g. text typed in dashboard)
        if not satellite_id:
            return await self._delegate_downstream(user_input)

        # Resolve satellite slot, wake word, and active threshold
        slot_index, wake_word = self._resolve_satellite_context(satellite_id)
        
        gate_enabled = self._is_slot_gate_enabled(slot_index)
        if not gate_enabled:
            _LOGGER.debug(
                "Gatekeeper disabled for satellite %s (Slot %d); passing through",
                satellite_id,
                slot_index + 1,
            )
            return await self._delegate_downstream(user_input)

        threshold = self._get_slot_threshold(slot_index)
        question_template = self._select_question_template(slot_index, wake_word)

        # Evaluate through System 1
        try:
            choice, confidence, rtt_ms = await self._client.classify_addressing(
                text=text,
                question_text=question_template,
                min_confidence=threshold,
            )
        except SystemOneClientError as err:
            fallback = self._entry.options.get(
                CONF_FALLBACK_BEHAVIOR,
                self._entry.data.get(CONF_FALLBACK_BEHAVIOR, "allow"),
            )
            if fallback == "drop":
                _LOGGER.warning(
                    "[Gatekeeper] System 1 unavailable (%s). Fail-closed: dropping utterance '%s'",
                    err,
                    text,
                )
                return self._create_silent_drop_result(user_input)
            
            _LOGGER.warning(
                "[Gatekeeper] System 1 unavailable (%s). Fail-open: passing to downstream agent",
                err,
            )
            return await self._delegate_downstream(user_input)

        # Intercept ambient conversation
        if choice == CHOICE_AMBIENT and confidence >= threshold:
            _LOGGER.info(
                "[Gatekeeper] INTERCEPTED ambient speech on satellite %s (Slot %d, wake='%s', conf=%.2f, rtt=%.1fms): '%s'",
                satellite_id,
                slot_index + 1,
                wake_word,
                confidence,
                rtt_ms,
                text,
            )
            return self._create_silent_drop_result(user_input)

        # Addressed utterance confirmed
        _LOGGER.info(
            "[Gatekeeper] APPROVED addressed utterance on satellite %s (Slot %d, conf=%.2f, rtt=%.1fms): '%s'",
            satellite_id,
            slot_index + 1,
            confidence,
            rtt_ms,
            text,
        )
        return await self._delegate_downstream(user_input)

    def _resolve_satellite_context(self, satellite_id: str) -> tuple[int, str]:
        """Extract active pipeline slot (0-indexed) and wake word from satellite entity."""
        # 1. Inspect assist_satellite entity state or attributes
        satellite_entity = self.hass.states.get(satellite_id)
        active_slot = 0
        wake_word = ""

        if satellite_entity:
            # Check internal or attribute active pipeline index
            active_slot = satellite_entity.attributes.get("active_pipeline_index", 0)
            wake_word = satellite_entity.attributes.get("wake_word", "")

        # 2. Check dedicated slot sensor if published
        slot_sensor_id = f"sensor.{satellite_id.split('.')[-1]}_active_assistant_slot"
        slot_sensor = self.hass.states.get(slot_sensor_id)
        if slot_sensor and slot_sensor.state not in (None, "unknown", "unavailable"):
            try:
                active_slot = max(0, int(float(slot_sensor.state)) - 1)
            except (ValueError, TypeError):
                pass

        return (active_slot, wake_word)

    def _select_question_template(self, slot_index: int, wake_word: str) -> str:
        """Select calibrated question template based on slot and wake word."""
        ww_lower = wake_word.lower()
        if "clemens" in ww_lower or slot_index == 0:
            return QUESTION_TEMPLATE_CLEMENS
        return QUESTION_TEMPLATE_GENERAL

    def _get_slot_threshold(self, slot_index: int) -> float:
        """Retrieve threshold for specific slot, inheriting default threshold if not overridden."""
        options = self._entry.options
        data = self._entry.data
        default_thresh = options.get(
            CONF_DEFAULT_THRESHOLD, data.get(CONF_DEFAULT_THRESHOLD, DEFAULT_THRESHOLD)
        )
        if slot_index == 0:
            return float(options.get(CONF_SLOT1_THRESHOLD, default_thresh))
        if slot_index == 1:
            return float(options.get(CONF_SLOT2_THRESHOLD, default_thresh))
        return float(default_thresh)

    def _is_slot_gate_enabled(self, slot_index: int) -> bool:
        """Check if gatekeeper is enabled for specific slot."""
        options = self._entry.options
        if slot_index == 0:
            return bool(options.get(CONF_SLOT1_ENABLED, True))
        if slot_index == 1:
            return bool(options.get(CONF_SLOT2_ENABLED, True))
        return True

    def _create_silent_drop_result(self, user_input: ConversationInput) -> ConversationResult:
        """Return an empty ConversationResult fulfilling the HA pipeline.py line 1803 silent-drop contract."""
        resp = intent.IntentResponse(language=user_input.language)
        resp.async_set_speech("")  # Empty speech payload triggers silent finish
        return ConversationResult(
            response=resp,
            conversation_id=user_input.conversation_id,
        )

    async def _delegate_downstream(self, user_input: ConversationInput) -> ConversationResult:
        """Delegate conversational turn to configured downstream conversation agent."""
        downstream_agent_id = self._entry.options.get(
            CONF_DOWNSTREAM_AGENT,
            self._entry.data.get(CONF_DOWNSTREAM_AGENT),
        )
        return await conversation.async_converse(
            hass=self.hass,
            text=user_input.text,
            conversation_id=user_input.conversation_id,
            context=user_input.context,
            language=user_input.language,
            agent_id=downstream_agent_id,
            device_id=user_input.device_id,
        )
