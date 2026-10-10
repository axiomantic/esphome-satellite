"""Constants for the ESPHome Satellite Gatekeeper integration."""
from typing import Final
import re

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
CONF_SLOT1_PATTERNS: Final = "slot1_patterns"
CONF_SLOT2_PATTERNS: Final = "slot2_patterns"
CONF_TIMEOUT_SECONDS: Final = "timeout_seconds"
CONF_FALLBACK_BEHAVIOR: Final = "fallback_behavior"
CONF_ENFORCE_WAKE_WORD: Final = "enforce_wake_word"

# Default Configuration Values
DEFAULT_SYSTEMONE_URL: Final = "http://localhost:8000/v1/systemone"
DEFAULT_SYSTEMONE_TOKEN: Final = ""
DEFAULT_THRESHOLD: Final = 0.60
DEFAULT_TIMEOUT: Final = 2.5
DEFAULT_FALLBACK: Final = "drop"  # "drop" (fail-closed) | "allow" (fail-open)
DEFAULT_ENFORCE_WAKE_WORD: Final = True

# Decision Classification Choices & Criteria
CHOICE_ADDRESSED: Final = "addressed"
CHOICE_AMBIENT: Final = "ambient"
CLASSIFICATION_CHOICES: Final = [CHOICE_ADDRESSED, CHOICE_AMBIENT]
CLASSIFICATION_CRITERIA: Final = {
    CHOICE_ADDRESSED: "Spoken command, request, or query explicitly addressing the smart home assistant",
    CHOICE_AMBIENT: "Casual bystander conversation between humans, third-person mention of a name, or TV chatter",
}

# Question Templates
QUESTION_TEMPLATE_GENERAL: Final = (
    "Is this utterance an addressed request, command, or query directed to the smart home assistant, "
    "or is it ambient conversation between humans or TV audio?"
)

QUESTION_TEMPLATE_SLOT1: Final = (
    "The voice satellite triggered on wake phrase '{wake_word}'. "
    "Is this utterance an addressed request or query directed to the assistant, "
    "or is it ambient bystander conversation talking about someone or TV chatter?"
)

QUESTION_TEMPLATE_SLOT2: Final = (
    "The voice satellite triggered on secondary wake phrase '{wake_word}'. "
    "Is this utterance an addressed request or query directed to the assistant, "
    "or is it ambient bystander conversation talking about someone or TV chatter?"
)

# Built-in Default Wake Word Regex Patterns
WAKE_WORD_PATTERNS_CLEMENS: Final = (
    r"\b("
    r"(?:hey\s+)?(?:(?:mr\.?|mister|mista)\s+)?(?:clemens|clemons|clamance|clamonds|claments|clamons|clements|clement)"
    r"|(?:(?:hey\s+)?(?:mark\s+)?(?:twain|twane))"
    r")\b"
)

WAKE_WORD_PATTERNS_NABU: Final = (
    r"\b(?:(?:hey|okay|ok)\s+)?(?:nabu|naboo)\b"
)

REGEX_WAKE_WORD_CLEMENS = re.compile(WAKE_WORD_PATTERNS_CLEMENS, re.IGNORECASE)
REGEX_WAKE_WORD_NABU = re.compile(WAKE_WORD_PATTERNS_NABU, re.IGNORECASE)
