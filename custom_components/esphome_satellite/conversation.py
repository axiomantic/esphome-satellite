"""Gatekeeper Conversation Entity for ESPHome Voice Satellites."""
from __future__ import annotations

import logging
import re
import time
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
    CHOICE_ADDRESSED,
    CHOICE_AMBIENT,
    CONF_DEFAULT_THRESHOLD,
    CONF_DOWNSTREAM_AGENT,
    CONF_ENFORCE_WAKE_WORD,
    CONF_FALLBACK_BEHAVIOR,
    CONF_SLOT1_ALIASES,
    CONF_SLOT1_ENABLED,
    CONF_SLOT1_THRESHOLD,
    CONF_SLOT2_ALIASES,
    CONF_SLOT2_ENABLED,
    CONF_SLOT2_THRESHOLD,
    CONF_SYSTEMONE_TOKEN,
    CONF_SYSTEMONE_URL,
    CONF_TIMEOUT_SECONDS,
    DEFAULT_ENFORCE_WAKE_WORD,
    DEFAULT_FALLBACK,
    DEFAULT_SYSTEMONE_TOKEN,
    DEFAULT_SYSTEMONE_URL,
    DEFAULT_THRESHOLD,
    DEFAULT_TIMEOUT,
    DOMAIN,
    expand_wake_phrase,
    make_followup_prompt,
    make_initial_prompt,
)
from .systemone_client import SystemOneClient, SystemOneClientError

_LOGGER = logging.getLogger(__name__)


def extract_instruction_after_wake(text: str, patterns: list[re.Pattern]) -> str | None:
    """Return the instruction following the wake phrase, or None if only the wake phrase was spoken."""
    if not text:
        return None

    for pattern in patterns:
        match = pattern.search(text)
        if match:
            prefix = text[: match.start()].strip()
            if len(prefix.split()) <= 1:
                remainder = text[match.end() :].lstrip(" ,;:.-!?")
                return remainder if remainder else None

    return text.strip()


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
        self._active_followup_convs: dict[str, float] = {}
        self._active_followup_satellites: dict[str, float] = {}

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

        now = time.monotonic()
        conv_id = user_input.conversation_id
        is_followup = False
        if conv_id and conv_id in self._active_followup_convs:
            if (now - self._active_followup_convs[conv_id]) < 30.0:
                is_followup = True
            self._active_followup_convs.pop(conv_id, None)

        if not is_followup and satellite_id in self._active_followup_satellites:
            if (now - self._active_followup_satellites[satellite_id]) < 30.0:
                is_followup = True
            self._active_followup_satellites.pop(satellite_id, None)

        if not is_followup and satellite_id:
            sat_entity = self.hass.states.get(satellite_id)
            if sat_entity and sat_entity.state in ("follow_up", "followup", "continuing"):
                is_followup = True

        # Resolve satellite slot, wake word, and active threshold
        slot_index, wake_word = self._resolve_satellite_context(satellite_id)
        
        gate_enabled = self._is_slot_gate_enabled(slot_index)
        if not gate_enabled:
            _LOGGER.debug(
                "Gatekeeper disabled for satellite %s (Slot %d); passing through",
                satellite_id,
                slot_index + 1,
            )
            await self._notify_wake_word_verified(satellite_id)
            return await self._delegate_downstream(user_input)

        eval_text = text
        threshold = self._get_slot_threshold(slot_index)
        target_ww = self._get_slot_wake_word(slot_index, wake_word)
        user_aliases = self._get_slot_user_aliases(slot_index)
        all_aliases = expand_wake_phrase(target_ww, user_aliases)

        if is_followup:
            question_text, criteria = make_followup_prompt(target_ww)
        else:
            question_text, criteria = make_initial_prompt(target_ww, all_aliases)

        # Evaluate through System 1
        try:
            choice, confidence, rtt_ms = await self._client.classify_addressing(
                text=eval_text,
                question_text=question_text,
                min_confidence=threshold,
                criteria=criteria,
            )
        except SystemOneClientError as err:
            fallback = self._entry.options.get(
                CONF_FALLBACK_BEHAVIOR,
                self._entry.data.get(CONF_FALLBACK_BEHAVIOR, DEFAULT_FALLBACK),
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
            await self._notify_wake_word_verified(satellite_id)
            return await self._delegate_downstream(user_input)

        # Addressed utterance confirmed (Default-Drop / Fail-Closed)
        if choice in (CHOICE_ADDRESSED, "addressed") and confidence >= threshold:
            _LOGGER.info(
                "[Gatekeeper] APPROVED addressed utterance on satellite %s (Slot %d, is_followup=%s, conf=%.2f, rtt=%.1fms): '%s'",
                satellite_id,
                slot_index + 1,
                is_followup,
                confidence,
                rtt_ms,
                text,
            )
            await self._notify_wake_word_verified(satellite_id)

            # Check if user spoke ONLY the wake word and paused (Wake-and-Pause Mode)
            wake_words = target_ww.split() if target_ww else []
            words = text.split()
            if not is_followup and len(words) <= len(wake_words) + 1:
                _LOGGER.info(
                    "[Gatekeeper] Wake word prompt acknowledged on satellite %s (Slot %d, wake='%s'). Opening follow-up.",
                    satellite_id,
                    slot_index + 1,
                    target_ww,
                )
                if conv_id:
                    self._active_followup_convs[conv_id] = now
                self._active_followup_satellites[satellite_id] = now
                resp = intent.IntentResponse(language=user_input.language)
                resp.async_set_speech("Yes?")
                return ConversationResult(
                    response=resp,
                    conversation_id=user_input.conversation_id,
                    continue_conversation=True,
                )

            return await self._delegate_downstream(user_input)

        # Any utterance that is ambient, low-confidence, or abstained is silently dropped
        _LOGGER.info(
            "[Gatekeeper] INTERCEPTED non-addressed speech on satellite %s (Slot %d, wake='%s', choice='%s', conf=%.2f, rtt=%.1fms): '%s'",
            satellite_id,
            slot_index + 1,
            wake_word,
            choice,
            confidence,
            rtt_ms,
            text,
        )
        return self._create_silent_drop_result(user_input)

    def _is_wake_word_enforced(self) -> bool:
        """Check if wake word presence is required on the incoming transcript."""
        options = self._entry.options
        data = self._entry.data
        return bool(
            options.get(
                CONF_ENFORCE_WAKE_WORD,
                data.get(CONF_ENFORCE_WAKE_WORD, DEFAULT_ENFORCE_WAKE_WORD),
            )
        )

    def _get_slot_wake_word(self, slot_index: int, reported_wake_word: str) -> str:
        """Get the effective wake word label for the slot."""
        if reported_wake_word:
            return reported_wake_word
        return f"Assistant Slot {slot_index + 1}"


    async def _notify_wake_word_verified(self, satellite_id: str) -> None:
        """Signal the ESPHome satellite that wake word / addressing was verified."""
        try:
            from homeassistant.helpers import entity_registry as er
            ent_reg = er.async_get(self.hass)
            entry = ent_reg.async_get(satellite_id) if satellite_id else None

            services = self.hass.services.async_services().get("esphome", {})
            target_svc: str | None = None

            if entry and entry.config_entry_id:
                config_entry = self.hass.config_entries.async_get_entry(entry.config_entry_id)
                if config_entry and config_entry.domain == "esphome":
                    device_name = str(config_entry.data.get("device_name") or getattr(config_entry, "title", "")).lower()
                    mac_match = re.search(r"([0-9a-fA-F]{6})", device_name)
                    if not mac_match and entry.unique_id:
                        clean_uid = entry.unique_id.replace(":", "").lower()
                        mac_match = re.search(r"([0-9a-fA-F]{6})", clean_uid)
                    mac_suffix = mac_match.group(1).lower() if mac_match else ""

                    service_prefix = device_name.replace("-", "_")
                    candidate = f"{service_prefix}_wake_word_verified"
                    if candidate in services:
                        target_svc = candidate
                    elif mac_suffix:
                        for svc in services:
                            if svc.endswith(f"_{mac_suffix}_wake_word_verified"):
                                target_svc = svc
                                break

            # If target_svc was not found via config entry, check satellite_id string for MAC
            if not target_svc and satellite_id:
                mac_match = re.search(r"([0-9a-fA-F]{6})", satellite_id)
                if mac_match:
                    mac_suffix = mac_match.group(1).lower()
                    for svc in services:
                        if svc.endswith(f"_{mac_suffix}_wake_word_verified"):
                            target_svc = svc
                            break

            if target_svc:
                await self.hass.services.async_call("esphome", target_svc, blocking=False)
                _LOGGER.info(
                    "[Gatekeeper] Notified satellite %s via %s", satellite_id, target_svc
                )
            else:
                # Fallback broadcast to any registered wake_word_verified service
                for svc in services:
                    if svc.endswith("_wake_word_verified"):
                        await self.hass.services.async_call("esphome", svc, blocking=False)
                        _LOGGER.info(
                            "[Gatekeeper] Broadcast wake_word_verified via %s", svc
                        )
        except Exception as err:
            _LOGGER.debug("[Gatekeeper] Could not notify satellite %s: %s", satellite_id, err)

    def _resolve_satellite_context(self, satellite_id: str) -> tuple[int, str]:
        """Extract active pipeline slot (0-indexed) and wake word from satellite entity."""
        active_slot = 0
        wake_word = ""

        # 1. Inspect assist_satellite entity state or attributes
        satellite_entity = self.hass.states.get(satellite_id)
        if satellite_entity:
            active_slot = satellite_entity.attributes.get("active_pipeline_index", 0)
            wake_word = satellite_entity.attributes.get("wake_word", "")

        # 2. Check dedicated slot sensor via device registry linkage
        try:
            from homeassistant.helpers import entity_registry as er
            ent_reg = er.async_get(self.hass)
            entry = ent_reg.async_get(satellite_id)
            if entry and entry.device_id:
                dev_entries = []
                if hasattr(ent_reg, "async_entries_for_device") and callable(ent_reg.async_entries_for_device):
                    res = ent_reg.async_entries_for_device(entry.device_id)
                    if isinstance(res, list):
                        dev_entries = res
                if not dev_entries and hasattr(er, "async_entries_for_device") and callable(er.async_entries_for_device):
                    try:
                        res = er.async_entries_for_device(ent_reg, entry.device_id)
                        if isinstance(res, list):
                            dev_entries = res
                    except Exception:
                        pass

                for dev_entry in dev_entries:
                    if dev_entry.domain == "sensor" and "active_assistant_slot" in dev_entry.entity_id:
                        slot_sensor = self.hass.states.get(dev_entry.entity_id)
                        if slot_sensor and slot_sensor.state not in (None, "unknown", "unavailable"):
                            try:
                                active_slot = max(0, int(float(slot_sensor.state)) - 1)
                            except (ValueError, TypeError):
                                pass

                if not wake_word:
                    for dev_entry in dev_entries:
                        if dev_entry.domain == "select":
                            is_slot2 = "wake_word_2" in dev_entry.entity_id or "slot_2_wake_word" in dev_entry.entity_id
                            is_slot1 = ("wake_word" in dev_entry.entity_id and not is_slot2) or "slot_1_wake_word" in dev_entry.entity_id
                            if (active_slot == 1 and is_slot2) or (active_slot == 0 and is_slot1):
                                ww_state = self.hass.states.get(dev_entry.entity_id)
                                if ww_state and ww_state.state not in (None, "unknown", "unavailable", "no_wake_word"):
                                    wake_word = str(ww_state.state).strip()
                                    break
        except Exception as err:
            _LOGGER.debug("[Gatekeeper] Device-linked context lookup failed: %s", err)

        # 3. Fallback candidate checks by entity name or MAC suffix
        sat_part = satellite_id.split(".")[-1]
        slot_sensor_candidates = [
            f"sensor.{sat_part}_active_assistant_slot",
            f"sensor.{sat_part}_voice_active_assistant_slot",
        ]

        # Check for 6-character hex MAC suffix matching in sensor registry
        mac_match = re.search(r"([0-9a-fA-F]{6})", sat_part)
        if mac_match and hasattr(self.hass.states, "async_all"):
            mac_suffix = mac_match.group(1).lower()
            try:
                for state in self.hass.states.async_all("sensor"):
                    if mac_suffix in state.entity_id and "active_assistant_slot" in state.entity_id:
                        slot_sensor_candidates.append(state.entity_id)
                        break
            except Exception:
                pass

        for cand_id in slot_sensor_candidates:
            slot_sensor = self.hass.states.get(cand_id)
            if slot_sensor and slot_sensor.state not in (None, "unknown", "unavailable"):
                try:
                    active_slot = max(0, int(float(slot_sensor.state)) - 1)
                    break
                except (ValueError, TypeError):
                    pass

        return (active_slot, wake_word)

    def _get_slot_user_aliases(self, slot_index: int) -> list[str]:
        """Retrieve user-configured phonetic aliases for specific slot."""
        options = self._entry.options
        data = self._entry.data
        raw = ""
        if slot_index == 0:
            raw = options.get(CONF_SLOT1_ALIASES, data.get(CONF_SLOT1_ALIASES, ""))
            if not raw:
                raw = options.get("slot1_patterns", data.get("slot1_patterns", ""))
        elif slot_index == 1:
            raw = options.get(CONF_SLOT2_ALIASES, data.get(CONF_SLOT2_ALIASES, ""))
            if not raw:
                raw = options.get("slot2_patterns", data.get("slot2_patterns", ""))

        if isinstance(raw, list):
            return [str(s).strip() for s in raw if str(s).strip()]
        if isinstance(raw, str):
            return [s.strip() for s in raw.split(",") if s.strip()]
        return []

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
        satellite_id = getattr(user_input, "satellite_id", None)
        downstream_agent_id = self._entry.options.get(
            CONF_DOWNSTREAM_AGENT,
            self._entry.data.get(CONF_DOWNSTREAM_AGENT),
        )
        res = await conversation.async_converse(
            hass=self.hass,
            text=user_input.text,
            conversation_id=user_input.conversation_id,
            context=user_input.context,
            language=user_input.language,
            agent_id=downstream_agent_id,
            device_id=user_input.device_id,
        )
        if getattr(res, "continue_conversation", False):
            now = time.monotonic()
            conv_id = user_input.conversation_id or getattr(res, "conversation_id", None)
            if conv_id:
                self._active_followup_convs[conv_id] = now
            if satellite_id:
                self._active_followup_satellites[satellite_id] = now
            _LOGGER.info(
                "[Gatekeeper] Downstream agent requested continuous conversation. Registered follow-up for conv=%s, sat=%s",
                conv_id,
                satellite_id,
            )
        return res
