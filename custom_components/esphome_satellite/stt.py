"""Speculative Streaming STT Proxy Entity for ESPHome Voice Satellites."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterable
import io
import logging
import re
import wave

from homeassistant.components.stt import (
    AudioBitRates,
    AudioChannels,
    AudioCodecs,
    AudioFormats,
    AudioSampleRates,
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
    CONF_SLOT1_PATTERNS,
    CONF_SLOT2_PATTERNS,
    CONF_SPECULATIVE_CHUNK_MS,
    CONF_SYSTEMONE_TOKEN,
    CONF_SYSTEMONE_URL,
    CONF_TIMEOUT_SECONDS,
    DEFAULT_DOWNSTREAM_STT,
    DEFAULT_EARLY_WAKE_VERIFICATION,
    DEFAULT_SPECULATIVE_CHUNK_MS,
    DEFAULT_SYSTEMONE_TOKEN,
    DEFAULT_SYSTEMONE_URL,
    DEFAULT_THRESHOLD,
    DEFAULT_TIMEOUT,
    QUESTION_TEMPLATE_GENERAL,
)
from .systemone_client import SystemOneClient, SystemOneClientError

_LOGGER = logging.getLogger(__name__)


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


def trim_wake_word(text: str, custom_patterns: list[re.Pattern] | None = None) -> str:
    """Trim wake word prefix from transcript if present, leaving the instruction.

    If the wake phrase is detected near the start of the utterance (allowing
    filler words like 'hey', 'um', 'please'), trims through the wake phrase
    and any leading delimiters. If no wake word is found or if trimming would
    result in an empty string, returns the original stripped text.
    """
    if not text:
        return ""

    patterns = custom_patterns or []
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            # Check if match occurs near the beginning (at most 1 leading word)
            prefix = text[: match.start()].strip()
            if len(prefix.split()) <= 1:
                remainder = text[match.end() :].lstrip(" ,;:.-!?")
                if remainder:
                    return remainder

    return text.strip()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ESPHome Satellite Speculative STT entity from a config entry."""
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

    async_add_entities([ESPHomeSatelliteSpeculativeSTT(hass, entry, client)])


class ESPHomeSatelliteSpeculativeSTT(SpeechToTextEntity):
    """STT proxy entity that performs speculative intent verification on live audio."""

    _attr_has_entity_name = True
    _attr_name = "Speculative STT Proxy"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SystemOneClient,
        downstream_stt_id: str | None = None,
        speculative_chunk_ms: int | None = None,
        early_wake_verification: bool | None = None,
    ) -> None:
        """Initialize the speculative STT proxy."""
        self.hass = hass
        self._entry = entry
        self._client = client
        self._override_downstream_stt_id = downstream_stt_id
        self._override_speculative_chunk_ms = speculative_chunk_ms
        self._override_early_wake_verification = early_wake_verification
        self._attr_unique_id = f"{entry.entry_id}_speculative_stt"

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

    def _get_active_wake_patterns(self) -> list[re.Pattern]:
        """Get compiled wake word regex patterns for trimming if user-configured."""
        patterns: list[re.Pattern] = []
        for key in (CONF_SLOT1_PATTERNS, CONF_SLOT2_PATTERNS):
            custom = self._entry.options.get(key, self._entry.data.get(key, ""))
            if custom:
                try:
                    patterns.append(re.compile(custom, re.IGNORECASE))
                except re.error:
                    pass
        return patterns

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

        chunk_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        verified_event = asyncio.Event()

        # Step 1: Fork live generator into dual pipe
        async def _tee_audio_stream() -> AsyncGenerator[bytes, None]:
            try:
                async for chunk in stream:
                    if not verified_event.is_set() and not chunk_queue.full():
                        chunk_queue.put_nowait(chunk)
                    yield chunk
            finally:
                try:
                    chunk_queue.put_nowait(b"")  # EOF sentinel
                except asyncio.QueueFull:
                    pass

        # Step 2: Spawn background speculative evaluation loop
        speculative_task = asyncio.create_task(
            self._speculative_verification_loop(
                metadata=metadata,
                queue=chunk_queue,
                verified_event=verified_event,
                downstream_entity=downstream_entity,
            )
        )

        # Step 3: Run downstream STT on primary stream
        try:
            downstream_result = await downstream_entity.async_process_audio_stream(
                metadata, _tee_audio_stream()
            )

            # Step 4: On speech end, trim transcript to post-wake phrase instruction
            if (
                downstream_result
                and downstream_result.result == SpeechResultState.SUCCESS
                and downstream_result.text
            ):
                patterns = self._get_active_wake_patterns()
                trimmed = trim_wake_word(downstream_result.text, patterns)
                _LOGGER.debug(
                    "[Speculative STT] Post-speech trimmed: '%s' -> '%s'",
                    downstream_result.text,
                    trimmed,
                )
                return SpeechResult(text=trimmed, result=SpeechResultState.SUCCESS)

            return downstream_result

        finally:
            if not speculative_task.done():
                speculative_task.cancel()
                try:
                    await speculative_task
                except asyncio.CancelledError:
                    pass

    async def _speculative_verification_loop(
        self,
        metadata: SpeechMetadata,
        queue: asyncio.Queue[bytes],
        verified_event: asyncio.Event,
        downstream_entity: SpeechToTextEntity,
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
        last_eval_len = 0

        while True:
            try:
                chunk = await queue.get()
            except asyncio.CancelledError:
                break

            if not chunk:  # EOF sentinel
                break

            pcm_accumulator.extend(chunk)

            # Evaluate when window threshold is met and satellite is not yet verified
            if (
                not verified_event.is_set()
                and len(pcm_accumulator) >= window_bytes
                and (len(pcm_accumulator) - last_eval_len) >= stride_bytes
            ):
                last_eval_len = len(pcm_accumulator)
                partial_text = await self._transcribe_partial_slice(
                    metadata=metadata,
                    pcm_data=bytes(pcm_accumulator),
                    downstream_entity=downstream_entity,
                    rate_hz=rate_hz,
                    channels=num_channels,
                    sample_width=bytes_per_sample,
                )

                if partial_text and len(partial_text.split()) >= 2:
                    try:
                        choice, conf, rtt_ms = await self._client.classify_addressing(
                            text=partial_text,
                            question_text=QUESTION_TEMPLATE_GENERAL,
                            min_confidence=0.80,
                        )
                        if choice in (CHOICE_ADDRESSED, "addressed") and conf >= 0.80:
                            _LOGGER.info(
                                "[Speculative STT] Early address confirmed by System 1 (conf=%.2f in %.1fms): '%s'",
                                conf,
                                rtt_ms,
                                partial_text,
                            )
                            verified_event.set()
                            await self._notify_satellite_verified()
                            break  # Terminate speculative loop once verified
                    except (SystemOneClientError, Exception) as err:
                        _LOGGER.debug(
                            "[Speculative STT] Speculative classification check failed: %s",
                            err,
                        )

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

            mac_match = re.search(r"([0-9a-fA-F]{6})", device_name)
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
