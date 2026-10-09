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
CHOICE_AMBIENT: Final = "ambient"
CLASSIFICATION_CHOICES: Final = [CHOICE_ADDRESSED, CHOICE_AMBIENT]
CLASSIFICATION_CRITERIA: Final = {
    CHOICE_ADDRESSED: "Spoken command, request (e.g. tell me a joke, turn on lights), or addressing the assistant",
    CHOICE_AMBIENT: "Casual bystander conversation between humans or TV chatter",
}

# Question Templates
QUESTION_TEMPLATE_GENERAL: Final = (
    "Is this utterance an addressed request, command, or query directed to the smart home assistant, "
    "or is it ambient conversation between humans or TV audio?"
)

QUESTION_TEMPLATE_CLEMENS: Final = (
    "The voice satellite triggered on wake phrase 'Mr. Clemens'. "
    "Is this utterance an addressed request to the assistant (including jokes, questions, device controls, "
    "or phonetic approximations of the wake phrase like Clamonds, Clamance, or Clemons), "
    "or is it ambient bystander conversation between humans or TV chatter?"
)

QUESTION_TEMPLATE_SLOT2: Final = (
    "The voice satellite triggered on secondary wake phrase. "
    "Is this utterance an addressed request to the assistant (including jokes, questions, device controls, "
    "or phonetic approximations of the wake phrase), "
    "or is it ambient bystander conversation between humans or TV chatter?"
)
