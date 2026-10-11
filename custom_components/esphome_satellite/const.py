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
CONF_DOWNSTREAM_STT: Final = "downstream_stt"
CONF_SPECULATIVE_CHUNK_MS: Final = "speculative_chunk_ms"
CONF_EARLY_WAKE_VERIFICATION: Final = "early_wake_verification"

# Default Configuration Values
DEFAULT_SYSTEMONE_URL: Final = "http://localhost:8000/v1/systemone"
DEFAULT_SYSTEMONE_TOKEN: Final = ""
DEFAULT_THRESHOLD: Final = 0.60
DEFAULT_TIMEOUT: Final = 2.5
DEFAULT_FALLBACK: Final = "drop"  # "drop" (fail-closed) | "allow" (fail-open)
DEFAULT_ENFORCE_WAKE_WORD: Final = True
DEFAULT_DOWNSTREAM_STT: Final = "stt.faster_whisper"
DEFAULT_SPECULATIVE_CHUNK_MS: Final = 500
DEFAULT_EARLY_WAKE_VERIFICATION: Final = True

# Decision Classification Choices & Criteria
CHOICE_ADDRESSED: Final = "addressed"
CHOICE_AMBIENT: Final = "ambient"
CLASSIFICATION_CHOICES: Final = [CHOICE_ADDRESSED, CHOICE_AMBIENT]
CLASSIFICATION_CRITERIA: Final = {
    CHOICE_ADDRESSED: (
        "Spoken command, instruction, request, question, or list operation directed to the smart assistant, "
        "accounting for phonetic STT errors (e.g. 'and' for 'add', 'turn on' vs 'turn in')"
    ),
    CHOICE_AMBIENT: (
        "Casual bystander conversation between humans, third-person mention of a name, gossip, or TV audio "
        "not intended to instruct the assistant"
    ),
}

# Question Templates
QUESTION_TEMPLATE_GENERAL: Final = (
    "This text is raw speech-to-text (STT) and probably contains phonetic mistranscriptions "
    "(such as 'and' for 'add', misheard verbs, or homophones). "
    "Assume it does, and determine what the user actually said. "
    "With the understanding that if it contains the wake phrase or is directed at the assistant, "
    "it most likely is an instruction and everything following is the instruction. "
    "Is this utterance an instruction, command, request, or query intended for the smart assistant?"
)

QUESTION_TEMPLATE_SLOT1: Final = (
    "This is raw speech-to-text (STT) from a voice satellite triggered on wake phrase '{wake_word}'. "
    "It probably contains phonetic mistranscriptions (e.g. 'and' instead of 'add', homophones, or misheard words). "
    "Assume it does, and infer what the user was trying to say. "
    "With the understanding that if it contains wake phrase '{wake_word}' or a command, "
    "it most likely is an instruction and everything following '{wake_word}' is the instruction. "
    "Is this an addressed instruction or query to {wake_word}?"
)

QUESTION_TEMPLATE_SLOT2: Final = (
    "This is raw speech-to-text (STT) from a voice satellite triggered on wake phrase '{wake_word}'. "
    "It probably contains phonetic mistranscriptions (e.g. 'and' instead of 'add', homophones, or misheard words). "
    "Assume it does, and infer what the user was trying to say. "
    "With the understanding that if it contains wake phrase '{wake_word}' or a command, "
    "it most likely is an instruction and everything following '{wake_word}' is the instruction. "
    "Is this an addressed instruction or query to {wake_word}?"
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
