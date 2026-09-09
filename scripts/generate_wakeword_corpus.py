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
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union, Any

CACHE_DIR = Path(".cache/mww_corpus")

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
        {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "accent": "American", "desc": "Calm, standard female"},
        {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah", "accent": "American", "desc": "Warm, professional female"},
        {"id": "piTKgcLEGmPE4e6mEKli", "name": "Nicole", "accent": "American", "desc": "Soft, whisper female"},
        {"id": "jsCqWAovK2LkecY7zXl4", "name": "Freya", "accent": "American", "desc": "Expressive female"},
        {"id": "ThT5KcBeYPX3keUQqHPh", "name": "Dorothy", "accent": "British", "desc": "Pleasant British female"},
        {"id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte", "accent": "Swedish-English", "desc": "Accented female"},
        {"id": "Xb7hH8MSUJpSbSDYk0k2", "name": "Alice", "accent": "British", "desc": "Clear British female"},
    ],
    "male": [
        {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam", "accent": "American", "desc": "Deep American male"},
        {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni", "accent": "American", "desc": "Energetic American male"},
        {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh", "accent": "American", "desc": "Youthful American male"},
        {"id": "VR6AewLTigWG4xSOukaG", "name": "Arnold", "accent": "American", "desc": "Crisp American male"},
        {"id": "yoZ06aMxZJJ28mfd3POQ", "name": "Sam", "accent": "American", "desc": "Raspy American male"},
        {"id": "JBFqnCBsd6RMkjVDRZzb", "name": "George", "accent": "British", "desc": "Warm British male"},
        {"id": "nPczCjzI2devNBz1zQrb", "name": "Brian", "accent": "American", "desc": "Deep narrator male"},
        {"id": "N2lVS1w4EtoT3dr4eOWO", "name": "Callum", "accent": "Transatlantic", "desc": "Irish/Transatlantic male"},
    ],
    "kids": [
        {"id": "zrHiDhphv9ZnVXBqCLjz", "name": "Mimi", "accent": "American", "desc": "Teen female, animated"},
        {"id": "D38z5RcWu1voky8WS1ja", "name": "Fin", "accent": "Irish", "desc": "Youth Irish male, energetic"},
        {"id": "TX3LPaxmHKxFdv7VOQHJ", "name": "Liam", "accent": "American", "desc": "Young American male"},
    ],
    "accents": [
        {"id": "XrExE9yKIg1WjnnlVkGX", "name": "Matilda", "accent": "Australian", "desc": "Australian female"},
        {"id": "IKne3meq5aSn9X8L4xzE", "name": "Charlie", "accent": "Australian", "desc": "Australian male"},
    ],
}

MACOS_SAY_VOICES = {
    "female": ["Samantha", "Victoria", "Karen", "Fiona", "Moira", "Tessa"],
    "male": ["Alex", "Daniel", "Oliver", "Fred"],
    "kids": ["Junior", "Kathy"],
    "accents": ["Lee", "Yuri", "Milena"],
}

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

# ---------------------------------------------------------------------------
# Phonetic Variation Generators
# ---------------------------------------------------------------------------
def generate_nabu_variations() -> List[str]:
    prefixes = ["okay", "ok", "hey", "ay", "kay", ""]
    nabus = ["nabu", "nahboo", "na boo", "nayboo", "nah bu", "naboo"]

    variants = set()
    for p, n in itertools.product(prefixes, nabus):
        phrase = f"{p} {n}".strip()
        phrase = " ".join(phrase.split())
        if phrase:
            variants.add(phrase)
    return sorted(list(variants))


def generate_clemens_variations() -> List[str]:
    honorifics = ["mister", "mr", "mr.", "mista", "mist ur", "miss ter", "misster", "miss tack", "mist ack", ""]
    clemens = ["clemens", "clemen", "clemence", "claman", "clem ins", "lemons", "klemens", "clay mens", "claymen"]

    variants = set()
    for h, c in itertools.product(honorifics, clemens):
        phrase = f"{h} {c}".strip()
        phrase = " ".join(phrase.split())
        if phrase:
            variants.add(phrase)
    return sorted(list(variants))


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


class F5TTSBackend:
    def __init__(self):
        self.cli_binary = self._find_cli()

    def _find_cli(self) -> Optional[str]:
        for bin_name in ["f5-tts_infer-cli", "f5-tts"]:
            res = subprocess.run(["which", bin_name], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        return None

    def is_available(self) -> bool:
        if self.cli_binary is not None:
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
    household_ratio: float = 0.50
) -> List[VoiceSpec]:
    """
    Returns a list of VoiceSpec instances sampled according to demographic distribution
    and household voice ratio.
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

    if generic_count > 0 and voice_pool:
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
    active_household: List[HouseholdVoice]
) -> bool:
    """
    Validates if an output directory already contains a complete, valid corpus
    matching the exact pipeline signature and household voice audio hashes.
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
    voice_cache = VoiceCacheManager()
    pipeline_sig = get_pipeline_signature(backend_name)

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
        if not household_voices:
            print("Error: F5-TTS is a zero-shot voice cloning model and requires reference audio.", file=sys.stderr)
            print("Provide at least one reference voice using --voice-sample or --household-dir.", file=sys.stderr)
            return 0

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

        household_ratio = 1.0  # F5-TTS synthesizes against reference clips

    elif backend_name == "macos_say":
        backend = MacOSSayBackend()
        voice_pool = get_available_macos_voices()
        if household_voices:
            print("Notice: macOS 'say' backend does not support neural voice cloning. Proceeding with system voices.")
    else:
        print(f"Error: Unknown backend '{backend_name}'.", file=sys.stderr)
        return 0

    if not force and is_corpus_complete(output_dir, count, model_name, backend_name, active_household):
        print(f"\n[Reentrant Cache Hit] Output directory '{output_dir}' already contains {count} trained samples.")
        print(f"Verified against pipeline signature {pipeline_sig} and matching reference audio file hashes.")
        print("Dataset is complete and up to date. Use --force to re-synthesize.")
        return count

    voices = sample_voices(distribution, count, voice_pool, active_household, household_ratio)
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
        print(f"Household Voices:   {len(active_household)} ({household_ratio*100:.0f}% allocation)")
    print(f"Output Directory:   {output_dir}")
    print("-" * 65)

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
        print(f"[{i+1:4d}/{count:4d}] [{status:5s}] '{phrase}' ({vspec.voice_name}) -> {out_name}")

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
            "household_ratio": household_ratio if active_household else 0.0,
            "samples": manifest
        }, f, indent=2)

    print("-" * 65)
    print(f"Corpus generation complete: {generated} valid 16kHz PCM audio files written to {output_dir}")
    print(f"Manifest written to: {manifest_path}")
    return generated


# ---------------------------------------------------------------------------
# Interactive TUI Wizard
# ---------------------------------------------------------------------------
def run_tui_wizard():
    print("=" * 65)
    print(" microWakeWord Synthetic Corpus Generator & Dataset Wizard")
    print("=" * 65)

    print("\n1. Select Target Wake Word Model:")
    print("   [1] Okay Nabu    (variations: okay nabu, ok nabu, hey nabu, etc.)")
    print("   [2] Mr. Clemens  (30+ phonetic variants: mister clemens, miss tack lemons, etc.)")
    print("   [3] Custom phrase")
    choice = input("Select [1-3, default=1]: ").strip() or "1"

    if choice == "1":
        model_name = "okay_nabu"
        phrases = generate_nabu_variations()
    elif choice == "2":
        model_name = "mister_clemens"
        phrases = generate_clemens_variations()
    else:
        custom_input = input("Enter custom wake word phrase: ").strip()
        model_name = custom_input.lower().replace(" ", "_")
        phrases = [custom_input]

    print(f"\nLoaded {len(phrases)} phonetic variations for '{model_name}'.")

    print("\n2. Select Synthesis Backend:")
    print("   [1] ElevenLabs API (Neural Cloud Voices + Instant Voice Cloning)")
    print("   [2] macOS 'say'   (Local system voices - zero API key required)")
    print("   [3] F5-TTS        (Local zero-shot flow-matching voice cloning)")
    backend_choice = input("Select [1-3, default=1]: ").strip() or "1"

    if backend_choice == "1":
        backend_name = "elevenlabs"
    elif backend_choice == "2":
        backend_name = "macos_say"
    else:
        backend_name = "f5_tts"

    api_key = None
    if backend_name == "elevenlabs":
        env_key = os.environ.get("ELEVENLABS_API_KEY", "")
        prompt = f"Enter ElevenLabs API Key [{env_key[:6]}...]: " if env_key else "Enter ElevenLabs API Key: "
        key_input = input(prompt).strip()
        api_key = key_input if key_input else env_key
        if not api_key:
            print("No ElevenLabs API key provided. Falling back to local macOS 'say' backend.")
            backend_name = "macos_say"

    household_voices: List[HouseholdVoice] = []
    household_ratio = 0.50

    if backend_name in ("elevenlabs", "f5_tts"):
        print("\n3. Household Member Voice Samples (Zero-Shot Voice Cloning):")
        print("   Adding samples of household members trains the wake word on their unique")
        print("   vocal timbre while maintaining generic demographic diversity to prevent overfitting.")
        hv_prompt = "Do you want to include household voice samples? [y/N]: "
        if backend_name == "f5_tts":
            hv_prompt = "F5-TTS requires reference voice sample(s). Ingest voice sample now? [Y/n]: "
        hv_resp = input(hv_prompt).strip().lower()

        if (backend_name == "f5_tts" and hv_resp not in ("n", "no")) or hv_resp in ("y", "yes"):
            print("   [1] Point to a directory containing voice samples (e.g. data/household_voices/)")
            print("   [2] Specify individual voice samples (e.g. you and your partner)")
            src_choice = input("   Select [1-2, default=1]: ").strip() or "1"
            if src_choice == "1":
                h_dir = input("   Enter directory path: ").strip()
                clean_hdir = clean_path(h_dir)
                if clean_hdir:
                    household_voices = load_household_voices(household_dir=clean_hdir)
            else:
                while True:
                    idx = len(household_voices) + 1
                    print(f"\n   --- Household Member Voice #{idx} ---")
                    s_file_input = input("   Enter path to audio sample (.wav, .mp3, .m4a): ").strip()
                    s_file = clean_path(s_file_input)
                    if not s_file:
                        if not household_voices:
                            print("   No audio file entered.")
                        break
                    if not s_file.exists():
                        print(f"   Warning: File '{s_file_input}' not found (resolved: {s_file}).")
                        retry = input("   Try again? [Y/n]: ").strip().lower()
                        if retry in ("", "y", "yes"):
                            continue
                        elif not household_voices:
                            break
                        else:
                            pass

                    default_name = s_file.stem.replace("_", " ").title()
                    s_name = input(f"   Enter person's name [default={default_name}]: ").strip() or default_name
                    s_trans = get_interactive_transcript(s_file)
                    new_voices = load_household_voices(
                        single_sample=s_file,
                        single_name=s_name,
                        single_transcript=s_trans
                    )
                    if new_voices:
                        household_voices.extend(new_voices)
                        print(f"   Successfully added '{new_voices[0].name}'.")

                    more = input("\n   Add another household member's voice (e.g. partner, child)? [y/N]: ").strip().lower()
                    if more not in ("y", "yes"):
                        break

            if household_voices:
                print(f"\n   Loaded {len(household_voices)} household voice(s): {', '.join(v.name for v in household_voices)}")
                if backend_name == "elevenlabs":
                    ratio_str = input("   Ratio of dataset for household voices [0.0 - 1.0, default=0.50]: ").strip() or "0.50"
                    try:
                        household_ratio = float(ratio_str)
                    except ValueError:
                        household_ratio = 0.50
            else:
                print("   No valid household voices found.")

    print("\n4. Sample Count to Generate:")
    count_str = input("Enter count [default=50]: ").strip() or "50"
    count = int(count_str)

    default_out = Path(f"data/{model_name}/positive")
    out_str = input(f"Output directory [default={default_out}]: ").strip()
    out_dir = clean_path(out_str) if out_str else default_out

    force = False
    if is_corpus_complete(out_dir, count, model_name, backend_name, household_voices):
        print(f"\n[Notice] A complete cached corpus already exists in '{out_dir}'.")
        re_synth = input("Re-synthesize and overwrite existing dataset? [y/N]: ").strip().lower()
        if re_synth in ("y", "yes"):
            force = True

    print("\nReady to generate corpus.")
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
            household_ratio=household_ratio,
            force=force
        )
    else:
        print("Aborted.")


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Synthetic Wake Word Corpus Generator for microWakeWord"
    )
    parser.add_argument("--model", choices=["okay_nabu", "mister_clemens", "custom"], default=None,
                        help="Pre-configured wake word model name")
    parser.add_argument("--phrase", type=str, default=None,
                        help="Custom phrase if --model custom is specified")
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
    parser.add_argument("--household-ratio", type=float, default=0.50,
                        help="Ratio of generated corpus allocated to household voices (default: 0.50)")
    parser.add_argument("--force", action="store_true",
                        help="Force regeneration of audio samples, bypassing cache")
    parser.add_argument("--wizard", action="store_true",
                        help="Run interactive TUI setup wizard")

    args = parser.parse_args()

    if args.wizard or args.model is None:
        run_tui_wizard()
        return

    if args.model == "okay_nabu":
        phrases = generate_nabu_variations()
    elif args.model == "mister_clemens":
        phrases = generate_clemens_variations()
    elif args.model == "custom":
        if not args.phrase:
            parser.error("--phrase is required when --model is custom")
        phrases = [args.phrase]
    else:
        phrases = []

    household_voices = load_household_voices(
        household_dir=args.household_dir,
        single_sample=args.voice_sample,
        single_name=args.voice_name,
        single_transcript=args.voice_transcript,
        single_transcript_file=args.voice_transcript_file
    )

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
        force=args.force
    )


if __name__ == "__main__":
    main()
