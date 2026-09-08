import std/[os, strutils, json]
import nim_esphome/dsl/installer

proc getPackageVersion(): string =
  let nimbleContent = readFile("esphome_satellite.nimble")
  for line in nimbleContent.splitLines():
    let trimmed = line.strip()
    if trimmed.startsWith("version"):
      let parts = trimmed.split('=')
      if parts.len == 2:
        return parts[1].strip().strip(chars = {'"', ' '})
  raise newException(ValueError, "Could not find version in esphome_satellite.nimble")

let currentVersion = getPackageVersion()

let satelliteInstaller = esphomeInstaller("esphome-satellite"):
  installer.title = "esphome-satellite Web Installer"
  installer.description = "On-device state supervisor for ESPHome and Home Assistant voice satellites with hardware target switching, multi-wake-word selection, and customizable audio feedback."
  installer.version = currentVersion
  installer.homeAssistantDomain = "esphome"
  installer.chipFamily = "ESP32-S3"
  installer.factoryBinPath = "firmware-factory.bin"

  # Discrete partition parts (skips NVS partition 0x9000-0xE000 to preserve device state across flashes)
  installer.addBasePart("bootloader.bin", 0x0'u32)
  installer.addBasePart("partitions.bin", 0x8000'u32)
  installer.addBasePart("ota_data_initial.bin", 0xE000'u32)
  installer.addBasePart("firmware-ota.bin", 0x10000'u32)

  let satelliteParts = @[
    InstallerPart(path: "bootloader.bin", offset: 0x0'u32),
    InstallerPart(path: "partitions.bin", offset: 0x8000'u32),
    InstallerPart(path: "ota_data_initial.bin", offset: 0xE000'u32),
    InstallerPart(path: "firmware-ota.bin", offset: 0x10000'u32)
  ]

  # Hardware Board Targets
  installer.addTarget(
    name = "Seeed ReSpeaker XVF3800",
    binPath = "firmware-ota.bin",
    chipFamily = "ESP32-S3",
    description = "Seeed ReSpeaker XVF3800 with 4-mic array and hardware acoustic echo cancellation",
    parts = satelliteParts
  )

  # Custom Wake Word Models (Up to 3 microWakeWord .tflite models in dedicated partitions)
  installer.addCustomWakeWordSlotsField(
    name = "custom_wake_words",
    label = "Custom Wake Word Models (.tflite)",
    maxSlots = 3,
    slotOffsets = @[0x510000'u32, 0x550000'u32, 0x590000'u32],
    slotPartitions = @["wake_model", "wake_model_2", "wake_model_3"],
    maxSize = 262144, # 256 KB per slot
    description = "Optional: Upload up to 3 custom microWakeWord .tflite models to flash into dedicated partitions. Note: Flashing custom wake words stores them on the device, but does not activate them. After flashing and setting up your device, open Home Assistant, navigate to your device controls page, and select your wake word from the Active Wake Word dropdown."
  )

  # Custom Wake Chimes (chime_data partition at 0x4D0000)
  installer.addMultiCustomAudioField(
    name = "custom_chimes",
    label = "Custom Wake Chimes",
    partition = "chime_data",
    flashOffset = 0x4D0000'u32,
    maxSize = 262144, # 256 KB
    description = "Optional: Add custom acknowledgement chimes. The web installer automatically resamples audio to 16kHz mono 16-bit PCM WAV, applies dynamic range compression, and normalizes peak volume to -1.0 dBFS directly in your browser. Note: Uploading sounds stores them on the device, but does not set the active chime. Once flashed and connected, choose your custom chime in Home Assistant on the device controls page."
  )

  # Custom Processing Sounds (sound_data partition at 0x490000)
  installer.addMultiCustomAudioField(
    name = "custom_processing_sounds",
    label = "Custom Processing Sounds",
    partition = "sound_data",
    flashOffset = 0x490000'u32,
    maxSize = 262144, # 256 KB
    description = "Optional: Add custom processing loop sounds. Transcoded, compressed, and peak-normalized automatically in your browser. Note: Uploading sounds stores them on the device, but does not set the active processing sound. Once flashed and connected, choose your custom sound in Home Assistant on the device controls page."
  )

  # Custom Cancel Sounds (cancel_data partition at 0x5D0000)
  installer.addMultiCustomAudioField(
    name = "custom_cancel_sounds",
    label = "Custom Cancel Sounds",
    partition = "cancel_data",
    flashOffset = 0x5D0000'u32,
    maxSize = 262144, # 256 KB
    description = "Optional: Add custom cancellation tones. Transcoded, compressed, and peak-normalized automatically in your browser. Note: Uploading sounds stores them on the device, but does not set the active cancel sound. Once flashed and connected, choose your custom sound in Home Assistant on the device controls page."
  )

writeFile("web/index.html", satelliteInstaller.generateHtml())
var manifestObj = parseJson(satelliteInstaller.generateManifest())
if fileExists("web/manifest.json"):
  try:
    let existing = parseJson(readFile("web/manifest.json"))
    if existing.hasKey("commit"):
      manifestObj["commit"] = existing["commit"]
    if existing.hasKey("built_at"):
      manifestObj["built_at"] = existing["built_at"]
    if existing.hasKey("version") and existing["version"].getStr().startsWith(currentVersion & "+"):
      manifestObj["version"] = existing["version"]
  except:
    discard
writeFile("web/manifest.json", pretty(manifestObj, indent = 2) & "\n")
echo "Successfully generated web/index.html and web/manifest.json (v" & currentVersion & ") via nim-esphome DSL!"
