#!/usr/bin/env bash
set -euo pipefail

echo "=== Running 1. Satellite FSM typestate invariant tests ==="
nim c -r tests/test_fsm.nim
rm -f tests/test_fsm

echo "=== Running 2. Version synchronization invariant tests ==="
nim c -r tests/test_version_sync.nim
rm -f tests/test_version_sync

echo "=== Running 3. Real-time audio DSP tests ==="
nim c -r tests/test_audio_dsp.nim
rm -f tests/test_audio_dsp

echo "=== Running 4. XVF3800 hardware and LED ring tests ==="
nim c -r tests/test_xvf3800.nim
rm -f tests/test_xvf3800

echo "=== Running 5. Dynamic microWakeWord partition loader tests ==="
nim c -r tests/test_wake_loader.nim
rm -f tests/test_wake_loader

echo "=== Running 6. PCM sound player and IMA-ADPCM decoder tests ==="
nim c -r tests/test_pcm_player.nim
rm -f tests/test_pcm_player

echo "=== Running 7. Mid-utterance cancellation phrase matcher tests ==="
nim c -r tests/test_cancellation.nim
rm -f tests/test_cancellation

echo "=== Running 8. Synthetic wake word corpus generator tests ==="
if [ -x ".venv/bin/python" ]; then
  .venv/bin/python -m unittest tests/test_wakeword_corpus.py
else
  python3 -m unittest tests/test_wakeword_corpus.py
fi

echo "=== Running 9. NVS preference migration and hash integrity tests ==="
nim c -r tests/test_nvs_migration.nim
rm -f tests/test_nvs_migration

echo "=== Testing embedded C++ transpilation (ESP32 target) ==="
nim cpp --compileOnly --noMain:on --mm:arc -d:danger -d:useMalloc -d:esphome --cpu:esp --os:any --exceptions:goto --panics:on src/nim_esphome_satellite.nim

echo "=== All satellite invariant test suites passed! ==="


