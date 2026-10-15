"""Speculative Streaming STT Proxy Entity for ESPHome Voice Satellites."""
from __future__ import annotations

import array
import asyncio
from collections.abc import AsyncGenerator, AsyncIterable
import io
import json
import logging
import math
from pathlib import Path
import re
import time
from typing import Final
import wave

from homeassistant.components.stt import (
    AudioBitRates,
    AudioChannels,
    AudioCodecs,
    AudioFormats,
    AudioSampleRates,
    SpeechAudioProcessing,
    SpeechMetadata,
    SpeechResult,
    SpeechResultState,
    SpeechToTextEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CHOICE_ADDRESSED,
    CONF_DEFAULT_THRESHOLD,
    CONF_DOWNSTREAM_STT,
    CONF_EARLY_WAKE_VERIFICATION,
    CONF_ENFORCE_WAKE_WORD,
    CONF_SLOT1_THRESHOLD,
    CONF_SLOT2_THRESHOLD,
    CONF_SPECULATIVE_CHUNK_MS,
    CONF_SYSTEMONE_TOKEN,
    CONF_SYSTEMONE_URL,
    CONF_TIMEOUT_SECONDS,
    DEFAULT_DOWNSTREAM_STT,
    DEFAULT_EARLY_WAKE_VERIFICATION,
    DEFAULT_ENFORCE_WAKE_WORD,
    DEFAULT_SPECULATIVE_CHUNK_MS,
    DEFAULT_SYSTEMONE_TOKEN,
    DEFAULT_SYSTEMONE_URL,
    DEFAULT_THRESHOLD,
    DEFAULT_TIMEOUT,
    DOMAIN,
    QUESTION_TEMPLATE_GENERAL,
    QUESTION_TEMPLATE_WAKE_VERIFICATION,
    make_wake_verification_criteria,
    CONF_SLOT1_ALIASES,
    CONF_SLOT2_ALIASES,
    expand_wake_phrase,
)
from .client_factory import create_gatekeeper_client, GatekeeperClient
from .systemone_client import GatekeeperClientError, SystemOneClientError

_LOGGER = logging.getLogger(__name__)

# Two-Phase Voice Activity & Silence Invariants
PRE_ROLL_DURATION_SECONDS: Final = 2.0                 # 2.0s pre-roll wake word buffer prepended by satellite
INITIAL_SPEECH_TIMEOUT_SECONDS: Final = 5.0            # Allow up to 5.0s post-wake pause once wake word is verified
UNVERIFIED_INITIAL_SPEECH_TIMEOUT_SECONDS: Final = 1.5 # Fast-abort unverified noise triggers after 1.5s of silence
END_OF_SPEECH_SILENCE_SECONDS: Final = 1.2             # Complete stream after 1.2s of post-speech silence
MAX_RECORDING_TIMEOUT_SECONDS: Final = 10.5            # Complete stream cleanly before 15s hardware watchdog
SPEECH_RMS_THRESHOLD: Final = 450.0                    # Voice activity threshold for 16-bit PCM



def pcm_to_wav(
    pcm_data: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wrap raw PCM bytes in a WAV header."""
    with io.BytesIO() as wav_io:
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        return wav_io.getvalue()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ESPHome Satellite Speculative STT entity from a config entry."""
    client = create_gatekeeper_client(hass, entry)
    async_add_entities([ESPHomeSatelliteSpeculativeSTT(hass, entry, client)])


class ESPHomeSatelliteSpeculativeSTT(SpeechToTextEntity):
    """STT proxy entity that performs speculative intent verification on live audio."""

    _attr_has_entity_name = True
    _attr_name = "Speculative STT Proxy"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GatekeeperClient,
        downstream_stt_id: str | None = None,
        speculative_chunk_ms: int | None = None,
        early_wake_verification: bool | None = None,
        enforce_wake_word: bool | None = None,
    ) -> None:
        """Initialize the speculative STT proxy."""
        self.hass = hass
        self._entry = entry
        self._client = client
        self._override_downstream_stt_id = downstream_stt_id
        self._override_speculative_chunk_ms = speculative_chunk_ms
        self._override_early_wake_verification = early_wake_verification
        self._override_enforce_wake_word = enforce_wake_word
        self._attr_unique_id = f"{entry.entry_id}_speculative_stt"
        domain_data = hass.data.setdefault(DOMAIN, {}) if isinstance(getattr(hass, "data", None), dict) else {}
        self._active_followup_convs: dict[str, float] = domain_data.setdefault("followup_convs", {})
        self._active_followup_satellites: dict[str, float] = domain_data.setdefault("followup_satellites", {})
        self._followup_sat_to_conv: dict[str, str] = domain_data.setdefault("followup_sat_to_conv", {})

    @property
    def downstream_stt_id(self) -> str:
        """Return configured downstream STT entity ID."""
        if self._override_downstream_stt_id is not None:
            return self._override_downstream_stt_id
        return self._entry.options.get(
            CONF_DOWNSTREAM_STT,
            self._entry.data.get(CONF_DOWNSTREAM_STT, DEFAULT_DOWNSTREAM_STT),
        )

    @property
    def speculative_chunk_ms(self) -> int:
        """Return speculative sliding evaluation window size in milliseconds."""
        if self._override_speculative_chunk_ms is not None:
            return self._override_speculative_chunk_ms
        return int(
            self._entry.options.get(
                CONF_SPECULATIVE_CHUNK_MS,
                self._entry.data.get(CONF_SPECULATIVE_CHUNK_MS, DEFAULT_SPECULATIVE_CHUNK_MS),
            )
        )

    @property
    def early_wake_verification(self) -> bool:
        """Return whether early wake verification signal is enabled."""
        if self._override_early_wake_verification is not None:
            return self._override_early_wake_verification
        return bool(
            self._entry.options.get(
                CONF_EARLY_WAKE_VERIFICATION,
                self._entry.data.get(
                    CONF_EARLY_WAKE_VERIFICATION, DEFAULT_EARLY_WAKE_VERIFICATION
                ),
            )
        )

    @property
    def enforce_wake_word(self) -> bool:
        """Return whether wake word enforcement is active."""
        if self._override_enforce_wake_word is not None:
            return self._override_enforce_wake_word
        return bool(
            self._entry.options.get(
                CONF_ENFORCE_WAKE_WORD,
                self._entry.data.get(CONF_ENFORCE_WAKE_WORD, DEFAULT_ENFORCE_WAKE_WORD),
            )
        )

    @property
    def audio_processing(self) -> SpeechAudioProcessing:
        """Return audio processing configuration.

        Disables external VAD so Home Assistant's VoiceCommandSegmenter does not cut off
        the audio stream during post-wake hesitation pauses before user speech starts.
        Two-phase VAD is handled directly by this entity.
        """
        return SpeechAudioProcessing(
            requires_external_vad=False,
            prefers_auto_gain_enabled=True,
            prefers_noise_reduction_enabled=True,
        )

    @property
    def supported_languages(self) -> list[str]:
        """Return supported languages, delegating to downstream STT if available."""
        downstream = self._get_downstream_entity()
        if downstream and hasattr(downstream, "supported_languages"):
            return downstream.supported_languages
        return ["en", "*"]

    @property
    def supported_formats(self) -> list[AudioFormats]:
        """Return supported audio formats."""
        downstream = self._get_downstream_entity()
        if downstream and hasattr(downstream, "supported_formats"):
            return downstream.supported_formats
        return [AudioFormats.WAV, AudioFormats.RAW]

    @property
    def supported_codecs(self) -> list[AudioCodecs]:
        """Return supported audio codecs."""
        downstream = self._get_downstream_entity()
        if downstream and hasattr(downstream, "supported_codecs"):
            return downstream.supported_codecs
        return [AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[AudioBitRates]:
        """Return supported audio bit rates."""
        downstream = self._get_downstream_entity()
        if downstream and hasattr(downstream, "supported_bit_rates"):
            return downstream.supported_bit_rates
        return [AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[AudioSampleRates]:
        """Return supported audio sample rates."""
        downstream = self._get_downstream_entity()
        if downstream and hasattr(downstream, "supported_sample_rates"):
            return downstream.supported_sample_rates
        return [AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[AudioChannels]:
        """Return supported audio channels."""
        downstream = self._get_downstream_entity()
        if downstream and hasattr(downstream, "supported_channels"):
            return downstream.supported_channels
        return [AudioChannels.CHANNEL_MONO]

    def _get_downstream_entity(self) -> SpeechToTextEntity | None:
        """Resolve the downstream STT entity from Home Assistant."""
        downstream_id = self.downstream_stt_id
        if not downstream_id:
            return None

        # 1. Try homeassistant.components.stt helper
        try:
            from homeassistant.components.stt import async_get_speech_to_text_engine

            engine = async_get_speech_to_text_engine(self.hass, downstream_id)
            if engine is not None and engine is not self:
                return engine
        except Exception:
            pass

        # 2. Try hass.data["stt"] or entity component
        stt_data = self.hass.data.get("stt")
        if hasattr(stt_data, "get_entity"):
            entity = stt_data.get_entity(downstream_id)
            if entity and entity is not self:
                return entity

        entity_comps = self.hass.data.get("entity_components", {})
        if "stt" in entity_comps:
            comp = entity_comps["stt"]
            if hasattr(comp, "get_entity"):
                entity = comp.get_entity(downstream_id)
                if entity and entity is not self:
                    return entity

        return None

    async def async_process_audio_stream(
        self,
        metadata: SpeechMetadata,
        stream: AsyncIterable[bytes],
    ) -> SpeechResult:
        """Tee incoming PCM stream into downstream STT and speculative sliding-window chunker."""
        downstream_entity = self._get_downstream_entity()
        if downstream_entity is None:
            _LOGGER.error(
                "[Speculative STT] Downstream STT entity '%s' not found",
                self.downstream_stt_id,
            )
            return SpeechResult(text=None, result=SpeechResultState.ERROR)

        sample_rate = getattr(metadata, "sample_rate", 16000)
        rate_hz = int(getattr(sample_rate, "value", sample_rate))
        bit_rate = getattr(metadata, "bit_rate", 16)
        bytes_per_sample = int(getattr(bit_rate, "value", bit_rate)) // 8
        channels = getattr(metadata, "channel", 1)
        num_channels = int(getattr(channels, "value", channels))
        bytes_per_sec = max(1, rate_hz * bytes_per_sample * num_channels)

        chunk_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        verified_event = asyncio.Event()
        unverified_abort_event = asyncio.Event()
        eval_state: dict[str, int | bool] = {"in_flight": False, "completed_count": 0}
        captured_chunks: list[bytes] = []

        # Step 1: Fork live generator into dual pipe with two-phase VAD silence gating
        async def _tee_audio_stream() -> AsyncGenerator[bytes, None]:
            in_speech = False
            initial_silence_elapsed = 0.0
            end_silence_elapsed = 0.0
            total_elapsed = 0.0
            speech_consec_chunks = 0

            try:
                stream_iter = aiter(stream)
                while True:
                    try:
                        chunk = await asyncio.wait_for(anext(stream_iter), timeout=2.5)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        _LOGGER.debug(
                            "[Speculative STT] Audio stream idle timeout (2.5s without chunks from satellite); closing stream"
                        )
                        break

                    if not chunk:
                        continue

                    captured_chunks.append(chunk)

                    chunk_sec = len(chunk) / bytes_per_sec
                    total_elapsed += chunk_sec
                    if total_elapsed >= MAX_RECORDING_TIMEOUT_SECONDS:
                        _LOGGER.info(
                            "[Speculative STT] Maximum recording duration (%.1fs) reached; terminating stream",
                            MAX_RECORDING_TIMEOUT_SECONDS,
                        )
                        break

                    # Only evaluate post-wake command VAD after the 2.0s pre-roll wake word buffer
                    if total_elapsed > PRE_ROLL_DURATION_SECONDS:
                        chunk_rms = self._calculate_pcm_rms(chunk)
                        is_speech = chunk_rms >= SPEECH_RMS_THRESHOLD

                        if not in_speech:
                            if is_speech:
                                speech_consec_chunks += 1
                                if speech_consec_chunks >= 3:
                                    in_speech = True
                                    _LOGGER.debug(
                                        "[Speculative STT] Voice command started after %.2fs post-wake pause (RMS=%.1f)",
                                        initial_silence_elapsed,
                                        chunk_rms,
                                    )
                            else:
                                speech_consec_chunks = 0
                                initial_silence_elapsed += chunk_sec
                                can_fast_abort_unverified = (
                                    self.early_wake_verification
                                    and not verified_event.is_set()
                                    and int(eval_state.get("completed_count", 0)) >= 1
                                    and not bool(eval_state.get("in_flight", False))
                                )
                                effective_initial_timeout = (
                                    UNVERIFIED_INITIAL_SPEECH_TIMEOUT_SECONDS
                                    if can_fast_abort_unverified
                                    else INITIAL_SPEECH_TIMEOUT_SECONDS
                                )
                                if initial_silence_elapsed >= effective_initial_timeout:
                                    if can_fast_abort_unverified:
                                        unverified_abort_event.set()
                                    _LOGGER.info(
                                        "[Speculative STT] Initial speech pause timeout (%.1fs, verified=%s) reached without speech; terminating stream",
                                        initial_silence_elapsed,
                                        verified_event.is_set(),
                                    )
                                    break
                        else:
                            if is_speech:
                                speech_consec_chunks += 1
                                if speech_consec_chunks >= 3:
                                    end_silence_elapsed = 0.0
                            else:
                                speech_consec_chunks = 0
                                end_silence_elapsed += chunk_sec
                                if end_silence_elapsed >= END_OF_SPEECH_SILENCE_SECONDS:
                                    _LOGGER.info(
                                        "[Speculative STT] End-of-speech silence (%.1fs) detected; completing stream",
                                        END_OF_SPEECH_SILENCE_SECONDS,
                                    )
                                    break

                    if not verified_event.is_set() and not chunk_queue.full():
                        chunk_queue.put_nowait(chunk)
                    yield chunk
            finally:
                try:
                    chunk_queue.put_nowait(b"")  # EOF sentinel
                except asyncio.QueueFull:
                    pass

        sat_id, target_ww = self._resolve_active_satellite_context()
        is_followup_stream = self._check_and_refresh_followup_start(sat_id)
        if is_followup_stream:
            verified_event.set()

        # Step 2: Spawn background speculative evaluation loop
        speculative_task = asyncio.create_task(
            self._speculative_verification_loop(
                metadata=metadata,
                queue=chunk_queue,
                verified_event=verified_event,
                downstream_entity=downstream_entity,
                eval_state=eval_state,
            )
        )

        # Step 3: Run downstream STT on primary stream and return verbatim result intact
        speech_result: SpeechResult | None = None
        downstream_task = asyncio.create_task(
            downstream_entity.async_process_audio_stream(
                metadata, _tee_audio_stream()
            )
        )
        abort_wait_task = asyncio.create_task(unverified_abort_event.wait())
        try:
            done, _ = await asyncio.wait(
                {downstream_task, abort_wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if abort_wait_task in done and unverified_abort_event.is_set():
                if not downstream_task.done():
                    downstream_task.cancel()
                    try:
                        await downstream_task
                    except (asyncio.CancelledError, Exception):
                        pass
                _LOGGER.info(
                    "[Speculative STT] Unverified silence timeout reached; fast-returning empty transcript to release satellite"
                )
                speech_result = SpeechResult(
                    text="",
                    result=SpeechResultState.SUCCESS,
                )
                return speech_result

            speech_result = await downstream_task
            return speech_result

        finally:
            if not abort_wait_task.done():
                abort_wait_task.cancel()
                try:
                    await abort_wait_task
                except asyncio.CancelledError:
                    pass
            if not downstream_task.done():
                downstream_task.cancel()
                try:
                    await downstream_task
                except (asyncio.CancelledError, Exception):
                    pass
            if not speculative_task.done():
                speculative_task.cancel()
                try:
                    await speculative_task
                except asyncio.CancelledError:
                    pass

            fresh_sat_id, fresh_ww = self._resolve_active_satellite_context()
            if fresh_sat_id:
                sat_id = fresh_sat_id
            if fresh_ww:
                target_ww = fresh_ww

            self._finalize_followup_stream(sat_id, is_followup_stream, speech_result)

            if captured_chunks:
                asyncio.create_task(
                    self._async_save_recorded_audio(
                        metadata=metadata,
                        audio_data=b"".join(captured_chunks),
                        satellite_id=sat_id,
                        wake_word=target_ww,
                        text=getattr(speech_result, "text", None) if speech_result else None,
                    )
                )

    def _get_satellite_fsm_state(self, satellite_id: str | None) -> str:
        """Return lowercase FSM state string from companion status_satellite_state sensor if available."""
        if not satellite_id or not hasattr(self.hass.states, "get"):
            return ""

        followup_states = {"follow up", "follow_up", "followup", "continuing"}
        sat_entity = self.hass.states.get(satellite_id)
        if sat_entity and isinstance(sat_entity.state, str) and sat_entity.state.strip().lower() in followup_states:
            return sat_entity.state.strip().lower()

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
                    if (
                        getattr(dev_entry, "domain", None) == "sensor"
                        and isinstance(getattr(dev_entry, "entity_id", None), str)
                        and "status_satellite_state" in dev_entry.entity_id
                    ):
                        st = self.hass.states.get(dev_entry.entity_id)
                        if st and isinstance(st.state, str) and st.state not in ("unknown", "unavailable"):
                            return st.state.strip().lower()
        except Exception:
            pass

        sat_part = satellite_id.split(".")[-1]
        base_part = re.sub(r"_voice_satellite$", "", sat_part)
        for cand_id in (
            f"sensor.{sat_part}_status_satellite_state",
            f"sensor.{base_part}_status_satellite_state",
        ):
            st = self.hass.states.get(cand_id)
            if st and isinstance(st.state, str) and st.state not in ("unknown", "unavailable"):
                return st.state.strip().lower()

        return ""

    def _check_and_refresh_followup_start(self, satellite_id: str | None) -> bool:
        """Detect if incoming STT stream is a follow-up turn and reset timer at TTS playback end."""
        if not satellite_id:
            return False

        followup_states = {"follow up", "follow_up", "followup", "continuing"}
        fsm_state = self._get_satellite_fsm_state(satellite_id)
        in_followup_dict = satellite_id in self._active_followup_satellites

        # If hardware explicitly woke from Idle on a wake word, it's a fresh initial turn
        if fsm_state in ("listening", "streaming speech verified", "woken"):
            if in_followup_dict:
                conv_id = self._followup_sat_to_conv.pop(satellite_id, None)
                self._active_followup_satellites.pop(satellite_id, None)
                if conv_id:
                    self._active_followup_convs.pop(conv_id, None)
            return False

        if fsm_state in followup_states or in_followup_dict:
            now = time.monotonic()
            self._active_followup_satellites[satellite_id] = now
            conv_id = self._followup_sat_to_conv.get(satellite_id)
            if conv_id:
                self._active_followup_convs[conv_id] = now
            _LOGGER.info(
                "[Speculative STT] Follow-up listening started on %s (conv=%s); timer started after TTS playback end",
                satellite_id,
                conv_id,
            )
            return True

        return False

    def _finalize_followup_stream(
        self,
        satellite_id: str | None,
        is_followup_stream: bool,
        speech_result: SpeechResult | None,
    ) -> None:
        """Refresh follow-up timer when follow-up speech completes, or clear if silent timeout."""
        if not satellite_id:
            return

        followup_states = {"follow up", "follow_up", "followup", "continuing"}
        fsm_state = self._get_satellite_fsm_state(satellite_id)
        if not (is_followup_stream or fsm_state in followup_states):
            return

        text = (getattr(speech_result, "text", None) or "").strip() if speech_result else ""
        conv_id = self._followup_sat_to_conv.get(satellite_id)
        if text:
            now = time.monotonic()
            self._active_followup_satellites[satellite_id] = now
            if conv_id:
                self._active_followup_convs[conv_id] = now
        else:
            self._active_followup_satellites.pop(satellite_id, None)
            self._followup_sat_to_conv.pop(satellite_id, None)
            if conv_id:
                self._active_followup_convs.pop(conv_id, None)

    async def _async_save_recorded_audio(
        self,
        metadata: SpeechMetadata,
        audio_data: bytes,
        satellite_id: str | None,
        wake_word: str | None,
        text: str | None,
    ) -> None:
        """Save captured microphone audio stream to disk as WAV and JSON metadata."""
        def _write_files() -> None:
            if hasattr(self.hass, "config") and hasattr(self.hass.config, "path"):
                rec_dir = Path(self.hass.config.path("www", "recordings"))
            else:
                rec_dir = Path("/tmp/recordings")

            rec_dir.mkdir(parents=True, exist_ok=True)

            ts_slug = time.strftime("%Y%m%d_%H%M%S")
            sat_clean = (satellite_id.split(".")[-1] if satellite_id else "unknown_sat").replace(" ", "_")
            ww_clean = (wake_word or "unknown_ww").replace(" ", "_").replace(".", "")
            base_name = f"{ts_slug}_{sat_clean}_{ww_clean}"

            wav_path = rec_dir / f"{base_name}.wav"
            json_path = rec_dir / f"{base_name}.json"

            sample_rate = getattr(metadata, "sample_rate", 16000)
            rate_hz = int(getattr(sample_rate, "value", sample_rate))
            bit_rate = getattr(metadata, "bit_rate", 16)
            bytes_per_sample = int(getattr(bit_rate, "value", bit_rate)) // 8
            channels = getattr(metadata, "channel", 1)
            num_channels = int(getattr(channels, "value", channels))

            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(num_channels)
                wf.setsampwidth(bytes_per_sample)
                wf.setframerate(rate_hz)
                wf.writeframes(audio_data)

            duration_sec = len(audio_data) / max(1, rate_hz * bytes_per_sample * num_channels)
            meta = {
                "timestamp": ts_slug,
                "satellite_id": satellite_id,
                "wake_word": wake_word,
                "duration_sec": round(duration_sec, 2),
                "sample_rate": rate_hz,
                "channels": num_channels,
                "bytes": len(audio_data),
                "text": text,
                "wav_file": f"{base_name}.wav",
                "wav_url": f"/local/recordings/{base_name}.wav",
            }
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(meta, jf, indent=2)

            _LOGGER.info(
                "[Speculative STT] Saved recorded audio (%.2fs) from %s to %s",
                duration_sec,
                satellite_id or "unknown",
                wav_path.name,
            )

            # Prune old recordings (keep last 50)
            try:
                wav_files = sorted(rec_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime)
                if len(wav_files) > 50:
                    for old_wav in wav_files[:-50]:
                        old_wav.unlink(missing_ok=True)
                        old_json = old_wav.with_suffix(".json")
                        old_json.unlink(missing_ok=True)
            except Exception as prune_err:
                _LOGGER.warning("[Speculative STT] Error pruning recordings: %s", prune_err)

        try:
            if hasattr(self.hass, "async_add_executor_job"):
                res = self.hass.async_add_executor_job(_write_files)
                if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                    await res
                else:
                    await asyncio.to_thread(_write_files)
            else:
                await asyncio.to_thread(_write_files)
        except Exception as err:
            _LOGGER.warning("[Speculative STT] Failed to save recorded audio: %s", err)

    def _resolve_active_satellite_context(self) -> tuple[str | None, str | None]:
        """Resolve the currently active assist_satellite entity ID and reported wake word.

        Extracts the exact wake phrase reported by the hardware wake circuit.
        Returns:
            tuple[satellite_entity_id, reported_wake_word]
        """
        if not hasattr(self.hass.states, "async_all"):
            return (None, None)

        try:
            # 1. Search for assist_satellite currently in active streaming/listening state
            active_states = [
                s for s in self.hass.states.async_all("assist_satellite")
                if s.state in ("listening", "recording", "streaming")
            ]
            if not active_states:
                all_sats = [
                    s for s in self.hass.states.async_all("assist_satellite")
                    if s.state not in ("unavailable", "unknown")
                ]
                if len(all_sats) == 1:
                    active_states = all_sats

            if not active_states:
                return (None, None)

            # Pick the most recently updated active satellite
            sat_state = max(active_states, key=lambda s: getattr(s, "last_updated", 0))
            sat_id = sat_state.entity_id

            # 2. Extract reported wake word from entity attributes
            wake_word = None
            if isinstance(getattr(sat_state, "attributes", None), dict):
                raw_ww = sat_state.attributes.get("wake_word")
                if isinstance(raw_ww, str) and raw_ww.strip():
                    wake_word = raw_ww.strip()
            if wake_word:
                return (sat_id, wake_word)

            # 3. Check active slot sensor and select entities via device registry linkage
            active_slot = sat_state.attributes.get("active_pipeline_index", 0)
            from homeassistant.helpers import entity_registry as er
            ent_reg = er.async_get(self.hass)
            entry = ent_reg.async_get(sat_id) if ent_reg else None
            device_id = entry.device_id if entry else None

            if device_id and ent_reg:
                dev_entries = []
                if hasattr(ent_reg, "async_entries_for_device") and callable(ent_reg.async_entries_for_device):
                    res = ent_reg.async_entries_for_device(device_id)
                    if isinstance(res, list):
                        dev_entries = res
                if not dev_entries and hasattr(er, "async_entries_for_device") and callable(er.async_entries_for_device):
                    try:
                        res = er.async_entries_for_device(ent_reg, device_id)
                        if isinstance(res, list):
                            dev_entries = res
                    except Exception:
                        pass

                for dev_entry in dev_entries:
                    if dev_entry.domain == "sensor" and "active_assistant_slot" in dev_entry.entity_id:
                        slot_state = self.hass.states.get(dev_entry.entity_id)
                        if slot_state and slot_state.state not in (None, "unknown", "unavailable"):
                            try:
                                active_slot = max(0, int(float(slot_state.state)) - 1)
                            except (ValueError, TypeError):
                                pass

                # If this config entry corresponds to a specific assistant pipeline selected on a slot,
                # prefer that slot deterministically to avoid Wi-Fi sensor update race conditions at t=0ms.
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
                                    break

                for dev_entry in dev_entries:
                    if dev_entry.domain == "select":
                        is_slot2 = "wake_word_2" in dev_entry.entity_id or "slot_2_wake_word" in dev_entry.entity_id
                        is_slot1 = ("wake_word" in dev_entry.entity_id and not is_slot2) or "slot_1_wake_word" in dev_entry.entity_id
                        if (active_slot == 1 and is_slot2) or (active_slot == 0 and is_slot1):
                            ww_state = self.hass.states.get(dev_entry.entity_id)
                            if ww_state and ww_state.state not in (None, "unknown", "unavailable", "no_wake_word"):
                                return (sat_id, str(ww_state.state).strip())

            return (sat_id, None)
        except Exception as err:
            _LOGGER.debug("[Speculative STT] Context resolution error: %s", err)
            return (None, None)

    def _resolve_active_slot_index(self, sat_id: str | None) -> int:
        """Resolve active slot index (0-indexed) for satellite."""
        if not sat_id or not hasattr(self.hass.states, "get"):
            return 0

        sat_state = self.hass.states.get(sat_id)
        active_slot = 0
        if sat_state and isinstance(getattr(sat_state, "attributes", None), dict):
            active_slot = sat_state.attributes.get("active_pipeline_index", 0)

        try:
            from homeassistant.helpers import entity_registry as er
            ent_reg = er.async_get(self.hass)
            entry = ent_reg.async_get(sat_id) if ent_reg else None
            device_id = entry.device_id if entry else None
            if device_id and ent_reg:
                dev_entries = []
                if hasattr(ent_reg, "async_entries_for_device") and callable(ent_reg.async_entries_for_device):
                    res = ent_reg.async_entries_for_device(device_id)
                    if isinstance(res, list):
                        dev_entries = res
                if not dev_entries and hasattr(er, "async_entries_for_device") and callable(er.async_entries_for_device):
                    try:
                        res = er.async_entries_for_device(ent_reg, device_id)
                        if isinstance(res, list):
                            dev_entries = res
                    except Exception:
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
                                    return 1 if is_slot2_pipe else 0

                for dev_entry in dev_entries:
                    if dev_entry.domain == "sensor" and "active_assistant_slot" in dev_entry.entity_id:
                        slot_state = self.hass.states.get(dev_entry.entity_id)
                        if slot_state and slot_state.state not in (None, "unknown", "unavailable"):
                            try:
                                return max(0, int(float(slot_state.state)) - 1)
                            except (ValueError, TypeError):
                                pass
        except Exception:
            pass

        return active_slot

    def _get_slot_threshold(self, slot_index: int = 0) -> float:
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

        if not raw:
            return []
        return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]

    async def _speculative_verification_loop(
        self,
        metadata: SpeechMetadata,
        queue: asyncio.Queue[bytes],
        verified_event: asyncio.Event,
        downstream_entity: SpeechToTextEntity,
        eval_state: dict[str, bool] | None = None,
    ) -> None:
        """Accumulate PCM audio chunks, transcribe sliding window, and query System 1."""
        pcm_accumulator = bytearray()

        sample_rate = getattr(metadata, "sample_rate", 16000)
        rate_hz = int(getattr(sample_rate, "value", sample_rate))
        bit_rate = getattr(metadata, "bit_rate", 16)
        bytes_per_sample = int(getattr(bit_rate, "value", bit_rate)) // 8
        channels = getattr(metadata, "channel", 1)
        num_channels = int(getattr(channels, "value", channels))

        bytes_per_second = rate_hz * bytes_per_sample * num_channels
        window_bytes = int(bytes_per_second * (self.speculative_chunk_ms / 1000.0))
        stride_bytes = int(bytes_per_second * 0.20)  # Re-evaluate every 200ms
        max_speculative_bytes = int(bytes_per_second * 4.5)  # Stop speculative partial STT after 4.5s
        last_eval_len = 0

        sat_id, target_wake_word = self._resolve_active_satellite_context()
        _LOGGER.debug(
            "[Speculative STT] Speculative verification started: sat_id=%s, target_wake_word=%s",
            sat_id,
            target_wake_word,
        )

        while True:
            try:
                chunk = await queue.get()
            except asyncio.CancelledError:
                break

            if not chunk:  # EOF sentinel
                break

            pcm_accumulator.extend(chunk)
            eof_seen = False
            while not queue.empty():
                try:
                    extra = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not extra:
                    eof_seen = True
                    break
                pcm_accumulator.extend(extra)

            # Evaluate when window threshold is met and satellite is not yet verified
            if (
                not verified_event.is_set()
                and len(pcm_accumulator) >= window_bytes
                and (len(pcm_accumulator) - last_eval_len) >= stride_bytes
                and len(pcm_accumulator) <= max_speculative_bytes
            ):
                last_eval_len = len(pcm_accumulator)
                if eval_state is not None:
                    eval_state["in_flight"] = True

                try:
                    # Dynamically re-resolve active satellite context on each evaluation stride
                    # to pick up slot transitions arriving over the network after audio stream initiation
                    fresh_sat_id, fresh_wake_word = self._resolve_active_satellite_context()
                    if fresh_wake_word:
                        target_wake_word = fresh_wake_word
                    if fresh_sat_id:
                        sat_id = fresh_sat_id

                    partial_text = await self._transcribe_partial_slice(
                        metadata=metadata,
                        pcm_data=bytes(pcm_accumulator),
                        downstream_entity=downstream_entity,
                        rate_hz=rate_hz,
                        channels=num_channels,
                        sample_width=bytes_per_sample,
                    )

                    if partial_text:
                        words = partial_text.strip().split()
                        target_words = target_wake_word.strip().split() if target_wake_word else []
                        min_words = min(2, len(target_words)) if target_words else 2
                        if len(words) < min_words:
                            if eof_seen:
                                break
                            continue

                        try:
                            active_slot = self._resolve_active_slot_index(sat_id)
                            threshold = self._get_slot_threshold(active_slot)
                            user_aliases = self._get_slot_user_aliases(active_slot)
                            all_aliases = expand_wake_phrase(target_wake_word, user_aliases) if target_wake_word else []

                            if target_wake_word:
                                question_text = QUESTION_TEMPLATE_WAKE_VERIFICATION.format(
                                    wake_word=target_wake_word
                                )
                                criteria = make_wake_verification_criteria(target_wake_word)
                            else:
                                question_text = QUESTION_TEMPLATE_GENERAL
                                criteria = None

                            choice, conf, rtt_ms = await self._client.classify_addressing(
                                text=partial_text,
                                question_text=question_text,
                                min_confidence=threshold,
                                criteria=criteria,
                                target_wake_word=target_wake_word,
                                phonetic_variants=all_aliases,
                                is_followup=False,
                            )
                            if choice in (CHOICE_ADDRESSED, "addressed") and conf >= threshold:
                                _LOGGER.info(
                                    "[Speculative STT] Phonetic wake verification confirmed for '%s' (conf=%.2f in %.1fms): '%s'",
                                    target_wake_word or "assistant",
                                    conf,
                                    rtt_ms,
                                    partial_text,
                                )
                                verified_event.set()
                                await self._notify_satellite_verified(sat_id)
                                break  # Terminate speculative loop once verified
                        except (GatekeeperClientError, Exception) as err:
                            _LOGGER.debug(
                                "[Speculative STT] Speculative classification check failed: %s",
                                err,
                            )
                finally:
                    if eval_state is not None:
                        eval_state["in_flight"] = False
                        eval_state["completed_count"] = int(eval_state.get("completed_count", 0)) + 1

            if eof_seen:
                break

    async def _transcribe_partial_slice(
        self,
        metadata: SpeechMetadata,
        pcm_data: bytes,
        downstream_entity: SpeechToTextEntity,
        rate_hz: int,
        channels: int,
        sample_width: int,
    ) -> str:
        """Transcribe a partial audio slice via the downstream STT engine."""
        async def _slice_generator() -> AsyncGenerator[bytes, None]:
            if getattr(metadata, "format", None) == AudioFormats.WAV:
                yield pcm_to_wav(pcm_data, rate_hz, channels, sample_width)
            else:
                yield pcm_data

        try:
            # Enforce 1.5s timeout on partial speculative transcription
            result = await asyncio.wait_for(
                downstream_entity.async_process_audio_stream(metadata, _slice_generator()),
                timeout=1.5,
            )
            if (
                result
                and result.result == SpeechResultState.SUCCESS
                and result.text
            ):
                return result.text.strip()
        except Exception as err:
            _LOGGER.debug("[Speculative STT] Partial slice transcription skipped: %s", err)

        return ""

    async def _notify_satellite_verified(self, satellite_id: str | None = None) -> None:
        """Signal ESPHome satellite that wake word / addressing was verified."""
        if not self.early_wake_verification:
            return

        candidates: list[str] = []
        if satellite_id:
            candidates.append(satellite_id)
        elif hasattr(self.hass.states, "async_all"):
            # Discover active assist_satellite entities in listening or streaming state
            try:
                for state in self.hass.states.async_all("assist_satellite"):
                    if state.state in ("listening", "recording", "streaming"):
                        candidates.append(state.entity_id)
            except Exception:
                pass

        notified = False
        for sat_id in candidates:
            if await self._notify_single_satellite(sat_id):
                notified = True

        if not notified:
            # Fallback: broadcast to any esphome.*_wake_word_verified services
            try:
                services = self.hass.services.async_services().get("esphome", {})
                for svc_name in services:
                    if svc_name.endswith("_wake_word_verified"):
                        await self.hass.services.async_call("esphome", svc_name, blocking=False)
                        _LOGGER.info(
                            "[Speculative STT] Broadcast wake_word_verified via %s", svc_name
                        )
            except Exception as err:
                _LOGGER.debug("[Speculative STT] Broadcast service call failed: %s", err)

    async def _notify_single_satellite(self, satellite_id: str) -> bool:
        """Notify a single satellite device via its esphome wake_word_verified service."""
        try:
            from homeassistant.helpers import entity_registry as er

            ent_reg = er.async_get(self.hass)
            entry = ent_reg.async_get(satellite_id)
            if not entry or not entry.config_entry_id:
                return False

            config_entry = self.hass.config_entries.async_get_entry(entry.config_entry_id)
            if not config_entry or config_entry.domain != "esphome":
                return False

            device_name = str(config_entry.data.get("device_name") or getattr(config_entry, "title", "")).lower()
            if not device_name:
                return False

            mac_match = re.search(r"([0-9a-fA-F]{6})", device_name) if isinstance(device_name, str) else None
            uid = getattr(entry, "unique_id", None)
            if not mac_match and isinstance(uid, str):
                clean_uid = uid.replace(":", "").lower()
                mac_match = re.search(r"([0-9a-fA-F]{6})", clean_uid)
            mac_suffix = mac_match.group(1).lower() if mac_match else ""

            services = self.hass.services.async_services().get("esphome", {})
            target_svc: str | None = None

            service_prefix = device_name.replace("-", "_")
            candidate = f"{service_prefix}_wake_word_verified"
            if (hasattr(self.hass.services, "has_service") and self.hass.services.has_service("esphome", candidate)) or candidate in services:
                target_svc = candidate
            elif mac_suffix:
                for svc in services:
                    if svc.endswith(f"_{mac_suffix}_wake_word_verified"):
                        target_svc = svc
                        break

            if not target_svc:
                for svc in services:
                    if svc.endswith("_wake_word_verified"):
                        target_svc = svc
                        break

            if target_svc:
                await self.hass.services.async_call("esphome", target_svc, blocking=False)
                _LOGGER.info(
                    "[Speculative STT] Successfully notified satellite %s via %s",
                    satellite_id,
                    target_svc,
                )
                return True
        except Exception as err:
            _LOGGER.debug(
                "[Speculative STT] Could not notify satellite %s: %s", satellite_id, err
            )
        return False

    @staticmethod
    def _calculate_pcm_rms(chunk: bytes) -> float:
        """Calculate Root Mean Square (RMS) amplitude for 16-bit PCM mono audio."""
        if not chunk or len(chunk) < 2:
            return 0.0
        try:
            samples = array.array("h")
            samples.frombytes(chunk)
            if not samples:
                return 0.0
            sum_sq = sum(s * s for s in samples)
            return math.sqrt(sum_sq / len(samples))
        except Exception:
            return 0.0

