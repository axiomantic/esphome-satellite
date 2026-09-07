import std/os
import nim_esphome/dsl/installer

let satelliteInstaller = esphomeInstaller("esphome-satellite"):
  installer.title = "esphome-satellite Web Installer"
  installer.description = "On-device state supervisor for ESPHome and Home Assistant voice satellites with hardware target switching, multi-wake-word selection, and customizable audio feedback."
  installer.version = "0.4.0"
  installer.homeAssistantDomain = "esphome"
  installer.chipFamily = "ESP32-S3"
  installer.factoryBinPath = "firmware-factory.bin"

  # Hardware Board Targets
  installer.addTarget(
    name = "Seeed ReSpeaker XVF3800",
    binPath = "firmware-factory.bin",
    chipFamily = "ESP32-S3",
    description = "Seeed ReSpeaker Lite XVF3800 with 4-mic array and hardware acoustic echo cancellation"
  )
  installer.addTarget(
    name = "Home Assistant Voice PE",
    binPath = "firmware-voice-pe.bin",
    chipFamily = "ESP32-S3",
    description = "Official Home Assistant Voice PE smart speaker satellite with hardware mute switch"
  )
  installer.addTarget(
    name = "ESP32-S3-BOX / BOX-3",
    binPath = "firmware-s3box.bin",
    chipFamily = "ESP32-S3",
    description = "Espressif ESP32-S3-BOX / BOX-3 with integrated display and dual microphones"
  )

  # Wake Word Selector (Up to 3 Concurrent Models)
  installer.addWakeWordSlotsField(
    name = "wake_words",
    label = "Active Wake Word Models (Up to 3 Concurrent)",
    options = @["Okay Nabu (Default)", "Hey Jarvis", "Alexa"],
    maxSlots = 3,
    slotOffsets = @[0x3B0000'u32, 0x3F0000'u32, 0x430000'u32],
    description = "ESP32-S3 hardware neural accelerator runs up to 3 wake word models concurrently in parallel. Add slots to configure multiple active wake words."
  )

  # Wake Chime Selector
  installer.addSelectField(
    name = "wake_chime_sound",
    label = "Wake Chime Sound",
    options = @["Bell Ping (Default)", "Modern Chime", "Marimba", "Subtle Beep", "Silent", "Custom Chime Audio"],
    defaultVal = "Bell Ping (Default)",
    description = "Acoustic acknowledgement chime played immediately upon wake word detection before opening the microphone",
    hasAudioPreview = true,
    optionDetails = @[
      optionDetail("Bell Ping (Default)", "Single tone (880Hz)", "Clean, crisp resonant bell with exponential acoustic decay"),
      optionDetail("Modern Chime", "Two-tone ascending (587Hz -> 880Hz)", "Warm harmonic two-tone chord with gentle release"),
      optionDetail("Marimba", "Harmonic triad (523Hz, 659Hz, 784Hz)", "Organic mellow wooden marimba strike for discreet ambient homes"),
      optionDetail("Subtle Beep", "Discrete blip (600Hz, 80ms)", "Minimal unobtrusive tick tone for quiet environments"),
      optionDetail("Silent", "No sound", "Completely silent wake without audible acknowledgement"),
      optionDetail("Custom Chime Audio", "User audio", "Plays custom audio from flash partition chime_data")
    ]
  )

  installer.addFileField(
    name = "custom_chime_audio",
    label = "Custom Wake Chime Audio (.wav)",
    accept = ".wav,audio/wav",
    partition = "chime_data",
    maxSize = 131072,
    flashOffset = 0x390000'u32,
    description = "Upload an uncompressed mono PCM WAV audio file to flash into the dedicated chime_data partition",
    dependsOnField = "wake_chime_sound",
    dependsOnValue = "Custom Chime Audio"
  )

  # Processing Sound Style
  installer.addSelectField(
    name = "default_sound_style",
    label = "Default Processing Sound Style",
    options = @["Spinner", "Pulse", "Sonar", "Tick", "Silent", "Custom"],
    defaultVal = "Spinner",
    description = "Acoustic feedback rhythm played while the assistant is processing speech",
    hasAudioPreview = true,
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
    maxSize = 131072,
    flashOffset = 0x370000'u32,
    description = "Upload an uncompressed mono PCM WAV audio file to flash into the dedicated sound_data partition",
    dependsOnField = "default_sound_style",
    dependsOnValue = "Custom"
  )

writeFile("web/index.html", satelliteInstaller.generateHtml())
echo "Successfully generated web/index.html via nim-esphome DSL!"
