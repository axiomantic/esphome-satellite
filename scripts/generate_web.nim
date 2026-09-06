import std/os
import nim_esphome/dsl/installer

let satelliteInstaller = esphomeInstaller("esphome-satellite"):
  installer.title = "esphome-satellite Web Installer"
  installer.description = "Rock-solid on-device state supervisor for ESPHome and Home Assistant voice satellites with customizable audio feedback."
  installer.version = "0.3.0"
  installer.homeAssistantDomain = "esphome"
  installer.chipFamily = "ESP32-S3"
  installer.factoryBinPath = "firmware-factory.bin"

  installer.addSelectField(
    name = "default_sound_style",
    label = "Default Processing Sound Style",
    options = @["Spinner", "Pulse", "Sonar", "Tick", "Silent", "Custom"],
    defaultVal = "Spinner",
    description = "Acoustic feedback rhythm played while the assistant is processing speech",
    optionDetails = @[
      optionDetail("Spinner", "120ms cadence", "Fast rhythmic progress ticking for rapid feedback"),
      optionDetail("Pulse", "250ms cadence", "Subtle undulating heartbeat pattern for ambient presence"),
      optionDetail("Sonar", "800ms cadence", "Periodic nautical acoustic ping for deliberate tracking"),
      optionDetail("Tick", "500ms cadence", "Mechanical clockwork pulse for steady pacing"),
      optionDetail("Silent", "No sound", "Completely silent processing for zero distraction"),
      optionDetail("Custom", "User audio", "Loops custom audio from flash partition sound_data")
    ]
  )

  installer.addFileField(
    name = "custom_audio",
    label = "Custom Audio Feedback Loop (.wav)",
    accept = ".wav,audio/wav",
    partition = "sound_data",
    maxSize = 262144,
    flashOffset = 0x370000'u32,
    description = "Upload an uncompressed mono PCM WAV audio file to flash into the dedicated sound_data partition",
    dependsOnField = "default_sound_style",
    dependsOnValue = "Custom"
  )

writeFile("web/index.html", satelliteInstaller.generateHtml())
echo "Successfully generated web/index.html via nim-esphome DSL!"
