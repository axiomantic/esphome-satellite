import std/os
import nim_esphome/dsl/installer

let satelliteInstaller = esphomeInstaller("esphome-satellite"):
  installer.title = "esphome-satellite Web Installer"
  installer.description = "On-device state supervisor for ESPHome and Home Assistant voice satellites with hardware target switching, multi-wake-word selection, and customizable audio feedback."
  installer.version = "0.3.0"
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

  # Wake Word Selector
  installer.addSelectField(
    name = "wake_word",
    label = "Active Wake Word Model(s)",
    options = @["Okay Nabu (Default)", "Hey Jarvis", "Alexa", "All 3 Models (Concurrent)", "Custom Wake Word"],
    defaultVal = "Okay Nabu (Default)",
    description = "On-device micro-wake-word models. ESP32-S3 with 8MB PSRAM supports up to 3 concurrent models in parallel without reflashing.",
    hasAudioPreview = false
  )

  installer.addTextField(
    name = "custom_wake_word_phrase",
    label = "Phonetic Wake Word Phrase",
    placeholder = "okay see three pee oh",
    calloutHtml = "<strong>Phonetic spelling recommendation:</strong> Spell words phonetically for optimal acoustic feature matching &mdash; e.g. <code>ok c3p0</code> &rarr; <code>okay see three pee oh</code> or <code>dj pj</code> &rarr; <code>dee jay pee jay</code>.",
    description = "Phonetic representation used by the wake word model engine and WASM/WebGPU generator",
    dependsOnField = "wake_word",
    dependsOnValue = "Custom Wake Word"
  )

  installer.addFileField(
    name = "custom_wake_word_model",
    label = "Custom Wake Word Model (.tflite)",
    accept = ".tflite",
    partition = "wake_model",
    maxSize = 262144,
    flashOffset = 0x3B0000'u32,
    description = "Upload a pre-trained micro_wake_word model or one generated with the browser WASM/WebGPU trainer",
    dependsOnField = "wake_word",
    dependsOnValue = "Custom Wake Word"
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
    maxSize = 262144,
    flashOffset = 0x370000'u32,
    description = "Upload an uncompressed mono PCM WAV audio file to flash into the dedicated sound_data partition",
    dependsOnField = "default_sound_style",
    dependsOnValue = "Custom"
  )

writeFile("web/index.html", satelliteInstaller.generateHtml())
echo "Successfully generated web/index.html via nim-esphome DSL!"
