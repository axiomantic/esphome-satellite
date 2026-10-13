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
DEFAULT_THRESHOLD: Final = 0.70
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


def generate_phonetic_variants(phrase: str) -> list[str]:
    """Dynamically generate phonetic, acoustic, and orthographic variants for a wake phrase."""
    variants: set[str] = set()
    cleaned = phrase.strip()
    if not cleaned:
        return []
    variants.add(cleaned)

    norm = re.sub(r"[^\w\s]", "", cleaned)
    words = norm.split()
    if not words:
        return [cleaned]

    prefixes = {"hey", "hi", "ok", "okay", "hello"}
    has_prefix = words[0].lower() in prefixes
    core_words = words[1:] if has_prefix else words
    core_phrase = " ".join(core_words)

    # 1. Title expansions (e.g. Mr. <-> Mister, Dr. <-> Doctor)
    expanded_titles = []
    for w in core_words:
        wl = w.lower()
        if wl in TITLE_EXPANSIONS:
            expanded_titles.append(TITLE_EXPANSIONS[wl])
        elif wl in TITLE_EXPANSIONS_REV:
            expanded_titles.append(TITLE_EXPANSIONS_REV[wl])
        else:
            expanded_titles.append(w)
    title_variant = " ".join(expanded_titles)
    if title_variant.lower() != core_phrase.lower():
        variants.add(title_variant)

    # 2. Acronym expansions
    acronym_rev = []
    has_acr = False
    for w in core_words:
        w_clean = w.strip(".,!?")
        if w_clean.isupper() and len(w_clean) >= 2 and all(c in LETTER_NAMES for c in w_clean):
            acronym_rev.extend([LETTER_NAMES[c].capitalize() for c in w_clean])
            has_acr = True
        else:
            acronym_rev.append(w)
    if has_acr:
        variants.add(" ".join(acronym_rev))

    acr_fwd = []
    i = 0
    while i < len(core_words):
        wl = core_words[i].lower()
        if wl in LETTER_NAMES_REV:
            grp = []
            while i < len(core_words) and core_words[i].lower() in LETTER_NAMES_REV:
                grp.append(LETTER_NAMES_REV[core_words[i].lower()])
                i += 1
            acr_fwd.append("".join(grp))
        else:
            acr_fwd.append(core_words[i])
            i += 1
    if len(acr_fwd) != len(core_words) or any(w.isupper() for w in acr_fwd):
        variants.add(" ".join(acr_fwd))

    # 3. Phonetic spelling permutations on base/core variants
    base_pool = list(variants)
    for base in base_pool:
        bw = base.split()
        for idx, w in enumerate(bw):
            wl = w.lower().strip(".,!?")
            alts: set[str] = set()
            # Unstressed er/or/ar/ur/ah
            if wl.endswith("er"):
                alts.add(wl[:-2] + "ur")
                alts.add(wl[:-2] + "ar")
                alts.add(wl[:-2] + "ah")
            elif wl.endswith("ur") or wl.endswith("ar"):
                alts.add(wl[:-2] + "er")
            # Unstressed ens/ons/ins/ence/uns/enz
            if wl.endswith("ens"):
                alts.add(wl[:-3] + "ons")
                alts.add(wl[:-3] + "ins")
                alts.add(wl[:-3] + "ence")
                alts.add(wl[:-3] + "uns")
                alts.add(wl[:-3] + "enz")
            elif wl.endswith("ons") or wl.endswith("ins"):
                alts.add(wl[:-3] + "ens")
            # Double consonant m / mm
            if "em" in wl and "emm" not in wl:
                alts.add(wl.replace("em", "emm"))
            # ance / ans / ence
            if wl.endswith("ance"):
                alts.add(wl[:-4] + "ans")
                alts.add(wl[:-4] + "ence")
            elif wl.endswith("ans"):
                alts.add(wl[:-3] + "ance")
            # Hard c / k
            if wl.startswith("cl"):
                alts.add("kl" + wl[2:])
            elif wl.startswith("kl"):
                alts.add("cl" + wl[2:])
            # ph / f
            if "ph" in wl:
                alts.add(wl.replace("ph", "f"))

            for alt in alts:
                new_bw = list(bw)
                new_bw[idx] = alt.capitalize() if w[0].isupper() else alt
                variants.add(" ".join(new_bw))

    # 4. Prefix permutations for core phrases
    all_core = list(variants)
    for v in all_core:
        vw = v.split()
        if vw and vw[0].lower() not in prefixes:
            variants.add(f"Hey {v}")
            variants.add(f"Ok {v}")
        elif vw and vw[0].lower() in prefixes and len(vw) > 1:
            variants.add(" ".join(vw[1:]))

    # 5. Compound words (e.g. MisterClemens, JayDee)
    for v in list(variants):
        vw = v.split()
        if len(vw) == 2 and vw[0].lower() not in prefixes:
            variants.add("".join(vw))

    return sorted(list(variants))


def expand_wake_phrase(wake_phrase: str, user_aliases: list[str] | None = None) -> list[str]:
    """Dynamically generate phonetic variants for the wake phrase and append additive user aliases."""
    expansions: set[str] = set(generate_phonetic_variants(wake_phrase))

    # User-provided aliases (strictly additive)
    if user_aliases:
        for alias in user_aliases:
            a = alias.strip()
            if a:
                expansions.add(a)

    return sorted(list(expansions))


def make_initial_prompt(wake_word: str, known_aliases: list[str]) -> tuple[str, dict[str, str]]:
    """Build dynamic question and criteria for the initial turn, interpolating phonetic variants."""
    # Present up to 6 distinct representative phonetic variants and aliases
    filtered = [a for a in known_aliases if a.lower() != wake_word.lower()]
    sample = filtered[:6] if len(filtered) > 6 else filtered
    aliases_str = ", ".join(f"'{a}'" for a in sample) if sample else f"'{wake_word}'"
    instructions = (
        f"The voice satellite triggered on wake phrase '{wake_word}'. "
        f"Recognized phonetic approximations, name variants, and spellings include: {aliases_str}. "
        f"Is this utterance directly addressing the assistant '{wake_word}' (or its variants), "
        "or is it ambient bystander conversation, talking to oneself, or TV/room chatter?"
    )
    criteria = {
        CHOICE_ADDRESSED: (
            f"Directly speaking to or commanding the assistant '{wake_word}' (e.g. questions, device commands, timers, jokes)."
        ),
        CHOICE_AMBIENT: (
            "Side conversation between humans, self-talk, dictating/typing, or background chatter."
        ),
    }
    return instructions, criteria


def make_followup_prompt(wake_word: str) -> tuple[str, dict[str, str]]:
    """Build dynamic question and criteria for an ongoing conversational follow-up turn."""
    instructions = (
        f"In an ongoing voice assistant conversation, the assistant listening for '{wake_word}' just spoke and the microphone is open for a follow-up. "
        f"Because this is an active dialogue, the user does NOT need to repeat the wake word '{wake_word}'. "
        "Determine whether the speaker is responding to the assistant (answering, asking for clarification, reacting to what the assistant said, or giving the next request) "
        "versus talking to someone else in the room, talking to oneself, or room chatter."
    )
    criteria = {
        CHOICE_ADDRESSED: (
            "Responding to or conversing with the assistant in the active dialogue (no wake word required; answers, questions, reactions, and commands)."
        ),
        CHOICE_AMBIENT: (
            "Addressing someone else in the room (e.g. spouse, child, roommate), talking to oneself, background noise, or unrelated side chatter."
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
