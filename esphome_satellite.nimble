# Package

version       = "0.3.0"
author        = "Elijah Rust"
description   = "An on-device state supervisor for ESPHome voice satellites that eliminates audio glitches, race conditions, and stuck states"
license       = "MIT"
srcDir        = "src"

# Dependencies

requires "nim >= 2.2.8"
requires "nim_esphome >= 0.3.0"
requires "typestates >= 0.12.0"

task test, "Run satellite typestate invariant tests":
  exec "nim c -r tests/test_fsm.nim"

task check_cpp, "Verify embedded C++ generation for ESP32 target":
  exec "nim cpp --compileOnly --noMain:on --mm:arc -d:danger -d:useMalloc -d:esphome --cpu:esp --os:any --exceptions:goto --panics:on src/nim_esphome_satellite.nim"

