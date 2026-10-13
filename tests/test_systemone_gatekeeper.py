"""Unit and adversarial test suite for ESPHome Satellite SystemOne Gatekeeper."""
from __future__ import annotations

import asyncio
from pathlib import Path
import re
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
        """Mock HA OptionsFlow with config_entry property that has no setter."""
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
        """Mock base conversation entity."""
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

from custom_components.esphome_satellite.const import (
    CHOICE_ADDRESSED,
    CHOICE_AMBIENT,
    CLASSIFICATION_CRITERIA,
    CONF_DEFAULT_THRESHOLD,
    CONF_DOWNSTREAM_AGENT,
    CONF_DOWNSTREAM_STT,
    CONF_EARLY_WAKE_VERIFICATION,
    CONF_ENFORCE_WAKE_WORD,
    CONF_FALLBACK_BEHAVIOR,
    CONF_SLOT1_ENABLED,
    CONF_SLOT1_PATTERNS,
    CONF_SLOT1_THRESHOLD,
    CONF_SLOT2_ENABLED,
    CONF_SLOT2_PATTERNS,
    CONF_SLOT2_THRESHOLD,
    CONF_SPECULATIVE_CHUNK_MS,
    CONF_SYSTEMONE_TOKEN,
    CONF_SYSTEMONE_URL,
    DEFAULT_DOWNSTREAM_STT,
    DEFAULT_EARLY_WAKE_VERIFICATION,
    DEFAULT_SPECULATIVE_CHUNK_MS,
    DEFAULT_THRESHOLD,
    QUESTION_TEMPLATE_GENERAL,
    QUESTION_TEMPLATE_SLOT1,
)
from custom_components.esphome_satellite.conversation import ESPHomeSatelliteGatekeeperEntity
from custom_components.esphome_satellite.stt import (
    ESPHomeSatelliteSpeculativeSTT,
    pcm_to_wav,
)
from custom_components.esphome_satellite.systemone_client import (
    SystemOneClient,
    SystemOneClientError,
)


class TestSystemOneGatekeeper(unittest.IsolatedAsyncioTestCase):
    """Test suite for SystemOneClient and ESPHomeSatelliteGatekeeperEntity."""

    def setUp(self):
        self.mock_hass = MagicMock()
        self.mock_hass.states = MagicMock()

    async def test_systemone_client_empty_text(self):
        """Empty or whitespace text is immediately classified as ambient with zero network I/O."""
        client = SystemOneClient(self.mock_hass, "http://localhost:8000/v1/systemone")
        choice, conf, rtt = await client.classify_addressing("", "question")
        self.assertEqual(choice, CHOICE_AMBIENT)
        self.assertEqual(conf, 1.0)
        self.assertEqual(rtt, 0.0)

        choice, conf, rtt = await client.classify_addressing("   \n\t  ", "question")
        self.assertEqual(choice, CHOICE_AMBIENT)
        self.assertEqual(conf, 1.0)

    async def test_systemone_client_laya_criteria_payload(self):
        """Verify request payload uses Laya 'criteria' schema per emergent design addendum."""
        client = SystemOneClient(
            self.mock_hass,
            "http://flanopticon.lan:8000/v1/systemone",
            auth_token="test_token_123",
            timeout_seconds=2.0,
        )

        captured_payload = {}
        captured_headers = {}

        class MockResponse:
            status = 200

            async def json(self):
                return {
                    "answers": {
                        "address_intent": {
                            "choice": "addressed",
                            "answer_confidence": 0.94,
                            "abstention": "passed",
                        }
                    }
                }

            async def text(self):
                return ""

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        class MockSession:
            def post(self, url, json=None, headers=None, timeout=None):
                nonlocal captured_payload, captured_headers
                captured_payload = json
                captured_headers = headers
                return MockResponse()

        with patch(
            "custom_components.esphome_satellite.systemone_client.async_get_clientsession",
            return_value=MockSession(),
        ):
            choice, conf, rtt = await client.classify_addressing(
                text="what time is it",
                question_text=QUESTION_TEMPLATE_GENERAL,
                min_confidence=0.60,
            )

            self.assertEqual(choice, "addressed")
            self.assertEqual(conf, 0.94)
            self.assertGreaterEqual(rtt, 0.0)
            self.assertEqual(captured_headers.get("Authorization"), "Bearer test_token_123")
            self.assertEqual(captured_payload["state"], "what time is it")
            self.assertIn("criteria", captured_payload["questions"]["address_intent"])
            self.assertEqual(
                captured_payload["questions"]["address_intent"]["criteria"],
                CLASSIFICATION_CRITERIA,
            )

    async def test_systemone_client_abstention_handling(self):
        """When model returns abstention='abstained', client safely defaults to addressed with 0 confidence."""
        client = SystemOneClient(self.mock_hass, "http://localhost:8000/v1/systemone")

        class MockResponse:
            status = 200

            async def json(self):
                return {
                    "answers": {
                        "address_intent": {
                            "choice": "ambient_conversation",
                            "answer_confidence": 0.88,
                            "abstention": "abstained",
                        }
                    }
                }

            async def text(self):
                return ""

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        class MockSession:
            def post(self, *args, **kwargs):
                return MockResponse()

        with patch(
            "custom_components.esphome_satellite.systemone_client.async_get_clientsession",
            return_value=MockSession(),
        ):
            choice, conf, rtt = await client.classify_addressing(
                text="something ambiguous", question_text=QUESTION_TEMPLATE_GENERAL
            )
            self.assertEqual(choice, CHOICE_ADDRESSED)
            self.assertEqual(conf, 0.0)

    async def test_systemone_client_http_error(self):
        """HTTP 500 raises SystemOneClientError."""
        client = SystemOneClient(self.mock_hass, "http://localhost:8000/v1/systemone")

        class MockResponse:
            status = 500

            async def text(self):
                return "Internal Server Error"

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        class MockSession:
            def post(self, *args, **kwargs):
                return MockResponse()

        with patch(
            "custom_components.esphome_satellite.systemone_client.async_get_clientsession",
            return_value=MockSession(),
        ):
            with self.assertRaises(SystemOneClientError):
                await client.classify_addressing("hello", "question")

    async def test_gatekeeper_entity_silent_drop_on_ambient(self):
        """Gatekeeper intercepts ambient speech and returns speech='' for silent drop contract."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry_123"
        mock_entry.data = {CONF_DOWNSTREAM_AGENT: "conversation.home_assistant"}
        mock_entry.options = {
            CONF_SLOT1_ENABLED: True,
            CONF_SLOT1_THRESHOLD: 0.60,
        }

        mock_client = MagicMock()
        mock_client.classify_addressing = AsyncMock(
            return_value=(CHOICE_AMBIENT, 0.85, 22.0)
        )

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        # Setup satellite entity state
        sat_state = MagicMock()
        sat_state.attributes = {"active_pipeline_index": 0, "wake_word": "clemens"}
        self.mock_hass.states.get.return_value = sat_state

        user_input = MagicMock()
        user_input.text = "We were talking about Mark Twain yesterday"
        user_input.satellite_id = "assist_satellite.living_room"
        user_input.conversation_id = "conv_1"
        user_input.language = "en"

        result = await entity.async_process(user_input)

        self.assertEqual(result.conversation_id, "conv_1")
        # Silent drop: plain speech must be empty string
        self.assertEqual(result.response.speech.get("plain", {}).get("speech"), "")

    async def test_gatekeeper_entity_delegation_on_addressed(self):
        """Gatekeeper delegates addressed speech to downstream agent."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry_123"
        mock_entry.data = {CONF_DOWNSTREAM_AGENT: "conversation.home_assistant"}
        mock_entry.options = {
            CONF_DOWNSTREAM_AGENT: "conversation.claude",
            CONF_SLOT1_ENABLED: True,
            CONF_SLOT1_THRESHOLD: 0.60,
        }

        mock_client = MagicMock()
        mock_client.classify_addressing = AsyncMock(
            return_value=(CHOICE_ADDRESSED, 0.95, 18.0)
        )

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        sat_state = MagicMock()
        sat_state.attributes = {"active_pipeline_index": 0, "wake_word": "clemens"}
        self.mock_hass.states.get.return_value = sat_state

        user_input = MagicMock()
        user_input.text = "Mr. Clemens, turn off the kitchen lights"
        user_input.satellite_id = "assist_satellite.living_room"
        user_input.conversation_id = "conv_2"
        user_input.language = "en"
        user_input.context = MagicMock()
        user_input.device_id = "dev_1"

        downstream_mock = AsyncMock(return_value="delegated_result")
        with patch(
            "custom_components.esphome_satellite.conversation.conversation.async_converse",
            downstream_mock,
        ):
            result = await entity.async_process(user_input)
            self.assertEqual(result, "delegated_result")
            downstream_mock.assert_called_once()
            call_kwargs = downstream_mock.call_args[1]
            self.assertEqual(call_kwargs["agent_id"], "conversation.claude")
            self.assertEqual(call_kwargs["text"], "Mr. Clemens, turn off the kitchen lights")

    async def test_gatekeeper_entity_non_satellite_bypass(self):
        """Direct dashboard typing (no satellite_id) immediately bypasses System 1."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry_123"
        mock_entry.data = {CONF_DOWNSTREAM_AGENT: "conversation.home_assistant"}
        mock_entry.options = {}

        mock_client = MagicMock()
        mock_client.classify_addressing = AsyncMock()

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        user_input = MagicMock()
        user_input.text = "What is the status?"
        user_input.satellite_id = None
        user_input.conversation_id = "conv_3"
        user_input.language = "en"
        user_input.context = MagicMock()
        user_input.device_id = None

        downstream_mock = AsyncMock(return_value="dashboard_result")
        with patch(
            "custom_components.esphome_satellite.conversation.conversation.async_converse",
            downstream_mock,
        ):
            result = await entity.async_process(user_input)
            self.assertEqual(result, "dashboard_result")
            mock_client.classify_addressing.assert_not_called()

    async def test_gatekeeper_fail_closed_and_fail_open(self):
        """Verify fallback policy on System 1 failure."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry_123"
        mock_entry.data = {CONF_DOWNSTREAM_AGENT: "conversation.home_assistant"}

        mock_client = MagicMock()
        mock_client.classify_addressing = AsyncMock(
            side_effect=SystemOneClientError("Network timeout")
        )

        sat_state = MagicMock()
        sat_state.attributes = {"active_pipeline_index": 0, "wake_word": "clemens"}
        self.mock_hass.states.get.return_value = sat_state

        user_input = MagicMock()
        user_input.text = "Mr. Clemens, hello world"
        user_input.satellite_id = "assist_satellite.living_room"
        user_input.conversation_id = "conv_4"
        user_input.language = "en"
        user_input.context = MagicMock()
        user_input.device_id = None

        # Test 1: fail-closed (drop)
        mock_entry.options = {CONF_FALLBACK_BEHAVIOR: "drop"}
        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)
        result = await entity.async_process(user_input)
        self.assertEqual(result.response.speech.get("plain", {}).get("speech"), "")

        # Test 2: fail-open (allow)
        mock_entry.options = {CONF_FALLBACK_BEHAVIOR: "allow"}
        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)
        downstream_mock = AsyncMock(return_value="allowed_result")
        with patch(
            "custom_components.esphome_satellite.conversation.conversation.async_converse",
            downstream_mock,
        ):
            result = await entity.async_process(user_input)
            self.assertEqual(result, "allowed_result")

    def test_resolve_satellite_context_float_sensor_state(self):
        """Verify float-formatted sensor states ('1.0', '2.0') from ESPHome are correctly parsed."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry_123"
        mock_entry.data = {}
        mock_entry.options = {}
        mock_client = MagicMock()

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        sat_state = MagicMock()
        sat_state.attributes = {"active_pipeline_index": 0, "wake_word": "clemens"}

        sensor_state = MagicMock()

        def get_state(eid):
            if "assist_satellite" in eid:
                return sat_state
            if "active_assistant_slot" in eid:
                return sensor_state
            return None

        self.mock_hass.states.get.side_effect = get_state

        # Case 1: ESPHome publishes "2.0"
        sensor_state.state = "2.0"
        slot, ww = entity._resolve_satellite_context("assist_satellite.living_room")
        self.assertEqual(slot, 1)
        self.assertEqual(ww, "clemens")

        # Case 2: ESPHome publishes "1.0"
        sensor_state.state = "1.0"
        slot, ww = entity._resolve_satellite_context("assist_satellite.living_room")
        self.assertEqual(slot, 0)

        # Case 3: Standard integer string "2"
        sensor_state.state = "2"
        slot, ww = entity._resolve_satellite_context("assist_satellite.living_room")
        self.assertEqual(slot, 1)

        # Case 4: Sensor unavailable or unknown; falls back to satellite attributes
        sensor_state.state = "unavailable"
        sat_state.attributes["active_pipeline_index"] = 1
        slot, ww = entity._resolve_satellite_context("assist_satellite.living_room")
        self.assertEqual(slot, 1)

    def test_gatekeeper_threshold_inheritance(self):
        """Verify slot thresholds inherit default_threshold if not explicitly configured in options."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry_123"
        mock_entry.data = {"default_threshold": 0.72}
        mock_entry.options = {}
        mock_client = MagicMock()

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        # Inherits from data default_threshold (0.72)
        self.assertAlmostEqual(entity._get_slot_threshold(0), 0.72)
        self.assertAlmostEqual(entity._get_slot_threshold(1), 0.72)

        # Configured in options default_threshold (0.80)
        mock_entry.options = {"default_threshold": 0.80}
        self.assertAlmostEqual(entity._get_slot_threshold(0), 0.80)
        self.assertAlmostEqual(entity._get_slot_threshold(1), 0.80)

        # Slot-specific override takes precedence
        mock_entry.options = {
            "default_threshold": 0.80,
            "slot1_threshold": 0.65,
            "slot2_threshold": 0.85,
        }
        self.assertAlmostEqual(entity._get_slot_threshold(0), 0.65)
        self.assertAlmostEqual(entity._get_slot_threshold(1), 0.85)

    async def test_systemone_client_probabilities_schema(self):
        """Verify client correctly parses probabilities dictionary if confidence is not top-level."""
        client = SystemOneClient(self.mock_hass, "http://localhost:8000/v1/systemone")

        class MockResponse:
            status = 200

            async def json(self):
                return {
                    "answers": {
                        "address_intent": {
                            "choice": "ambient_conversation",
                            "probabilities": {
                                "ambient_conversation": 0.91,
                                "addressed": 0.09,
                            },
                        }
                    }
                }

            async def text(self):
                return ""

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class MockSession:
            def post(self, *args, **kwargs):
                return MockResponse()

        with patch(
            "custom_components.esphome_satellite.systemone_client.async_get_clientsession",
            return_value=MockSession(),
        ):
            choice, conf, rtt = await client.classify_addressing("talking nearby", "question")
            self.assertEqual(choice, "ambient_conversation")
            self.assertAlmostEqual(conf, 0.91)


    async def test_notify_wake_word_verified_on_addressed(self):
        """Verify _notify_wake_word_verified calls the ESPHome service when addressed."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {}
        mock_entry.data = {}
        mock_client = AsyncMock()
        mock_client.classify_addressing.return_value = ("addressed", 0.95, 12.0)

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        user_input = MagicMock()
        user_input.text = "Mr. Clemens, turn on the lights"
        user_input.satellite_id = "assist_satellite.test_satellite"
        user_input.language = "en"
        user_input.conversation_id = "conv_123"

        with patch.object(entity, "_resolve_satellite_context", return_value=(0, "assistant")), \
             patch.object(entity, "_notify_wake_word_verified", new_callable=AsyncMock) as mock_notify, \
             patch.object(entity, "_delegate_downstream", new_callable=AsyncMock) as mock_delegate:
            mock_delegate.return_value = MagicMock()
            await entity.async_process(user_input)

            mock_notify.assert_awaited_once_with("assist_satellite.test_satellite")
            mock_delegate.assert_awaited_once_with(user_input)

    async def test_notify_wake_word_verified_not_called_on_ambient(self):
        """Verify _notify_wake_word_verified is NOT called when ambient speech is intercepted."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {}
        mock_entry.data = {}
        mock_client = AsyncMock()
        mock_client.classify_addressing.return_value = ("ambient_conversation", 0.95, 12.0)

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        user_input = MagicMock()
        user_input.text = "pass the salt please"
        user_input.satellite_id = "assist_satellite.test_satellite"
        user_input.language = "en"
        user_input.conversation_id = "conv_123"

        with patch.object(entity, "_resolve_satellite_context", return_value=(0, "assistant")), \
             patch.object(entity, "_notify_wake_word_verified", new_callable=AsyncMock) as mock_notify, \
             patch.object(entity, "_delegate_downstream", new_callable=AsyncMock) as mock_delegate:
            result = await entity.async_process(user_input)

            mock_notify.assert_not_called()
            mock_delegate.assert_not_called()
            self.assertEqual(result.response.speech.get("plain", {}).get("speech"), "")

    async def test_gatekeeper_delegates_to_system_one_without_regex_drop(self):
        """Utterances without explicit wake word are not regex-dropped; they delegate directly to System 1."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {}
        mock_entry.data = {}
        mock_client = AsyncMock()
        mock_client.classify_addressing.return_value = ("ambient", 0.90, 12.0)

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        sat_state = MagicMock()
        sat_state.attributes = {"active_pipeline_index": 0, "wake_word": "clemens"}
        self.mock_hass.states.get.return_value = sat_state

        utterances = [
            "turn off the kitchen lights",
            "set a timer for 15 minutes",
            "white rice and roti",
            "a nice stop",
            "Mr. Business is a funny cat",
        ]

        for text in utterances:
            mock_client.classify_addressing.reset_mock()
            mock_client.classify_addressing.return_value = ("ambient", 0.90, 12.0)
            user_input = MagicMock()
            user_input.text = text
            user_input.satellite_id = "assist_satellite.living_room"
            user_input.language = "en"
            user_input.conversation_id = f"conv_{text[:5]}"

            result = await entity.async_process(user_input)

            # Dropped because System 1 classified as ambient, NOT by regex pre-filter
            self.assertEqual(result.response.speech.get("plain", {}).get("speech"), "")
            # System 1 was invoked directly
            mock_client.classify_addressing.assert_called_once()

    async def test_gatekeeper_wake_word_soundalikes_accepted(self):
        """Phonetic approximations of Clemens / Mark Twain pass fast-path to System 1."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {}
        mock_entry.data = {}
        mock_client = AsyncMock()
        mock_client.classify_addressing.return_value = ("addressed", 0.95, 15.0)

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        sat_state = MagicMock()
        sat_state.attributes = {"active_pipeline_index": 0, "wake_word": "clemens"}
        self.mock_hass.states.get.return_value = sat_state

        valid_utterances = [
            "Mr. Clemens, tell me a joke",
            "mr clemens what time is it",
            "mister clemens turn on lights",
            "mista clemens turn on lights",
            "Clamance what time is it",
            "clamonds are good",
            "Mark Twain tell me a story",
            "twain what is 2 plus 2",
            "hey clemens how are you",
        ]

        for text in valid_utterances:
            mock_client.classify_addressing.reset_mock()
            user_input = MagicMock()
            user_input.text = text
            user_input.satellite_id = "assist_satellite.living_room"
            user_input.language = "en"
            user_input.conversation_id = "conv_test"

            with patch.object(entity, "_delegate_downstream", new_callable=AsyncMock) as mock_delegate:
                mock_delegate.return_value = "delegated"
                result = await entity.async_process(user_input)
                self.assertEqual(result, "delegated")
                mock_client.classify_addressing.assert_called_once()

    async def test_gatekeeper_slot2_wake_words(self):
        """Slot 2 satellite accepts Slot 2 default wake word variants (e.g. Okay Nabu) or custom patterns."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_slot2"
        mock_entry.title = "Satellite Slot 2 Gatekeeper"
        mock_entry.options = {}
        mock_entry.data = {}
        mock_client = AsyncMock()
        mock_client.classify_addressing.return_value = ("addressed", 0.92, 14.0)

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        sat_state = MagicMock()
        sat_state.attributes = {"active_pipeline_index": 1, "wake_word": "Okay Nabu"}
        self.mock_hass.states.get.return_value = sat_state

        slot2_utterances = [
            "Okay Nabu, what is the news",
            "hey nabu what time is it",
            "OK Nabu what is the weather",
            "nabu turn on lights",
            "Nabu, turn off lights",
            "hey naboo how are you",
        ]

        for text in slot2_utterances:
            mock_client.classify_addressing.reset_mock()
            user_input = MagicMock()
            user_input.text = text
            user_input.satellite_id = "assist_satellite.living_room_slot2"
            user_input.language = "en"
            user_input.conversation_id = "conv_slot2"

            with patch.object(entity, "_delegate_downstream", new_callable=AsyncMock) as mock_delegate:
                mock_delegate.return_value = "delegated_slot2"
                result = await entity.async_process(user_input)
                self.assertEqual(result, "delegated_slot2")
                mock_client.classify_addressing.assert_called_once()

        # Custom Slot 2 options support
        mock_entry.options = {CONF_SLOT2_THRESHOLD: 0.60}
        user_input_custom = MagicMock()
        user_input_custom.text = "Hey assistant two, what time is it"
        user_input_custom.satellite_id = "assist_satellite.living_room_slot2"
        user_input_custom.language = "en"
        user_input_custom.conversation_id = "conv_custom"

        with patch.object(entity, "_delegate_downstream", new_callable=AsyncMock) as mock_delegate:
            mock_delegate.return_value = "delegated_custom"
            result = await entity.async_process(user_input_custom)
            self.assertEqual(result, "delegated_custom")

        # Ambient commands on Slot 2 satellite must drop
        naked_user_input = MagicMock()
        naked_user_input.text = "turn off the kitchen lights"
        naked_user_input.satellite_id = "assist_satellite.living_room_slot2"
        naked_user_input.language = "en"
        naked_user_input.conversation_id = "conv_naked"
        mock_client.classify_addressing.return_value = ("ambient", 0.92, 14.0)

        result = await entity.async_process(naked_user_input)
        self.assertEqual(result.response.speech.get("plain", {}).get("speech"), "")

    async def test_gatekeeper_enforce_wake_word_disabled(self):
        """When enforce_wake_word=False, naked commands pass through to System 1."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {CONF_ENFORCE_WAKE_WORD: False}
        mock_entry.data = {}
        mock_client = AsyncMock()
        mock_client.classify_addressing.return_value = ("addressed", 0.95, 10.0)

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        sat_state = MagicMock()
        sat_state.attributes = {"active_pipeline_index": 0, "wake_word": "clemens"}
        self.mock_hass.states.get.return_value = sat_state

        user_input = MagicMock()
        user_input.text = "turn off the kitchen lights"
        user_input.satellite_id = "assist_satellite.living_room"
        user_input.language = "en"
        user_input.conversation_id = "conv_no_enforce"

        with patch.object(entity, "_delegate_downstream", new_callable=AsyncMock) as mock_delegate:
            mock_delegate.return_value = "delegated"
            result = await entity.async_process(user_input)
            self.assertEqual(result, "delegated")
            mock_client.classify_addressing.assert_called_once()

    async def test_gatekeeper_default_drop_fail_closed(self):
        """Under default-drop, ambient, low confidence (<0.60), or abstained results are dropped."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {"default_threshold": 0.60}
        mock_entry.data = {}
        mock_client = AsyncMock()

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        sat_state = MagicMock()
        sat_state.attributes = {"active_pipeline_index": 0, "wake_word": "clemens"}
        self.mock_hass.states.get.return_value = sat_state

        cases = [
            ("ambient", 0.90, True),     # Ambient -> drop
            ("ambient", 0.30, True),     # Ambient low confidence -> drop
            ("addressed", 0.45, True),   # Addressed below 0.60 threshold -> drop
            ("addressed", 0.0, True),    # Abstained (conf 0.0) -> drop
            ("addressed", 0.95, False),  # Confirmed addressed -> approve
        ]

        for choice, conf, should_drop in cases:
            mock_client.classify_addressing.return_value = (choice, conf, 12.0)
            user_input = MagicMock()
            user_input.text = "Mr. Clemens, test utterance"
            user_input.satellite_id = "assist_satellite.living_room"
            user_input.language = "en"
            user_input.conversation_id = "conv_dd"

            with patch.object(entity, "_delegate_downstream", new_callable=AsyncMock) as mock_delegate:
                mock_delegate.return_value = "delegated"
                result = await entity.async_process(user_input)
                if should_drop:
                    self.assertEqual(result.response.speech.get("plain", {}).get("speech"), "")
                    mock_delegate.assert_not_called()
                else:
                    self.assertEqual(result, "delegated")
                    mock_delegate.assert_called_once()


class TestESPHomeSatelliteOptionsFlow(unittest.IsolatedAsyncioTestCase):
    """Regression tests for ESPHomeSatelliteOptionsFlow and config flow."""

    def setUp(self):
        self.mock_hass = MagicMock()
        self.mock_entry = MagicMock()
        self.mock_entry.entry_id = "test_entry_123"
        self.mock_entry.options = {
            "downstream_agent": "conversation.test_agent",
            "systemone_url": "http://10.0.0.1:8000/v1/systemone",
            "systemone_token": "secret_token_123",
            "slot1_enabled": True,
            "slot1_threshold": 0.85,
            "slot2_enabled": False,
            "slot2_threshold": 0.80,
            "timeout_seconds": 3.0,
            "fallback_behavior": "drop",
        }
        self.mock_entry.data = {}
        self.mock_hass.config_entries.async_get_known_entry.return_value = self.mock_entry

    async def test_options_flow_instantiation_no_setter_error(self):
        """Verify OptionsFlow does not raise AttributeError when initialized."""
        from custom_components.esphome_satellite.config_flow import (
            ESPHomeSatelliteConfigFlow,
            ESPHomeSatelliteOptionsFlow,
        )

        flow = ESPHomeSatelliteConfigFlow.async_get_options_flow(self.mock_entry)
        self.assertIsInstance(flow, ESPHomeSatelliteOptionsFlow)

        # Directly passing entry should also succeed without setter AttributeError
        flow_direct = ESPHomeSatelliteOptionsFlow(self.mock_entry)
        self.assertEqual(flow_direct.config_entry, self.mock_entry)

    async def test_options_flow_async_step_init_renders_form(self):
        """Verify async_step_init renders form populated with existing options."""
        from custom_components.esphome_satellite.config_flow import (
            ESPHomeSatelliteConfigFlow,
        )

        flow = ESPHomeSatelliteConfigFlow.async_get_options_flow(self.mock_entry)
        flow.hass = self.mock_hass
        flow.handler = self.mock_entry.entry_id

        result = await flow.async_step_init()
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "init")

    async def test_options_flow_async_step_init_saves_user_input(self):
        """Verify async_step_init saves user_input when submitted."""
        from custom_components.esphome_satellite.config_flow import (
            ESPHomeSatelliteConfigFlow,
        )

        flow = ESPHomeSatelliteConfigFlow.async_get_options_flow(self.mock_entry)
        flow.hass = self.mock_hass
        flow.handler = self.mock_entry.entry_id

        user_input = {
            "systemone_url": "http://10.0.0.2:8000/v1/systemone",
            "systemone_token": "new_secret_token",
        }
        result = await flow.async_step_init(user_input=user_input)
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"], user_input)


class TestSpeculativeSTTProxy(unittest.IsolatedAsyncioTestCase):
    """Test suite for ESPHomeSatelliteSpeculativeSTT proxy and helper functions."""

    def setUp(self):
        self.mock_hass = MagicMock()
        self.mock_hass.states = MagicMock()
        self.mock_hass.services = MagicMock()
        self.mock_hass.data = {}

        self.mock_entry = MagicMock()
        self.mock_entry.entry_id = "test_entry_456"
        self.mock_entry.data = {
            CONF_SYSTEMONE_URL: "http://localhost:8000/v1/systemone",
            CONF_DOWNSTREAM_STT: "stt.faster_whisper",
            CONF_SPECULATIVE_CHUNK_MS: 500,
            CONF_EARLY_WAKE_VERIFICATION: True,
        }
        self.mock_entry.options = {}

        self.mock_client = MagicMock(spec=SystemOneClient)
        self.mock_client.classify_addressing = AsyncMock(
            return_value=(CHOICE_ADDRESSED, 0.95, 25.0)
        )


    def test_pcm_to_wav_helper(self):
        """Verify pcm_to_wav packages raw bytes into valid RIFF WAV header."""
        raw_pcm = b"\x00\x00" * 8000  # 0.5s of 16-bit mono 16kHz silence
        wav_bytes = pcm_to_wav(raw_pcm, sample_rate=16000, channels=1, sample_width=2)
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertIn(b"WAVEfmt ", wav_bytes)
        self.assertIn(b"data", wav_bytes)
        self.assertEqual(len(wav_bytes), 44 + len(raw_pcm))

    async def test_stt_entity_properties_default(self):
        """Verify default supported audio formats and configuration properties."""
        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )
        self.assertEqual(stt_proxy.downstream_stt_id, "stt.faster_whisper")
        self.assertEqual(stt_proxy.speculative_chunk_ms, 500)
        self.assertTrue(stt_proxy.early_wake_verification)
        self.assertEqual(stt_proxy.supported_languages, ["en", "*"])

        from homeassistant.components.stt import (
            AudioBitRates,
            AudioChannels,
            AudioCodecs,
            AudioFormats,
            AudioSampleRates,
        )
        self.assertIn(AudioFormats.RAW, stt_proxy.supported_formats)
        self.assertIn(AudioCodecs.PCM, stt_proxy.supported_codecs)
        self.assertIn(AudioBitRates.BITRATE_16, stt_proxy.supported_bit_rates)
        self.assertIn(AudioSampleRates.SAMPLERATE_16000, stt_proxy.supported_sample_rates)
        self.assertIn(AudioChannels.CHANNEL_MONO, stt_proxy.supported_channels)

    async def test_stt_entity_properties_delegated(self):
        """Verify supported properties delegate to downstream entity when available."""
        mock_downstream = MagicMock()
        mock_downstream.supported_languages = ["fr", "de"]
        mock_downstream.supported_formats = ["wav"]

        self.mock_hass.data["stt"] = MagicMock()
        self.mock_hass.data["stt"].get_entity = MagicMock(return_value=mock_downstream)

        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )
        self.assertEqual(stt_proxy.supported_languages, ["fr", "de"])
        self.assertEqual(stt_proxy.supported_formats, ["wav"])

    async def test_stt_process_audio_stream_dual_pipe_preserves_intact_transcript(self):
        """Verify dual-pipe streaming, downstream delegation, and verbatim transcript preservation."""
        from homeassistant.components.stt import (
            SpeechMetadata,
            SpeechResult,
            SpeechResultState,
        )

        mock_downstream = MagicMock()
        captured_chunks = []

        async def downstream_stream_handler(metadata, stream):
            async for chunk in stream:
                captured_chunks.append(chunk)
            return SpeechResult(
                text="Hey Computer, what is the weather tomorrow",
                result=SpeechResultState.SUCCESS,
            )

        mock_downstream.async_process_audio_stream = AsyncMock(
            side_effect=downstream_stream_handler
        )
        self.mock_hass.data["stt"] = MagicMock()
        self.mock_hass.data["stt"].get_entity = MagicMock(return_value=mock_downstream)
        self.mock_entry.options = {}
        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )

        # Generate 5 chunks of 1024 bytes (160ms total, below 500ms speculative window)
        async def dummy_audio_stream():
            for i in range(5):
                yield b"\x01\x02" * 512

        metadata = SpeechMetadata()
        result = await stt_proxy.async_process_audio_stream(metadata, dummy_audio_stream())

        # Verify downstream STT received all chunks
        self.assertEqual(len(captured_chunks), 5)
        # Verify returned result preserves transcript verbatim with zero trimming
        self.assertEqual(result.result, SpeechResultState.SUCCESS)
        self.assertEqual(result.text, "Hey Computer, what is the weather tomorrow")

    async def test_stt_speculative_verification_triggers_satellite_notification(self):
        """Verify 500ms sliding window triggers System 1 and fires satellite verified service."""
        from homeassistant.components.stt import (
            SpeechMetadata,
            SpeechResult,
            SpeechResultState,
        )

        # Setup mock satellite entity & registry entry
        mock_satellite_state = MagicMock()
        mock_satellite_state.entity_id = "assist_satellite.living_room"
        mock_satellite_state.state = "listening"
        self.mock_hass.states.async_all = MagicMock(return_value=[mock_satellite_state])

        mock_reg_entry = MagicMock()
        mock_reg_entry.config_entry_id = "esphome_living_room_entry"

        mock_config_entry = MagicMock()
        mock_config_entry.domain = "esphome"
        mock_config_entry.data = {"device_name": "living-room"}

        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get = MagicMock(return_value=mock_reg_entry)

        with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_ent_reg):
            self.mock_hass.config_entries.async_get_entry = MagicMock(
                return_value=mock_config_entry
            )
            self.mock_hass.services.has_service = MagicMock(return_value=True)
            self.mock_hass.services.async_call = AsyncMock()

            mock_downstream = MagicMock()

            # Downstream STT handler for partial vs final streams
            async def downstream_stream_handler(metadata, stream):
                chunks = []
                async for chunk in stream:
                    chunks.append(chunk)
                total_len = sum(len(c) for c in chunks)
                # If short slice (speculative window), return partial transcription
                if total_len >= 16000:
                    return SpeechResult(
                        text="Mr Clemens turn on the lights",
                        result=SpeechResultState.SUCCESS,
                    )
                return SpeechResult(
                    text="turn on the lights",
                    result=SpeechResultState.SUCCESS,
                )

            mock_downstream.async_process_audio_stream = AsyncMock(
                side_effect=downstream_stream_handler
            )
            self.mock_hass.data["stt"] = MagicMock()
            self.mock_hass.data["stt"].get_entity = MagicMock(return_value=mock_downstream)
            self.mock_entry.options = {}

            stt_proxy = ESPHomeSatelliteSpeculativeSTT(
                self.mock_hass,
                self.mock_entry,
                self.mock_client,
                speculative_chunk_ms=500,
            )

            # Stream 20 chunks of 1024 bytes (20,480 bytes > 16,000 bytes 500ms window)
            async def audio_stream():
                for _ in range(20):
                    yield b"\x01\x02" * 512
                    await asyncio.sleep(0.005)

            metadata = SpeechMetadata()
            result = await stt_proxy.async_process_audio_stream(metadata, audio_stream())

            # Verify System 1 was called speculatively
            self.mock_client.classify_addressing.assert_called()
            # Verify satellite service living_room_wake_word_verified was invoked
            self.mock_hass.services.async_call.assert_called_with(
                "esphome",
                "living_room_wake_word_verified",
                blocking=False,
            )
            self.assertEqual(result.text, "Mr Clemens turn on the lights")

    async def test_stt_speculative_ambient_speech_does_not_trigger_verified(self):
        """Verify ambient classification during sliding window does not notify satellite."""
        from homeassistant.components.stt import (
            SpeechMetadata,
            SpeechResult,
            SpeechResultState,
        )

        # Mock ambient response (< 0.80)
        self.mock_client.classify_addressing = AsyncMock(
            return_value=(CHOICE_AMBIENT, 0.25, 20.0)
        )

        self.mock_hass.services.async_call = AsyncMock()

        mock_downstream = MagicMock()

        async def downstream_stream_handler(metadata, stream):
            async for _ in stream:
                pass
            return SpeechResult(
                text="we were discussing the weather outside",
                result=SpeechResultState.SUCCESS,
            )

        mock_downstream.async_process_audio_stream = AsyncMock(
            side_effect=downstream_stream_handler
        )
        self.mock_hass.data["stt"] = MagicMock()
        self.mock_hass.data["stt"].get_entity = MagicMock(return_value=mock_downstream)

        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
            speculative_chunk_ms=500,
        )

        async def audio_stream():
            for _ in range(20):
                yield b"\x01\x02" * 512
                await asyncio.sleep(0.005)

        metadata = SpeechMetadata()
        result = await stt_proxy.async_process_audio_stream(metadata, audio_stream())

        # Verify satellite was NOT notified
        self.mock_hass.services.async_call.assert_not_called()
        self.assertEqual(result.text, "we were discussing the weather outside")

    async def test_stt_downstream_missing_returns_error(self):
        """Verify missing downstream STT entity returns SpeechResultState.ERROR."""
        from homeassistant.components.stt import SpeechMetadata, SpeechResultState

        self.mock_hass.data["stt"] = MagicMock()
        self.mock_hass.data["stt"].get_entity = MagicMock(return_value=None)

        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )

        async def audio_stream():
            yield b"\x00"

        metadata = SpeechMetadata()
        result = await stt_proxy.async_process_audio_stream(metadata, audio_stream())
        self.assertEqual(result.result, SpeechResultState.ERROR)
        self.assertIsNone(result.text)

    async def test_stt_downstream_error_passed_through(self):
        """Verify downstream STT failure is returned cleanly without trimming."""
        from homeassistant.components.stt import (
            SpeechMetadata,
            SpeechResult,
            SpeechResultState,
        )

        mock_downstream = MagicMock()
        mock_downstream.async_process_audio_stream = AsyncMock(
            return_value=SpeechResult(text=None, result=SpeechResultState.ERROR)
        )
        self.mock_hass.data["stt"] = MagicMock()
        self.mock_hass.data["stt"].get_entity = MagicMock(return_value=mock_downstream)

        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )

        async def audio_stream():
            yield b"\x00"

        metadata = SpeechMetadata()
        result = await stt_proxy.async_process_audio_stream(metadata, audio_stream())
        self.assertEqual(result.result, SpeechResultState.ERROR)
        self.assertIsNone(result.text)

    async def test_stt_async_setup_entry(self):
        """Verify async_setup_entry registers ESPHomeSatelliteSpeculativeSTT entity."""
        from custom_components.esphome_satellite.stt import async_setup_entry

        added_entities = []

        def mock_add_entities(entities):
            added_entities.extend(entities)

        await async_setup_entry(self.mock_hass, self.mock_entry, mock_add_entities)
        self.assertEqual(len(added_entities), 1)
        self.assertIsInstance(added_entities[0], ESPHomeSatelliteSpeculativeSTT)

    async def test_stt_early_verification_disabled(self):
        """Verify when early verification is disabled, satellite is never notified."""
        self.mock_entry.options[CONF_EARLY_WAKE_VERIFICATION] = False
        self.mock_hass.services.async_call = AsyncMock()

        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )
        self.assertFalse(stt_proxy.early_wake_verification)

        await stt_proxy._notify_satellite_verified()
        self.mock_hass.services.async_call.assert_not_called()

    async def test_stt_broadcast_fallback_service_call(self):
        """Verify when no active assist_satellite state exists, calls matching esphome services."""
        self.mock_hass.states.async_all = MagicMock(return_value=[])
        self.mock_hass.services.async_services = MagicMock(
            return_value={"esphome": {"satellite1_wake_word_verified": {}}}
        )
        self.mock_hass.services.async_call = AsyncMock()

        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )

        await stt_proxy._notify_satellite_verified()
        self.mock_hass.services.async_call.assert_called_with(
            "esphome",
            "satellite1_wake_word_verified",
            blocking=False,
        )


    async def test_stt_long_utterance_no_queue_deadlock_on_verified(self):
        """Verify that utterances exceeding chunk_queue.maxsize (128) do not deadlock when verified early."""
        from homeassistant.components.stt import (
            SpeechMetadata,
            SpeechResult,
            SpeechResultState,
        )

        mock_downstream = MagicMock()

        async def downstream_stream_handler(metadata, stream):
            chunks = []
            async for chunk in stream:
                chunks.append(chunk)
            return SpeechResult(text="long test instruction", result=SpeechResultState.SUCCESS)

        mock_downstream.async_process_audio_stream = AsyncMock(side_effect=downstream_stream_handler)
        self.mock_hass.data["stt"] = MagicMock()
        self.mock_hass.data["stt"].get_entity = MagicMock(return_value=mock_downstream)

        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )

        async def long_stream():
            # Send 200 chunks (exceeds maxsize 128)
            for _ in range(200):
                yield b"\x00" * 640

        metadata = SpeechMetadata()
        result = await stt_proxy.async_process_audio_stream(metadata, long_stream())
        self.assertEqual(result.result, SpeechResultState.SUCCESS)
        self.assertEqual(result.text, "long test instruction")

    def test_audio_stream_frame_and_sample_alignment_invariants(self):
        """Verify 16kHz 16-bit mono audio stream frame and sample alignment invariants."""
        from custom_components.esphome_satellite.const import (
            AUDIO_FRAME_BYTES,
            AUDIO_FRAME_MS,
            AUDIO_SAMPLE_RATE,
            AUDIO_SAMPLE_WIDTH,
            validate_audio_frame_alignment,
        )

        # 1. Fundamental acoustic constants
        self.assertEqual(AUDIO_SAMPLE_RATE, 16000)
        self.assertEqual(AUDIO_SAMPLE_WIDTH, 2)
        self.assertEqual(AUDIO_FRAME_MS, 20)
        self.assertEqual(AUDIO_FRAME_BYTES, 640)

        # 2. Valid frame-aligned chunks
        valid_20ms = b"\x00" * 640
        samples, frames = validate_audio_frame_alignment(valid_20ms)
        self.assertEqual(samples, 320)
        self.assertEqual(frames, 1)

        valid_40ms = b"\x00" * 1280
        samples, frames = validate_audio_frame_alignment(valid_40ms)
        self.assertEqual(samples, 640)
        self.assertEqual(frames, 2)

        valid_500ms = b"\x00" * 16000
        samples, frames = validate_audio_frame_alignment(valid_500ms)
        self.assertEqual(samples, 8000)
        self.assertEqual(frames, 25)

        # Zero length buffer
        samples, frames = validate_audio_frame_alignment(b"")
        self.assertEqual(samples, 0)
        self.assertEqual(frames, 0)

        # 3. Sample alignment violation: odd byte count
        with self.assertRaisesRegex(ValueError, "Sample alignment violation"):
            validate_audio_frame_alignment(b"\x00" * 641)

        # 4. Frame alignment violation: even bytes, but not a multiple of 640 bytes (20ms)
        with self.assertRaisesRegex(ValueError, "Frame alignment violation"):
            validate_audio_frame_alignment(b"\x00" * 700)


class TestDynamicPhoneticWakeGate(unittest.IsolatedAsyncioTestCase):
    """Test suite for dynamic phonetic wake phrase verification and context resolution."""

    def setUp(self):
        self.mock_hass = MagicMock()
        self.mock_hass.states = MagicMock()
        self.mock_hass.services = MagicMock()
        self.mock_hass.data = {}

        self.mock_entry = MagicMock()
        self.mock_entry.entry_id = "test_entry_dynamic_wake"
        self.mock_entry.data = {
            CONF_SYSTEMONE_URL: "http://localhost:8000/v1/systemone",
            CONF_DOWNSTREAM_STT: "stt.faster_whisper",
            CONF_DOWNSTREAM_AGENT: "conversation.downstream_llm",
            CONF_SPECULATIVE_CHUNK_MS: 500,
            CONF_EARLY_WAKE_VERIFICATION: True,
            CONF_DEFAULT_THRESHOLD: 0.5,
        }
        self.mock_entry.options = {}

        self.mock_client = MagicMock(spec=SystemOneClient)

    async def test_speculative_stt_phonetic_wake_verification(self):
        """Verify speculative STT passes dynamic wake phrase to System 1 and fires satellite signal."""
        from homeassistant.components.stt import (
            SpeechMetadata,
            SpeechResult,
            SpeechResultState,
        )

        mock_satellite_state = MagicMock()
        mock_satellite_state.entity_id = "assist_satellite.living_room"
        mock_satellite_state.state = "listening"
        mock_satellite_state.attributes = {"wake_word": "Mr. Clemens"}
        mock_satellite_state.last_updated = 1000.0
        self.mock_hass.states.async_all = MagicMock(return_value=[mock_satellite_state])

        mock_reg_entry = MagicMock()
        mock_reg_entry.config_entry_id = "esphome_living_room_entry"
        mock_reg_entry.unique_id = "28:84:85:ba:2c:6c-assist_satellite"

        mock_config_entry = MagicMock()
        mock_config_entry.domain = "esphome"
        mock_config_entry.data = {"device_name": "living-room"}

        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get = MagicMock(return_value=mock_reg_entry)

        with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_ent_reg):
            self.mock_hass.config_entries.async_get_entry = MagicMock(
                return_value=mock_config_entry
            )
            self.mock_hass.services.has_service = MagicMock(return_value=True)
            self.mock_hass.services.async_call = AsyncMock()

            mock_downstream = MagicMock()

            async def downstream_stream_handler(metadata, stream):
                chunks = []
                async for chunk in stream:
                    chunks.append(chunk)
                total_len = sum(len(c) for c in chunks)
                if total_len >= 16000:
                    return SpeechResult(text="Mister Clemens turn on the lights", result=SpeechResultState.SUCCESS)
                return SpeechResult(text="Mister Clemens", result=SpeechResultState.SUCCESS)

            mock_downstream.async_process_audio_stream = AsyncMock(side_effect=downstream_stream_handler)
            self.mock_hass.data["stt"] = MagicMock()
            self.mock_hass.data["stt"].get_entity = MagicMock(return_value=mock_downstream)

            # System 1 verifies phonetic match
            self.mock_client.classify_addressing = AsyncMock(
                return_value=(CHOICE_ADDRESSED, 0.75, 20.0)
            )

            stt_proxy = ESPHomeSatelliteSpeculativeSTT(
                self.mock_hass,
                self.mock_entry,
                self.mock_client,
                speculative_chunk_ms=500,
            )

            async def audio_stream():
                for _ in range(20):
                    yield b"\x01\x02" * 512
                    await asyncio.sleep(0.005)

            metadata = SpeechMetadata()
            result = await stt_proxy.async_process_audio_stream(metadata, audio_stream())

            # Verify System 1 was called with dynamic wake verification question and criteria
            self.mock_client.classify_addressing.assert_called()
            call_kwargs = self.mock_client.classify_addressing.call_args.kwargs
            self.assertIn("Mr. Clemens", call_kwargs["question_text"])
            self.assertIn("Mr. Clemens", call_kwargs["criteria"][CHOICE_ADDRESSED])

            # Verify satellite service was called to transition FSM to StreamingSpeechVerified
            self.mock_hass.services.async_call.assert_called_with(
                "esphome",
                "living_room_wake_word_verified",
                blocking=False,
            )

    async def test_speculative_stt_context_resolution_from_device_registry(self):
        """Verify wake word is dynamically resolved from device slot sensor and select entity."""
        mock_satellite_state = MagicMock()
        mock_satellite_state.entity_id = "assist_satellite.living_room"
        mock_satellite_state.state = "listening"
        mock_satellite_state.attributes = {}  # Empty wake_word attribute
        mock_satellite_state.last_updated = 1000.0
        self.mock_hass.states.async_all = MagicMock(return_value=[mock_satellite_state])

        mock_reg_entry = MagicMock()
        mock_reg_entry.device_id = "dev_123"

        dev_sensor = MagicMock()
        dev_sensor.domain = "sensor"
        dev_sensor.entity_id = "sensor.living_room_active_assistant_slot"

        dev_select1 = MagicMock()
        dev_select1.domain = "select"
        dev_select1.entity_id = "select.living_room_wake_word"

        dev_select2 = MagicMock()
        dev_select2.domain = "select"
        dev_select2.entity_id = "select.living_room_wake_word_2"

        mock_ent_reg = MagicMock()
        mock_ent_reg.async_get = MagicMock(return_value=mock_reg_entry)
        mock_ent_reg.async_entries_for_device = MagicMock(
            return_value=[dev_sensor, dev_select1, dev_select2]
        )

        # Slot 2 is active
        mock_slot_state = MagicMock()
        mock_slot_state.state = "2.0"

        # Slot 2 wake word is Hey Computer
        mock_ww2_state = MagicMock()
        mock_ww2_state.state = "Hey Computer"

        def mock_get_state(entity_id):
            if entity_id == "sensor.living_room_active_assistant_slot":
                return mock_slot_state
            if entity_id == "select.living_room_wake_word_2":
                return mock_ww2_state
            return None

        self.mock_hass.states.get = MagicMock(side_effect=mock_get_state)

        with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_ent_reg):
            stt_proxy = ESPHomeSatelliteSpeculativeSTT(
                self.mock_hass,
                self.mock_entry,
                self.mock_client,
            )
            sat_id, target_ww = stt_proxy._resolve_active_satellite_context()
            self.assertEqual(sat_id, "assist_satellite.living_room")
            self.assertEqual(target_ww, "Hey Computer")

    async def test_gatekeeper_wake_and_pause_handling(self):
        """Verify Gatekeeper recognizes wake-and-pause prompt and opens follow-up."""
        gatekeeper = ESPHomeSatelliteGatekeeperEntity(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )

        mock_satellite_state = MagicMock()
        mock_satellite_state.attributes = {"wake_word": "Mr. Clemens"}
        self.mock_hass.states.get = MagicMock(return_value=mock_satellite_state)

        # System 1 confirms phonetic wake phrase is present
        self.mock_client.classify_addressing = AsyncMock(
            return_value=(CHOICE_ADDRESSED, 0.77, 20.0)
        )

        user_input = MagicMock()
        user_input.text = "Mr. Clemens"
        user_input.satellite_id = "assist_satellite.living_room"
        user_input.conversation_id = "conv_123"
        user_input.language = "en"

        with patch.object(gatekeeper, "_notify_wake_word_verified", new_callable=AsyncMock) as mock_notify:
            result = await gatekeeper.async_process(user_input)

            mock_notify.assert_called_with("assist_satellite.living_room")
            self.assertTrue(result.continue_conversation)
            self.assertEqual(result.response.speech["plain"]["speech"], "Yes?")

    async def test_gatekeeper_wake_plus_command_delegation(self):
        """Verify Gatekeeper delegates wake + instruction downstream to conversation agent."""
        gatekeeper = ESPHomeSatelliteGatekeeperEntity(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )

        mock_satellite_state = MagicMock()
        mock_satellite_state.attributes = {"wake_word": "Mr. Clemens"}
        self.mock_hass.states.get = MagicMock(return_value=mock_satellite_state)

        self.mock_client.classify_addressing = AsyncMock(
            return_value=(CHOICE_ADDRESSED, 0.70, 22.0)
        )

        user_input = MagicMock()
        user_input.text = "Mr. Clemens turn on the living room light"
        user_input.satellite_id = "assist_satellite.living_room"
        user_input.conversation_id = "conv_456"
        user_input.language = "en"

        with patch.object(gatekeeper, "_notify_wake_word_verified", new_callable=AsyncMock) as mock_notify, \
             patch.object(gatekeeper, "_delegate_downstream", new_callable=AsyncMock) as mock_delegate:
            mock_delegate.return_value = MagicMock()

            await gatekeeper.async_process(user_input)

            mock_notify.assert_called_with("assist_satellite.living_room")
            mock_delegate.assert_called_with(user_input)

    async def test_gatekeeper_ambient_speech_dropped(self):
        """Verify ambient background speech is silently dropped without notifying satellite."""
        gatekeeper = ESPHomeSatelliteGatekeeperEntity(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )

        mock_satellite_state = MagicMock()
        mock_satellite_state.attributes = {"wake_word": "Mr. Clemens"}
        self.mock_hass.states.get = MagicMock(return_value=mock_satellite_state)

        # System 1 determines speech is ambient
        self.mock_client.classify_addressing = AsyncMock(
            return_value=(CHOICE_AMBIENT, 0.85, 22.0)
        )

        user_input = MagicMock()
        user_input.text = "The weather outside is really nice today"
        user_input.satellite_id = "assist_satellite.living_room"
        user_input.conversation_id = "conv_789"
        user_input.language = "en"

        with patch.object(gatekeeper, "_notify_wake_word_verified", new_callable=AsyncMock) as mock_notify, \
             patch.object(gatekeeper, "_delegate_downstream", new_callable=AsyncMock) as mock_delegate:
            result = await gatekeeper.async_process(user_input)

            mock_notify.assert_not_called()
            mock_delegate.assert_not_called()
            self.assertEqual(result.response.speech["plain"]["speech"], "")


    async def test_speculative_stt_short_fragment_skipped(self):
        """Verify single-word fragments are skipped in speculative STT when wake target is multi-word."""
        from homeassistant.components.stt import (
            SpeechMetadata,
            SpeechResult,
            SpeechResultState,
        )

        mock_satellite_state = MagicMock()
        mock_satellite_state.entity_id = "assist_satellite.living_room"
        mock_satellite_state.state = "listening"
        mock_satellite_state.attributes = {"wake_word": "Mr. Clemens"}
        self.mock_hass.states.async_all = MagicMock(return_value=[mock_satellite_state])

        mock_downstream = MagicMock()
        # Downstream STT produces single-word fragment "Yeah."
        mock_downstream.async_process_audio_stream = AsyncMock(
            return_value=SpeechResult(text="Yeah.", result=SpeechResultState.SUCCESS)
        )
        self.mock_hass.data["stt"] = MagicMock()
        self.mock_hass.data["stt"].get_entity = MagicMock(return_value=mock_downstream)

        self.mock_client.classify_addressing = AsyncMock()

        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
            speculative_chunk_ms=500,
        )

        async def audio_stream():
            for _ in range(5):
                yield b"\x01\x02" * 512
                await asyncio.sleep(0.005)

        metadata = SpeechMetadata()
        with patch.object(stt_proxy, "_notify_satellite_verified", new_callable=AsyncMock) as mock_notify:
            await stt_proxy.async_process_audio_stream(metadata, audio_stream())
            # Single-word fragment must not trigger System 1 or verify satellite
            self.mock_client.classify_addressing.assert_not_called()
            mock_notify.assert_not_called()

    async def test_speculative_stt_threshold_enforcement(self):
        """Verify speculative STT does not verify satellite when System 1 confidence is below threshold."""
        from homeassistant.components.stt import (
            SpeechMetadata,
            SpeechResult,
            SpeechResultState,
        )

        mock_satellite_state = MagicMock()
        mock_satellite_state.entity_id = "assist_satellite.living_room"
        mock_satellite_state.state = "listening"
        mock_satellite_state.attributes = {"wake_word": "Mr. Clemens"}
        self.mock_hass.states.async_all = MagicMock(return_value=[mock_satellite_state])

        mock_downstream = MagicMock()
        mock_downstream.async_process_audio_stream = AsyncMock(
            return_value=SpeechResult(text="Yeah really", result=SpeechResultState.SUCCESS)
        )
        self.mock_hass.data["stt"] = MagicMock()
        self.mock_hass.data["stt"].get_entity = MagicMock(return_value=mock_downstream)

        # System 1 returns weak confidence 0.56 below DEFAULT_THRESHOLD (0.65)
        self.mock_client.classify_addressing = AsyncMock(
            return_value=(CHOICE_ADDRESSED, 0.56, 15.0)
        )

        # Set default threshold to 0.65
        self.mock_entry.options = {CONF_DEFAULT_THRESHOLD: 0.65}

        stt_proxy = ESPHomeSatelliteSpeculativeSTT(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
            speculative_chunk_ms=500,
        )

        async def audio_stream():
            for _ in range(5):
                yield b"\x01\x02" * 512
                await asyncio.sleep(0.005)

        metadata = SpeechMetadata()
        with patch.object(stt_proxy, "_notify_satellite_verified", new_callable=AsyncMock) as mock_notify:
            await stt_proxy.async_process_audio_stream(metadata, audio_stream())
            mock_notify.assert_not_called()

    def test_slot_template_criteria_no_command_loophole(self):
        """Verify prompt templates do not contain the ambiguous 'or a command' loophole."""
        from custom_components.esphome_satellite.const import (
            QUESTION_TEMPLATE_SLOT1,
            QUESTION_TEMPLATE_SLOT2,
        )
        self.assertNotIn("or a command", QUESTION_TEMPLATE_SLOT1)
        self.assertNotIn("or a command", QUESTION_TEMPLATE_SLOT2)

    def test_expand_wake_phrase_rule_based_and_additive_aliases(self):
        """Verify rule-based orthographic expansions and additive user-configured aliases."""
        from custom_components.esphome_satellite.const import expand_wake_phrase

        # Test forward acronym: Kay Tee -> KT
        kt_expanded = expand_wake_phrase("Okay Nabu")
        self.assertIn("Okay Nabu", kt_expanded)
        self.assertIn("Okay Nabu", kt_expanded)

        # Test title expansion: Mr. -> Mister
        clemens_expanded = expand_wake_phrase("Mr. Clemens")
        self.assertIn("Mister Clemens", clemens_expanded)
        self.assertIn("Mr. Clemens", clemens_expanded)

        # Test additive user aliases (default empty, additive when provided)
        with_aliases = expand_wake_phrase("Okay Nabu", ["Ok Nabo", "Hey Nabu"])
        self.assertIn("Okay Nabu", with_aliases)
        self.assertIn("Okay Nabu", with_aliases)
        self.assertIn("Ok Nabo", with_aliases)
        self.assertIn("Hey Nabu", with_aliases)

    def test_prompt_factories_generic_and_followup(self):
        """Verify initial and follow-up prompt structure conforms to requirements."""
        from custom_components.esphome_satellite.const import (
            CHOICE_ADDRESSED,
            CHOICE_AMBIENT,
            make_followup_prompt,
            make_initial_prompt,
        )

        instr_init, crit_init = make_initial_prompt("Okay Nabu", ["Okay Nabu", "Ok Nabo"])
        self.assertIn("Okay Nabu", instr_init)
        self.assertIn("Okay Nabu", instr_init)
        self.assertIn("Ok Nabo", instr_init)
        self.assertIn(CHOICE_ADDRESSED, crit_init)
        self.assertIn(CHOICE_AMBIENT, crit_init)

        instr_follow, crit_follow = make_followup_prompt("Okay Nabu")
        self.assertIn("follow-up", instr_follow.lower())
        self.assertIn("NOT need to repeat the wake word", instr_follow)
        self.assertIn(CHOICE_ADDRESSED, crit_follow)
        self.assertIn(CHOICE_AMBIENT, crit_follow)

    def test_speech_audio_processing_requires_external_vad_disabled(self):
        """Verify ESPHomeSatelliteSpeculativeSTT disables requires_external_vad."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {}
        entry.data = {}
        client = MagicMock()
        stt_entity = ESPHomeSatelliteSpeculativeSTT(MagicMock(), entry, client)
        self.assertFalse(stt_entity.audio_processing.requires_external_vad)

    def test_is_wake_and_pause_turn_matching(self):
        """Verify is_wake_and_pause_turn matches wake words and aliases accurately."""
        from custom_components.esphome_satellite.conversation import is_wake_and_pause_turn

        # Wake phrases and aliases
        self.assertTrue(is_wake_and_pause_turn("Mr. Clemens.", "Mr. Clemens", ["Mister Clemens"]))
        self.assertTrue(is_wake_and_pause_turn("Hey Mr Clemens", "Mr. Clemens", ["Mister Clemens"]))
        self.assertTrue(is_wake_and_pause_turn("Mister Clemens", "Mr. Clemens", ["Mister Clemens"]))
        self.assertTrue(is_wake_and_pause_turn("Okay Nabu", "Okay Nabu", ["Okay Nabu"]))
        self.assertTrue(is_wake_and_pause_turn("Okay Nabu", "Okay Nabu", ["Okay Nabu"]))
        self.assertTrue(is_wake_and_pause_turn("Mark Twain", "Mark Twain", []))
        self.assertTrue(is_wake_and_pause_turn("Hey Mark Twain", "Mark Twain", []))

        # Short commands must NOT trigger wake-and-pause
        self.assertFalse(is_wake_and_pause_turn("Lights on", "Mr. Clemens", ["Mister Clemens"]))
        self.assertFalse(is_wake_and_pause_turn("Turn off lights", "Mr. Clemens", ["Mister Clemens"]))
        self.assertFalse(is_wake_and_pause_turn("Stop", "Mr. Clemens", ["Mister Clemens"]))
        self.assertFalse(is_wake_and_pause_turn("Cancel", "Mr. Clemens", ["Mister Clemens"]))

        # Ambient speech must NOT trigger wake-and-pause
        self.assertFalse(is_wake_and_pause_turn("It won't work.", "Mr. Clemens", ["Mister Clemens"]))
        self.assertFalse(is_wake_and_pause_turn("Remove the set.", "Mr. Clemens", ["Mister Clemens"]))

        # Wake word + command must NOT trigger wake-and-pause
        self.assertFalse(is_wake_and_pause_turn("Mr Clemens what time is it", "Mr. Clemens", ["Mister Clemens"]))
        self.assertFalse(is_wake_and_pause_turn("Okay Nabu tell me a joke", "Okay Nabu", []))

    async def test_gatekeeper_short_command_delegation(self):
        """Verify 2-word commands like 'Lights on' are delegated downstream and NOT intercepted as Yes?."""
        gatekeeper = ESPHomeSatelliteGatekeeperEntity(
            self.mock_hass,
            self.mock_entry,
            self.mock_client,
        )

        mock_satellite_state = MagicMock()
        mock_satellite_state.attributes = {"wake_word": "Mr. Clemens"}
        self.mock_hass.states.get = MagicMock(return_value=mock_satellite_state)

        self.mock_client.classify_addressing = AsyncMock(
            return_value=(CHOICE_ADDRESSED, 0.85, 20.0)
        )

        user_input = MagicMock()
        user_input.text = "Lights on"
        user_input.satellite_id = "assist_satellite.living_room"
        user_input.conversation_id = "conv_short_cmd"
        user_input.language = "en"

        with patch.object(gatekeeper, "_notify_wake_word_verified", new_callable=AsyncMock) as mock_notify, \
             patch.object(gatekeeper, "_delegate_downstream", new_callable=AsyncMock) as mock_delegate:
            mock_delegate.return_value = "delegated_result"

            result = await gatekeeper.async_process(user_input)

            mock_notify.assert_called_with("assist_satellite.living_room")
            mock_delegate.assert_called_with(user_input)
            self.assertEqual(result, "delegated_result")

    def test_dynamic_phonetic_variant_generation(self):
        """Verify dynamic generation of phonetic and acoustic variants for detected wake words."""
        from custom_components.esphome_satellite.const import generate_phonetic_variants, expand_wake_phrase, make_initial_prompt

        # Test Clemens dynamic phonetic variants
        clemens_variants = generate_phonetic_variants("Mr. Clemens")
        self.assertIn("Mister Clemens", clemens_variants)
        self.assertIn("Hey Mister Clemens", clemens_variants)
        self.assertTrue(any("Clemons" in v for v in clemens_variants))
        self.assertTrue(any("Klemens" in v for v in clemens_variants))
        self.assertTrue(any("Mistah" in v or "Mistur" in v for v in clemens_variants))

        # Test Okay Nabu dynamic phonetic variants
        kt_variants = generate_phonetic_variants("Okay Nabu")
        self.assertIn("Okay Nabu", kt_variants)
        self.assertIn("Okay Nabu", kt_variants)
        self.assertTrue(any("KT" in v for v in kt_variants))

        # Test arbitrary wake phrase without hardcoded knowledge
        wizard_variants = generate_phonetic_variants("Little Wizard")
        self.assertIn("Hey Little Wizard", wizard_variants)

        # Verify additive user aliases and interpolation into prompt
        expanded = expand_wake_phrase("Mr. Clemens", ["Custom Alias"])
        self.assertIn("Custom Alias", expanded)
        self.assertIn("Mister Clemens", expanded)

        prompt, criteria = make_initial_prompt("Mr. Clemens", expanded)
        self.assertIn("The voice satellite triggered on wake phrase 'Mr. Clemens'", prompt)
        self.assertIn("Recognized phonetic approximations, name variants, and spellings include:", prompt)
        self.assertIn("Mr. Clemens", prompt)


if __name__ == "__main__":
    unittest.main()



