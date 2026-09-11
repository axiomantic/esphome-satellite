## Satellite System Control & OTA Update Orchestration in Nim
##
## Implements:
## - Software system restart (invoking App.safe_reboot via nim-esphome API)
## - FreeRTOS microWakeWord task suspension and resumption to prevent flash cache panics
## - Firmware OTA download, validation, partition writing, and boot configuration

import nim_esphome
export isValidOtaUrl

# Forward declarations of FSM callbacks if not already declared in compilation unit
when not declared(nim_satellite_ota_start):
  proc nim_satellite_ota_start*() {.importc: "nim_satellite_ota_start", cdecl.}
when not declared(nim_satellite_ota_end):
  proc nim_satellite_ota_end*(ok: bool) {.importc: "nim_satellite_ota_end", cdecl.}

proc nim_satellite_restart*() {.exportc, cdecl.} =
  ## Triggers a clean software restart of the satellite with a 1-second grace delay.
  info("SatelliteSystem", "Software restart requested. Flushing preferences and rebooting in 1000ms...")
  discard syncPreferences()
  delayMs(1000)
  reboot()

proc nim_satellite_suspend_inference*() {.exportc, cdecl.} =
  ## Suspends microWakeWord FreeRTOS task to prevent CPU 0 instruction cache invalidation
  ## while flash memory sectors are erased and written during OTA.
  info("SatelliteSystem", "Suspending microWakeWord inference before flash operations...")
  discard suspendTask("mww")

proc nim_satellite_resume_inference*() {.exportc, cdecl.} =
  ## Resumes microWakeWord FreeRTOS task after flash operations complete.
  info("SatelliteSystem", "Resuming microWakeWord inference after flash operations...")
  discard resumeTask("mww")

proc nim_satellite_flash_firmware_ota*(urlCStr: cstring): bool {.exportc, cdecl.} =
  ## Orchestrates remote firmware OTA download and partition writing in Nim.
  if urlCStr == nil:
    error("SatelliteOTA", "Firmware OTA URL is null!")
    return false

  let url = $urlCStr
  if not isValidOtaUrl(url):
    error("SatelliteOTA", "Firmware OTA URL is invalid: " & url)
    return false

  info("SatelliteOTA", "Starting remote firmware OTA from URL: " & url)

  # Notify FSM to enter Updating typestate (suppresses DSP audio & sets LEDs)
  nim_satellite_ota_start()

  # Suspend inference FreeRTOS task to prevent flash cache collision
  nim_satellite_suspend_inference()

  let ok = flashOtaPartition(url)

  nim_satellite_resume_inference()
  nim_satellite_ota_end(ok)

  if ok:
    info("SatelliteOTA", "Firmware OTA update successful! Rebooting in 1000ms...")
    delayMs(1000)
    reboot()

  return ok
