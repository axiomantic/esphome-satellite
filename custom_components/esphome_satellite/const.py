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
DEFAULT_THRESHOLD: Final = 0.50
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

QUESTION_TEMPLATE_WAKE_VERIFICATION: Final = (
    "Does this speech recognition transcript contain the wake phrase '{wake_word}'?"
)


def make_wake_verification_criteria(wake_word: str) -> dict[str, str]:
    """Generate dynamic criteria for System 1 phonetic wake phrase verification."""
    return {
        CHOICE_ADDRESSED: (
            f"The wake phrase {wake_word} (or a phonetic equivalent, abbreviation, or homophone)."
        ),
        CHOICE_AMBIENT: (
            "A different wake phrase, ambient conversation, or noise."
        ),
    }

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


# Audio Stream & Frame Invariants (16kHz 16-bit Mono)
AUDIO_SAMPLE_RATE: Final = 16000
AUDIO_SAMPLE_WIDTH: Final = 2  # 16-bit signed PCM
AUDIO_CHANNELS: Final = 1      # Mono
AUDIO_FRAME_MS: Final = 20     # Standard 20ms frame
AUDIO_FRAME_BYTES: Final = (AUDIO_SAMPLE_RATE // 1000) * AUDIO_FRAME_MS * AUDIO_SAMPLE_WIDTH  # 640 bytes


def validate_audio_frame_alignment(chunk: bytes) -> tuple[int, int]:
    """Validate 16kHz 16-bit mono PCM audio chunk sample and frame alignment.

    Returns:
        tuple[samples, frames_20ms]

    Raises:
        ValueError: If chunk violates sample alignment (% 2 != 0) or frame alignment (% 640 != 0).
    """
    length = len(chunk)
    if length % AUDIO_SAMPLE_WIDTH != 0:
        raise ValueError(
            f"Sample alignment violation: chunk length {length} is not a multiple of {AUDIO_SAMPLE_WIDTH} bytes"
        )
    if length % AUDIO_FRAME_BYTES != 0:
        raise ValueError(
            f"Frame alignment violation: chunk length {length} is not a multiple of {AUDIO_FRAME_BYTES} bytes (20ms frames)"
        )
    samples = length // AUDIO_SAMPLE_WIDTH
    frames = length // AUDIO_FRAME_BYTES
    return (samples, frames)

