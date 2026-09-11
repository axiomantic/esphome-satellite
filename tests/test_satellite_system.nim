import unittest
import ../src/satellite_system

var otaStartedCalled = false
var otaEndResult = false

proc nim_satellite_ota_start() {.exportc, cdecl.} =
  otaStartedCalled = true

proc nim_satellite_ota_end(ok: bool) {.exportc, cdecl.} =
  otaEndResult = ok

suite "Satellite System Control & OTA Invariants":
  setup:
    otaStartedCalled = false
    otaEndResult = false

  test "OTA URL validation rules":
    check isValidOtaUrl("https://raw.githubusercontent.com/axiomantic/esphome-satellite/main/web/firmware-ota.bin") == true
    check isValidOtaUrl("http://10.0.2.1/firmware.bin") == true
    check isValidOtaUrl("ftp://example.com/firmware.bin") == false
    check isValidOtaUrl("") == false
    check isValidOtaUrl("https://") == false
    check isValidOtaUrl("short") == false

  test "Host simulated OTA execution":
    # On host platform, nim_satellite_flash_firmware_ota runs the simulated validation path
    check nim_satellite_flash_firmware_ota(nil) == false
    check otaStartedCalled == false

    check nim_satellite_flash_firmware_ota("invalid-url") == false
    check otaStartedCalled == false

    check nim_satellite_flash_firmware_ota("https://example.com/valid.bin") == true
    check otaStartedCalled == true
    check otaEndResult == true

  test "Inference suspension and resumption safety":
    # Must execute safely without panic on host
    nim_satellite_suspend_inference()
    nim_satellite_resume_inference()
