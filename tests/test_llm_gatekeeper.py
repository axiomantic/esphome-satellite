"""Unit and integration test suite for ESPHome Satellite Local LLM Gatekeeper."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure repo root is on sys.path for direct imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Mock homeassistant modules if not present in environment
if "voluptuous" not in sys.modules:
    sys.modules["voluptuous"] = MagicMock()

if "homeassistant" not in sys.modules:
    ha = MagicMock()
    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.core"] = MagicMock()
    sys.modules["homeassistant.core"].callback = lambda f: f
    sys.modules["homeassistant.config_entries"] = MagicMock()

    class MockOptionsFlow:
        def __init__(self):
            self.hass = None
            self.handler = None

        @property
        def config_entry(self):
            if self.hass is not None and hasattr(self.hass, "config_entries"):
                return self.hass.config_entries.async_get_known_entry(self.handler)
            raise ValueError("The config entry is not available during initialisation")

        def async_show_form(self, step_id=None, data_schema=None, errors=None):
            return {"type": "form", "step_id": step_id, "data_schema": data_schema, "errors": errors}

        def async_create_entry(self, title="", data=None):
            return {"type": "create_entry", "title": title, "data": data}

    class MockConfigFlow:
        def __init_subclass__(cls, domain=None, **kwargs):
            super().__init_subclass__(**kwargs)

    sys.modules["homeassistant.config_entries"].OptionsFlow = MockOptionsFlow
    sys.modules["homeassistant.config_entries"].ConfigFlow = MockConfigFlow
    sys.modules["homeassistant.const"] = MagicMock()
    sys.modules["homeassistant.helpers"] = MagicMock()
    sys.modules["homeassistant.helpers.aiohttp_client"] = MagicMock()
    sys.modules["homeassistant.helpers.entity_platform"] = MagicMock()
    sys.modules["homeassistant.helpers.intent"] = MagicMock()
    sys.modules["homeassistant.helpers.selector"] = MagicMock()
    sys.modules["homeassistant.components"] = MagicMock()
    sys.modules["homeassistant.components.conversation"] = MagicMock()
    ha.core = sys.modules["homeassistant.core"]
    ha.config_entries = sys.modules["homeassistant.config_entries"]
    ha.const = sys.modules["homeassistant.const"]
    ha.helpers = sys.modules["homeassistant.helpers"]
    ha.components = sys.modules["homeassistant.components"]
    ha.components.conversation = sys.modules["homeassistant.components.conversation"]

    class MockConversationEntity:
        _attr_has_entity_name = True
        _attr_name = "Gatekeeper"

    sys.modules["homeassistant.components.conversation"].ConversationEntity = MockConversationEntity

    class MockIntentResponse:
        def __init__(self, language=None):
            self.language = language
            self.speech = {}

        def async_set_speech(self, text, speech_type="plain"):
            self.speech["plain"] = {"speech": text}

    sys.modules["homeassistant.helpers.intent"].IntentResponse = MockIntentResponse
    sys.modules["homeassistant.helpers"].intent.IntentResponse = MockIntentResponse

    class MockConversationResult:
        def __init__(self, response, conversation_id=None, continue_conversation=False):
            self.response = response
            self.conversation_id = conversation_id
            self.continue_conversation = continue_conversation

    sys.modules["homeassistant.components.conversation"].ConversationResult = MockConversationResult

    from enum import Enum
    try:
        from enum import StrEnum
    except ImportError:
        class StrEnum(str, Enum):
            pass

    class MockAudioFormats(StrEnum):
        WAV = "wav"
        RAW = "raw"
        OGG = "ogg"

    class MockAudioCodecs(StrEnum):
        PCM = "pcm"
        OPUS = "opus"

    class MockAudioBitRates(int, Enum):
        BITRATE_16 = 16

    class MockAudioSampleRates(int, Enum):
        SAMPLERATE_16000 = 16000

    class MockAudioChannels(int, Enum):
        CHANNEL_MONO = 1

    class MockSpeechResultState(StrEnum):
        SUCCESS = "success"
        ERROR = "error"

    class MockSpeechMetadata:
        def __init__(
            self,
            language="en",
            format=MockAudioFormats.RAW,
            codec=MockAudioCodecs.PCM,
            bit_rate=MockAudioBitRates.BITRATE_16,
            sample_rate=MockAudioSampleRates.SAMPLERATE_16000,
            channel=MockAudioChannels.CHANNEL_MONO,
        ):
            self.language = language
            self.format = format
            self.codec = codec
            self.bit_rate = bit_rate
            self.sample_rate = sample_rate
            self.channel = channel

    class MockSpeechResult:
        def __init__(self, text, result):
            self.text = text
            self.result = result

    class MockSpeechToTextEntity:
        _attr_has_entity_name = True
        _attr_name = "STT"

    class MockSpeechAudioProcessing:
        def __init__(self, requires_external_vad=True, prefers_auto_gain_enabled=True, prefers_noise_reduction_enabled=True):
            self.requires_external_vad = requires_external_vad
            self.prefers_auto_gain_enabled = prefers_auto_gain_enabled
            self.prefers_noise_reduction_enabled = prefers_noise_reduction_enabled

    sys.modules["homeassistant.components.stt"] = MagicMock()
    sys.modules["homeassistant.components.stt"].AudioFormats = MockAudioFormats
    sys.modules["homeassistant.components.stt"].AudioCodecs = MockAudioCodecs
    sys.modules["homeassistant.components.stt"].AudioBitRates = MockAudioBitRates
    sys.modules["homeassistant.components.stt"].AudioSampleRates = MockAudioSampleRates
    sys.modules["homeassistant.components.stt"].AudioChannels = MockAudioChannels
    sys.modules["homeassistant.components.stt"].SpeechResultState = MockSpeechResultState
    sys.modules["homeassistant.components.stt"].SpeechMetadata = MockSpeechMetadata
    sys.modules["homeassistant.components.stt"].SpeechResult = MockSpeechResult
    sys.modules["homeassistant.components.stt"].SpeechToTextEntity = MockSpeechToTextEntity
    sys.modules["homeassistant.components.stt"].SpeechAudioProcessing = MockSpeechAudioProcessing

    def mock_get_stt_engine(hass, engine_id):
        if not hass or not hasattr(hass, "data"):
            return None
        stt_data = hass.data.get("stt")
        if hasattr(stt_data, "get_entity"):
            return stt_data.get_entity(engine_id)
        return None

    sys.modules["homeassistant.components.stt"].async_get_speech_to_text_engine = mock_get_stt_engine
    ha.components.stt = sys.modules["homeassistant.components.stt"]
    ha.const.Platform.CONVERSATION = "conversation"
    ha.const.Platform.STT = "stt"

if "aiohttp" not in sys.modules:
    aiohttp_mock = MagicMock()

    class MockClientTimeout:
        def __init__(self, total=None):
            self.total = total

    class MockClientError(Exception):
        pass

    aiohttp_mock.ClientTimeout = MockClientTimeout
    aiohttp_mock.ClientError = MockClientError
    sys.modules["aiohttp"] = aiohttp_mock

import aiohttp
from custom_components.esphome_satellite.const import (
    CHOICE_ADDRESSED,
    CHOICE_AMBIENT,
    CONF_DOWNSTREAM_AGENT,
    CONF_FALLBACK_BEHAVIOR,
    CONF_GATEKEEPER_ENGINE,
    CONF_LLM_MODEL,
    CONF_LLM_TOKEN,
    CONF_LLM_URL,
    CONF_SLOT1_ALIASES,
    CONF_SLOT2_ALIASES,
    CONF_SYSTEMONE_TOKEN,
    CONF_SYSTEMONE_URL,
    CONF_TIMEOUT_SECONDS,
    DEFAULT_FALLBACK,
    DEFAULT_GATEKEEPER_ENGINE,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TOKEN,
    DEFAULT_LLM_URL,
    GATEKEEPER_ENGINE_LLM,
    GATEKEEPER_ENGINE_SYSTEMONE,
    make_llm_followup_prompt,
    make_llm_initial_prompt,
)
from custom_components.esphome_satellite.client_factory import create_gatekeeper_client
from custom_components.esphome_satellite.conversation import ESPHomeSatelliteGatekeeperEntity
from custom_components.esphome_satellite.llm_client import (
    GatekeeperClientError,
    GatekeeperLlmClient,
    GatekeeperLlmClientError,
)
from custom_components.esphome_satellite.systemone_client import SystemOneClient


class TestGatekeeperLlmClient(unittest.IsolatedAsyncioTestCase):
    """Test suite for GatekeeperLlmClient."""

    def setUp(self):
        self.mock_hass = MagicMock()
        self.mock_session = MagicMock()

    def test_url_normalization(self):
        """URL normalization adds /v1/chat/completions correctly."""
        c1 = GatekeeperLlmClient(self.mock_hass, "http://localhost:8080")
        self.assertEqual(c1.endpoint_url, "http://localhost:8080/v1/chat/completions")

        c2 = GatekeeperLlmClient(self.mock_hass, "http://llm.local:8080/v1")
        self.assertEqual(c2.endpoint_url, "http://llm.local:8080/v1/chat/completions")

        c3 = GatekeeperLlmClient(self.mock_hass, "http://llm.local:8080/v1/")
        self.assertEqual(c3.endpoint_url, "http://llm.local:8080/v1/chat/completions")

        c4 = GatekeeperLlmClient(self.mock_hass, "http://llm.local:8080/v1/chat/completions")
        self.assertEqual(c4.endpoint_url, "http://llm.local:8080/v1/chat/completions")

    async def test_classify_empty_text(self):
        """Empty or whitespace text is immediately classified as ambient with zero network I/O."""
        client = GatekeeperLlmClient(self.mock_hass, "http://localhost:8080/v1")
        choice, conf, rtt = await client.classify_addressing("", target_wake_word="Clemens")
        self.assertEqual(choice, CHOICE_AMBIENT)
        self.assertEqual(conf, 1.0)
        self.assertEqual(rtt, 0.0)

        choice, conf, rtt = await client.classify_addressing("   \n\t  ", target_wake_word="Clemens")
        self.assertEqual(choice, CHOICE_AMBIENT)
        self.assertEqual(conf, 1.0)

    @patch("custom_components.esphome_satellite.llm_client.async_get_clientsession")
    async def test_classify_yes_addressed(self, mock_get_session):
        """Valid YES response from LLM classifies as CHOICE_ADDRESSED."""
        mock_get_session.return_value = self.mock_session
        client = GatekeeperLlmClient(
            self.mock_hass,
            "http://llm.local:8080/v1",
            auth_token="secret",
            model="llama-3.1-8b",
        )

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "choices": [{"message": {"content": "YES"}}]
        })
        self.mock_session.post.return_value.__aenter__.return_value = mock_resp

        choice, conf, rtt = await client.classify_addressing(
            "Clemens, what time is it?",
            target_wake_word="Clemens",
            phonetic_variants=["clemens", "clemons"],
        )

        self.assertEqual(choice, CHOICE_ADDRESSED)
        self.assertEqual(conf, 1.0)
        self.assertGreaterEqual(rtt, 0.0)

        # Verify POST payload and headers
        self.mock_session.post.assert_called_once()
        args, kwargs = self.mock_session.post.call_args
        self.assertEqual(args[0], "http://llm.local:8080/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(kwargs["json"]["model"], "llama-3.1-8b")
        self.assertEqual(kwargs["json"]["max_tokens"], 2)
        self.assertEqual(kwargs["json"]["temperature"], 0.0)

    @patch("custom_components.esphome_satellite.llm_client.async_get_clientsession")
    async def test_classify_no_ambient(self, mock_get_session):
        """Valid NO response from LLM classifies as CHOICE_AMBIENT."""
        mock_get_session.return_value = self.mock_session
        client = GatekeeperLlmClient(self.mock_hass, "http://llm.local:8080/v1")

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "choices": [{"message": {"content": "NO."}}]
        })
        self.mock_session.post.return_value.__aenter__.return_value = mock_resp

        choice, conf, rtt = await client.classify_addressing(
            "Patches should be allowed to run.",
            target_wake_word="Clemens",
        )

        self.assertEqual(choice, CHOICE_AMBIENT)
        self.assertEqual(conf, 0.0)

    @patch("custom_components.esphome_satellite.llm_client.async_get_clientsession")
    async def test_classify_http_error_raises(self, mock_get_session):
        """HTTP error raises GatekeeperLlmClientError."""
        mock_get_session.return_value = self.mock_session
        client = GatekeeperLlmClient(self.mock_hass, "http://llm.local:8080/v1")

        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="Internal Server Error")
        self.mock_session.post.return_value.__aenter__.return_value = mock_resp

        with self.assertRaises(GatekeeperLlmClientError):
            await client.classify_addressing("Turn on the lamp", target_wake_word="Clemens")

    @patch("custom_components.esphome_satellite.llm_client.async_get_clientsession")
    async def test_classify_timeout_raises(self, mock_get_session):
        """Timeout raises GatekeeperLlmClientError."""
        mock_get_session.return_value = self.mock_session
        client = GatekeeperLlmClient(self.mock_hass, "http://llm.local:8080/v1", timeout_seconds=0.1)

        self.mock_session.post.return_value.__aenter__.side_effect = TimeoutError()

        with self.assertRaises(GatekeeperLlmClientError):
            await client.classify_addressing("Turn on the lamp", target_wake_word="Clemens")

    def test_prompt_generation(self):
        """Test prompt formatting for initial and follow-up turns."""
        initial_prompt = make_llm_initial_prompt(
            "Clemens",
            ["clemens", "clemons", "clement"],
        )
        self.assertIn("Target assistant: Clemens", initial_prompt)
        self.assertIn("Phonetic variations: 'clemons', 'clement'", initial_prompt)
        self.assertIn("phonetic mis-dictations and homophones are the rule rather than the exception", initial_prompt)
        self.assertIn("not close to exhaustive", initial_prompt)
        self.assertIn("Use your judgment of phonetic pronunciations.", initial_prompt)
        self.assertIn("Output ONLY 'YES' or 'NO'.", initial_prompt)

        followup_prompt = make_llm_followup_prompt(
            "Clemens",
            prior_user_text="Hey JD Dance. You think of yourself as masculine?",
            prior_assistant_reply="A master? Hell no, I'm just a guy from Middletown.",
        )
        self.assertIn("The assistant 'Clemens' just spoke", followup_prompt)
        self.assertIn("No wake word is required on a follow-up turn", followup_prompt)
        self.assertIn("Recent conversation context:", followup_prompt)
        self.assertIn("You think of yourself as masculine?", followup_prompt)
        self.assertIn("A master? Hell no", followup_prompt)
        self.assertIn("profanity", followup_prompt)



class TestClientFactory(unittest.TestCase):
    """Test suite for create_gatekeeper_client factory."""

    def setUp(self):
        self.mock_hass = MagicMock()

    def test_factory_creates_llm_client(self):
        """Factory creates GatekeeperLlmClient when engine is llm."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_GATEKEEPER_ENGINE: GATEKEEPER_ENGINE_LLM,
            CONF_LLM_URL: "http://llm.local:8080/v1",
            CONF_LLM_TOKEN: "tok123",
            CONF_LLM_MODEL: "llama-3.1-8b",
            CONF_TIMEOUT_SECONDS: 2.0,
        }
        mock_entry.options = {}

        client = create_gatekeeper_client(self.mock_hass, mock_entry)
        self.assertIsInstance(client, GatekeeperLlmClient)
        self.assertEqual(client.endpoint_url, "http://llm.local:8080/v1/chat/completions")
        self.assertEqual(client.token, "tok123")
        self.assertEqual(client.model, "llama-3.1-8b")
        self.assertEqual(client.timeout, 2.0)

    def test_factory_creates_systemone_client(self):
        """Factory creates SystemOneClient when engine is systemone."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_GATEKEEPER_ENGINE: GATEKEEPER_ENGINE_SYSTEMONE,
            CONF_SYSTEMONE_URL: "http://system1.lan:8000/v1/systemone",
            CONF_SYSTEMONE_TOKEN: "sys1tok",
            CONF_TIMEOUT_SECONDS: 1.5,
        }
        mock_entry.options = {}

        client = create_gatekeeper_client(self.mock_hass, mock_entry)
        self.assertIsInstance(client, SystemOneClient)
        self.assertEqual(client.endpoint_url, "http://system1.lan:8000/v1/systemone")
        self.assertEqual(client.token, "sys1tok")
        self.assertEqual(client.timeout, 1.5)

    def test_factory_options_override_data(self):
        """Options override entry data in factory."""
        mock_entry = MagicMock()
        mock_entry.data = {
            CONF_GATEKEEPER_ENGINE: GATEKEEPER_ENGINE_SYSTEMONE,
            CONF_SYSTEMONE_URL: "http://old:8000",
        }
        mock_entry.options = {
            CONF_GATEKEEPER_ENGINE: GATEKEEPER_ENGINE_LLM,
            CONF_LLM_URL: "http://new:8080/v1",
            CONF_LLM_MODEL: "custom-model",
        }

        client = create_gatekeeper_client(self.mock_hass, mock_entry)
        self.assertIsInstance(client, GatekeeperLlmClient)
        self.assertEqual(client.endpoint_url, "http://new:8080/v1/chat/completions")
        self.assertEqual(client.model, "custom-model")


class TestGatekeeperConversationEntityWithLlm(unittest.IsolatedAsyncioTestCase):
    """Test suite for GatekeeperConversationEntity using GatekeeperLlmClient."""

    def setUp(self):
        self.mock_hass = MagicMock()
        self.mock_entry = MagicMock()
        self.mock_entry.entry_id = "test_entry_llm"
        self.mock_entry.data = {
            CONF_DOWNSTREAM_AGENT: "conversation.mock_downstream",
            CONF_GATEKEEPER_ENGINE: GATEKEEPER_ENGINE_LLM,
            CONF_LLM_URL: "http://llm.local:8080/v1",
            CONF_LLM_MODEL: "llama-3.1-8b",
            CONF_FALLBACK_BEHAVIOR: DEFAULT_FALLBACK,
        }
        self.mock_entry.options = {
            CONF_SLOT1_ALIASES: "clemens, clemons, clement",
            CONF_SLOT2_ALIASES: "jarvis, jay dee",
        }

        self.sat_state = MagicMock()
        self.sat_state.attributes = {"active_pipeline_index": 0, "wake_word": "clemens"}
        self.mock_hass.states.get.return_value = self.sat_state

    async def test_llm_addressed_passes_downstream(self):
        """When LLM returns CHOICE_ADDRESSED, utterance is passed to downstream agent."""
        mock_client = MagicMock()
        mock_client.classify_addressing = AsyncMock(return_value=(CHOICE_ADDRESSED, 1.0, 0.25))

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, self.mock_entry, mock_client)

        user_input = MagicMock()
        user_input.text = "Clemens, turn on the kitchen lights."
        user_input.satellite_id = "assist_satellite.twain"
        user_input.conversation_id = "conv_1"
        user_input.device_id = "device_twain"
        user_input.extra_system_prompt = None
        user_input.language = "en"
        user_input.context = MagicMock()

        downstream_mock = AsyncMock(return_value="allowed_result")
        with patch(
            "custom_components.esphome_satellite.conversation.conversation.async_converse",
            downstream_mock,
        ):
            result = await entity.async_process(user_input)

        self.assertEqual(result, "allowed_result")
        mock_client.classify_addressing.assert_called_once()
        downstream_mock.assert_called_once()

    async def test_llm_ambient_blocks_downstream(self):
        """When LLM returns CHOICE_AMBIENT, utterance is dropped and downstream is NOT called."""
        mock_client = MagicMock()
        mock_client.classify_addressing = AsyncMock(return_value=(CHOICE_AMBIENT, 0.0, 0.25))

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, self.mock_entry, mock_client)

        user_input = MagicMock()
        user_input.text = "Patches should be allowed to run."
        user_input.satellite_id = "assist_satellite.twain"
        user_input.conversation_id = "conv_1"
        user_input.device_id = "device_twain"
        user_input.language = "en"
        user_input.context = MagicMock()

        downstream_mock = AsyncMock()
        with patch(
            "custom_components.esphome_satellite.conversation.conversation.async_converse",
            downstream_mock,
        ):
            result = await entity.async_process(user_input)

        # Ambient dropped: conversation speech is empty and downstream not called
        self.assertEqual(result.response.speech.get("plain", {}).get("speech"), "")
        downstream_mock.assert_not_called()

    async def test_llm_error_fallback_allow(self):
        """When LLM raises GatekeeperClientError and fallback is allow, utterance passes."""
        mock_client = MagicMock()
        mock_client.classify_addressing = AsyncMock(side_effect=GatekeeperLlmClientError("HTTP 500"))

        self.mock_entry.options[CONF_FALLBACK_BEHAVIOR] = "allow"
        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, self.mock_entry, mock_client)

        user_input = MagicMock()
        user_input.text = "Clemens, turn on the lights"
        user_input.satellite_id = "assist_satellite.twain"
        user_input.conversation_id = "conv_1"
        user_input.device_id = "device_twain"
        user_input.language = "en"
        user_input.context = MagicMock()

        downstream_mock = AsyncMock(return_value="fallback_allowed")
        with patch(
            "custom_components.esphome_satellite.conversation.conversation.async_converse",
            downstream_mock,
        ):
            result = await entity.async_process(user_input)

        self.assertEqual(result, "fallback_allowed")
        downstream_mock.assert_called_once()

    async def test_llm_error_fallback_drop(self):
        """When LLM raises GatekeeperClientError and fallback is drop, utterance is dropped."""
        mock_client = MagicMock()
        mock_client.classify_addressing = AsyncMock(side_effect=GatekeeperLlmClientError("Network error"))

        self.mock_entry.options[CONF_FALLBACK_BEHAVIOR] = "drop"
        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, self.mock_entry, mock_client)

        user_input = MagicMock()
        user_input.text = "Clemens, turn on the lights"
        user_input.satellite_id = "assist_satellite.twain"
        user_input.conversation_id = "conv_1"
        user_input.device_id = "device_twain"
        user_input.language = "en"
        user_input.context = MagicMock()

        downstream_mock = AsyncMock()
        with patch(
            "custom_components.esphome_satellite.conversation.conversation.async_converse",
            downstream_mock,
        ):
            result = await entity.async_process(user_input)

        self.assertEqual(result.response.speech.get("plain", {}).get("speech"), "")
        downstream_mock.assert_not_called()

    async def test_speculative_stt_drains_preroll_queue_single_eval(self) -> None:
        """Verify 2.0s of pre-roll chunks queued at once are drained into a single STT call."""
        from custom_components.esphome_satellite.stt import ESPHomeSatelliteSpeculativeSTT

        entry = MagicMock()
        entry.entry_id = "test_drain"
        entry.title = "Mark Twain Gatekeeper"
        entry.options = {}
        entry.data = {}

        mock_client = MagicMock()
        mock_client.classify_addressing = AsyncMock(
            return_value=(CHOICE_ADDRESSED, 1.0, 50.0)
        )

        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass, entry, mock_client, speculative_chunk_ms=500
        )
        stt_proxy._resolve_active_satellite_context = MagicMock(
            return_value=("assist_satellite.twain", "Mr. Clemens")
        )
        stt_proxy._notify_satellite_verified = AsyncMock()
        stt_proxy._transcribe_partial_slice = AsyncMock(return_value="Mr. Clemens what time")

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        # Push 64 chunks of 1000 bytes (64,000 bytes = 2.0s pre-roll) + EOF before loop runs
        for _ in range(64):
            queue.put_nowait(b"\x01\x00" * 500)
        queue.put_nowait(b"")

        verified_event = asyncio.Event()
        metadata = MagicMock(sample_rate=16000, bit_rate=16, channel=1)

        await stt_proxy._speculative_verification_loop(
            metadata=metadata,
            queue=queue,
            verified_event=verified_event,
            downstream_entity=MagicMock(),
        )

        self.assertEqual(stt_proxy._transcribe_partial_slice.call_count, 1)
        call_kwargs = stt_proxy._transcribe_partial_slice.call_args.kwargs
        self.assertEqual(len(call_kwargs["pcm_data"]), 64000)
        self.assertTrue(verified_event.is_set())

    def test_deterministic_pipeline_slot_resolution(self) -> None:
        """Verify pipeline title matching overrides stale MAC-suffixed active_assistant_slot sensor in both STT and Conversation entities."""
        from custom_components.esphome_satellite.stt import ESPHomeSatelliteSpeculativeSTT

        entry = MagicMock()
        entry.entry_id = "slot2_entry"
        entry.title = "JD Vance Gatekeeper"
        entry.options = {}
        entry.data = {}

        sat_id = "assist_satellite.voice_satellite_46cbe8_assist_satellite"
        sat_state = MagicMock()
        sat_state.entity_id = sat_id
        sat_state.state = "listening"
        sat_state.last_updated = 100
        sat_state.attributes = {}

        stale_slot_sensor = MagicMock(
            entity_id="sensor.voice_satellite_46cbe8_active_assistant_slot",
            state="1.0",  # Stale Slot 1!
        )

        def async_all_side_effect(domain=None):
            if domain == "assist_satellite":
                return [sat_state]
            if domain == "sensor":
                return [stale_slot_sensor]
            return []

        self.mock_hass.states.async_all = MagicMock(side_effect=async_all_side_effect)

        state_map = {
            sat_id: sat_state,
            "sensor.voice_satellite_46cbe8_active_assistant_slot": stale_slot_sensor,
            "select.voice_satellite_46cbe8_assistant": MagicMock(state="Mark Twain"),
            "select.voice_satellite_46cbe8_assistant_2": MagicMock(state="JD Vance"),
            "select.voice_satellite_46cbe8_wake_word": MagicMock(state="Mr. Clemens"),
            "select.voice_satellite_46cbe8_wake_word_2": MagicMock(state="Hey Jay Dee Vance"),
        }
        self.mock_hass.states.get = MagicMock(side_effect=lambda eid: state_map.get(eid))

        dev_entries = [
            MagicMock(domain="sensor", entity_id="sensor.voice_satellite_46cbe8_active_assistant_slot"),
            MagicMock(domain="select", entity_id="select.voice_satellite_46cbe8_assistant"),
            MagicMock(domain="select", entity_id="select.voice_satellite_46cbe8_assistant_2"),
            MagicMock(domain="select", entity_id="select.voice_satellite_46cbe8_wake_word"),
            MagicMock(domain="select", entity_id="select.voice_satellite_46cbe8_wake_word_2"),
        ]
        mock_er = MagicMock()
        mock_er.async_get = MagicMock(return_value=MagicMock(device_id="dev_46cbe8"))
        mock_er.async_entries_for_device = MagicMock(return_value=dev_entries)

        with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_er):
            stt_proxy = ESPHomeSatelliteSpeculativeSTT(self.mock_hass, entry, MagicMock())
            resolved_sat_id, ww = stt_proxy._resolve_active_satellite_context()
            slot_idx = stt_proxy._resolve_active_slot_index(sat_id)

            conv_entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, entry, MagicMock())
            conv_slot_idx, conv_ww = conv_entity._resolve_satellite_context(sat_id)

        self.assertEqual(resolved_sat_id, sat_id)
        self.assertEqual(ww, "Hey Jay Dee Vance")
        self.assertEqual(slot_idx, 1)
        self.assertEqual(conv_slot_idx, 1)
        self.assertEqual(conv_ww, "Hey Jay Dee Vance")


if __name__ == "__main__":
    unittest.main()

