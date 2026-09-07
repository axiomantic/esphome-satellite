#!/usr/bin/env bash
set -euo pipefail

echo "=== Running nim-esphome-satellite typestate invariant test suite ==="
nim c -r tests/test_fsm.nim
rm -f tests/test_fsm

echo "=== Running version synchronization invariant test ==="
nim c -r tests/test_version_sync.nim
rm -f tests/test_version_sync

echo "=== Testing embedded C++ transpilation (ESP32 target) ==="
nim cpp --compileOnly --noMain:on --mm:arc -d:danger -d:useMalloc -d:esphome --cpu:esp --os:any --exceptions:goto --panics:on src/nim_esphome_satellite.nim

echo "=== Running wake word trainer TypeScript tests ==="
(cd trainer && npm test)

echo "=== All satellite state machine checks passed! ==="

