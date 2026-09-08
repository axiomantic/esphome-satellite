# Package

version       = "0.5.0"
author        = "Elijah Rust"
description   = "An on-device state supervisor for ESPHome voice satellites that eliminates audio glitches, race conditions, and stuck states"
license       = "MIT"
srcDir        = "src"

# Dependencies

requires "nim >= 2.2.8"
requires "https://github.com/axiomantic/nim-esphome >= 0.4.0"
requires "typestates >= 0.12.0"

task test, "Run satellite invariant test suites":
  exec "nim c -r tests/test_fsm.nim"
  exec "nim c -r tests/test_version_sync.nim"
  exec "nim c -r tests/test_audio_dsp.nim"
  exec "nim c -r tests/test_xvf3800.nim"
  exec "nim c -r tests/test_wake_loader.nim"
  exec "nim c -r tests/test_pcm_player.nim"
  exec "nim c -r tests/test_cancellation.nim"

task check_cpp, "Verify embedded C++ generation for ESP32 target":
  exec "nim cpp --compileOnly --noMain:on --mm:arc -d:danger -d:useMalloc -d:esphome --cpu:esp --os:any --exceptions:goto --panics:on src/nim_esphome_satellite.nim"

