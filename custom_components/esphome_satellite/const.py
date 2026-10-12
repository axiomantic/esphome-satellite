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
CONF_SLOT1_ALIASES: Final = "slot1_aliases"
CONF_SLOT2_ALIASES: Final = "slot2_aliases"
CONF_TIMEOUT_SECONDS: Final = "timeout_seconds"
CONF_FALLBACK_BEHAVIOR: Final = "fallback_behavior"
CONF_ENFORCE_WAKE_WORD: Final = "enforce_wake_word"
CONF_DOWNSTREAM_STT: Final = "downstream_stt"
CONF_SPECULATIVE_CHUNK_MS: Final = "speculative_chunk_ms"
CONF_EARLY_WAKE_VERIFICATION: Final = "early_wake_verification"

# Default Configuration Values
DEFAULT_SYSTEMONE_URL: Final = "http://localhost:8000/v1/systemone"
DEFAULT_SYSTEMONE_TOKEN: Final = ""
DEFAULT_THRESHOLD: Final = 0.65
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

# Rule-Based Phonetic & Orthographic Pre-Expansions
LETTER_NAMES: Final[dict[str, str]] = {
    "A": "ay", "B": "bee", "C": "see", "D": "dee", "E": "ee", "F": "ef",
    "G": "gee", "H": "aitch", "I": "eye", "J": "jay", "K": "kay", "L": "el",
    "M": "em", "N": "en", "O": "oh", "P": "pee", "Q": "cue", "R": "ar",
    "S": "ess", "T": "tee", "U": "you", "V": "vee", "W": "double-u",
    "X": "ex", "Y": "why", "Z": "zee",
}
LETTER_NAMES_REV: Final[dict[str, str]] = {v: k for k, v in LETTER_NAMES.items()}
LETTER_NAMES_REV["jay"] = "J"
LETTER_NAMES_REV["dee"] = "D"

TITLE_EXPANSIONS: Final[dict[str, str]] = {
    "mr": "Mister", "mr.": "Mister",
    "mrs": "Missus", "mrs.": "Missus",
    "ms": "Miz", "ms.": "Miz",
    "dr": "Doctor", "dr.": "Doctor",
    "st": "Saint", "st.": "Saint",
}
TITLE_EXPANSIONS_REV: Final[dict[str, str]] = {v.lower(): k.capitalize() for k, v in TITLE_EXPANSIONS.items()}


def expand_wake_phrase(wake_phrase: str, user_aliases: list[str] | None = None) -> list[str]:
    """Dynamically expand a wake phrase with rule-based title, acronym, and additive user aliases."""
    expansions: set[str] = set()
    cleaned = wake_phrase.strip()
    if not cleaned:
        return []
    expansions.add(cleaned)
    words = cleaned.split()

    # 1. Title expansions (e.g. Mr. <-> Mister)
    title_words: list[str] = []
    has_title = False
    for w in words:
        wl = w.lower()
        if wl in TITLE_EXPANSIONS:
            title_words.append(TITLE_EXPANSIONS[wl])
            has_title = True
        elif wl in TITLE_EXPANSIONS_REV:
            title_words.append(TITLE_EXPANSIONS_REV[wl])
            has_title = True
        else:
            title_words.append(w)
    if has_title:
        expansions.add(" ".join(title_words))

    # 2. Acronym forward expansion (e.g. Jay Dee -> JD)
    words_lower = [w.lower().strip(".,!?") for w in words]
    acronym_chars = [LETTER_NAMES_REV.get(wl) for wl in words_lower]
    if any(acronym_chars):
        new_words: list[str] = []
        i = 0
        while i < len(words):
            if acronym_chars[i] is not None:
                group = []
                while i < len(words) and acronym_chars[i] is not None:
                    group.append(acronym_chars[i])
                    i += 1
                new_words.append("".join(group))
            else:
                new_words.append(words[i])
                i += 1
        expansions.add(" ".join(new_words))

    # 3. Acronym reverse expansion (e.g. JD -> Jay Dee)
    expanded_letters: list[str] = []
    has_acronym = False
    for w in words:
        clean_w = w.strip(".,!?")
        if clean_w.isupper() and len(clean_w) >= 2 and all(c in LETTER_NAMES for c in clean_w):
            expanded_letters.extend([LETTER_NAMES[c].capitalize() for c in clean_w])
            has_acronym = True
        else:
            expanded_letters.append(w)
    if has_acronym:
        expansions.add(" ".join(expanded_letters))

    # 4. User-provided aliases (additive)
    if user_aliases:
        for alias in user_aliases:
            a = alias.strip()
            if a:
                expansions.add(a)

    return sorted(list(expansions))


def make_initial_prompt(wake_word: str, known_aliases: list[str]) -> tuple[str, dict[str, str]]:
    """Build dynamic question and criteria for the initial turn."""
    aliases_str = ", ".join(f"'{a}'" for a in known_aliases)
    instructions = (
        f"This speech transcript was captured by a voice assistant listening for '{wake_word}'. "
        f"Recognized name variants and spellings include: {aliases_str}. "
        "Speech recognition frequently produces ambiguous, distorted, or loose phonetic transcriptions for the wake phrase, "
        "including misheard syllables, compound words, dropped consonants, or sound-alikes. "
        f"Do not restrict recognition to exact 1:1 phonetic rhymes or literal spellings. Any utterance that begins with an ambiguous or fuzzy phonetic approximation of '{wake_word}' "
        "and expresses a question, instruction, creative banter, joke, or remark for the assistant is addressed. "
        "Determine if the speaker is addressing the voice assistant, or if this is unaddressed ambient conversation "
        "(talking to other people in the room, dinner table talk, third-person references, or media audio)."
    )
    criteria = {
        CHOICE_ADDRESSED: (
            f"The speaker is addressing the voice assistant '{wake_word}' (or loose phonetic variations, spellings, or abbreviations of it) "
            "with a question, instruction, joke, conversational banter, or request."
        ),
        CHOICE_AMBIENT: (
            "Not addressing the assistant (unrelated side conversation between humans in the room, commands to family or pets, "
            "third-person discussions about someone, or background media audio)."
        ),
    }
    return instructions, criteria


def make_followup_prompt(wake_word: str) -> tuple[str, dict[str, str]]:
    """Build dynamic question and criteria for an ongoing conversational follow-up turn."""
    instructions = (
        f"In an ongoing voice assistant conversation, the assistant listening for '{wake_word}' just spoke and the microphone is open for a follow-up. "
        f"Because this is an active dialogue, the user does NOT need to repeat the wake word '{wake_word}'. "
        "Determine whether the speaker is responding to the assistant (answering, asking for clarification, reacting to what the assistant said, or giving the next request) "
        "versus talking to someone else in the room."
    )
    criteria = {
        CHOICE_ADDRESSED: (
            "Responding to or conversing with the assistant in the active dialogue (no wake word required; answers, questions, reactions, and commands)."
        ),
        CHOICE_AMBIENT: (
            "Addressing someone else in the room (e.g. spouse, child, roommate), background noise, or unrelated side chatter."
        ),
    }
    return instructions, criteria


# Speculative STT Question Templates & Criteria
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
    """Generate dynamic criteria for System 1 early slice wake phrase verification."""
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
    "With the understanding that if it contains wake phrase '{wake_word}', "
    "it most likely is an instruction and everything following '{wake_word}' is the instruction. "
    "Is this an addressed instruction or query to {wake_word}?"
)

QUESTION_TEMPLATE_SLOT2: Final = QUESTION_TEMPLATE_SLOT1



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

