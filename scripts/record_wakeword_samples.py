#!/usr/bin/env python3
"""
Interactive Wake Word Voice Sample Recorder & Ingestion Tool
===========================================================

Guides the user through recording acoustic variations of "Mr. Clemens"
for microWakeWord training, or splits an existing continuous audio recording.

Features:
- Live guided recording via ffmpeg (AVFoundation default mic) with 20 curated intonations
- Auto-normalization, silence trimming, and 16,000 Hz 16-bit mono PCM conversion
- Option to re-record individual takes on stumble / noise
- Auto-splitting mode (--input <file>) for batch slicing single continuous voice memos
- Saves directly to data/household_voices/user/ with metadata manifest
"""

import os
import sys
import json
import time
import shutil
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

DEFAULT_OUTPUT_DIR = Path("data/household_voices/user")

GUIDED_PROMPTS = [
    {"phrase": "Mr. Clemens", "note": "Normal, clear conversational tone"},
    {"phrase": "Mr. Clemens", "note": "Brisk / quick everyday pace"},
    {"phrase": "Mr. Clemens", "note": "Deliberate, steady enunciation"},
    {"phrase": "Hey Mr. Clemens", "note": "Casual greeting tone"},
    {"phrase": "Hey Mr. Clemens", "note": "Fast, connected syllables ('heymisterclemens')"},
    {"phrase": "Okay Mr. Clemens", "note": "Clear assistant command tone"},
    {"phrase": "OK Mr. Clemens", "note": "Short, punchy 'OK'"},
    {"phrase": "Hi Mr. Clemens", "note": "Friendly, slightly upbeat"},
    {"phrase": "Mr. Clemens", "note": "Projected / louder (as if across the kitchen)"},
    {"phrase": "Mr. Clemens", "note": "Quiet / soft (as if speaking late at night)"},
    {"phrase": "Mr. Clemens?", "note": "Rising inflection (as if asking a question)"},
    {"phrase": "Mister Clemens", "note": "Exaggerated 'Mister' (clear 'mis-ter')"},
    {"phrase": "Mr. Clemens", "note": "Walking by / turning your head while speaking"},
    {"phrase": "Hey Mr. Clemens", "note": "From 5-8 feet away from the mic"},
    {"phrase": "Okay Mr. Clemens", "note": "Casual, relaxed kitchen voice"},
    {"phrase": "Mr. Clemens", "note": "Slightly deeper pitch"},
    {"phrase": "Hey Mr. Clemens", "note": "Slightly higher pitch"},
    {"phrase": "Mr. Clemens", "note": "Low energy / morning voice"},
    {"phrase": "Okay Mr. Clemens", "note": "Confident, prompt wake tone"},
    {"phrase": "Mr. Clemens", "note": "Natural everyday invocation"},
]


def check_ffmpeg() -> str:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        # Check standard Homebrew location
        hb_bin = "/opt/homebrew/bin/ffmpeg"
        if os.path.isfile(hb_bin) and os.access(hb_bin, os.X_OK):
            return hb_bin
        print("Error: 'ffmpeg' executable not found in PATH or /opt/homebrew/bin/ffmpeg.", file=sys.stderr)
        print("Please install ffmpeg: brew install ffmpeg", file=sys.stderr)
        sys.exit(1)
    return ffmpeg_bin


def postprocess_audio(ffmpeg_bin: str, raw_path: Path, clean_path: Path) -> bool:
    """
    Trims silence, normalizes volume, and formats to 16kHz 16-bit mono PCM.
    """
    # Filter chain:
    # 1. silenceremove at start: stop_periods=0 (don't stop), start_threshold=-40dB
    # 2. silenceremove at end: stop_periods=1, stop_threshold=-40dB, stop_duration=0.3
    # 3. loudnorm: standard broadcast audio normalization
    # 4. aresample=16000
    filter_chain = (
        "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-42dB,"
        "areverse,silenceremove=start_periods=1:start_duration=0.08:start_threshold=-42dB,areverse,"
        "loudnorm=I=-16:TP=-1.5:LRA=11,"
        "aresample=16000"
    )

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(raw_path),
        "-af", filter_chain,
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(clean_path)
    ]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode == 0 and clean_path.is_file() and clean_path.stat().st_size > 1024:
        return True

    # Fallback to simple resample if filter chain trimmed everything (e.g. whisper)
    fallback_cmd = [
        ffmpeg_bin, "-y",
        "-i", str(raw_path),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(clean_path)
    ]
    fb_res = subprocess.run(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return fb_res.returncode == 0 and clean_path.is_file() and clean_path.stat().st_size > 512


def record_live_prompt(ffmpeg_bin: str, prompt_idx: int, total: int, item: Dict[str, str], out_path: Path) -> bool:
    phrase = item["phrase"]
    note = item["note"]

    print("\n" + "=" * 65)
    print(f" Prompt [{prompt_idx}/{total}]: \"{phrase}\"")
    print(f" Style/Guidance: {note}")
    print("=" * 65)
    print(" Press [ENTER] when ready to speak (records 2.8 seconds)...", end="", flush=True)

    try:
        input()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted by user.")
        sys.exit(0)

    print(" 🔴 [RECORDING NOW] Speak clearly: ", f"\"{phrase}\" ... ", end="", flush=True)

    raw_temp = out_path.with_suffix(".raw.wav")
    rec_cmd = [
        ffmpeg_bin, "-y",
        "-f", "avfoundation",
        "-i", ":default",
        "-t", "2.8",
        "-ar", "48000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(raw_temp)
    ]

    proc = subprocess.run(rec_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if proc.returncode != 0:
        # Retry with device 2 (MacBook Pro Microphone fallback)
        rec_cmd[4] = ":2"
        proc = subprocess.run(rec_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("✓ Done!")

    if proc.returncode != 0 or not raw_temp.is_file():
        print(" ❌ Error recording audio. Check microphone permissions.")
        return False

    success = postprocess_audio(ffmpeg_bin, raw_temp, out_path)
    if raw_temp.is_file():
        raw_temp.unlink()

    if not success:
        print(" ⚠️  Audio seemed empty or silent. Press [r] to retry, or [Enter] to skip.")
        ans = input(" [r]etry / [ENTER] skip: ").strip().lower()
        if ans == "r":
            return record_live_prompt(ffmpeg_bin, prompt_idx, total, item, out_path)
        return False

    # Review step
    dur_sec = out_path.stat().st_size / (16000 * 2)
    print(f" 💾 Saved: {out_path.name} ({dur_sec:.2f}s, 16kHz mono)")
    print(" Press [ENTER] to continue, or [r] to re-record take: ", end="", flush=True)
    ans = input().strip().lower()
    if ans == "r":
        return record_live_prompt(ffmpeg_bin, prompt_idx, total, item, out_path)

    return True


def run_guided_session(ffmpeg_bin: str, output_dir: Path, count: int):
    output_dir.mkdir(parents=True, exist_ok=True)
    prompts = GUIDED_PROMPTS[:count]

    print("\n" + "#" * 65)
    print("  Mr. Clemens Wake Word — Voice Training Data Collector")
    print("#" * 65)
    print(f" Target Directory: {output_dir.resolve()}")
    print(f" Prompts to Record: {len(prompts)}")
    print("\n Tips for Maximum Accuracy:")
    print(" • Speak naturally as you would to your voice satellite.")
    print(" • Vary your distance slightly (arm's length to across the room).")
    print(" • Don't over-enunciate—everyday conversational cadence is best.")

    manifest: List[Dict[str, str]] = []
    success_count = 0

    for i, item in enumerate(prompts, start=1):
        target_file = output_dir / f"sample_{i:02d}.wav"
        ok = record_live_prompt(ffmpeg_bin, i, len(prompts), item, target_file)
        if ok:
            success_count += 1
            manifest.append({
                "file": target_file.name,
                "phrase": item["phrase"],
                "note": item["note"],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })

    # Save manifest
    manifest_file = output_dir / "samples_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("\n" + "=" * 65)
    print(f" 🎉 Recording Complete! Successfully captured {success_count}/{len(prompts)} samples.")
    print(f" Manifest saved: {manifest_file}")
    print("=" * 65)


def split_audio_file(ffmpeg_bin: str, input_file: Path, output_dir: Path):
    """
    Splits a single continuous audio recording (e.g. from Voice Memos) into
    individual 16kHz mono wake word samples based on silence detection.
    """
    if not input_file.is_file():
        print(f"Error: Input file '{input_file}' not found.", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nAnalyzing continuous audio file: {input_file}")
    print("Detecting speech segments using silence detection...")

    # Run silencedetect
    cmd = [
        ffmpeg_bin, "-i", str(input_file),
        "-af", "silencedetect=noise=-30dB:d=0.45",
        "-f", "null", "-"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    silence_starts = []
    silence_ends = []

    for line in proc.stderr.splitlines():
        if "silence_start:" in line:
            try:
                val = float(line.split("silence_start:")[1].strip().split()[0])
                silence_starts.append(val)
            except Exception:
                pass
        elif "silence_end:" in line:
            try:
                val = float(line.split("silence_end:")[1].split("|")[0].strip().split()[0])
                silence_ends.append(val)
            except Exception:
                pass

    if not silence_starts and not silence_ends:
        print("No distinct silence intervals detected. Converting full file to 16kHz mono.")
        out_single = output_dir / "sample_01.wav"
        postprocess_audio(ffmpeg_bin, input_file, out_single)
        print(f"Saved: {out_single}")
        return

    # Derive speech segments between silences
    segments = []
    last_end = 0.0

    for s_start in silence_starts:
        if s_start - last_end >= 0.4:
            segments.append((last_end, s_start))
        # Find corresponding silence end
        matching_ends = [e for e in silence_ends if e >= s_start]
        if matching_ends:
            last_end = matching_ends[0]
        else:
            last_end = s_start + 0.5

    # Check tail
    if len(silence_ends) > 0 and last_end > 0:
        # Check if there is speech after last silence
        pass

    if not segments:
        print("Could not isolate distinct speech intervals. Converting full file.")
        out_single = output_dir / "sample_01.wav"
        postprocess_audio(ffmpeg_bin, input_file, out_single)
        return

    print(f"Detected {len(segments)} candidate speech segment(s). Exporting...")
    manifest = []
    saved_count = 0

    for idx, (start, end) in enumerate(segments, start=1):
        duration = end - start
        if duration < 0.4 or duration > 4.5:
            # Skip blips or huge run-ons
            continue

        raw_chunk = output_dir / f"chunk_{idx}.wav"
        cut_cmd = [
            ffmpeg_bin, "-y",
            "-ss", f"{start:.3f}",
            "-to", f"{end:.3f}",
            "-i", str(input_file),
            "-c:a", "copy",
            str(raw_chunk)
        ]
        subprocess.run(cut_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        clean_file = output_dir / f"sample_{saved_count + 1:02d}.wav"
        ok = postprocess_audio(ffmpeg_bin, raw_chunk, clean_file)
        if raw_chunk.is_file():
            raw_chunk.unlink()

        if ok:
            saved_count += 1
            manifest.append({
                "file": clean_file.name,
                "start": start,
                "end": end,
                "duration": duration,
                "phrase": "Mr. Clemens"
            })
            print(f" ✓ Saved: {clean_file.name} [{start:.2f}s -> {end:.2f}s, dur: {duration:.2f}s]")

    manifest_file = output_dir / "samples_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n🎉 Successfully split and formatted {saved_count} samples into {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Record or split voice samples for microWakeWord training")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"Target output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--count", type=int, default=20,
                        help="Number of guided prompts to record (default: 20)")
    parser.add_argument("--input", type=Path, default=None,
                        help="Path to an existing continuous audio file (.wav, .m4a, .mp3) to split automatically")

    args = parser.parse_args()
    ffmpeg_bin = check_ffmpeg()

    if args.input:
        split_audio_file(ffmpeg_bin, args.input, args.output_dir)
    else:
        run_guided_session(ffmpeg_bin, args.output_dir, args.count)


if __name__ == "__main__":
    main()
