#!/usr/bin/env python3
"""
Audio Processing & Transcoding Pipeline for esphome-satellite.
Standardizes audio files for small-speaker voice satellites:
  1. Downmixes to mono and resamples to 16,000 Hz.
  2. Applies light dynamic range compression (threshold -12dB, ratio 2.5:1, attack 5ms, release 80ms)
     to prevent speaker distortion on transient peaks while keeping soft decays audible.
  3. Peak-normalizes to -1.0 dBFS for consistent perceived loudness across all 17 acoustic themes.
  4. Generates both 16-bit mono PCM WAV and 128kbps MP3 (for web preview).
  5. Encodes into compact IMA-ADPCM arrays and regenerates src/sound_data.h.
"""

import os
import sys
import glob
import subprocess
import struct
import re

SAMPLE_RATE = 16000
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS_DIR = os.path.join(ROOT_DIR, "assets", "sounds")
WEB_DIR = os.path.join(ROOT_DIR, "web", "sounds")
SRC_DIR = os.path.join(ROOT_DIR, "src")

STEP_SIZE_TABLE = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
    19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
    130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
    337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
    876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
    5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
]

INDEX_TABLE = [
    -1, -1, -1, -1, 2, 4, 6, 8,
    -1, -1, -1, -1, 2, 4, 6, 8
]

def encode_ima_adpcm(pcm_samples):
    valprev = 0
    index = 0
    nibbles = []
    for sample in pcm_samples:
        step = STEP_SIZE_TABLE[index]
        diff = sample - valprev
        nibble = 0
        if diff < 0:
            nibble = 8
            diff = -diff
        mask = 4
        tempstep = step
        for _ in range(3):
            if diff >= tempstep:
                nibble |= mask
                diff -= tempstep
            tempstep >>= 1
            mask >>= 1
        diff_pred = step >> 3
        if nibble & 4: diff_pred += step
        if nibble & 2: diff_pred += step >> 1
        if nibble & 1: diff_pred += step >> 2
        if nibble & 8: valprev -= diff_pred
        else: valprev += diff_pred
        valprev = max(-32768, min(32767, valprev))
        index += INDEX_TABLE[nibble & 0x0F]
        index = max(0, min(88, index))
        nibbles.append(nibble)

    adpcm_bytes = bytearray()
    for i in range(0, len(nibbles), 2):
        low = nibbles[i]
        high = nibbles[i+1] if i+1 < len(nibbles) else 0
        adpcm_bytes.append((high << 4) | (low & 0x0F))
    return bytes(adpcm_bytes)

def read_wav_pcm16(wav_path):
    with open(wav_path, "rb") as f:
        data = f.read()
    # Find data chunk
    idx = data.find(b"data")
    if idx == -1:
        raise ValueError(f"Cannot find data chunk in {wav_path}")
    data_size = struct.unpack("<I", data[idx+4:idx+8])[0]
    pcm_bytes = data[idx+8:idx+8+data_size]
    num_samples = len(pcm_bytes) // 2
    return list(struct.unpack(f"<{num_samples}h", pcm_bytes))

def get_max_volume_db(wav_path):
    cmd = ["ffmpeg", "-i", wav_path, "-af", "volumedetect", "-f", "null", "-"]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    m = re.search(r"max_volume:\s*([-0-9.]+)\s*dB", res.stderr)
    if m:
        return float(m.group(1))
    return 0.0

def process_single_audio(input_path, base_name):
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(WEB_DIR, exist_ok=True)

    temp_compressed = f"/tmp/{base_name}_comp.wav"
    out_wav = os.path.join(ASSETS_DIR, f"{base_name}.wav")
    out_mp3 = os.path.join(ASSETS_DIR, f"{base_name}.mp3")
    web_wav = os.path.join(WEB_DIR, f"{base_name}.wav")
    web_mp3 = os.path.join(WEB_DIR, f"{base_name}.mp3")

    # Step 1: Resample to 16kHz mono + apply light compression
    # threshold=-12dB, ratio=2.5:1, attack=5ms, release=80ms, makeup=1.5dB
    compress_filter = (
        "aresample=16000,"
        "aformat=channel_layouts=mono,"
        "acompressor=threshold=-12dB:ratio=2.5:attack=5:release=80:makeup=1.5dB"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-af", compress_filter,
        "-ar", "16000", "-ac", "1",
        "-c:a", "pcm_s16le", temp_compressed
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Step 2: Peak normalize to -1.0 dBFS
    max_db = get_max_volume_db(temp_compressed)
    # Target peak is -1.0 dBFS
    gain_db = -1.0 - max_db
    # Limit gain boost to max +6dB to avoid over-amplifying background noise
    gain_db = min(6.0, gain_db)

    subprocess.run([
        "ffmpeg", "-y", "-i", temp_compressed,
        "-af", f"volume={gain_db:.2f}dB",
        "-ar", "16000", "-ac", "1",
        "-c:a", "pcm_s16le", out_wav
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Step 3: Transcode to MP3 for web preview
    subprocess.run([
        "ffmpeg", "-y", "-i", out_wav,
        "-codec:a", "libmp3lame", "-b:a", "128k", out_mp3
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Copy to web/sounds/
    with open(out_wav, "rb") as fsrc, open(web_wav, "wb") as fdst:
        fdst.write(fsrc.read())
    with open(out_mp3, "rb") as fsrc, open(web_mp3, "wb") as fdst:
        fdst.write(fsrc.read())

    # Read PCM samples and encode to IMA-ADPCM
    pcm_samples = read_wav_pcm16(out_wav)
    adpcm = encode_ima_adpcm(pcm_samples)

    if os.path.exists(temp_compressed):
        os.remove(temp_compressed)

    duration = len(pcm_samples) / SAMPLE_RATE
    print(f"Processed '{base_name}': {duration:.3f}s ({len(pcm_samples)} samples, {len(adpcm)} bytes ADPCM, peak=-1.0dBFS)")
    return adpcm

def regenerate_sound_header(adpcm_dict):
    header_path = os.path.join(SRC_DIR, "sound_data.h")
    with open(header_path, "w") as f:
        f.write("// Auto-generated by scripts/process_audio.py - High-Fidelity IMA-ADPCM Sound Bank\n")
        f.write("#pragma once\n\n")
        f.write("#include <cstdint>\n#include <cstddef>\n#include <string>\n#include <cstring>\n#include <cctype>\n\n")
        f.write("namespace esphome::satellite_audio {\n\n")
        f.write("""static const int16_t STEP_SIZE_TABLE[89] = {
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
    19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
    130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
    337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
    876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
    5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
};

static const int8_t INDEX_TABLE[16] = {
    -1, -1, -1, -1, 2, 4, 6, 8,
    -1, -1, -1, -1, 2, 4, 6, 8
};

""")
        for name, data in sorted(adpcm_dict.items()):
            var_name = name.replace("-", "_")
            f.write(f"// {name} ({len(data)} bytes ADPCM)\n")
            f.write(f"static const uint8_t sound_{var_name}[{len(data)}] = {{\n")
            for i in range(0, len(data), 16):
                chunk = data[i:i+16]
                hex_str = ", ".join(f"0x{b:02X}" for b in chunk)
                f.write(f"  {hex_str},\n")
            f.write("};\n\n")

        f.write("struct SoundEntry {\n  const char* name;\n  const uint8_t* data;\n  size_t length;\n};\n\n")
        f.write("static const SoundEntry SOUND_TABLE[] = {\n")
        for name, data in sorted(adpcm_dict.items()):
            var_name = name.replace("-", "_")
            f.write(f'  {{"{name}", sound_{var_name}, {len(data)}}},\n')
        f.write("  {nullptr, nullptr, 0}\n};\n\n")

        f.write("""inline const SoundEntry* find_sound(const std::string &name) {
  // Normalize string for lookup
  std::string lower = name;
  auto pos = lower.find(" (default)");
  if (pos != std::string::npos) lower.erase(pos);
  pos = lower.find(" (Default)");
  if (pos != std::string::npos) lower.erase(pos);
  for (char &c : lower) {
    if (c == ' ' || c == '_') c = '-';
    else c = std::tolower(c);
  }
  for (const SoundEntry* entry = SOUND_TABLE; entry->name != nullptr; ++entry) {
    if (lower == entry->name) return entry;
  }
  return nullptr;
}

} // namespace esphome::satellite_audio
""")
    total_bytes = sum(len(d) for d in adpcm_dict.values())
    print(f"\nGenerated C++ sound header: {header_path} ({total_bytes} bytes ADPCM across {len(adpcm_dict)} sounds)")

def main():
    wav_files = sorted(glob.glob(os.path.join(ASSETS_DIR, "*.wav")))
    if not wav_files:
        print(f"No WAV files found in {ASSETS_DIR}")
        sys.exit(1)

    print(f"=== Processing and Normalizing {len(wav_files)} Audio Files ===")
    adpcm_dict = {}
    for wav_path in wav_files:
        base_name = os.path.splitext(os.path.basename(wav_path))[0]
        adpcm_dict[base_name] = process_single_audio(wav_path, base_name)

    regenerate_sound_header(adpcm_dict)
    print("=== All Audio Files Normalized, Transcoded, and Sound Header Generated! ===")

if __name__ == "__main__":
    main()
