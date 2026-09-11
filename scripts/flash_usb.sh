#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PORT="${1:-}"

if [ -z "$PORT" ]; then
    echo "Usage: $0 <serial-port> [baud]"
    echo ""
    echo "Available ports:"
    ls -1 /dev/cu.usb* /dev/cu.wch* 2>/dev/null || echo "  (no USB serial ports found)"
    exit 1
fi

BAUD="${2:-460800}"

cd "$ROOT_DIR"

if command -v esptool.py >/dev/null 2>&1; then
    ESPTOOL=(esptool.py)
elif command -v uv >/dev/null 2>&1; then
    ESPTOOL=(uv run --with esphome esptool.py)
else
    echo "ERROR: Neither esptool.py nor uv found!" >&2
    exit 1
fi

echo "=== Flashing discrete partitions over USB (Preserving NVS at 0x9000) ==="
echo "Port: $PORT at $BAUD baud"

# Check binary existence
BOOTLOADER="web/bootloader.bin"
PARTITIONS="web/partitions.bin"
OTADATA="web/ota_data_initial.bin"
APP="web/firmware-ota.bin"

for f in "$BOOTLOADER" "$PARTITIONS" "$OTADATA" "$APP"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: Required binary '$f' not found! Run scripts/build_factory_binary.sh first." >&2
        exit 1
    fi
done

"${ESPTOOL[@]}" --chip esp32s3 --port "$PORT" --baud "$BAUD" \
    --before default_reset --after hard_reset write_flash -z \
    --flash_mode dio --flash_freq 80m --flash_size 16MB \
    0x0 "$BOOTLOADER" \
    0x8000 "$PARTITIONS" \
    0xE000 "$OTADATA" \
    0x10000 "$APP"

echo "=== USB flash complete! NVS preferences preserved. ==="
