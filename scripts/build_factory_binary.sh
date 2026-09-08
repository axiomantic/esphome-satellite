#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building esphome-satellite factory firmware for Web Installer ==="
cd "$ROOT_DIR"

# Enable ccache for ESP-IDF toolchain
export IDF_CCACHE_ENABLE=1
if [ -d "$HOME/.cache/ccache-links" ]; then
    export PATH="$HOME/.cache/ccache-links:/opt/homebrew/opt/ccache/libexec:/opt/homebrew/bin:$PATH"
elif [ -d "/opt/homebrew/opt/ccache/libexec" ]; then
    export PATH="/opt/homebrew/opt/ccache/libexec:/opt/homebrew/bin:$PATH"
fi

if [ -n "${ESPHOME_CMD:-}" ]; then
    CMD=($ESPHOME_CMD)
elif command -v esphome >/dev/null 2>&1; then
    CMD=(esphome)
elif command -v uv >/dev/null 2>&1; then
    CMD=(uv run --python 3.11 --with esphome esphome)
else
    echo "ERROR: Neither esphome nor uv found!" >&2
    exit 1
fi

echo "Refreshing external components cache..."
rm -rf packages/.esphome/external_components
rm -rf packages/.esphome/build/*/src/esphome/components/nim

if [ "${PROCESS_AUDIO:-0}" = "1" ] || [ ! -f "$ROOT_DIR/src/sound_data.h" ]; then
    echo "Processing, compressing, and normalizing audio assets..."
    if command -v ffmpeg >/dev/null 2>&1; then
        if command -v python3 >/dev/null 2>&1; then
            python3 "$ROOT_DIR/scripts/process_audio.py"
        elif command -v nim >/dev/null 2>&1; then
            nim c -r "$ROOT_DIR/scripts/transcode_sounds.nim"
        fi
    else
        echo "ffmpeg not found; using existing audio assets."
    fi
else
    echo "Using existing pre-compiled sound_data.h assets (set PROCESS_AUDIO=1 to re-transcode)."
fi

VERSION=$(grep -E '^\s*version\s*=' esphome_satellite.nimble | head -n 1 | sed -E 's/.*"([^"]+)".*/\1/')
echo "Compiling packages/respeaker_xvf3800.yaml for version v$VERSION..."
"${CMD[@]}" -s version "$VERSION" compile packages/respeaker_xvf3800.yaml

# Find factory and ota binaries
FACTORY_BIN=$(find . -type f -name "firmware.factory.bin" -not -path "*/.git/*" -not -path "./web/*" | head -n 1)
OTA_BIN=$(find . -type f -name "firmware.ota.bin" -not -path "*/.git/*" -not -path "./web/*" | head -n 1)

if [ -z "$FACTORY_BIN" ] || [ ! -f "$FACTORY_BIN" ]; then
    echo "ERROR: firmware.factory.bin not found!" >&2
    exit 1
fi

mkdir -p web
cp "$FACTORY_BIN" web/firmware-factory.bin
echo "Copied factory binary to web/firmware-factory.bin ($(wc -c < web/firmware-factory.bin | tr -d ' ') bytes)"

if [ -n "$OTA_BIN" ] && [ -f "$OTA_BIN" ]; then
    cp "$OTA_BIN" web/firmware-ota.bin
    echo "Copied OTA binary to web/firmware-ota.bin ($(wc -c < web/firmware-ota.bin | tr -d ' ') bytes)"
fi

echo "SHA256 checksums:"
FACTORY_SHA256=$(shasum -a 256 web/firmware-factory.bin | awk '{print $1}')
echo "  factory: $FACTORY_SHA256"
OTA_SHA256=""
if [ -f web/firmware-ota.bin ]; then
    OTA_SHA256=$(shasum -a 256 web/firmware-ota.bin | awk '{print $1}')
    echo "  ota:     $OTA_SHA256"
fi

GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat << EOF > web/version.json
{
  "name": "esphome-satellite",
  "version": "$VERSION",
  "commit": "$GIT_SHA",
  "built_at": "$BUILD_TIME",
  "factory_sha256": "$FACTORY_SHA256",
  "ota_sha256": "$OTA_SHA256"
}
EOF
echo "Generated web/version.json (v$VERSION, commit $GIT_SHA, built $BUILD_TIME)"

# Update version in web/manifest.json
if [ -f web/manifest.json ]; then
    python3 -c "
import json
with open('web/manifest.json', 'r') as f:
    m = json.load(f)
m['version'] = '$VERSION+$GIT_SHA'
m['commit'] = '$GIT_SHA'
m['built_at'] = '$BUILD_TIME'
with open('web/manifest.json', 'w') as f:
    json.dump(m, f, indent=2)
"
    echo "Updated web/manifest.json with build metadata (v$VERSION+$GIT_SHA)"
fi

echo "=== Factory binary build complete! ==="

