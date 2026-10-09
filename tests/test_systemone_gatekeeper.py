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

    async def test_notify_wake_word_verified_on_approved(self):
        """Verify _notify_wake_word_verified is called when addressed speech is approved."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {}
        mock_entry.data = {}
        mock_client = AsyncMock()
        mock_client.classify_addressing.return_value = ("addressed", 0.95, 15.0)

        entity = ESPHomeSatelliteGatekeeperEntity(self.mock_hass, mock_entry, mock_client)

        user_input = MagicMock()
        user_input.text = "turn off the lights"
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


if __name__ == "__main__":
    unittest.main()
