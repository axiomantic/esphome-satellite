"""Constants for the ESPHome Satellite Gatekeeper integration."""
from typing import Final

DOMAIN: Final = "esphome_satellite"

# Configuration Keys
CONF_DOWNSTREAM_AGENT: Final = "downstream_agent"
CONF_SYSTEMONE_URL: Final = "systemone_url"
CONF_SYSTEMONE_TOKEN: Final = "systemone_token"
CONF_DEFAULT_THRESHOLD: Final = "default_threshold"
CONF_SLOT1_THRESHOLD: Final = "slot1_threshold"
CONF_SLOT2_THRESHOLD: Final = "slot2_threshold"
CONF_SLOT1_ENABLED: Final = "slot1_enabled"
CONF_SLOT2_ENABLED: Final = "slot2_enabled"
CONF_TIMEOUT_SECONDS: Final = "timeout_seconds"
CONF_FALLBACK_BEHAVIOR: Final = "fallback_behavior"

# Default Configuration Values
DEFAULT_SYSTEMONE_URL: Final = "http://localhost:8000/v1/systemone"
DEFAULT_SYSTEMONE_TOKEN: Final = ""
DEFAULT_THRESHOLD: Final = 0.60
DEFAULT_TIMEOUT: Final = 2.5
DEFAULT_FALLBACK: Final = "allow"  # "allow" (fail-open) | "drop" (fail-closed)

# Decision Classification Choices & Criteria
CHOICE_ADDRESSED: Final = "addressed"
CHOICE_AMBIENT: Final = "ambient_conversation"
CLASSIFICATION_CHOICES: Final = [CHOICE_ADDRESSED, CHOICE_AMBIENT]
CLASSIFICATION_CRITERIA: Final = {
    CHOICE_ADDRESSED: "Spoken directly to the voice assistant as a command or query",
    CHOICE_AMBIENT: "Background chatter, bystander talk, or speech not directed at the assistant",
}

# Question Templates
QUESTION_TEMPLATE_GENERAL: Final = (
    "Is this utterance directly addressing the smart home voice assistant with a question, command, "
    "or statement meant for the device, or is it background speech, television audio, or ambient conversation between humans?"
)

QUESTION_TEMPLATE_CLEMENS: Final = (
    "Is this utterance addressing Mr. Clemens (Mark Twain / the home assistant persona) or issuing a command to the household, "
    "or is it ambient conversational speech between people in the room or television audio?"
)
