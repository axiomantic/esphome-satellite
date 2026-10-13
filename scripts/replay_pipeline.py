#!/usr/bin/env python3
"""Deterministic Audio Replay and Voice Pipeline Testing Tool.

Replays recorded microphone audio through Wyoming Faster-Whisper, evaluates
addressing with System 1 Gatekeeper, and tests end-to-end assistant responses.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave

# Dynamically import const.py helpers from the local repo
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

spec = importlib.util.spec_from_file_location(
    "esphome_satellite_const",
    REPO_ROOT / "custom_components" / "esphome_satellite" / "const.py",
)
if spec and spec.loader:
    const_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(const_mod)
    expand_wake_phrase = const_mod.expand_wake_phrase
    make_initial_prompt = const_mod.make_initial_prompt
    DEFAULT_TOKEN = const_mod.DEFAULT_SYSTEMONE_TOKEN
    DEFAULT_SYS1_URL = const_mod.DEFAULT_SYSTEMONE_URL
else:
    expand_wake_phrase = lambda w, a=None: [w]  # type: ignore
    make_initial_prompt = lambda w, a: (f"Is this utterance addressing {w}?", {})  # type: ignore
    DEFAULT_TOKEN = "660ffbac0245bfdd9744385963696d8e64875494ea205f419a6462ebb827b4c1"
    DEFAULT_SYS1_URL = "http://laya.flanopticon.lan/v1/systemone"

DEFAULT_SYS1_URL = "http://laya.flanopticon.lan/v1/systemone"
DEFAULT_TOKEN = "660ffbac0245bfdd9744385963696d8e64875494ea205f419a6462ebb827b4c1"
DEFAULT_WYOMING_HOST = "flanopticon.lan"
DEFAULT_WYOMING_PORT = 10300
DEFAULT_HA_HOST = "10.0.2.136"
DEFAULT_HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI3MjQyY2Y3OTYxNGQ0Yjc2YTFjYmFlMzNjZDhjNTEwZiIsImlhdCI6MTc4ODY1NDg3MSwiZXhwIjoyMTA0MDE0ODcxfQ.dummy"


def calculate_audio_stats(wav_path: Path) -> dict:
    """Read WAV file and calculate duration, RMS, and peak amplitude."""
    with wave.open(str(wav_path), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        rate = wf.getframerate()
        nframes = wf.getnframes()
        frames = wf.readframes(nframes)

    duration = nframes / max(1, rate)

    # Calculate RMS and peak from 16-bit PCM
    rms = 0.0
    peak = 0.0
    if sampwidth == 2 and len(frames) >= 2:
        import array
        samples = array.array("h")
        samples.frombytes(frames)
        if samples:
            peak = max(abs(s) for s in samples) / 32768.0
            sum_sq = sum(s * s for s in samples)
            rms = math.sqrt(sum_sq / len(samples))

    return {
        "channels": channels,
        "sample_rate": rate,
        "sample_width": sampwidth,
        "duration_sec": round(duration, 2),
        "peak_norm": round(peak, 3),
        "rms": round(rms, 1),
        "bytes": len(frames),
    }


async def transcribe_wyoming(
    wav_path: Path,
    host: str = DEFAULT_WYOMING_HOST,
    port: int = DEFAULT_WYOMING_PORT,
    language: str = "en",
) -> tuple[str, float]:
    """Stream WAV audio to Wyoming Faster-Whisper and return verbatim transcript and RTT."""
    try:
        from wyoming.audio import AudioChunk, AudioStart, AudioStop
        from wyoming.client import AsyncTcpClient
        from wyoming.asr import Transcribe, Transcript
    except ImportError:
        print("[!] Wyoming package not installed. Run via: uv run --with wyoming python ...")
        return ("", 0.0)

    with wave.open(str(wav_path), "rb") as wf:
        rate = wf.getframerate()
        width = wf.getsampwidth()
        channels = wf.getnchannels()
        audio_data = wf.readframes(wf.getnframes())

    start_time = time.perf_counter()
    client = AsyncTcpClient(host, port)
    await client.connect()

    await client.write_event(Transcribe(language=language).event())
    await client.write_event(AudioStart(rate=rate, width=width, channels=channels).event())

    chunk_size = 1024
    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i : i + chunk_size]
        await client.write_event(AudioChunk(audio=chunk, rate=rate, width=width, channels=channels).event())

    await client.write_event(AudioStop().event())

    transcript_text = ""
    while True:
        event = await client.read_event()
        if event is None:
            break
        if Transcript.is_type(event.type):
            tr = Transcript.from_event(event)
            transcript_text = tr.text.strip()
            break

    await client.disconnect()
    rtt_ms = (time.perf_counter() - start_time) * 1000.0
    return transcript_text, rtt_ms


def evaluate_systemone(
    text: str,
    wake_word: str,
    endpoint_url: str = DEFAULT_SYS1_URL,
    token: str = DEFAULT_TOKEN,
    threshold: float = 0.60,
) -> dict:
    """Evaluate address classification with System 1 Gatekeeper."""
    all_aliases = expand_wake_phrase(wake_word)
    instructions, criteria = make_initial_prompt(wake_word, all_aliases)

    payload = {
        "state": text,
        "questions": {
            "address_intent": {
                "type": "choice",
                "instructions": instructions,
                "criteria": criteria,
            }
        },
        "min_confidence": 0.0,
    }

    req = urllib.request.Request(
        endpoint_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )

    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            rtt_ms = (time.perf_counter() - start_time) * 1000.0
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return {"error": f"HTTP {err.code}: {err.read().decode('utf-8')}"}
    except Exception as err:
        return {"error": str(err)}

    ans = data.get("answers", {}).get("address_intent", {})
    choice = ans.get("choice", "ambient")
    probs = ans.get("probabilities", {})
    conf = float(ans.get("answer_confidence", probs.get(choice, 0.0)))
    verdict = "APPROVED" if (choice == "addressed" and conf >= threshold) else "DROPPED"

    return {
        "choice": choice,
        "confidence": conf,
        "probabilities": probs,
        "verdict": verdict,
        "threshold": threshold,
        "rtt_ms": round(rtt_ms, 1),
        "instructions": instructions,
    }


def fetch_latest_ha_recording(ha_host: str = DEFAULT_HA_HOST) -> Path:
    """Fetch the latest recording from Home Assistant via SSH."""
    cmd = (
        f"ssh -o BatchMode=yes root@{ha_host} "
        '"ls -t /config/www/recordings/*.wav 2>/dev/null | head -n 1"'
    )
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    remote_wav = res.stdout.strip()
    if not remote_wav:
        raise FileNotFoundError(f"No recordings found on {ha_host}:/config/www/recordings/")

    filename = Path(remote_wav).name
    local_dir = Path("/tmp/ha_recordings")
    local_dir.mkdir(parents=True, exist_ok=True)
    local_wav = local_dir / filename

    scp_cmd = f"scp -q root@{ha_host}:{remote_wav} {local_wav}"
    subprocess.run(scp_cmd, shell=True, check=True)

    # Also try to copy companion JSON
    remote_json = remote_wav.rsplit(".", 1)[0] + ".json"
    subprocess.run(f"scp -q root@{ha_host}:{remote_json} {local_dir}/", shell=True)

    return local_wav


def list_ha_recordings(ha_host: str = DEFAULT_HA_HOST) -> None:
    """List available recordings on Home Assistant."""
    cmd = (
        f"ssh -o BatchMode=yes root@{ha_host} "
        '"ls -lht /config/www/recordings/*.wav 2>/dev/null | head -n 20"'
    )
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(res.stdout if res.stdout else "No recordings found in /config/www/recordings/.")


async def main_async() -> None:
    parser = argparse.ArgumentParser(description="Deterministic Audio Replay and Voice Pipeline Testing Tool")
    parser.add_argument("--file", "-f", type=str, help="Path to local WAV recording file")
    parser.add_argument("--latest", action="store_true", help="Fetch and replay the latest recording from HA")
    parser.add_argument("--list", action="store_true", help="List recent recordings on HA")
    parser.add_argument("--wake", "-w", type=str, default="", help="Override target wake phrase")
    parser.add_argument("--threshold", "-t", type=float, default=0.60, help="Gatekeeper confidence threshold")
    parser.add_argument("--host", default=DEFAULT_WYOMING_HOST, help="Wyoming server hostname")
    parser.add_argument("--port", type=int, default=DEFAULT_WYOMING_PORT, help="Wyoming server port")
    parser.add_argument("--sys1-url", default=DEFAULT_SYS1_URL, help="System 1 endpoint URL")
    parser.add_argument("--sys1-token", default=DEFAULT_TOKEN, help="System 1 bearer token")
    parser.add_argument("--ha-host", default=DEFAULT_HA_HOST, help="Home Assistant hostname or IP")

    args = parser.parse_args()

    if args.list:
        print(f"=== Recent Recordings on {args.ha_host}:/config/www/recordings/ ===")
        list_ha_recordings(args.ha_host)
        return

    wav_path: Path
    if args.latest:
        print(f"[*] Fetching latest recording from {args.ha_host}...")
        wav_path = fetch_latest_ha_recording(args.ha_host)
        print(f"[*] Fetched: {wav_path.name}")
    elif args.file:
        wav_path = Path(args.file)
        if not wav_path.is_file():
            print(f"[!] File not found: {wav_path}")
            sys.exit(1)
    else:
        # Default: try to fetch latest from HA
        try:
            print(f"[*] No file specified. Checking {args.ha_host} for latest recording...")
            wav_path = fetch_latest_ha_recording(args.ha_host)
            print(f"[*] Using latest: {wav_path.name}")
        except Exception:
            # Fall back to sample
            fallback = REPO_ROOT / "assets" / "reference_voices" / "gigi.wav"
            if fallback.is_file():
                print(f"[*] Using fallback sample: {fallback}")
                wav_path = fallback
            else:
                parser.print_help()
                sys.exit(1)

    # Load companion JSON if available
    json_path = wav_path.with_suffix(".json")
    meta = {}
    if json_path.is_file():
        try:
            with open(json_path, encoding="utf-8") as jf:
                meta = json.load(jf)
        except Exception:
            pass

    wake_word = args.wake or meta.get("wake_word") or "Mr. Clemens"
    sat_id = meta.get("satellite_id") or "assist_satellite.voice_satellite"

    # Step 1: Audio Metrics
    stats = calculate_audio_stats(wav_path)

    print("\n" + "=" * 65)
    print("      DETERMINISTIC AUDIO REPLAY & PIPELINE TEST")
    print("=" * 65)
    print(f"File:       {wav_path.name}")
    print(f"Satellite:  {sat_id}")
    print(f"Wake Word:  '{wake_word}'")
    print(f"Audio Stats: {stats['duration_sec']}s, {stats['sample_rate']}Hz, {stats['channels']}ch, RMS={stats['rms']}, Peak={stats['peak_norm']}")

    # Step 2: Wyoming Faster-Whisper Transcription
    print("\n[-] Streaming audio to Faster-Whisper (Wyoming @ " + f"{args.host}:{args.port})...")
    transcript, stt_rtt = await transcribe_wyoming(wav_path, host=args.host, port=args.port)
    print(f"Transcript: \"{transcript}\"  (STT latency: {stt_rtt:.1f}ms)")

    if not transcript:
        print("[!] No speech detected by STT. Utterance terminated.")
        print("=" * 65 + "\n")
        return

    # Step 3: System 1 Gatekeeper Evaluation
    print("\n[-] Evaluating address classification via System 1 (Laya)...")
    res = evaluate_systemone(
        text=transcript,
        wake_word=wake_word,
        endpoint_url=args.sys1_url,
        token=args.sys1_token,
        threshold=args.threshold,
    )

    if "error" in res:
        print(f"[!] System 1 error: {res['error']}")
        return

    choice = res["choice"]
    conf = res["confidence"]
    probs = res["probabilities"]
    verdict = res["verdict"]

    print(f"Gatekeeper: Choice='{choice}', Confidence={conf:.2f} (Threshold={args.threshold:.2f})")
    print(f"Probabilities: {probs}")
    print(f"Latency:    {res['rtt_ms']}ms")
    print(f"Verdict:    >>> {verdict} <<<")

    print("\nInterpolated Prompt:")
    print(f"  {res['instructions']}")
    print("=" * 65 + "\n")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
