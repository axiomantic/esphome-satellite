#!/usr/bin/env python3
"""
Synthetic Wake Word Corpus Generator & microWakeWord Dataset Builder
===================================================================

Generates rich, acoustically balanced synthetic speech training datasets for
microWakeWord using diverse synthetic voices (female, male, kids, accents) and
exhaustive phonetic permutations.

Backends Supported:
- ElevenLabs API (cloud neural TTS with diverse voice registry & Instant Voice Cloning)
- macOS 'say' (built-in zero-dependency local macOS synthesizer)
- Piper TTS (local neural TTS via piper binary)

Architecture & Implementation Notes:
- F5-TTS Zero-Shot Cloning Integration:
  - F5-TTS utilizes flow matching diffusion for zero-shot voice cloning.
  - Allows household members (self, partner, children) to record a short 3-10s
    reference sample + transcript to clone their unique timbre, pitch, and formants.
  - ElevenLabs Instant Voice Cloning (IVC) provides an equivalent cloud path via
    the /v1/voices/add API endpoint.
  - Household voices should be blended additively with default/generic voices
    (40% female, 40% male, 10% kids, 10% accents) to achieve hyper-tuned
    accuracy for residents while preventing model overfitting on ambient noise.

Features:
- Deterministic content-addressed disk cache (.cache/mww_corpus/<sha256>.wav)
- Formats audio directly for microWakeWord (16,000 Hz mono 16-bit PCM)
- Peak normalization and silence trimming via ffmpeg
- Interactive TUI wizard and headless CLI modes
"""

import os
import sys
import json
import hashlib
import argparse
import subprocess
import urllib.request
import urllib.error
import itertools
import random
import select
import tempfile
import shutil
import shlex
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union, Any

try:
    import questionary
    from questionary import Choice, Separator
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
    HAVE_TUI = True
except ImportError:
    HAVE_TUI = False

CACHE_DIR = Path(".cache/mww_corpus")
WIZARD_STATE_FILE = CACHE_DIR / "wizard_state.json"


def load_wizard_state(state_file: Optional[Path] = None) -> Dict[str, Any]:
    """Loads previously saved wizard state from disk if present."""
    target = state_file or WIZARD_STATE_FILE
    if target.is_file():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_wizard_field(key: str, value: Any, state_file: Optional[Path] = None):
    """
    Persists a single wizard input value immediately at select/input time.
    Ensures user progress is never lost if aborted, interrupted, or execution fails.
    """
    target = state_file or WIZARD_STATE_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        state = load_wizard_state(target)
        state[key] = value
        temp_file = target.with_suffix(".tmp")
        temp_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temp_file.replace(target)
    except Exception:
        pass


def get_valid_default(choices: Sequence[Any], desired_val: Any, fallback: Any = None) -> Any:
    """
    Returns desired_val if it corresponds to an existing selectable Choice in choices,
    otherwise returns fallback if present in choices, otherwise None.
    Prevents ValueError in questionary.select/checkbox.
    """
    choices_values = []
    for c in choices:
        if type(c).__name__ == "Separator":
            continue
        if hasattr(c, "value"):
            choices_values.append(c.value)
        else:
            choices_values.append(c)
    if desired_val is not None and desired_val in choices_values:
        return desired_val
    if fallback is not None and fallback in choices_values:
        return fallback
    return None


# ---------------------------------------------------------------------------
# Pipeline Versioning & Training Parameters Specification
# ---------------------------------------------------------------------------
# Semantic version for the audio synthesis and feature pipeline.
# Bump this whenever DSP post-processing, sample rates, silence trimming, or
# model inference parameters are modified to invalidate stale derived models.
PIPELINE_VERSION = "1.0.0"

AUDIO_PIPELINE_PARAMS = {
    "sample_rate_hz": 16000,
    "channels": 1,
    "sample_format": "s16le",
    "peak_norm_dbfs": -1.0,
    "silence_trim_db": -40.0,
    "silence_trim_duration_s": 0.15,
}

BACKEND_PARAMS = {
    "f5_tts": {
        "model": "F5-TTS",
        "vocoder": "vocos",
    },
    "elevenlabs": {
        "model_id": "eleven_multilingual_v2",
        "stability": 0.50,
        "similarity_boost": 0.75,
    },
    "macos_say": {
        "rate": 175,
    }
}


def compute_file_hash(path: Path) -> str:
    """Computes deterministic SHA-256 hash of a file for content-addressed verification."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        print(f"[Warning] Failed to hash file '{path}': {e}", file=sys.stderr)
        return ""


def get_pipeline_signature(backend_name: str) -> str:
    """
    Computes a deterministic hash of the pipeline version, audio DSP parameters,
    and backend synthesis parameters.
    """
    spec = {
        "pipeline_version": PIPELINE_VERSION,
        "audio_params": AUDIO_PIPELINE_PARAMS,
        "backend": backend_name,
        "backend_params": BACKEND_PARAMS.get(backend_name, {})
    }
    spec_json = json.dumps(spec, sort_keys=True)
    return hashlib.sha256(spec_json.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Curated Voice Registry
# ---------------------------------------------------------------------------
ELEVENLABS_VOICES = {
    "female": [
        {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "accent": "American", "desc": "Calm, standard female", "default": True},
        {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah", "accent": "American", "desc": "Warm, professional female", "default": True},
        {"id": "piTKgcLEGmPE4e6mEKli", "name": "Nicole", "accent": "American", "desc": "Soft, whisper female", "default": False},
        {"id": "jsCqWAovK2LkecY7zXl4", "name": "Freya", "accent": "American", "desc": "Expressive female", "default": False},
        {"id": "ThT5KcBeYPX3keUQqHPh", "name": "Dorothy", "accent": "British", "desc": "Pleasant British female", "default": False},
        {"id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte", "accent": "Swedish-English", "desc": "Accented female", "default": False},
        {"id": "Xb7hH8MSUJpSbSDYk0k2", "name": "Alice", "accent": "British", "desc": "Clear British female", "default": False},
    ],
    "male": [
        {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam", "accent": "American", "desc": "Deep American male", "default": True},
        {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni", "accent": "American", "desc": "Energetic American male", "default": False},
        {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh", "accent": "American", "desc": "Youthful American male", "default": False},
        {"id": "VR6AewLTigWG4xSOukaG", "name": "Arnold", "accent": "American", "desc": "Crisp American male", "default": False},
        {"id": "yoZ06aMxZJJ28mfd3POQ", "name": "Sam", "accent": "American", "desc": "Raspy American male", "default": False},
        {"id": "JBFqnCBsd6RMkjVDRZzb", "name": "George", "accent": "British", "desc": "Warm British male", "default": True},
        {"id": "nPczCjzI2devNBz1zQrb", "name": "Brian", "accent": "American", "desc": "Deep narrator male", "default": False},
        {"id": "N2lVS1w4EtoT3dr4eOWO", "name": "Callum", "accent": "Transatlantic", "desc": "Irish/Transatlantic male", "default": False},
    ],
    "kids": [
        {"id": "zrHiDhphv9ZnVXBqCLjz", "name": "Mimi", "accent": "American", "desc": "Teen female, animated", "default": True},
        {"id": "D38z5RcWu1voky8WS1ja", "name": "Fin", "accent": "Irish", "desc": "Youth Irish male, energetic", "default": False},
        {"id": "TX3LPaxmHKxFdv7VOQHJ", "name": "Liam", "accent": "American", "desc": "Young American male", "default": False},
    ],
    "accents": [
        {"id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda", "accent": "Australian", "desc": "Australian female", "default": True},
        {"id": "IKne3meq5aSn9X8L4xzE", "name": "Charlie", "accent": "Australian", "desc": "Australian male", "default": False},
    ],
}

MACOS_SAY_VOICES = {
    "female": ["Samantha", "Victoria", "Karen", "Fiona", "Moira", "Tessa"],
    "male": ["Alex", "Daniel", "Oliver", "Fred"],
    "kids": ["Junior", "Kathy"],
    "accents": ["Lee", "Yuri", "Milena"],
}

DEFAULT_REFERENCE_VOICES_DIR = Path("assets/reference_voices")

def get_available_macos_voices() -> Dict[str, List[str]]:
    try:
        proc = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True)
        installed = set()
        for line in proc.stdout.splitlines():
            parts = line.strip().split()
            if parts:
                installed.add(parts[0])
        filtered: Dict[str, List[str]] = {}
        for cat, vlist in MACOS_SAY_VOICES.items():
            valid = [v for v in vlist if v in installed]
            if valid:
                filtered[cat] = valid
            elif "Alex" in installed:
                filtered[cat] = ["Alex"]
        return filtered if filtered else MACOS_SAY_VOICES
    except Exception:
        return MACOS_SAY_VOICES

DEFAULT_F5_VOICE_METADATA: Dict[str, Dict[str, str]] = {
    "adam": {"name": "Adam", "category": "male", "desc": "Deep, Monotone and Commanding"},
    "claire": {"name": "Claire", "category": "female", "desc": "Goofy, Youthful, Fun & Girly"},
    "david": {"name": "David", "category": "male", "desc": "Deep, Warm, and Steady"},
    "davy": {"name": "Davy", "category": "male", "desc": "Deep, Friendly and Round"},
    "emma": {"name": "Emma", "category": "female", "desc": "Adorable and Upbeat"},
    "gigi": {"name": "Gigi", "category": "female", "desc": "Cute, Peppy, Energetic"},
    "jake": {"name": "Jake", "category": "male", "desc": "Deep, Smooth, Dramatic"},
    "joy": {"name": "Joy", "category": "female", "desc": "Happy, Sweet, Bubbly"},
    "lulu_lolipop": {"name": "Lulu Lolipop", "category": "female", "desc": "High-Pitched and Bubbly"},
    "pirate": {"name": "Pirate", "category": "accents", "desc": "Nautical, Gritty Character Accent"},
    "river": {"name": "River", "category": "female", "desc": "Relaxed, Neutral, Informative"},
    "shelly": {"name": "Shelly", "category": "female", "desc": "Warm, Natural Storytelling"},
}


def get_available_builtin_voices(backend_name: str, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns curated list of default/built-in voices for the specified backend.
    Each item contains:
      - name: str
      - id: str
      - desc: str
      - category: str
      - default: bool (whether pre-selected by default)
      - reference_audio: Optional[Path] (for F5-TTS zero-shot cloning)
      - reference_transcript: Optional[str] (for F5-TTS)
    """
    voices: List[Dict[str, Any]] = []

    if backend_name == "elevenlabs":
        for cat, vlist in ELEVENLABS_VOICES.items():
            for v in vlist:
                voices.append({
                    "id": v["id"],
                    "name": v["name"],
                    "desc": f"{v.get('desc', '')} [{v.get('accent', '')}]",
                    "category": cat,
                    "default": v.get("default", False),
                    "reference_audio": None,
                    "reference_transcript": None
                })
    elif backend_name == "f5_tts":
        ref_dir = DEFAULT_REFERENCE_VOICES_DIR
        manifest_file = ref_dir / "manifest.json"

        # 1. Manifest-driven configuration (preferred)
        if manifest_file.is_file():
            try:
                manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                default_transcript_rel = manifest_data.get("default_transcript", "transcript.txt")
                default_transcript_path = ref_dir / default_transcript_rel
                default_transcript_text = (
                    default_transcript_path.read_text(encoding="utf-8").strip()
                    if default_transcript_path.is_file()
                    else ""
                )

                for item in manifest_data.get("voices", []):
                    audio_rel = item.get("audio", f"{item['id']}.wav")
                    audio_path = ref_dir / audio_rel
                    if not audio_path.is_file():
                        continue

                    trans_text = ""
                    if "transcript_text" in item:
                        trans_text = item["transcript_text"].strip()
                    elif "transcript" in item:
                        t_path = ref_dir / item["transcript"]
                        if t_path.is_file():
                            trans_text = t_path.read_text(encoding="utf-8").strip()
                    if not trans_text:
                        trans_text = default_transcript_text

                    vid = item.get("id", audio_path.stem)
                    vname = item.get("name", audio_path.stem.replace("_", " ").title())
                    vdesc = item.get("description", "Built-in voice preset")
                    cat = item.get("category", "male")

                    voices.append({
                        "id": f"builtin_{vid}",
                        "name": vname,
                        "desc": vdesc,
                        "category": cat,
                        "default": item.get("default", True),
                        "reference_audio": audio_path,
                        "reference_transcript": trans_text
                    })
            except Exception as e:
                print(f"[Warning] Failed to parse voice manifest '{manifest_file}': {e}", file=sys.stderr)

        # 2. Fallback discovery for any standalone wav files not listed in manifest
        known_audio_files = {v["reference_audio"] for v in voices}
        female_names = {
            "claire", "emma", "gigi", "joy", "lulu_lolipop", "river", "shelly",
            "samantha", "victoria"
        }
        if ref_dir.is_dir():
            for wav_file in sorted(ref_dir.glob("*.wav")):
                if wav_file in known_audio_files:
                    continue
                txt_file = wav_file.with_suffix(".txt")
                transcript = txt_file.read_text(encoding="utf-8").strip() if txt_file.is_file() else ""
                stem = wav_file.stem.lower()
                meta = DEFAULT_F5_VOICE_METADATA.get(stem, {})
                vname = meta.get("name", wav_file.stem.replace("_", " ").title())
                vdesc = meta.get("desc", "Built-in voice preset")
                cat = meta.get("category", "female" if stem in female_names else "male")
                voices.append({
                    "id": f"builtin_{wav_file.stem}",
                    "name": vname,
                    "desc": vdesc,
                    "category": cat,
                    "default": True,
                    "reference_audio": wav_file,
                    "reference_transcript": transcript
                })
    elif backend_name == "macos_say":
        voice_pool = get_available_macos_voices()
        default_names = {"Samantha", "Alex", "Victoria", "Fred"}
        for cat, vlist in voice_pool.items():
            for vname in vlist:
                voices.append({
                    "id": vname,
                    "name": vname,
                    "desc": f"macOS system voice ({cat})",
                    "category": cat,
                    "default": vname in default_names,
                    "reference_audio": None,
                    "reference_transcript": None
                })

    return voices

# ---------------------------------------------------------------------------
# Phonetic Variation Generators
# ---------------------------------------------------------------------------
def generate_clemens_variations() -> List[str]:
    return [
        "mister clemens", "hey mister clemens", "ok mister clemens", "okay mister clemens", "hi mister clemens",
        "mr clemens", "mistah clemens", "mistuh clemens", "mister clemons", "misterclemens",
        "mistr clemens", "meester clemens", "missed her clemens", "miss tur cleh muns", "mis ter clem ens",
        "hay mister clemmons", "ey mistuh clem ins", "hey mistah clemens", "ok mistr clemons", "hi missed her clem ens",
        "heymisterclemens", "missturclemuns", "mstr clemens", "mist ur clem uns", "mister klemens",
        "a mister clemens", "hey miss ter clem mens", "mrclemens", "mister clem ins", "meahster clemens",
        "mistuh clemons", "ok mistah clemmens", "hi misterclemens", "hay mistur klemens", "ey mister clemens"
    ]


def generate_bumblebee_variations() -> List[str]:
    return [
        "bumblebee", "hey bumblebee", "ok bumblebee", "okay bumblebee", "hi bumblebee",
        "bum bull bee", "bumbulbee", "bummle bee", "bammel bee", "hey bumbelbee",
        "bum bl bee", "bumbolbee", "ok bummlebee", "hi bummbellbee", "bumbul bee",
        "bahmble bee", "bomblebee", "bumbalbee", "ok bum bull bee", "heybumblebee",
        "okbumblebee", "bumblbee", "a bumblebee", "ay bumblebee", "hey bum ble bee",
        "o k bumblebee", "oh kay bumbel bee", "hi bummble bee", "bummbell bee"
    ]


def generate_gizmo_variations() -> List[str]:
    return [
        "hey gizmo", "gizmo", "ok gizmo", "okay gizmo", "hi gizmo",
        "hey giz mo", "heygizmo", "hay gizmo", "a gizmo", "ey gizmo",
        "ay gizmo", "hey gizz mo", "ok gizzmo", "hi gizz moe", "heygeezmo",
        "haygismo", "gismo", "hey jizmo", "ok gismo", "okay gizz moe",
        "hey guizmo", "heygezmo", "ey gizzmo", "heyy gizmo", "oh kay giz mo",
        "mkay gizmo", "giz moe", "hey gihz mo", "hay gihzmoh", "hey gismoe"
    ]


def generate_chief_variations() -> List[str]:
    return [
        "hey chief", "chief", "ok chief", "okay chief", "hi chief",
        "heychief", "hay chief", "hey cheef", "a chief", "ey chief",
        "ay cheef", "hay cheef", "hey cheaf", "hey chafe", "ok cheef",
        "hi cheef", "heyyy chief", "heycheef", "hey chif", "hay chif",
        "ok chif", "hey tchief", "hey sheef", "mkay chief", "oh kay cheef",
        "o k chief", "k chief", "a cheef", "eh chief", "hey chee eff",
        "hey cheeve"
    ]


def generate_captain_variations() -> List[str]:
    return [
        "oh captain", "captain", "hey captain", "ok captain", "okay captain",
        "hi captain", "o captain", "oh cap ten", "oh cap in", "oh capn",
        "oh cap tin", "ocapn", "ohcapn", "o captin", "oh capitan",
        "ohcaptain", "hey capn", "hey cap tin", "ok capn", "okay cap ten",
        "hi cap tin", "a captain", "ah captain", "uh captain", "oh kep ten",
        "o keptin", "oh cap ton", "cap ton", "cap in", "oh cappin",
        "oak happen", "oh cap den"
    ]


def generate_computer_variations() -> List[str]:
    return [
        "ok computer", "okay computer", "computer", "hey computer", "hi computer",
        "oh kay computer", "o k computer", "okcomputer", "okaycomputer", "oh kay com pyoo ter",
        "o kay com pu ter", "ok compyooter", "ok puter", "kay puter", "o kay kahm pyoo ter",
        "oak a computer", "ok cumputer", "ok compudrr", "ok compudah", "ok compooter",
        "okay compooder", "oak hay computer", "ok compuetar", "okay computa", "mkay computer",
        "ah kay computer", "ok com pyoo dur", "o k com pew ter", "okay compewter", "ok compooda",
        "k computer", "ok comp yoo ter", "oh kay compyooter", "ok computr"
    ]


def generate_wizard_variations() -> List[str]:
    return [
        "little wizard", "hey little wizard", "ok little wizard", "okay little wizard", "hi little wizard",
        "lil wizard", "littlewizard", "hey lil wizard", "liddle wizard", "liddl wizzard",
        "lit tull wiz urd", "lih tull wiz ard", "hey liddle wizard", "ok lil wizard", "hi liddo wizzard",
        "okay liddl wizard", "a little wizard", "ay little wizard", "ey lil wizard", "hey litl wizrd",
        "litl wizrd", "mkay liddle wizard", "liddle whizz urd", "lee tul wee zard", "hey lih tul wiz urd",
        "lituhl wizard", "lid ul wiz erd", "litul wizerd", "hey lidl wizard", "okay liddle whizz ard",
        "heylittlewizard", "lilwizard", "liddo wizard", "liddlewizard", "lit uhl wizz urd"
    ]


BUILTIN_WAKE_WORDS: Dict[str, Dict[str, Any]] = {
    "mister_clemens": {
        "name": "Mr. Clemens",
        "description": "35 phonetic variations: 'mister clemens', 'hey mister clemens', etc.",
        "generator": generate_clemens_variations,
    },
    "bumblebee": {
        "name": "Bumblebee",
        "description": "29 phonetic variations: 'bumblebee', 'hey bumblebee', etc.",
        "generator": generate_bumblebee_variations,
    },
    "hey_gizmo": {
        "name": "Hey Gizmo",
        "description": "30 phonetic variations: 'hey gizmo', 'ok gizmo', etc.",
        "generator": generate_gizmo_variations,
    },
    "hey_chief": {
        "name": "Hey Chief",
        "description": "31 phonetic variations: 'hey chief', 'ok chief', etc.",
        "generator": generate_chief_variations,
    },
    "oh_captain": {
        "name": "Oh Captain",
        "description": "32 phonetic variations: 'oh captain', 'captain', etc.",
        "generator": generate_captain_variations,
    },
    "ok_computer": {
        "name": "OK Computer",
        "description": "34 phonetic variations: 'ok computer', 'okay computer', etc.",
        "generator": generate_computer_variations,
    },
    "little_wizard": {
        "name": "Little Wizard",
        "description": "35 phonetic variations: 'little wizard', 'hey little wizard', etc.",
        "generator": generate_wizard_variations,
    },
}


def parse_variations(raw_text: str) -> List[str]:
    """
    Parses comma-separated or newline-delimited phonetic variations.
    Normalizes whitespace and removes duplicates while preserving order.
    Ignores lines starting with '#' (comments) and empty lines.
    """
    lines = raw_text.replace(",", "\n").splitlines()
    cleaned: List[str] = []
    seen = set()
    for line in lines:
        line_str = line.strip()
        if not line_str or line_str.startswith("#"):
            continue
        c = " ".join(line_str.lower().split())
        if c and c not in seen:
            seen.add(c)
            cleaned.append(c)
    return cleaned


def display_variations_table(phrases: List[str], model_name: str, console: Optional[Any] = None) -> None:
    """Renders phonetic variations in a neat multi-column terminal table."""
    if not HAVE_TUI:
        return
    if console is None:
        console = Console()

    num = len(phrases)
    cols = 3 if num >= 15 else (2 if num >= 6 else 1)

    table = Table(
        title=f"Phonetic Variations for '{model_name}' ({num} total)",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
    )
    for _ in range(cols):
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Variation", style="bold white")

    per_col = (num + cols - 1) // cols
    for row_idx in range(per_col):
        row_cells = []
        for col_idx in range(cols):
            idx = row_idx + col_idx * per_col
            if idx < num:
                row_cells.extend([str(idx + 1), phrases[idx]])
            else:
                row_cells.extend(["", ""])
        table.add_row(*row_cells)

    console.print(table)


def edit_phrases_in_editor(phrases: List[str]) -> List[str]:
    """
    Opens the current phrases in the user's preferred text editor ($EDITOR, $VISUAL, nano, or vim).
    Returns the parsed phrases after editing, or original phrases if unchanged or aborted.
    """
    header = (
        "# microWakeWord Phonetic Variations Review & Editor\n"
        "# Enter one phonetic variation per line (or comma-separated).\n"
        "# Lines starting with '#' and blank lines are ignored.\n"
        "# Save and exit your editor when finished.\n"
        "# ---------------------------------------------------------------------------\n"
    )
    temp_fd, temp_path_str = tempfile.mkstemp(suffix=".txt", prefix="mww_variations_")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("\n".join(phrases))
            f.write("\n")

        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if not editor:
            for candidate in ["nano", "vim", "vi", "emacs", "code -w", "subl -w"]:
                candidate_bin = candidate.split()[0]
                if shutil.which(candidate_bin):
                    editor = candidate
                    break
        if not editor:
            editor = "nano" if shutil.which("nano") else "vi"

        cmd = shlex.split(editor) + [temp_path_str]
        res = subprocess.call(cmd)
        if res != 0:
            print(f"[Warning] Editor exited with non-zero status code: {res}")

        content = Path(temp_path_str).read_text(encoding="utf-8")
        new_phrases = parse_variations(content)
        if new_phrases:
            return new_phrases
        print("[Warning] No valid phrases found in edited file; keeping existing list.")
        return phrases
    except Exception as exc:
        print(f"[Warning] Failed to edit variations in external editor: {exc}")
        return phrases
    finally:
        try:
            os.unlink(temp_path_str)
        except OSError:
            pass


def remove_phrases_interactive(phrases: List[str]) -> List[str]:
    """Allows user to select phrases to remove using checkboxes."""
    if len(phrases) <= 1:
        if HAVE_TUI:
            Console().print("[yellow]Cannot remove: at least one phrase is required.[/yellow]")
        else:
            print("Cannot remove: at least one phrase is required.")
        return phrases

    choices = [Choice(title=p, value=p) for p in phrases]
    selected_to_remove = questionary.checkbox(
        "Select variations to REMOVE (Space to toggle, Enter to confirm):",
        choices=choices,
    ).ask()

    if not selected_to_remove:
        return phrases

    remaining = [p for p in phrases if p not in set(selected_to_remove)]
    if not remaining:
        if HAVE_TUI:
            Console().print("[yellow]Cannot remove all phrases. At least one phrase is required.[/yellow]")
        else:
            print("Cannot remove all phrases. At least one phrase is required.")
        return phrases

    return remaining


def add_phrases_interactive(phrases: List[str], console: Optional[Any] = None) -> List[str]:
    """Prompts user to type or paste new phonetic variations."""
    raw = questionary.text(
        "Enter new variation(s) [separated by commas or newlines]:"
    ).ask()

    if not raw or not raw.strip():
        return phrases

    new_items = parse_variations(raw)
    if not new_items:
        return phrases

    seen = set(phrases)
    updated = list(phrases)
    added_count = 0
    for item in new_items:
        if item not in seen:
            seen.add(item)
            updated.append(item)
            added_count += 1

    msg = f"Added {added_count} new variation(s)."
    if console:
        console.print(f"[green]{msg}[/green]")
    else:
        print(msg)

    return updated


def generate_llm_prompt(phrase: str) -> str:
    """Generates an optimized LLM prompt for creating diverse phonetic variations."""
    return (
        f"Generate 25-35 diverse phonetic variations, homophones, and acoustic respellings of the wake word phrase \"{phrase}\" for training a microWakeWord neural speech model.\n\n"
        "Requirements:\n"
        "1. Include natural conversational prefixes and omissions (e.g., 'hey', 'ok', 'okay', 'hi', or omitting the prefix entirely).\n"
        "2. Include intentional phonetic misspellings that instruct text-to-speech engines to produce slurred consonants, vowel shifts, fast speech blends, and regional dialect variations.\n"
        "3. Include both single-word contractions and spaced-out syllable breakdowns.\n"
        "4. Format the result ONLY as a comma-separated list on a single line (no numbering, markdown bullet points, or introductory commentary), e.g.:\n"
        f"   {phrase}, ...\n"
    )


def copy_to_clipboard(text: str) -> bool:
    """Attempts to copy text to system clipboard (macOS pbcopy, Linux wl-copy/xclip, Windows clip)."""
    for cmd in [["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["clip"]]:
        if shutil.which(cmd[0]):
            try:
                res = subprocess.run(cmd, input=text.encode("utf-8"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if res.returncode == 0:
                    return True
            except Exception:
                pass
    return False


def show_llm_prompt_panel(phrase: str, console: Optional[Any] = None) -> str:
    """Displays a ready-to-copy LLM prompt for generating phonetic variations."""
    prompt_text = generate_llm_prompt(phrase)
    copied = copy_to_clipboard(prompt_text)
    clip_status = " [green](Copied to clipboard!)[/green]" if copied else ""

    if HAVE_TUI:
        c = console or Console()
        c.print()
        c.print(Panel(
            f"[bold cyan]LLM Prompt for Phonetic Variations[/bold cyan]{clip_status}\n"
            f"[dim]Copy and paste this into ChatGPT, Claude, or Gemini, then paste the output below:[/dim]\n\n"
            f"[white]{prompt_text}[/white]",
            border_style="cyan",
            title="Prompt Generator",
            expand=False,
        ))
        c.print()
    else:
        print("\n" + "=" * 65)
        print(f" LLM Prompt for Phonetic Variations{' (Copied to clipboard!)' if copied else ''}")
        print("=" * 65)
        print(prompt_text)
        print("=" * 65 + "\n")

    return prompt_text


def review_phrases_fallback(phrases: List[str], model_name: str) -> List[str]:
    """Text-based review and editing loop for environments without questionary."""
    current_phrases = list(phrases)
    while True:
        print(f"\nCurrent Phonetic Variations for '{model_name}' ({len(current_phrases)} total):")
        for idx, p in enumerate(current_phrases, 1):
            print(f"  {idx:2d}. {p}")
        print("\nOptions:")
        print(f"  [1] Accept variations as-is ({len(current_phrases)} phrases) [default]")
        print("  [2] Add more variations (comma-separated)")
        print("  [3] Generate LLM prompt for phonetic variations (copies to clipboard)")
        print("  [4] Edit full list in text editor")
        print("  [5] Remove variations by numbers (comma-separated, e.g. '1, 3, 5')")
        choice = input("Select [1-5, default=1]: ").strip() or "1"
        if choice == "1":
            break
        elif choice == "2":
            new_text = input("Enter variations (comma-separated): ").strip()
            if new_text:
                new_items = parse_variations(new_text)
                seen = set(current_phrases)
                for item in new_items:
                    if item not in seen:
                        seen.add(item)
                        current_phrases.append(item)
        elif choice == "3":
            show_llm_prompt_panel(model_name.replace("_", " "))
            new_text = input("Enter variations (comma-separated): ").strip()
            if new_text:
                new_items = parse_variations(new_text)
                seen = set(current_phrases)
                for item in new_items:
                    if item not in seen:
                        seen.add(item)
                        current_phrases.append(item)
        elif choice == "4":
            current_phrases = edit_phrases_in_editor(current_phrases)
        elif choice == "5":
            rem_str = input("Enter numbers to remove (comma-separated): ").strip()
            if rem_str:
                indices_to_remove = set()
                for token in rem_str.split(","):
                    t = token.strip()
                    if t.isdigit():
                        indices_to_remove.add(int(t) - 1)
                remaining = [p for i, p in enumerate(current_phrases) if i not in indices_to_remove]
                if remaining:
                    current_phrases = remaining
                else:
                    print("Cannot remove all phrases. At least one phrase is required.")
    return current_phrases


def review_phrases_interactive(phrases: List[str], model_name: str, console: Optional[Any] = None) -> List[str]:
    """
    Presents an interactive review and editing loop for phonetic variations.
    Allows accepting, adding, removing, loading from file, or editing in $EDITOR.
    """
    if not HAVE_TUI:
        return review_phrases_fallback(phrases, model_name)

    if console is None:
        console = Console()

    current_phrases = list(phrases)

    while True:
        console.print()
        display_variations_table(current_phrases, model_name, console)
        console.print()

        action = questionary.select(
            f"Review & Edit Phonetic Variations ({len(current_phrases)} phrases):",
            choices=[
                Choice(f"Accept variations as-is ({len(current_phrases)} phrases - proceed)", value="accept"),
                Choice("Add more variations (type or paste)", value="add"),
                Choice("Generate LLM prompt for phonetic variations (copies to clipboard)", value="llm_prompt"),
                Choice("Remove variations (select with checkboxes)", value="remove"),
                Choice("Edit full list in text editor ($EDITOR / nano)", value="edit"),
                Choice("Load additional variations from a text file", value="file"),
            ]
        ).ask()

        if action is None or action == "accept":
            break
        elif action == "add":
            current_phrases = add_phrases_interactive(current_phrases, console)
        elif action == "llm_prompt":
            show_llm_prompt_panel(model_name.replace("_", " "), console)
            current_phrases = add_phrases_interactive(current_phrases, console)
        elif action == "remove":
            current_phrases = remove_phrases_interactive(current_phrases)
        elif action == "edit":
            current_phrases = edit_phrases_in_editor(current_phrases)
        elif action == "file":
            f_path_str = questionary.text("Path to text file containing variations:").ask()
            f_path = clean_path(f_path_str)
            if f_path and f_path.is_file():
                added_from_file = parse_variations(f_path.read_text(encoding="utf-8"))
                seen = set(current_phrases)
                new_count = 0
                for p in added_from_file:
                    if p not in seen:
                        seen.add(p)
                        current_phrases.append(p)
                        new_count += 1
                console.print(f"[green]Loaded {new_count} new variation(s) from '{f_path.name}'.[/green]")
            else:
                console.print(f"[yellow]File not found: {f_path_str}[/yellow]")

    return current_phrases


# ---------------------------------------------------------------------------
# Audio Processing Utilities (via ffmpeg)
# ---------------------------------------------------------------------------
def postprocess_audio(raw_input: Path, target_wav: Path) -> bool:
    """
    Standardizes audio to microWakeWord requirements:
    16,000 Hz mono 16-bit PCM, silence trimmed, normalized to -1.0 dBFS.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(raw_input),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        "-af", "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB:detection=peak,areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB:detection=peak,areverse,loudnorm=I=-16:TP=-1.0:LRA=7",
        str(target_wav)
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and target_wav.exists() and target_wav.stat().st_size > 44


def encode_multipart_formdata(fields: Dict[str, str], files: List[Tuple[str, Path]]) -> Tuple[bytes, str]:
    """Encodes fields and file attachments into standard multipart/form-data payload."""
    boundary = f"----WebKitFormBoundary{hashlib.md5(str(random.random()).encode()).hexdigest()}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(f"{value}\r\n".encode())
    for name, filepath in files:
        filename = filepath.name
        content_type = "audio/wav" if filepath.suffix.lower() == ".wav" else "audio/mpeg"
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode())
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.extend(filepath.read_bytes())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


# ---------------------------------------------------------------------------
# Household Member Voice Ingestion
# ---------------------------------------------------------------------------
class HouseholdVoice:
    def __init__(
        self,
        name: str,
        audio_path: Path,
        transcript: str = "",
        voice_id: Optional[str] = None,
        audio_hash: Optional[str] = None
    ):
        self.name = name
        self.audio_path = Path(audio_path)
        self.transcript = transcript
        self.voice_id = voice_id
        self.audio_hash = audio_hash or (compute_file_hash(self.audio_path) if self.audio_path.is_file() else "")


class VoiceCacheManager:
    """
    Manages persistent, reentrant caching of trained voice models and cloned profiles.
    Encodes:
    - PIPELINE_VERSION (explicit semantic version)
    - AUDIO_PIPELINE_PARAMS (sample rate, channels, bit depth, normalization, silence trim)
    - BACKEND_PARAMS (model, vocoder, hyperparameters)
    - Input reference audio SHA-256 hash
    - Spoken reference transcript
    """
    def __init__(self, cache_file: Optional[Path] = None):
        self.cache_file = cache_file or (CACHE_DIR / "trained_voices.json")
        self._entries: Dict[str, dict] = self._load()

    def _load(self) -> Dict[str, dict]:
        if self.cache_file.is_file():
            try:
                return json.loads(self.cache_file.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[Warning] Failed to parse voice cache {self.cache_file}: {e}", file=sys.stderr)
        return {}

    def _save(self):
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[Warning] Failed to write voice cache {self.cache_file}: {e}", file=sys.stderr)

    def compute_voice_key(self, backend: str, name: str, audio_hash: str, transcript: str) -> str:
        data = {
            "pipeline_version": PIPELINE_VERSION,
            "backend": backend,
            "backend_params": BACKEND_PARAMS.get(backend, {}),
            "audio_params": AUDIO_PIPELINE_PARAMS,
            "name": name,
            "audio_hash": audio_hash,
            "transcript": transcript
        }
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get_trained_voice(self, backend: str, name: str, audio_hash: str, transcript: str) -> Optional[dict]:
        key = self.compute_voice_key(backend, name, audio_hash, transcript)
        return self._entries.get(key)

    def register_trained_voice(
        self,
        backend: str,
        name: str,
        audio_hash: str,
        transcript: str,
        voice_id: str,
        extra_metadata: Optional[dict] = None
    ) -> str:
        key = self.compute_voice_key(backend, name, audio_hash, transcript)
        entry = {
            "name": name,
            "voice_id": voice_id,
            "backend": backend,
            "audio_hash": audio_hash,
            "transcript": transcript,
            "pipeline_version": PIPELINE_VERSION,
            "pipeline_sig": get_pipeline_signature(backend),
            "backend_params": BACKEND_PARAMS.get(backend, {}),
            "audio_params": AUDIO_PIPELINE_PARAMS,
            "metadata": extra_metadata or {}
        }
        self._entries[key] = entry
        self._save()
        return key


def clean_path(val: Any) -> Optional[Path]:
    """
    Sanitizes file path inputs:
    - Strips whitespace
    - Strips surrounding single and double quotes (e.g. from macOS Finder drag-and-drop)
    - Unescapes backslash-escaped spaces ('\\ ')
    - Expands user tilde (~ and ~user)
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    s = s.replace(r"\ ", " ")
    if not s:
        return None
    return Path(s).expanduser()


def normalize_transcript(text: str) -> str:
    """Collapses newlines, tabs, and duplicate spaces into single spaces."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def load_household_voices(
    household_dir: Optional[Union[Path, str]] = None,
    single_sample: Optional[Union[Path, str, List[Union[Path, str]]]] = None,
    single_name: Optional[Union[str, List[str]]] = None,
    single_transcript: Optional[Union[str, List[str]]] = None,
    single_transcript_file: Optional[Union[Path, str, List[Union[Path, str]]]] = None
) -> List[HouseholdVoice]:
    voices: List[HouseholdVoice] = []

    # Support multiple samples passed as a list
    if isinstance(single_sample, list):
        names = single_name if isinstance(single_name, list) else ([single_name] * len(single_sample) if single_name else [])
        transcripts = single_transcript if isinstance(single_transcript, list) else ([single_transcript] * len(single_sample) if single_transcript else [])
        trans_files = single_transcript_file if isinstance(single_transcript_file, list) else ([single_transcript_file] * len(single_sample) if single_transcript_file else [])

        for i, s in enumerate(single_sample):
            n = names[i] if i < len(names) else None
            t = transcripts[i] if i < len(transcripts) else None
            tf = trans_files[i] if i < len(trans_files) else None
            voices.extend(load_household_voices(
                single_sample=s,
                single_name=n,
                single_transcript=t,
                single_transcript_file=tf
            ))
        return voices

    clean_sample = clean_path(single_sample)
    if clean_sample and clean_sample.exists():
        name = single_name or clean_sample.stem.replace("_", " ").title()
        transcript = ""

        clean_trans_file = clean_path(single_transcript_file)
        if clean_trans_file and clean_trans_file.is_file():
            try:
                transcript = clean_trans_file.read_text(encoding="utf-8")
            except Exception as e:
                print(f"[Warning] Failed to read transcript file '{clean_trans_file}': {e}", file=sys.stderr)
        elif single_transcript:
            candidate_path = clean_path(single_transcript)
            if candidate_path and candidate_path.is_file():
                try:
                    transcript = candidate_path.read_text(encoding="utf-8")
                except Exception as e:
                    print(f"[Warning] Failed to read transcript file '{candidate_path}': {e}", file=sys.stderr)
            else:
                transcript = str(single_transcript)
        else:
            # Auto-detect companion .txt file next to single_sample
            companion_txt = clean_sample.with_suffix(".txt")
            dir_txt = clean_sample.parent / "transcript.txt"
            if companion_txt.is_file():
                try:
                    transcript = companion_txt.read_text(encoding="utf-8")
                except Exception as e:
                    print(f"[Warning] Failed to read companion transcript '{companion_txt}': {e}", file=sys.stderr)
            elif dir_txt.is_file():
                try:
                    transcript = dir_txt.read_text(encoding="utf-8")
                except Exception as e:
                    print(f"[Warning] Failed to read companion transcript '{dir_txt}': {e}", file=sys.stderr)

        voices.append(HouseholdVoice(name=name, audio_path=clean_sample, transcript=normalize_transcript(transcript)))

    clean_hdir = clean_path(household_dir)
    if clean_hdir and clean_hdir.is_dir():
        for item in sorted(clean_hdir.iterdir()):
            if item.is_dir():
                audio_file = None
                for ext in [".wav", ".mp3", ".m4a", ".flac", ".ogg"]:
                    candidate = item / f"sample{ext}"
                    if candidate.exists():
                        audio_file = candidate
                        break
                    matches = list(item.glob(f"*{ext}"))
                    if matches:
                        audio_file = matches[0]
                        break
                transcript = ""
                trans_file = item / "transcript.txt"
                if trans_file.exists():
                    transcript = trans_file.read_text(encoding="utf-8")
                if audio_file:
                    name = item.name.replace("_", " ").title()
                    voices.append(HouseholdVoice(name=name, audio_path=audio_file, transcript=normalize_transcript(transcript)))
            elif item.suffix.lower() in [".wav", ".mp3", ".m4a", ".flac", ".ogg"]:
                name = item.stem.replace("_", " ").title()
                transcript = ""
                trans_file = item.with_suffix(".txt")
                if trans_file.exists():
                    transcript = trans_file.read_text(encoding="utf-8")
                voices.append(HouseholdVoice(name=name, audio_path=item, transcript=normalize_transcript(transcript)))

    return voices


def get_interactive_transcript(sample_path: Optional[Union[Path, str]] = None) -> str:
    """
    Interactively captures reference audio transcript supporting:
    - Automatic companion .txt detection (sample.txt or transcript.txt)
    - File path selection (bypasses terminal line length / canonical buffer limits)
    - Multi-line pasting (safe against newlines corrupting subsequent prompts)
    - Direct editing in $EDITOR / nano
    """
    clean_sample = clean_path(sample_path)
    if clean_sample:
        companion_txt = clean_sample.with_suffix(".txt")
        dir_txt = clean_sample.parent / "transcript.txt"
        candidate = None
        if companion_txt.is_file():
            candidate = companion_txt
        elif dir_txt.is_file():
            candidate = dir_txt

        if candidate:
            try:
                content = candidate.read_text(encoding="utf-8").strip()
                preview = content[:70] + ("..." if len(content) > 70 else "")
                print(f"\n   Detected companion transcript: {candidate}")
                print(f"   Preview: \"{preview}\"")
                use_comp = input("   Use this companion transcript? [Y/n]: ").strip().lower()
                if use_comp not in ("n", "no"):
                    return normalize_transcript(content)
            except Exception as e:
                print(f"   [Warning] Could not read companion file {candidate}: {e}", file=sys.stderr)

    print("\n   Reference Audio Transcript:")
    print("   (Spoken text helps F5-TTS align phonemes for hyper-accurate voice cloning)")
    print("   [1] Point to a .txt file (recommended: avoids terminal line limits)")
    print("   [2] Paste or type transcript into terminal (multi-line supported)")
    print("   [3] Open in text editor ($EDITOR / nano)")
    print("   [4] Skip (no transcript)")

    choice = input("   Select [1-4, default=1]: ").strip() or "1"

    # Direct file path entered at menu prompt
    cand_choice = clean_path(choice)
    if cand_choice and (cand_choice.is_file() or choice.lower().endswith(".txt")):
        try:
            return normalize_transcript(cand_choice.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"   [Error] Could not read file '{choice}': {e}", file=sys.stderr)

    if choice == "1":
        while True:
            path_str = input("   Enter path to transcript file (.txt, or empty to skip): ").strip()
            if not path_str:
                return ""
            fpath = clean_path(path_str)
            if fpath and fpath.is_file():
                try:
                    return normalize_transcript(fpath.read_text(encoding="utf-8"))
                except Exception as e:
                    print(f"   [Error] Failed to read {fpath}: {e}", file=sys.stderr)
            else:
                print(f"   File not found: '{path_str}'. Please try again.")

    elif choice == "2":
        print("   Paste transcript below.")
        print("   Type 'EOF' or 'END' on a new line, or press Ctrl-D when finished:")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip() in ("EOF", "END", ":wq"):
                break
            # If line looks like an empty line, check if more lines are immediately buffered in stdin
            if not line.strip() and lines:
                has_more = False
                try:
                    r, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if r:
                        has_more = True
                except Exception:
                    pass
                if not has_more:
                    break
            lines.append(line)
        raw_text = "\n".join(lines).strip()
        # If the user pasted a single line that happens to be an existing file path:
        cand_raw = clean_path(raw_text)
        if cand_raw and cand_raw.is_file():
            try:
                return normalize_transcript(cand_raw.read_text(encoding="utf-8"))
            except Exception:
                pass
        return normalize_transcript(raw_text)

    elif choice == "3":
        editor = os.environ.get("EDITOR") or ("nano" if sys.platform != "win32" else "notepad")
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w+", delete=False, encoding="utf-8") as tf:
            tf.write("# Paste or type the transcript for your voice sample below.\n")
            tf.write("# Lines beginning with '#' will be ignored.\n")
            tf.write("# Save and close when finished.\n\n")
            tf.flush()
            temp_path = tf.name
        try:
            subprocess.run([editor, temp_path], check=True)
            content_lines = []
            for l in Path(temp_path).read_text(encoding="utf-8").splitlines():
                if not l.strip().startswith("#"):
                    content_lines.append(l)
            return normalize_transcript("\n".join(content_lines))
        except Exception as e:
            print(f"   [Editor Error]: {e}", file=sys.stderr)
            return ""
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    return ""


# ---------------------------------------------------------------------------
# TTS Backend Implementations
# ---------------------------------------------------------------------------
class ElevenLabsBackend:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.elevenlabs.io/v1/text-to-speech"

    def get_existing_voices(self) -> Dict[str, str]:
        """Returns dict of voice_name -> voice_id from user account."""
        url = "https://api.elevenlabs.io/v1/voices"
        req = urllib.request.Request(url, headers={"xi-api-key": self.api_key})
        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return {v["name"]: v["voice_id"] for v in data.get("voices", [])}
        except Exception as e:
            print(f"[ElevenLabs Voices Error] {e}", file=sys.stderr)
        return {}

    def clone_voice(self, name: str, audio_path: Path, description: str = "") -> Optional[str]:
        """Clones a voice via Instant Voice Cloning (IVC). POST /v1/voices/add"""
        existing = self.get_existing_voices()
        if name in existing:
            print(f"[ElevenLabs IVC] Reusing existing cloned voice '{name}' ({existing[name]})")
            return existing[name]

        url = "https://api.elevenlabs.io/v1/voices/add"
        fields = {"name": name, "description": description or f"Household voice profile for {name}"}
        files = [("files", audio_path)]
        body, content_type = encode_multipart_formdata(fields, files)

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": content_type
            }
        )
        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status in (200, 201):
                    res_json = json.loads(resp.read().decode("utf-8"))
                    vid = res_json.get("voice_id")
                    print(f"[ElevenLabs IVC] Successfully cloned '{name}' -> voice_id: {vid}")
                    return vid
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="replace")
            print(f"[ElevenLabs IVC Error] HTTP {e.code}: {err_msg}", file=sys.stderr)
        except Exception as e:
            print(f"[ElevenLabs IVC Error] {e}", file=sys.stderr)
        return None

    def synthesize(self, text: str, voice_id: str, out_path: Path) -> bool:
        url = f"{self.base_url}/{voice_id}"
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": round(random.uniform(0.35, 0.65), 2),
                "similarity_boost": round(random.uniform(0.70, 0.85), 2),
                "style": round(random.uniform(0.0, 0.20), 2),
                "use_speaker_boost": True
            }
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg"
            }
        )
        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status == 200:
                    temp_mp3 = out_path.with_suffix(".temp.mp3")
                    with open(temp_mp3, "wb") as f:
                        f.write(resp.read())
                    ok = postprocess_audio(temp_mp3, out_path)
                    if temp_mp3.exists():
                        temp_mp3.unlink()
                    return ok
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="replace")
            print(f"[ElevenLabs Error] HTTP {e.code}: {err_msg}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"[ElevenLabs Error] {e}", file=sys.stderr)
            return False
        return False


def install_f5_tts_dependencies(console: Optional[Any] = None) -> bool:
    """
    Installs f5-tts, torch, and torchaudio into the active Python environment.
    Uses uv if available, falling back to pip.
    """
    msg = "Installing F5-TTS and PyTorch dependencies (this may take a minute)..."
    if console:
        console.print(f"\n[bold cyan]{msg}[/bold cyan]")
    else:
        print(f"\n{msg}")

    if shutil.which("uv"):
        cmd = ["uv", "pip", "install", "f5-tts", "torch", "torchaudio"]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "f5-tts", "torch", "torchaudio"]

    try:
        res = subprocess.run(cmd, check=False)
        if res.returncode == 0:
            if console:
                console.print("[bold green]F5-TTS installed successfully![/bold green]\n")
            else:
                print("F5-TTS installed successfully!\n")
            return True
        else:
            err_msg = f"Installation command exited with code {res.returncode}."
            if console:
                console.print(f"[bold red]{err_msg}[/bold red]")
            else:
                print(err_msg, file=sys.stderr)
            return False
    except Exception as e:
        err_msg = f"Failed to run installer: {e}"
        if console:
            console.print(f"[bold red]{err_msg}[/bold red]")
        else:
            print(err_msg, file=sys.stderr)
        return False


class F5TTSBackend:
    def __init__(self):
        self.cli_binary = self._find_cli()

    def _find_cli(self) -> Optional[str]:
        for bin_name in ["f5-tts_infer-cli", "f5-tts"]:
            found = shutil.which(bin_name)
            if found:
                return found
            venv_bin = Path(sys.executable).parent
            cand = venv_bin / bin_name
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
        return None

    def is_available(self) -> bool:
        if self._find_cli() is not None:
            return True
        try:
            import f5_tts  # noqa: F401
            return True
        except ImportError:
            return False

    def synthesize(self, text: str, ref_audio: Path, ref_text: str, out_path: Path) -> bool:
        if not ref_audio.exists():
            print(f"[F5-TTS Error] Reference audio '{ref_audio}' does not exist.", file=sys.stderr)
            return False

        temp_out = out_path.with_suffix(".temp.wav")
        if self.cli_binary:
            cmd = [
                self.cli_binary,
                "--model", "F5-TTS",
                "--ref_audio", str(ref_audio),
                "--ref_text", ref_text if ref_text else "",
                "--gen_text", text,
                "--output_file", str(temp_out)
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0 and temp_out.exists():
                ok = postprocess_audio(temp_out, out_path)
                if temp_out.exists():
                    temp_out.unlink()
                return ok

        # Python API fallback
        try:
            from f5_tts.infer.utils_infer import infer_process, load_model, load_vocoder
            import soundfile as sf
            vocoder = load_vocoder()
            model = load_model("F5-TTS")
            wav, sr, _ = infer_process(
                ref_audio=str(ref_audio),
                ref_text=ref_text if ref_text else "",
                gen_text=text,
                model_obj=model,
                vocoder=vocoder
            )
            sf.write(str(temp_out), wav, sr)
            if temp_out.exists():
                ok = postprocess_audio(temp_out, out_path)
                if temp_out.exists():
                    temp_out.unlink()
                return ok
        except Exception as e:
            print(f"[F5-TTS Error] Execution failed: {e}", file=sys.stderr)
            print("To use local zero-shot voice cloning with F5-TTS, install via: pip install f5-tts torch torchaudio", file=sys.stderr)
            return False

        return False


class MacOSSayBackend:
    def synthesize(self, text: str, voice_name: str, out_path: Path) -> bool:
        temp_aiff = out_path.with_suffix(".temp.aiff")
        cmd = ["say", "-v", voice_name, "-o", str(temp_aiff), text]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0 and temp_aiff.exists():
            ok = postprocess_audio(temp_aiff, out_path)
            if temp_aiff.exists():
                temp_aiff.unlink()
            return ok
        return False


# ---------------------------------------------------------------------------
# Corpus Generation Orchestrator
# ---------------------------------------------------------------------------
class VoiceSpec:
    def __init__(
        self,
        voice_id: str,
        voice_name: str,
        category: str = "generic",
        household: Optional[HouseholdVoice] = None
    ):
        self.voice_id = voice_id
        self.voice_name = voice_name
        self.category = category
        self.household = household


def sample_voices(
    category_distribution: Dict[str, float],
    total_count: int,
    voice_pool: dict,
    household_voices: Optional[List[HouseholdVoice]] = None,
    household_ratio: float = 0.50,
    selected_builtin_voices: Optional[List[VoiceSpec]] = None
) -> List[VoiceSpec]:
    """
    Returns a list of VoiceSpec instances sampled according to demographic distribution,
    household voice ratio, and explicit built-in voice selection.
    Default distribution: 40% female, 40% male, 10% kids, 10% accents.
    """
    selected: List[VoiceSpec] = []

    if household_voices and len(household_voices) > 0 and household_ratio > 0.0:
        h_count = min(total_count, int(round(total_count * household_ratio)))
        for i in range(h_count):
            hv = household_voices[i % len(household_voices)]
            vid = hv.voice_id or hv.name.lower().replace(" ", "_")
            selected.append(VoiceSpec(voice_id=vid, voice_name=hv.name, category="household", household=hv))
        generic_count = total_count - len(selected)
    else:
        generic_count = total_count

    if generic_count > 0:
        if selected_builtin_voices and len(selected_builtin_voices) > 0:
            for i in range(generic_count):
                bv = selected_builtin_voices[i % len(selected_builtin_voices)]
                selected.append(bv)
        elif voice_pool:
            generic_selected: List[VoiceSpec] = []
            for cat, ratio in category_distribution.items():
                count = int(round(generic_count * ratio))
                pool = voice_pool.get(cat, [])
                if not pool:
                    continue
                for _ in range(count):
                    item = random.choice(pool)
                    if isinstance(item, dict):
                        generic_selected.append(VoiceSpec(voice_id=item["id"], voice_name=item["name"], category=cat))
                    else:
                        generic_selected.append(VoiceSpec(voice_id=item, voice_name=item, category=cat))
            while len(generic_selected) < generic_count:
                cat = random.choice(list(category_distribution.keys()))
                pool = voice_pool.get(cat, [])
                if pool:
                    item = random.choice(pool)
                    if isinstance(item, dict):
                        generic_selected.append(VoiceSpec(voice_id=item["id"], voice_name=item["name"], category=cat))
                    else:
                        generic_selected.append(VoiceSpec(voice_id=item, voice_name=item, category=cat))
            selected.extend(generic_selected[:generic_count])

    if len(selected) < total_count and household_voices:
        while len(selected) < total_count:
            hv = random.choice(household_voices)
            vid = hv.voice_id or hv.name.lower().replace(" ", "_")
            selected.append(VoiceSpec(voice_id=vid, voice_name=hv.name, category="household", household=hv))

    random.shuffle(selected)
    return selected[:total_count]


def get_sample_cache_key(backend_name: str, vspec: VoiceSpec, phrase: str) -> str:
    """
    Computes content-addressed cache key encoding:
    - PIPELINE_VERSION
    - AUDIO_PIPELINE_PARAMS
    - BACKEND_PARAMS
    - backend_name
    - voice identity / audio_hash / transcript
    - target phrase
    """
    voice_token = (
        f"{vspec.household.audio_hash}_{vspec.household.transcript}_{vspec.household.name}"
        if vspec.household
        else str(vspec.voice_id)
    )
    spec = {
        "pipeline_version": PIPELINE_VERSION,
        "audio_params": AUDIO_PIPELINE_PARAMS,
        "backend": backend_name,
        "backend_params": BACKEND_PARAMS.get(backend_name, {}),
        "voice": voice_token,
        "phrase": phrase
    }
    serialized = json.dumps(spec, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def is_corpus_complete(
    output_dir: Path,
    expected_count: int,
    model_name: str,
    backend_name: str,
    active_household: List[HouseholdVoice],
    builtin_voices: Optional[List[str]] = None
) -> bool:
    """
    Validates if an output directory already contains a complete, valid corpus
    matching the exact pipeline signature, household voice audio hashes, and
    selected built-in voices.
    """
    manifest_file = output_dir / "manifest.json"
    if not manifest_file.is_file():
        return False
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        if data.get("model") != model_name:
            return False
        if data.get("backend") != backend_name:
            return False
        if data.get("pipeline_version") != PIPELINE_VERSION:
            return False
        if data.get("pipeline_signature") != get_pipeline_signature(backend_name):
            return False
        if data.get("total_samples", 0) < expected_count:
            return False

        cached_hashes = data.get("household_voice_hashes", {})
        for hv in active_household:
            if cached_hashes.get(hv.name) != hv.audio_hash:
                return False

        if builtin_voices is not None:
            cached_builtin = data.get("builtin_voices", [])
            c_set = set(v.lower().split()[0] for v in cached_builtin)
            b_set = set(v.lower().split()[0] for v in builtin_voices)
            if c_set != b_set:
                return False

        samples = data.get("samples", [])
        if len(samples) < expected_count:
            return False
        for s in samples[:expected_count]:
            fpath = output_dir / s["filename"]
            if not fpath.is_file() or fpath.stat().st_size < 44:
                return False
        return True
    except Exception:
        return False


def generate_corpus(
    model_name: str,
    phrases: List[str],
    backend_name: str,
    count: int,
    output_dir: Path,
    api_key: Optional[str] = None,
    distribution: Optional[Dict[str, float]] = None,
    household_voices: Optional[List[HouseholdVoice]] = None,
    household_ratio: float = 0.50,
    builtin_voices: Optional[List[str]] = None,
    force: bool = False
) -> int:
    """
    Generates synthetic speech corpus saving to output_dir with content caching.
    Reentrantly caches derived models and synthetic clips using deterministic pipeline parameters.
    """
    if distribution is None:
        distribution = {"female": 0.40, "male": 0.40, "kids": 0.10, "accents": 0.10}

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    backend = None
    voice_pool = {}
    active_household: List[HouseholdVoice] = []
    selected_builtin_vspecs: List[VoiceSpec] = []
    voice_cache = VoiceCacheManager()
    pipeline_sig = get_pipeline_signature(backend_name)

    # 1. Resolve selected built-in voices if requested
    if builtin_voices:
        all_builtin = get_available_builtin_voices(backend_name, api_key)
        name_map = {v["name"].lower(): v for v in all_builtin}
        id_map = {v["id"].lower(): v for v in all_builtin}

        for bv_name in builtin_voices:
            clean_name = bv_name.strip().lower()
            item = name_map.get(clean_name) or id_map.get(clean_name)
            if not item:
                for k, candidate in name_map.items():
                    if clean_name in k:
                        item = candidate
                        break
            if item:
                if item["reference_audio"]:
                    ref_hv = HouseholdVoice(
                        name=f"{item['name']} (Built-in)",
                        audio_path=item["reference_audio"],
                        transcript=item["reference_transcript"],
                        voice_id=item["id"]
                    )
                    selected_builtin_vspecs.append(VoiceSpec(
                        voice_id=item["id"],
                        voice_name=ref_hv.name,
                        category=item["category"],
                        household=ref_hv
                    ))
                else:
                    selected_builtin_vspecs.append(VoiceSpec(
                        voice_id=item["id"],
                        voice_name=item["name"],
                        category=item["category"]
                    ))

    # Adjust household ratio based on presence of voices
    has_household = bool(household_voices and len(household_voices) > 0)
    has_builtin = bool(selected_builtin_vspecs and len(selected_builtin_vspecs) > 0)

    if has_household and not has_builtin:
        effective_ratio = 1.0
    elif not has_household and has_builtin:
        effective_ratio = 0.0
    else:
        effective_ratio = household_ratio

    if backend_name == "elevenlabs":
        if not api_key:
            api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not api_key:
            print("Error: ElevenLabs API key is required. Pass --api-key or export ELEVENLABS_API_KEY.", file=sys.stderr)
            return 0
        backend = ElevenLabsBackend(api_key)
        voice_pool = ELEVENLABS_VOICES

        if household_voices:
            print(f"Processing {len(household_voices)} household voice sample(s) for ElevenLabs IVC...")
            for hv in household_voices:
                if not hv.audio_hash and hv.audio_path.is_file():
                    hv.audio_hash = compute_file_hash(hv.audio_path)
                cached = voice_cache.get_trained_voice("elevenlabs", hv.name, hv.audio_hash, hv.transcript)
                if cached and cached.get("voice_id") and not force:
                    hv.voice_id = cached["voice_id"]
                    print(f"Reusing cached trained voice profile for '{hv.name}' (Voice ID: {hv.voice_id})")
                    active_household.append(hv)
                else:
                    if not hv.voice_id or force:
                        print(f"Cloning household voice '{hv.name}' ({hv.audio_path.name})...")
                        cloned_id = backend.clone_voice(hv.name, hv.audio_path)
                        if cloned_id:
                            hv.voice_id = cloned_id
                            voice_cache.register_trained_voice("elevenlabs", hv.name, hv.audio_hash, hv.transcript, cloned_id)
                            active_household.append(hv)
                        else:
                            print(f"Warning: Failed to clone '{hv.name}'. Falling back to generic voices for this profile.", file=sys.stderr)
                    else:
                        voice_cache.register_trained_voice("elevenlabs", hv.name, hv.audio_hash, hv.transcript, hv.voice_id)
                        active_household.append(hv)

    elif backend_name == "f5_tts":
        backend = F5TTSBackend()
        if not backend.is_available():
            print("Error: F5-TTS is not available in PATH or current Python environment.", file=sys.stderr)
            print("To use local zero-shot voice cloning with F5-TTS, install via:", file=sys.stderr)
            print("  pip install f5-tts torch torchaudio", file=sys.stderr)
            return 0
        if not household_voices and not selected_builtin_vspecs:
            print("Error: F5-TTS is a zero-shot voice cloning model and requires reference audio.", file=sys.stderr)
            print("Provide at least one reference voice using --voice-sample or select built-in reference voices.", file=sys.stderr)
            return 0

        if household_voices:
            for hv in household_voices:
                if not hv.audio_hash and hv.audio_path.is_file():
                    hv.audio_hash = compute_file_hash(hv.audio_path)
                cached = voice_cache.get_trained_voice("f5_tts", hv.name, hv.audio_hash, hv.transcript)
                vid = hv.voice_id or (cached.get("voice_id") if cached else None) or hv.name.lower().replace(" ", "_")
                hv.voice_id = vid
                if not cached or force:
                    voice_cache.register_trained_voice("f5_tts", hv.name, hv.audio_hash, hv.transcript, vid)
                    print(f"Registered voice model specification for '{hv.name}' (hash: {hv.audio_hash[:10]})")
                else:
                    print(f"Reusing verified trained voice model for '{hv.name}' (hash: {hv.audio_hash[:10]})")
                active_household.append(hv)

        # Register built-in reference voices in voice_cache for F5-TTS
        for bv in selected_builtin_vspecs:
            if bv.household:
                if not bv.household.audio_hash and bv.household.audio_path.is_file():
                    bv.household.audio_hash = compute_file_hash(bv.household.audio_path)
                voice_cache.register_trained_voice("f5_tts", bv.household.name, bv.household.audio_hash, bv.household.transcript, bv.voice_id)

    elif backend_name == "macos_say":
        backend = MacOSSayBackend()
        voice_pool = get_available_macos_voices()
        if household_voices:
            print("Notice: macOS 'say' backend does not support neural voice cloning. Proceeding with system voices.")
    else:
        print(f"Error: Unknown backend '{backend_name}'.", file=sys.stderr)
        return 0

    if not force and is_corpus_complete(output_dir, count, model_name, backend_name, active_household, builtin_voices):
        print(f"\n[Reentrant Cache Hit] Output directory '{output_dir}' already contains {count} trained samples.")
        print(f"Verified against pipeline signature {pipeline_sig} and matching reference audio file hashes.")
        print("Dataset is complete and up to date. Use --force to re-synthesize.")
        return count

    voices = sample_voices(
        distribution,
        count,
        voice_pool,
        active_household,
        effective_ratio,
        selected_builtin_voices=selected_builtin_vspecs
    )
    if not voices:
        print("Error: No voices available for generation.", file=sys.stderr)
        return 0

    generated = 0
    manifest = []

    print(f"Target Model:       {model_name}")
    print(f"Synthesis Backend:  {backend_name}")
    print(f"Pipeline Signature: {pipeline_sig} (v{PIPELINE_VERSION})")
    print(f"Variations Pool:    {len(phrases)} unique phonetic forms")
    print(f"Target Count:       {count} audio files")
    if active_household:
        print(f"Household Voices:   {len(active_household)} ({effective_ratio*100:.0f}% allocation)")
    if selected_builtin_vspecs:
        print(f"Built-in Voices:    {len(selected_builtin_vspecs)} ({', '.join(v.voice_name for v in selected_builtin_vspecs)})")
    print(f"Output Directory:   {output_dir}")
    print("-" * 65)

    use_progress = HAVE_TUI and sys.stdout.isatty()
    progress_bar = None
    task_id = None

    if use_progress:
        progress_bar = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeRemainingColumn(),
            console=Console()
        )
        progress_bar.start()
        task_id = progress_bar.add_task("Synthesizing training audio...", total=count)

    try:
        for i, vspec in enumerate(voices):
            phrase = random.choice(phrases)

            # Content-addressed cache key encoding deterministic parameters
            cache_key = get_sample_cache_key(backend_name, vspec, phrase)
            cached_file = CACHE_DIR / f"{cache_key}.wav"

            if not force and cached_file.exists() and cached_file.stat().st_size > 44:
                hit = True
            else:
                hit = False
                if backend_name == "f5_tts" and vspec.household:
                    ok = backend.synthesize(phrase, vspec.household.audio_path, vspec.household.transcript, cached_file)
                else:
                    ok = backend.synthesize(phrase, vspec.voice_id, cached_file)
                if not ok:
                    if not use_progress:
                        print(f"[{i+1}/{count}] FAILED: '{phrase}' (voice: {vspec.voice_name})")
                    continue

            clean_vname = vspec.voice_name.lower().replace(" ", "_")
            out_name = f"{cache_key[:12]}_{clean_vname}_{hashlib.md5(phrase.encode()).hexdigest()[:6]}.wav"
            dest_file = output_dir / out_name

            dest_file.write_bytes(cached_file.read_bytes())
            generated += 1

            manifest.append({
                "filename": out_name,
                "phrase": phrase,
                "voice": vspec.voice_name,
                "voice_id": vspec.voice_id,
                "category": vspec.category,
                "backend": backend_name,
                "cache_hit": hit,
                "sha256": cache_key
            })

            status = "CACHE" if hit else "SYNTH"
            if progress_bar and task_id is not None:
                progress_bar.update(task_id, completed=i + 1, description=f"[{status}] {vspec.voice_name}: '{phrase}'")
            else:
                print(f"[{i+1:4d}/{count:4d}] [{status:5s}] '{phrase}' ({vspec.voice_name}) -> {out_name}")
    finally:
        if progress_bar:
            progress_bar.stop()

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "model": model_name,
            "total_samples": generated,
            "backend": backend_name,
            "pipeline_version": PIPELINE_VERSION,
            "pipeline_signature": pipeline_sig,
            "audio_params": AUDIO_PIPELINE_PARAMS,
            "distribution": distribution,
            "household_voices": [hv.name for hv in active_household],
            "household_voice_hashes": {hv.name: hv.audio_hash for hv in active_household},
            "household_ratio": effective_ratio if active_household else 0.0,
            "builtin_voices": [bv.voice_name for bv in selected_builtin_vspecs],
            "samples": manifest
        }, f, indent=2)

    print("-" * 65)
    print(f"Corpus generation complete: {generated} valid 16kHz PCM audio files written to {output_dir}")
    print(f"Manifest written to: {manifest_path}")
    return generated


# ---------------------------------------------------------------------------
# Interactive TUI Wizard (using questionary & rich)
# ---------------------------------------------------------------------------
def run_tui_wizard():
    if not HAVE_TUI:
        _run_fallback_wizard()
        return

    console = Console()
    console.print()
    console.print(Panel(
        "[bold cyan]microWakeWord Synthetic Dataset Generator[/bold cyan]\n"
        "[dim]Multi-Voice Neural Synthesis, Built-in Voice Registry & Deterministic Pipeline[/dim]",
        border_style="cyan"
    ))

    prev_state = load_wizard_state()

    # 1. Target Wake Word Model
    model_choices = [
        Choice(f"{meta['name']:<14} ({meta['description']})", value=m_id)
        for m_id, meta in BUILTIN_WAKE_WORDS.items()
    ]
    model_choices.append(Choice("Custom Phrase...", value="custom"))

    default_model = get_valid_default(model_choices, prev_state.get("model_choice"))
    model_choice = questionary.select(
        "1. Select Target Wake Word Model:",
        choices=model_choices,
        default=default_model
    ).ask()
    if model_choice is None:
        console.print("[dim]Aborted.[/dim]")
        return
    save_wizard_field("model_choice", model_choice)

    if model_choice in BUILTIN_WAKE_WORDS:
        model_name = model_choice
        save_wizard_field("model_name", model_name)
        phrases = BUILTIN_WAKE_WORDS[model_choice]["generator"]()
    else:
        prev_custom = prev_state.get("custom_wake_word", "")
        custom_input = questionary.text(
            "Enter custom wake word identifier (e.g. 'hey_computer', 'jarvis'):",
            default=prev_custom
        ).ask()
        if not custom_input or not custom_input.strip():
            console.print("[dim]Aborted.[/dim]")
            return
        save_wizard_field("custom_wake_word", custom_input)
        model_name = custom_input.strip().lower().replace(" ", "_")
        save_wizard_field("model_name", model_name)

        input_mode_choices = [
            Choice("Type / paste phonetic variations (comma-separated or multi-line)", value="text"),
            Choice("Load variations from a text file (one variant per line)", value="file"),
            Choice("Single base phrase only (no phonetic permutations)", value="single"),
        ]
        input_mode = questionary.select(
            "How would you like to provide phonetic variations for this wake word?",
            choices=input_mode_choices,
            default=get_valid_default(input_mode_choices, prev_state.get("input_mode"))
        ).ask()
        if input_mode is None:
            return
        save_wizard_field("input_mode", input_mode)

        if input_mode == "file":
            prev_file = prev_state.get("variations_file", "")
            f_path_str = questionary.text(
                "Path to text file containing variations:",
                default=prev_file
            ).ask()
            if f_path_str is not None:
                save_wizard_field("variations_file", f_path_str)
            f_path = clean_path(f_path_str)
            if not f_path or not f_path.is_file():
                console.print(f"[yellow]File '{f_path_str}' not found. Using default base phrase.[/yellow]")
                phrases = [model_name.replace("_", " ")]
            else:
                phrases = parse_variations(f_path.read_text(encoding="utf-8"))
        elif input_mode == "text":
            show_llm_prompt_panel(model_name.replace("_", " "), console)
            console.print("[dim]Enter phonetic variants separated by commas or newlines (or press Enter to keep base phrase):[/dim]")
            prev_var_text = prev_state.get("variations_text", "")
            var_text = questionary.text(
                "Phonetic variations:",
                default=prev_var_text
            ).ask()
            if var_text is not None:
                save_wizard_field("variations_text", var_text)
            phrases = parse_variations(var_text or "")
        else:
            prev_base = prev_state.get("base_phrase", model_name.replace("_", " "))
            base_phrase = questionary.text("Enter base phrase:", default=prev_base).ask()
            if base_phrase is not None:
                save_wizard_field("base_phrase", base_phrase)
            phrases = [base_phrase.strip().lower()] if base_phrase else [model_name.replace("_", " ")]

        if not phrases:
            phrases = [model_name.replace("_", " ")]

    phrases = review_phrases_interactive(phrases, model_name, console)
    if not phrases:
        phrases = [model_name.replace("_", " ")]
    save_wizard_field("phrases", phrases)

    console.print(f"[bold green]Finalized {len(phrases)} phonetic variation(s) for '{model_name}':[/bold green] [dim]{', '.join(phrases[:8])}{'...' if len(phrases) > 8 else ''}[/dim]\n")

    # 2. Synthesis Backend
    backend_choices = [
        Choice("ElevenLabs API (High-fidelity neural TTS, diverse voice registry, Instant Voice Cloning)", value="elevenlabs"),
        Choice("F5-TTS (Local zero-shot neural voice cloning via diffusion - offline)", value="f5_tts"),
        Choice("macOS 'say' (Fast local offline system voices - zero API key required)", value="macos_say"),
    ]
    backend_choice = questionary.select(
        "2. Select Speech Synthesis Backend:",
        choices=backend_choices,
        default=get_valid_default(backend_choices, prev_state.get("backend_choice"))
    ).ask()
    if backend_choice is None:
        console.print("[dim]Aborted.[/dim]")
        return
    save_wizard_field("backend_choice", backend_choice)

    api_key = None
    if backend_choice == "elevenlabs":
        env_key = os.environ.get("ELEVENLABS_API_KEY", "")
        if env_key:
            use_env = questionary.confirm(f"Use existing ELEVENLABS_API_KEY from environment ({env_key[:6]}...)?", default=True).ask()
            if use_env is None:
                return
            if use_env:
                api_key = env_key
        if not api_key:
            api_key = questionary.password("Enter ElevenLabs API Key:").ask()
            if not api_key:
                console.print("[yellow]No ElevenLabs API key provided. Falling back to local macOS 'say' backend.[/yellow]")
                backend_choice = "macos_say"
                save_wizard_field("backend_choice", backend_choice)

    elif backend_choice == "f5_tts":
        f5_backend = F5TTSBackend()
        if not f5_backend.is_available():
            console.print("\n[yellow]Notice: F5-TTS is not currently installed in this Python environment.[/yellow]")
            console.print("[dim]Local zero-shot neural voice cloning requires: f5-tts, torch, torchaudio[/dim]\n")
            f5_choices = [
                Choice("Install F5-TTS now (auto-install into current environment)", value="install"),
                Choice("Switch to macOS 'say' (built-in offline voices, zero dependencies)", value="macos_say"),
                Choice("Switch to ElevenLabs API (cloud neural synthesis)", value="elevenlabs"),
                Choice("Abort wizard", value="abort"),
            ]
            f5_action = questionary.select(
                "How would you like to proceed?",
                choices=f5_choices,
                default=get_valid_default(f5_choices, prev_state.get("f5_action"))
            ).ask()
            if f5_action is None or f5_action == "abort":
                console.print("[dim]Aborted.[/dim]")
                return
            save_wizard_field("f5_action", f5_action)
            if f5_action == "install":
                installed = install_f5_tts_dependencies(console=console)
                if not installed:
                    console.print("[yellow]F5-TTS installation was unsuccessful. Falling back to macOS 'say'.[/yellow]")
                    backend_choice = "macos_say"
                    save_wizard_field("backend_choice", backend_choice)
            elif f5_action == "elevenlabs":
                backend_choice = "elevenlabs"
                save_wizard_field("backend_choice", backend_choice)
                env_key = os.environ.get("ELEVENLABS_API_KEY", "")
                if env_key:
                    use_env = questionary.confirm(f"Use existing ELEVENLABS_API_KEY from environment ({env_key[:6]}...)?", default=True).ask()
                    if use_env:
                        api_key = env_key
                if not api_key:
                    api_key = questionary.password("Enter ElevenLabs API Key:").ask()
                    if not api_key:
                        console.print("[yellow]No ElevenLabs API key provided. Falling back to macOS 'say'.[/yellow]")
                        backend_choice = "macos_say"
                        save_wizard_field("backend_choice", backend_choice)
            else:
                backend_choice = "macos_say"
                save_wizard_field("backend_choice", backend_choice)

    # 3. Household Voices
    household_voices: List[HouseholdVoice] = []
    household_ratio = 0.50

    hv_choices = [
        Choice("Add household member voices (one at a time: audio sample, name, transcript)", value="add"),
        Choice("Skip household voices (use built-in / library voices only)", value="skip"),
    ]
    hv_mode = questionary.select(
        "3. Household Member Voice Samples (Zero-Shot Cloning):",
        choices=hv_choices,
        default=get_valid_default(hv_choices, prev_state.get("hv_mode"))
    ).ask()
    if hv_mode is None:
        return
    save_wizard_field("hv_mode", hv_mode)

    if hv_mode == "add":
        prev_hv_list = prev_state.get("household_voices", [])
        saved_hv_list = []
        while True:
            idx = len(household_voices) + 1
            console.print(f"\n[bold]--- Household Voice Sample #{idx} ---[/bold]")
            prev_entry = prev_hv_list[idx - 1] if idx - 1 < len(prev_hv_list) else {}
            default_audio = prev_entry.get("audio_path", "")

            s_file_input = questionary.text(
                "Path to audio sample (.wav, .mp3, .m4a):",
                default=default_audio
            ).ask()
            if not s_file_input or not s_file_input.strip():
                if not household_voices:
                    console.print("[dim]No file entered. Skipping household voices.[/dim]")
                break
            s_file = clean_path(s_file_input)
            if not s_file or not s_file.exists():
                console.print(f"[yellow]File '{s_file_input}' not found.[/yellow]")
                retry = questionary.confirm("Try again?", default=True).ask()
                if retry:
                    continue
                break

            default_name = prev_entry.get("name") or s_file.stem.replace("_", " ").title()
            s_name = questionary.text("Person's name:", default=default_name).ask() or default_name
            s_trans = get_interactive_transcript(s_file)

            saved_hv_list.append({
                "audio_path": str(s_file),
                "name": s_name,
                "transcript": s_trans
            })
            save_wizard_field("household_voices", saved_hv_list)

            new_voices = load_household_voices(
                single_sample=s_file,
                single_name=s_name,
                single_transcript=s_trans
            )
            if new_voices:
                household_voices.extend(new_voices)
                console.print(f"[green]Successfully loaded voice profile for '{new_voices[0].name}'.[/green]")

            has_more_prev = idx < len(prev_hv_list)
            more = questionary.confirm(
                "Add another household member's voice (e.g. partner, child)?",
                default=has_more_prev
            ).ask()
            if not more:
                break

    if household_voices:
        console.print(f"\n[bold green]Loaded {len(household_voices)} household voice(s):[/bold green] {', '.join(v.name for v in household_voices)}\n")

    # 4. Built-in Voice Checkbox Chooser
    available_builtin = get_available_builtin_voices(backend_choice, api_key)
    selected_builtin: List[str] = []

    if available_builtin:
        choices = []
        category_titles = {
            "female": "Curated Female Voices",
            "male": "Curated Male Voices",
            "kids": "Youth & Teen Voices",
            "accents": "Regional Accents",
        }
        max_name_len = max((len(v["name"]) for v in available_builtin), default=12)
        col_width = max(max_name_len + 2, 16)
        prev_builtin = prev_state.get("builtin_voices")

        for cat in ["female", "male", "kids", "accents"]:
            cat_voices = [v for v in available_builtin if v["category"] == cat]
            if cat_voices:
                title = category_titles.get(cat, cat.title())
                choices.append(Separator(f"=== {title} ==="))
                for v in cat_voices:
                    suffix = " (Default)" if v.get("default") else ""
                    desc_str = f" - {v['desc']}" if v.get("desc") else ""
                    label = f"{v['name']:<{col_width}}{desc_str}{suffix}"
                    is_checked = (v["name"] in prev_builtin) if prev_builtin is not None else v.get("default", False)
                    choices.append(Choice(label, value=v["name"], checked=is_checked))

        for v in available_builtin:
            if v["category"] not in ["female", "male", "kids", "accents"]:
                suffix = " (Default)" if v.get("default") else ""
                desc_str = f" - {v['desc']}" if v.get("desc") else ""
                label = f"{v['name']:<{col_width}}{desc_str}{suffix}"
                is_checked = (v["name"] in prev_builtin) if prev_builtin is not None else v.get("default", False)
                choices.append(Choice(label, value=v["name"], checked=is_checked))

        selected_builtin = questionary.checkbox(
            "4. Select Built-in Voices to Include in Dataset:",
            choices=choices,
            instruction="(Space to toggle, 'a' to toggle all, Enter to confirm)"
        ).ask()
        if selected_builtin is None:
            return
        save_wizard_field("builtin_voices", selected_builtin)

    # 5. Dataset Balance / Allocation Ratio
    if household_voices and selected_builtin:
        ratio_choices = [
            Choice("50% Household / 50% Built-in (Balanced accuracy & generalizability - Recommended)", value=0.50),
            Choice("70% Household / 30% Built-in (Prioritize household member accuracy)", value=0.70),
            Choice("30% Household / 70% Built-in (Prioritize general population diversity)", value=0.30),
            Choice("100% Household Voices only", value=1.00),
            Choice("Custom ratio...", value=-1.0),
        ]
        prev_ratio = prev_state.get("household_ratio")
        default_ratio_choice = get_valid_default(
            ratio_choices,
            prev_ratio,
            fallback=-1.0 if (prev_ratio is not None and isinstance(prev_ratio, (int, float))) else 0.50
        )
        ratio_choice = questionary.select(
            "5. Dataset Allocation Balance:",
            choices=ratio_choices,
            default=default_ratio_choice
        ).ask()
        if ratio_choice is None:
            return
        if ratio_choice < 0.0:
            custom_default = f"{prev_ratio:.2f}" if (prev_ratio is not None and prev_ratio > 0.0) else "0.50"
            custom_ratio_str = questionary.text(
                "Enter household ratio [0.0 - 1.0, default=0.50]:",
                default=custom_default
            ).ask()
            try:
                household_ratio = float(custom_ratio_str)
            except (ValueError, TypeError):
                household_ratio = 0.50
        else:
            household_ratio = ratio_choice
        save_wizard_field("household_ratio", household_ratio)
    elif household_voices:
        household_ratio = 1.0
        save_wizard_field("household_ratio", household_ratio)
    else:
        household_ratio = 0.0
        save_wizard_field("household_ratio", household_ratio)

    # 6. Sample Count
    count_choices = [
        Choice("100 samples (Recommended for household satellite deployment: balanced speed & coverage)", value=100),
        Choice("50 samples (Quick smoke test)", value=50),
        Choice("200 samples (High-fidelity household deployment)", value=200),
        Choice("500 samples (Large-scale production dataset)", value=500),
        Choice("Custom sample count...", value=-1),
    ]
    prev_count = prev_state.get("count")
    default_count_choice = get_valid_default(
        count_choices,
        prev_count,
        fallback=-1 if (prev_count is not None and isinstance(prev_count, int)) else 100
    )
    count_choice = questionary.select(
        "6. Positive Training Samples to Generate:",
        choices=count_choices,
        default=default_count_choice
    ).ask()
    if count_choice is None:
        return

    if count_choice == -1:
        custom_default = str(prev_count) if (prev_count is not None and prev_count > 0) else "100"
        count_str = questionary.text("Enter positive sample count [default=100]:", default=custom_default).ask()
        try:
            count = int(count_str)
        except (ValueError, TypeError):
            count = 100
    else:
        count = count_choice
    save_wizard_field("count", count)

    # 7. Output Directory & Cache Check
    default_out_path = Path(f"data/{model_name}/positive")
    prev_out_dir = prev_state.get("output_dir")
    if prev_out_dir and (prev_state.get("model_name") == model_name or prev_state.get("output_dir_custom")):
        default_out_str = prev_out_dir
    else:
        default_out_str = str(default_out_path)

    out_str = questionary.text("7. Output Directory:", default=default_out_str).ask()
    if out_str is None:
        return
    out_dir = clean_path(out_str) or default_out_path
    save_wizard_field("output_dir", str(out_dir))
    save_wizard_field("output_dir_custom", str(out_dir) != str(default_out_path))

    force = False
    if is_corpus_complete(out_dir, count, model_name, backend_choice, household_voices, selected_builtin):
        console.print(f"\n[yellow][Notice] A complete cached corpus already exists in '{out_dir}'.[/yellow]")
        force = questionary.confirm(
            "Re-synthesize and overwrite existing dataset?",
            default=prev_state.get("force", False)
        ).ask()
        if force is None:
            return
        save_wizard_field("force", force)

    # 8. Summary & Confirmation Table
    console.print()
    table = Table(title="Corpus Generation Configuration Summary", show_header=True, header_style="bold magenta")
    table.add_column("Parameter", style="cyan", no_wrap=True)
    table.add_column("Configured Value", style="green")

    table.add_row("Model Name", model_name)
    table.add_row("Backend", backend_choice)
    table.add_row("Phonetic Variations", f"{len(phrases)} unique forms")

    if household_voices:
        table.add_row("Household Voices", f"{len(household_voices)} ({', '.join(v.name for v in household_voices)})")
    else:
        table.add_row("Household Voices", "None (built-in voices only)")

    if selected_builtin:
        table.add_row("Built-in Voices", f"{len(selected_builtin)} ({', '.join(selected_builtin)})")
    else:
        table.add_row("Built-in Voices", "None (household voices only)")

    table.add_row("Total Samples", str(count))
    if household_voices and selected_builtin:
        h_cnt = int(round(count * household_ratio))
        b_cnt = count - h_cnt
        table.add_row("Sample Allocation", f"{h_cnt} Household ({household_ratio*100:.0f}%), {b_cnt} Built-in ({(1-household_ratio)*100:.0f}%)")

    table.add_row("Output Directory", str(out_dir))
    table.add_row("Bypass Cache (Force)", "Yes" if force else "No")
    console.print(table)
    console.print()

    proceed = questionary.confirm("Proceed with corpus generation?", default=True).ask()
    if not proceed:
        console.print("[dim]Aborted by user.[/dim]")
        return

    generate_corpus(
        model_name=model_name,
        phrases=phrases,
        backend_name=backend_choice,
        count=count,
        output_dir=out_dir,
        api_key=api_key,
        household_voices=household_voices,
        household_ratio=household_ratio,
        builtin_voices=selected_builtin,
        force=force
    )


def _run_fallback_wizard():
    """Minimal text fallback when questionary/rich are not installed."""
    print("=" * 65)
    print(" microWakeWord Synthetic Corpus Generator (CLI Fallback)")
    print("=" * 65)

    prev_state = load_wizard_state()

    print("\n1. Select Target Wake Word Model:")
    builtin_keys = list(BUILTIN_WAKE_WORDS.keys())
    for idx, key in enumerate(builtin_keys, start=1):
        ww = BUILTIN_WAKE_WORDS[key]
        print(f"   [{idx}] {ww['name']:<15} ({ww['description']})")
    custom_idx = len(builtin_keys) + 1
    print(f"   [{custom_idx}] Custom phrase")

    prev_model = prev_state.get("model_choice")
    default_idx = 1
    if prev_model in builtin_keys:
        default_idx = builtin_keys.index(prev_model) + 1
    elif prev_model == "custom":
        default_idx = custom_idx

    choice = input(f"Select [1-{custom_idx}, default={default_idx}]: ").strip() or str(default_idx)

    try:
        choice_num = int(choice)
    except ValueError:
        choice_num = default_idx

    if 1 <= choice_num <= len(builtin_keys):
        model_name = builtin_keys[choice_num - 1]
        save_wizard_field("model_choice", model_name)
        save_wizard_field("model_name", model_name)
        phrases = BUILTIN_WAKE_WORDS[model_name]["generator"]()
    else:
        save_wizard_field("model_choice", "custom")
        prev_custom = prev_state.get("custom_wake_word", "")
        prompt = f"Enter custom wake word identifier [default: {prev_custom}]: " if prev_custom else "Enter custom wake word identifier: "
        custom_input = input(prompt).strip() or prev_custom
        if not custom_input:
            custom_input = "hey_computer"
        save_wizard_field("custom_wake_word", custom_input)
        model_name = custom_input.lower().replace(" ", "_")
        save_wizard_field("model_name", model_name)
        show_llm_prompt_panel(model_name.replace("_", " "))

        prev_var = prev_state.get("variations_text", "")
        prompt_var = f"Enter phonetic variations (comma-separated or path to .txt file) [default: {prev_var}]: " if prev_var else "Enter phonetic variations (comma-separated or path to .txt file): "
        var_input = input(prompt_var).strip() or prev_var
        if var_input:
            save_wizard_field("variations_text", var_input)
        var_path = clean_path(var_input)
        if var_path and var_path.is_file():
            phrases = parse_variations(var_path.read_text(encoding="utf-8"))
        elif var_input:
            phrases = parse_variations(var_input)
        else:
            phrases = [model_name.replace("_", " ")]

    phrases = review_phrases_fallback(phrases, model_name)
    if not phrases:
        phrases = [model_name.replace("_", " ")]
    save_wizard_field("phrases", phrases)

    print(f"\nFinalized {len(phrases)} phonetic variation(s) for '{model_name}'.")

    print("\n2. Select Synthesis Backend:")
    print("   [1] ElevenLabs API")
    print("   [2] macOS 'say'")
    print("   [3] F5-TTS")
    backend_map = {"1": "elevenlabs", "2": "macos_say", "3": "f5_tts"}
    rev_backend_map = {"elevenlabs": "1", "macos_say": "2", "f5_tts": "3"}
    prev_backend = prev_state.get("backend_choice", "elevenlabs")
    default_backend_idx = rev_backend_map.get(prev_backend, "1")

    backend_choice = input(f"Select [1-3, default={default_backend_idx}]: ").strip() or default_backend_idx
    backend_name = backend_map.get(backend_choice, "elevenlabs")
    save_wizard_field("backend_choice", backend_name)

    api_key = None
    if backend_name == "elevenlabs":
        env_key = os.environ.get("ELEVENLABS_API_KEY", "")
        prompt = f"Enter ElevenLabs API Key [{env_key[:6]}...]: " if env_key else "Enter ElevenLabs API Key: "
        key_input = input(prompt).strip()
        api_key = key_input if key_input else env_key
    elif backend_name == "f5_tts":
        f5_backend = F5TTSBackend()
        if not f5_backend.is_available():
            print("\n[Notice] F5-TTS is not currently installed in this environment.")
            do_install = input("Install F5-TTS dependencies now? [Y/n]: ").strip().lower()
            if do_install not in ("n", "no"):
                success = install_f5_tts_dependencies()
                if not success:
                    print("Installation failed. Switching to macOS 'say'.")
                    backend_name = "macos_say"
                    save_wizard_field("backend_choice", backend_name)
            else:
                print("Switching to macOS 'say'.")
                backend_name = "macos_say"
                save_wizard_field("backend_choice", backend_name)

    household_voices: List[HouseholdVoice] = []
    print("\n3. Household Member Voice Samples (Zero-Shot Cloning):")
    prev_hv_mode = prev_state.get("hv_mode", "skip")
    default_add = "y" if prev_hv_mode == "add" else "N"
    add_hv = input(f"Add household member voices one at a time? [y/N, default: {default_add}]: ").strip().lower() or default_add.lower()
    save_wizard_field("hv_mode", "add" if add_hv in ("y", "yes") else "skip")

    if add_hv in ("y", "yes"):
        prev_hv_list = prev_state.get("household_voices", [])
        saved_hv_list = []
        while True:
            idx = len(household_voices) + 1
            prev_entry = prev_hv_list[idx - 1] if idx - 1 < len(prev_hv_list) else {}
            default_audio = prev_entry.get("audio_path", "")
            prompt_audio = f"\nEnter path to audio sample #{idx} [default: {default_audio}]: " if default_audio else f"\nEnter path to audio sample #{idx} (or press Enter to finish): "
            s_input = input(prompt_audio).strip() or default_audio
            if not s_input:
                break
            s_file = clean_path(s_input)
            if not s_file or not s_file.is_file():
                print(f"Error: Audio file '{s_input}' not found.")
                continue
            default_name = prev_entry.get("name") or s_file.stem.replace("_", " ").title()
            s_name = input(f"Person's name [default: {default_name}]: ").strip() or default_name
            s_trans = get_interactive_transcript(s_file)

            saved_hv_list.append({
                "audio_path": str(s_file),
                "name": s_name,
                "transcript": s_trans
            })
            save_wizard_field("household_voices", saved_hv_list)

            new_voices = load_household_voices(
                single_sample=s_file,
                single_name=s_name,
                single_transcript=s_trans
            )
            if new_voices:
                household_voices.extend(new_voices)
                print(f"Successfully loaded voice profile for '{new_voices[0].name}'.")

    prev_count = prev_state.get("count", 50)
    count_str = input(f"Enter positive sample count [default={prev_count}]: ").strip() or str(prev_count)
    try:
        count = int(count_str)
    except ValueError:
        count = prev_count
    save_wizard_field("count", count)

    default_out_path = Path(f"data/{model_name}/positive")
    prev_out_dir = prev_state.get("output_dir")
    if prev_out_dir and prev_state.get("model_name") == model_name:
        default_out = Path(prev_out_dir)
    else:
        default_out = default_out_path

    out_str = input(f"Output directory [default={default_out}]: ").strip()
    out_dir = clean_path(out_str) or default_out
    save_wizard_field("output_dir", str(out_dir))

    force = False
    if is_corpus_complete(out_dir, count, model_name, backend_name, household_voices):
        print(f"\n[Notice] A complete cached corpus already exists in '{out_dir}'.")
        re_synth = input("Re-synthesize and overwrite existing dataset? [y/N]: ").strip().lower()
        if re_synth in ("y", "yes"):
            force = True
        save_wizard_field("force", force)

    confirm = input("Proceed? [Y/n]: ").strip().lower()
    if confirm in ("", "y", "yes"):
        generate_corpus(
            model_name=model_name,
            phrases=phrases,
            backend_name=backend_name,
            count=count,
            output_dir=out_dir,
            api_key=api_key,
            household_voices=household_voices,
            household_ratio=0.50 if household_voices else 0.0,
            force=force
        )


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Synthetic Wake Word Corpus Generator for microWakeWord"
    )
    parser.add_argument("--model", choices=list(BUILTIN_WAKE_WORDS.keys()) + ["custom"], default=None,
                        help="Pre-configured wake word model name")
    parser.add_argument("--phrase", type=str, action="append", default=None,
                        help="Custom phrase or phonetic variant (can specify multiple times or comma-separated)")
    parser.add_argument("--phrase-file", type=str, default=None,
                        help="Path to text file containing phonetic variations (one per line)")
    parser.add_argument("--backend", choices=["elevenlabs", "macos_say", "f5_tts"], default="elevenlabs",
                        help="Audio synthesis backend")
    parser.add_argument("--count", type=int, default=50,
                        help="Number of synthetic audio samples to generate")
    parser.add_argument("--output", type=str, default=None,
                        help="Output directory for generated 16kHz PCM audio files")
    parser.add_argument("--api-key", type=str, default=None,
                        help="ElevenLabs API key (or set ELEVENLABS_API_KEY)")
    parser.add_argument("--household-dir", type=str, default=None,
                        help="Directory containing household member reference voice samples")
    parser.add_argument("--voice-sample", type=str, action="append", default=None,
                        help="Path to reference voice audio sample (can specify multiple times)")
    parser.add_argument("--voice-name", type=str, action="append", default=None,
                        help="Name of person for --voice-sample (can specify multiple times)")
    parser.add_argument("--voice-transcript", type=str, action="append", default=None,
                        help="Transcript for --voice-sample (text or path to .txt file, can specify multiple times)")
    parser.add_argument("--voice-transcript-file", type=str, action="append", default=None,
                        help="Path to file containing transcript for --voice-sample (can specify multiple times)")
    parser.add_argument("--builtin-voices", type=str, action="append", default=None,
                        help="Name of built-in voice to include (can specify multiple times or comma-separated)")
    parser.add_argument("--household-ratio", type=float, default=0.50,
                        help="Ratio of generated corpus allocated to household voices (default: 0.50)")
    parser.add_argument("--list-voices", action="store_true",
                        help="List available built-in / library voices for the chosen backend and exit")
    parser.add_argument("--force", action="store_true",
                        help="Force regeneration of audio samples, bypassing cache")
    parser.add_argument("--review-phrases", action="store_true",
                        help="Interactively review and edit phonetic variations before synthesizing")
    parser.add_argument("--wizard", action="store_true",
                        help="Run interactive TUI setup wizard")

    args = parser.parse_args()

    if args.list_voices:
        voices = get_available_builtin_voices(args.backend, args.api_key)
        print(f"Available built-in voices for backend '{args.backend}':")
        for v in voices:
            def_marker = " [default]" if v.get("default") else ""
            print(f"  - {v['name']:<12} ({v['category']}): {v['desc']}{def_marker}")
        return

    if args.wizard or args.model is None:
        run_tui_wizard()
        return

    if args.model in BUILTIN_WAKE_WORDS:
        phrases = BUILTIN_WAKE_WORDS[args.model]["generator"]()
    elif args.model == "custom":
        if args.phrase_file:
            p_file = clean_path(args.phrase_file)
            if p_file and p_file.is_file():
                phrases = parse_variations(p_file.read_text(encoding="utf-8"))
            else:
                parser.error(f"Phrase file '{args.phrase_file}' not found")
        elif args.phrase:
            phrases = []
            for p in args.phrase:
                phrases.extend(parse_variations(p))
        else:
            parser.error("--phrase or --phrase-file is required when --model is custom")
    else:
        phrases = []

    if args.review_phrases:
        phrases = review_phrases_interactive(phrases, args.model)
        if not phrases:
            phrases = [args.model.replace("_", " ")]

    household_voices = load_household_voices(
        household_dir=args.household_dir,
        single_sample=args.voice_sample,
        single_name=args.voice_name,
        single_transcript=args.voice_transcript,
        single_transcript_file=args.voice_transcript_file
    )

    # Flatten comma-separated builtin-voices if provided
    builtin_list: Optional[List[str]] = None
    if args.builtin_voices:
        builtin_list = []
        for bv in args.builtin_voices:
            for item in bv.split(","):
                clean_item = item.strip()
                if clean_item:
                    builtin_list.append(clean_item)

    out_dir = clean_path(args.output) or Path(f"data/{args.model}/positive")
    generate_corpus(
        model_name=args.model,
        phrases=phrases,
        backend_name=args.backend,
        count=args.count,
        output_dir=out_dir,
        api_key=args.api_key,
        household_voices=household_voices,
        household_ratio=args.household_ratio,
        builtin_voices=builtin_list,
        force=args.force
    )


if __name__ == "__main__":
    # Auto re-exec into local repo .venv if running outside it and .venv exists
    if "VIRTUAL_ENV" not in os.environ and sys.prefix == sys.base_prefix:
        _repo_venv_py = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
        if _repo_venv_py.is_file() and os.access(_repo_venv_py, os.X_OK):
            if Path(sys.executable).resolve() != _repo_venv_py.resolve():
                os.environ["VIRTUAL_ENV"] = str(_repo_venv_py.parent.parent)
                os.execv(str(_repo_venv_py), [str(_repo_venv_py)] + sys.argv)
    main()
