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

VERSION=$(grep -E '^\s*version\s*=' esphome_satellite.nimble | head -n 1 | sed -E 's/.*"([^"]+)".*/\1/')
echo "Compiling packages/respeaker_xvf3800.yaml for version v$VERSION..."
"${CMD[@]}" compile -s version "$VERSION" packages/respeaker_xvf3800.yaml

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
shasum -a 256 web/firmware-factory.bin
if [ -f web/firmware-ota.bin ]; then
    shasum -a 256 web/firmware-ota.bin
fi

echo "=== Factory binary build complete! ==="
