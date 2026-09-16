#!/usr/bin/env bash
set -euo pipefail

# scripts/ci/test.sh
# Shared CI & local test runner for esphome-satellite.
# Parameterized for paths and Nim versions.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"

# Resolve nim-esphome path
if [ -n "${NIM_ESPHOME_PATH:-}" ]; then
  ESPHOME_ARG="--path:${NIM_ESPHOME_PATH}"
elif [ -d "${REPO_ROOT}/../nim-esphome/src" ]; then
  ESPHOME_ARG="--path:../nim-esphome/src"
elif [ -d "${REPO_ROOT}/nim-esphome/src" ]; then
  ESPHOME_ARG="--path:nim-esphome/src"
else
  ESPHOME_ARG=""
fi

# Resolve nim-typestates path
if [ -n "${NIM_TYPESTATES_PATH:-}" ]; then
  TYPESTATES_ARG="--path:${NIM_TYPESTATES_PATH}"
elif [ -d "${REPO_ROOT}/../nim-typestates/src" ]; then
  TYPESTATES_ARG="--path:../nim-typestates/src"
elif [ -d "${REPO_ROOT}/nim-typestates/src" ]; then
  TYPESTATES_ARG="--path:nim-typestates/src"
else
  TYPESTATES_ARG=""
fi

NIM_OPTS=()
if [ -n "${ESPHOME_ARG}" ]; then
  NIM_OPTS+=("${ESPHOME_ARG}")
fi
if [ -n "${TYPESTATES_ARG}" ]; then
  NIM_OPTS+=("${TYPESTATES_ARG}")
fi

echo "=== Running esphome-satellite Test Suites ==="
echo "Nim version: $(nim --version | head -n 1)"
echo "Path flags: ${NIM_OPTS[*]:-none}"

TEST_FILES=(
  "tests/test_fsm.nim"
  "tests/test_version_sync.nim"
  "tests/test_audio_dsp.nim"
  "tests/test_audio_volume.nim"
  "tests/test_xvf3800.nim"
  "tests/test_wake_loader.nim"
  "tests/test_pcm_player.nim"
  "tests/test_cancellation.nim"
  "tests/test_nvs_migration.nim"
  "tests/test_satellite_system.nim"
  "tests/test_audio_stream_tracker.nim"
  "tests/test_watchdog_loop.nim"
)

for t in "${TEST_FILES[@]}"; do
  if [ -f "$t" ]; then
    echo "--- Running $t ---"
    nim c -r "${NIM_OPTS[@]}" "$t"
    bin="${t%.nim}"
    rm -f "$bin"
  fi
done

echo "--- Verifying ESP32 compilation syntax for src/nim_esphome_satellite.nim ---"
nim cpp --compileOnly --noMain:on --mm:arc -d:danger -d:useMalloc -d:esphome \
  --cpu:esp --os:any --exceptions:goto --panics:on \
  "${NIM_OPTS[@]}" src/nim_esphome_satellite.nim

echo "=== All tests passed successfully ==="
