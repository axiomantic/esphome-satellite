"""Unit and adversarial test suite for ESPHome Satellite SystemOne Gatekeeper."""
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
if "homeassistant" not in sys.modules:
    ha = MagicMock()
    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.core"] = MagicMock()
    sys.modules["homeassistant.config_entries"] = MagicMock()
    sys.modules["homeassistant.const"] = MagicMock()
    sys.modules["homeassistant.helpers"] = MagicMock()
    sys.modules["homeassistant.helpers.aiohttp_client"] = MagicMock()
    sys.modules["homeassistant.helpers.entity_platform"] = MagicMock()
    sys.modules["homeassistant.helpers.intent"] = MagicMock()
    sys.modules["homeassistant.helpers.selector"] = MagicMock()
    sys.modules["homeassistant.components"] = MagicMock()
    sys.modules["homeassistant.components.conversation"] = MagicMock()

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
        def __init__(self, response, conversation_id=None):
            self.response = response
            self.conversation_id = conversation_id

    sys.modules["homeassistant.components.conversation"].ConversationResult = MockConversationResult

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
    CONF_DOWNSTREAM_AGENT,
    CONF_FALLBACK_BEHAVIOR,
    CONF_SLOT1_ENABLED,
    CONF_SLOT1_THRESHOLD,
    CONF_SLOT2_ENABLED,
    CONF_SLOT2_THRESHOLD,
    CONF_SYSTEMONE_TOKEN,
    CONF_SYSTEMONE_URL,
    DEFAULT_THRESHOLD,
    QUESTION_TEMPLATE_CLEMENS,
    QUESTION_TEMPLATE_GENERAL,
)
from custom_components.esphome_satellite.conversation import ESPHomeSatelliteGatekeeperEntity
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
        user_input.text = "Turn off the kitchen lights"
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
            self.assertEqual(call_kwargs["text"], "Turn off the kitchen lights")

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
        user_input.text = "Hello world"
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


if __name__ == "__main__":
    unittest.main()
