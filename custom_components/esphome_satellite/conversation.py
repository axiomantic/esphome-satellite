"""Gatekeeper Conversation Entity for ESPHome Voice Satellites."""
from __future__ import annotations

import difflib
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
from .client_factory import create_gatekeeper_client, GatekeeperClient
from .systemone_client import GatekeeperClientError, SystemOneClientError

_LOGGER = logging.getLogger(__name__)


def _normalize_phrase(phrase: str) -> str:
    """Normalize a phrase for robust wake phrase matching."""
    return " ".join(re.sub(r"[^\w\s]", "", phrase).lower().split())


def is_wake_and_pause_turn(text: str, target_ww: str, aliases: list[str] | None = None) -> bool:
    """Check if an utterance consists strictly of the wake phrase (or recognized alias/phonetic mis-dictation) without a trailing command."""
    clean_text = _normalize_phrase(text)
    if not clean_text:
        return False

    phrases_to_match: set[str] = set()
    raw_candidates = [target_ww]
    if aliases:
        raw_candidates.extend(aliases)

    greeting_prefixes = ("hey ", "hi ", "hello ", "ok ", "okay ")

    for raw in raw_candidates:
        clean = _normalize_phrase(raw)
        if not clean:
            continue
        phrases_to_match.add(clean)
        has_prefix = any(clean.startswith(p) for p in greeting_prefixes)
        if not has_prefix:
            for p in ("hey ", "hi ", "ok ", "hello "):
                phrases_to_match.add(f"{p}{clean}")
        else:
            for p in greeting_prefixes:
                if clean.startswith(p):
                    phrases_to_match.add(clean[len(p) :].strip())

    if clean_text in phrases_to_match:
        return True

    # Phonetic STT mis-dictation check for wake-and-pause turns already approved by Gatekeeper:
    # Only consider short utterances whose word count cannot hold a trailing command.
    words = clean_text.split()
    target_words = _normalize_phrase(target_ww).split() if target_ww else []
    max_wake_words = max(len(target_words) + 1, 4)
    if len(words) > max_wake_words:
        return False

    for cand in phrases_to_match:
        if not cand:
            continue
        if abs(len(words) - len(cand.split())) <= 1:
            if difflib.SequenceMatcher(None, clean_text, cand).ratio() >= 0.72:
                return True

    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ESPHome Satellite Gatekeeper entity from a config entry."""
    client = create_gatekeeper_client(hass, entry)
    async_add_entities([ESPHomeSatelliteGatekeeperEntity(hass, entry, client)])


class ESPHomeSatelliteGatekeeperEntity(ConversationEntity):
    """Conversation entity that guards downstream agents against ambient speech."""

    _attr_has_entity_name = True
    _attr_name = "Gatekeeper"
    _attr_supports_streaming = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GatekeeperClient,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_gatekeeper"
        domain_data = hass.data.setdefault(DOMAIN, {}) if isinstance(getattr(hass, "data", None), dict) else {}
        self._active_followup_convs: dict[str, float] = domain_data.setdefault("followup_convs", {})
        self._active_followup_satellites: dict[str, float] = domain_data.setdefault("followup_satellites", {})
        self._followup_sat_to_conv: dict[str, str] = domain_data.setdefault("followup_sat_to_conv", {})
        self._followup_turn_context: dict[str, tuple[str, str]] = domain_data.setdefault("followup_turn_context", {})
        self._verified_wake_transcripts: dict[str, tuple[str, float]] = domain_data.setdefault("verified_wake_transcripts", {})

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
        verified_wake_prefix = ""
        if satellite_id in self._verified_wake_transcripts:
            vw_entry = self._verified_wake_transcripts.pop(satellite_id, None)
            if isinstance(vw_entry, tuple) and len(vw_entry) == 2:
                vw_text, vw_ts = vw_entry
                if (now - float(vw_ts)) < 20.0 and isinstance(vw_text, str) and vw_text.strip():
                    verified_wake_prefix = vw_text.strip()

        is_followup = False
        if conv_id and conv_id in self._active_followup_convs:
            if (now - self._active_followup_convs[conv_id]) < 30.0:
                is_followup = True
            self._active_followup_convs.pop(conv_id, None)

        if satellite_id in self._active_followup_satellites:
            if not is_followup and (now - self._active_followup_satellites[satellite_id]) < 30.0:
                is_followup = True
            self._active_followup_satellites.pop(satellite_id, None)
            self._followup_sat_to_conv.pop(satellite_id, None)
        elif is_followup and satellite_id:
            self._followup_sat_to_conv.pop(satellite_id, None)

        if not is_followup and satellite_id and self._is_satellite_in_followup_state(satellite_id):
            is_followup = True

        prior_user_text = ""
        prior_assistant_reply = ""
        if conv_id and conv_id in self._followup_turn_context:
            ctx_pair = self._followup_turn_context.pop(conv_id, None)
            if is_followup and isinstance(ctx_pair, tuple) and len(ctx_pair) == 2:
                prior_user_text, prior_assistant_reply = str(ctx_pair[0]), str(ctx_pair[1])
        if satellite_id and satellite_id in self._followup_turn_context:
            ctx_pair = self._followup_turn_context.pop(satellite_id, None)
            if (
                is_followup
                and not prior_user_text
                and not prior_assistant_reply
                and isinstance(ctx_pair, tuple)
                and len(ctx_pair) == 2
            ):
                prior_user_text, prior_assistant_reply = str(ctx_pair[0]), str(ctx_pair[1])

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
            question_text, criteria = make_followup_prompt(
                target_ww,
                prior_user_text=prior_user_text,
                prior_assistant_reply=prior_assistant_reply,
            )
        else:
            question_text, criteria = make_initial_prompt(target_ww, all_aliases)

        # Evaluate through Gatekeeper engine (System 1 or LLM)
        try:
            classify_kwargs: dict[str, Any] = {
                "text": eval_text,
                "question_text": question_text,
                "min_confidence": threshold,
                "criteria": criteria,
                "target_wake_word": target_ww,
                "phonetic_variants": all_aliases,
                "is_followup": is_followup,
            }
            if is_followup and (prior_user_text or prior_assistant_reply):
                classify_kwargs["prior_user_text"] = prior_user_text
                classify_kwargs["prior_assistant_reply"] = prior_assistant_reply
            choice, confidence, rtt_ms = await self._client.classify_addressing(
                **classify_kwargs
            )
        except GatekeeperClientError as err:
            fallback = self._entry.options.get(
                CONF_FALLBACK_BEHAVIOR,
                self._entry.data.get(CONF_FALLBACK_BEHAVIOR, DEFAULT_FALLBACK),
            )
            if fallback == "drop":
                _LOGGER.warning(
                    "[Gatekeeper] Gatekeeper engine unavailable (%s). Fail-closed: dropping utterance '%s'",
                    err,
                    text,
                )
                return self._create_silent_drop_result(user_input)
            
            _LOGGER.warning(
                "[Gatekeeper] Gatekeeper engine unavailable (%s). Fail-open: passing to downstream agent",
                err,
            )
            await self._notify_wake_word_verified(satellite_id)
            return await self._delegate_downstream(user_input)

        if (
            not is_followup
            and verified_wake_prefix
            and (choice not in (CHOICE_ADDRESSED, "addressed") or confidence < threshold)
        ):
            canonical_prefix = target_ww.strip() if target_ww and target_ww.strip() else verified_wake_prefix
            combined_text = f"{canonical_prefix}, {eval_text}".strip()
            try:
                fb_choice, fb_conf, fb_rtt = await self._client.classify_addressing(
                    text=combined_text,
                    question_text=question_text,
                    min_confidence=threshold,
                    criteria=criteria,
                    target_wake_word=target_ww,
                    phonetic_variants=all_aliases,
                    is_followup=False,
                )
                rtt_ms += fb_rtt
                if fb_choice in (CHOICE_ADDRESSED, "addressed") and fb_conf >= threshold:
                    _LOGGER.info(
                        "[Gatekeeper] Verified pre-roll prefix ('%s' -> '%s') recovered full-stream STT drift on %s: '%s'",
                        verified_wake_prefix,
                        canonical_prefix,
                        satellite_id,
                        eval_text,
                    )
                    choice, confidence = fb_choice, fb_conf
            except GatekeeperClientError:
                pass

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
            if not is_followup and is_wake_and_pause_turn(text, target_ww, all_aliases):
                _LOGGER.info(
                    "[Gatekeeper] Wake word prompt acknowledged on satellite %s (Slot %d, wake='%s'). Opening follow-up.",
                    satellite_id,
                    slot_index + 1,
                    target_ww,
                )
                if conv_id:
                    self._active_followup_convs[conv_id] = now
                    self._followup_sat_to_conv[satellite_id] = conv_id
                    self._followup_turn_context[conv_id] = (text, "Yes?")
                self._active_followup_satellites[satellite_id] = now
                self._followup_turn_context[satellite_id] = (text, "Yes?")
                resp = intent.IntentResponse(language=user_input.language)
                resp.async_set_speech("Yes?")
                return ConversationResult(
                    response=resp,
                    conversation_id=user_input.conversation_id,
                    continue_conversation=True,
                )

            if is_followup and target_ww:
                try:
                    setattr(user_input, "_followup_wake_context", (target_ww, all_aliases))
                except Exception:
                    pass

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
        slot_resolved_by_pipeline = False

        # 1. Inspect assist_satellite entity state or attributes
        satellite_entity = self.hass.states.get(satellite_id)
        if satellite_entity:
            active_slot = satellite_entity.attributes.get("active_pipeline_index", 0)
            wake_word = satellite_entity.attributes.get("wake_word", "")

        # 2. Check dedicated slot sensor & pipeline select via device registry linkage
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

                entry_title = getattr(self._entry, "title", None)
                if isinstance(entry_title, str) and entry_title.strip():
                    title_lower = entry_title.strip().lower()
                    for dev_entry in dev_entries:
                        if dev_entry.domain == "select" and "assistant" in dev_entry.entity_id and "wake_word" not in dev_entry.entity_id:
                            sel_state = self.hass.states.get(dev_entry.entity_id)
                            if sel_state and isinstance(sel_state.state, str):
                                pipe_name = sel_state.state.strip().lower()
                                if pipe_name and pipe_name not in ("unknown", "unavailable", "preferred") and pipe_name in title_lower:
                                    is_slot2_pipe = dev_entry.entity_id.endswith("_2") or "slot_2" in dev_entry.entity_id
                                    active_slot = 1 if is_slot2_pipe else 0
                                    slot_resolved_by_pipeline = True
                                    break

                if not wake_word or slot_resolved_by_pipeline:
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

        # 3. Fallback candidate checks by entity name or MAC suffix (only if pipeline didn't deterministically resolve slot)
        if not slot_resolved_by_pipeline:
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

    def _is_satellite_in_followup_state(self, satellite_id: str | None) -> bool:
        """Check if satellite or its companion FSM status sensor is in Follow Up state."""
        if not satellite_id or not isinstance(satellite_id, str) or not hasattr(self.hass.states, "get"):
            return False

        followup_states = {"follow up", "follow_up", "followup", "continuing"}
        sat_entity = self.hass.states.get(satellite_id)
        if sat_entity and isinstance(sat_entity.state, str) and sat_entity.state.strip().lower() in followup_states:
            return True

        try:
            from homeassistant.helpers import entity_registry as er
            ent_reg = er.async_get(self.hass)
            entry = ent_reg.async_get(satellite_id) if ent_reg else None
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
                    if dev_entry.domain == "sensor" and "status_satellite_state" in dev_entry.entity_id:
                        st = self.hass.states.get(dev_entry.entity_id)
                        if st and isinstance(st.state, str) and st.state.strip().lower() in followup_states:
                            return True
        except Exception:
            pass

        sat_part = satellite_id.split(".")[-1]
        base_part = re.sub(r"_voice_satellite$", "", sat_part)
        for cand_id in (
            f"sensor.{sat_part}_status_satellite_state",
            f"sensor.{base_part}_status_satellite_state",
        ):
            st = self.hass.states.get(cand_id)
            if st and isinstance(st.state, str) and st.state.strip().lower() in followup_states:
                return True

        return False

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
        downstream_text = user_input.text
        fu_ctx = getattr(user_input, "_followup_wake_context", None)
        if (
            isinstance(fu_ctx, tuple)
            and len(fu_ctx) == 2
            and isinstance(fu_ctx[0], str)
            and fu_ctx[0].strip()
            and not fu_ctx[0].startswith("Assistant Slot ")
            and isinstance(downstream_text, str)
            and downstream_text.strip()
        ):
            target_ww, all_aliases = fu_ctx
            norm_text = re.sub(r"[^a-z0-9\s]", "", downstream_text.lower())
            candidates = [target_ww, *(all_aliases if isinstance(all_aliases, list) else [])]
            has_wake = any(
                c_norm and c_norm in norm_text
                for c in candidates
                if isinstance(c, str)
                for c_norm in [re.sub(r"[^a-z0-9\s]", "", c.lower()).strip()]
            )
            if not has_wake:
                downstream_text = f"{target_ww}, {downstream_text}"

        res = await conversation.async_converse(
            hass=self.hass,
            text=downstream_text,
            conversation_id=user_input.conversation_id,
            context=user_input.context,
            language=user_input.language,
            agent_id=downstream_agent_id,
            device_id=user_input.device_id,
        )
        now = time.monotonic()
        conv_id = user_input.conversation_id or getattr(res, "conversation_id", None)
        has_tts_speech = True
        reply_speech_str = ""
        resp_obj = getattr(res, "response", None)
        if resp_obj is not None:
            speech_dict = getattr(resp_obj, "speech", None)
            if isinstance(speech_dict, dict):
                plain_speech = speech_dict.get("plain")
                speech_text = plain_speech.get("speech", "") if isinstance(plain_speech, dict) else ""
                reply_speech_str = str(speech_text).strip()
                has_tts_speech = bool(reply_speech_str)

        if has_tts_speech:
            turn_ctx = (str(user_input.text or "").strip(), reply_speech_str)
            if conv_id:
                self._active_followup_convs[conv_id] = now
                self._followup_turn_context[conv_id] = turn_ctx
            if satellite_id:
                self._active_followup_satellites[satellite_id] = now
                self._followup_turn_context[satellite_id] = turn_ctx
                if conv_id:
                    self._followup_sat_to_conv[satellite_id] = conv_id
            _LOGGER.info(
                "[Gatekeeper] Registered follow-up window for conv=%s, sat=%s",
                conv_id,
                satellite_id,
            )
        else:
            if conv_id:
                self._active_followup_convs.pop(conv_id, None)
                self._followup_turn_context.pop(conv_id, None)
            if satellite_id:
                self._active_followup_satellites.pop(satellite_id, None)
                self._followup_sat_to_conv.pop(satellite_id, None)
                self._followup_turn_context.pop(satellite_id, None)
            _LOGGER.info(
                "[Gatekeeper] Downstream returned no TTS speech for conv=%s, sat=%s; skipping follow-up window",
                conv_id,
                satellite_id,
            )
        return res

