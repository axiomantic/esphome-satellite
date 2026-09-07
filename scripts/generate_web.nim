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
    description = "Seeed ReSpeaker XVF3800 with 4-mic array and hardware acoustic echo cancellation"
  )

  # Wake Word Selector (Up to 3 Concurrent Models)
  installer.addWakeWordSlotsField(
    name = "wake_words",
    options = @["Okay Nabu (Default)", "Hey Jarvis", "Alexa", "Mr. Clemens"],
    maxSlots = 3,
    slotOffsets = @[0x3B0000'u32, 0x3F0000'u32, 0x430000'u32],
    description = "ESP32-S3 hardware neural accelerator runs up to 3 wake word models concurrently in parallel. Add slots to configure multiple active wake words.",
    presetModels = @[
      ("Mr. Clemens", "models/clemens.tflite")
    ]
  )

  # Wake Chime Selector
  installer.addSelectField(
    name = "wake_chime_sound",
    label = "Wake Chime Sound",
    options = @["Bell Ping (Default)", "Modern Chime", "Crystal Glass", "Warm Kalimba", "Meditation Bell", "Marimba", "Subtle Beep", "Silent", "Custom Chime Audio"],
    defaultVal = "Bell Ping (Default)",
    description = "Acoustic acknowledgement chime played immediately upon wake word detection before opening the microphone",
    hasAudioPreview = true,
    optionDetails = @[
      optionDetail("Bell Ping (Default)", "Single tone (880Hz)", "Clean, crisp resonant bell with exponential acoustic decay"),
      optionDetail("Modern Chime", "Two-tone ascending chord", "Modern minimalist crisp ascending harmonic chime (Kenney CC0)"),
      optionDetail("Crystal Glass", "Crystal ping resonance", "Modern minimalist delicate crystal resonance ping"),
      optionDetail("Warm Kalimba", "Dual-tine acoustic strike", "Organic acoustic thumb piano with wooden body resonance"),
      optionDetail("Meditation Bell", "Tibetan singing bowl", "Organic acoustic singing bowl with deep harmonic decay"),
      optionDetail("Marimba", "Harmonic triad (523Hz, 659Hz, 784Hz)", "Organic mellow wooden marimba strike for discreet ambient homes"),
      optionDetail("Subtle Beep", "Discrete blip (600Hz, 80ms)", "Minimal unobtrusive tick tone for quiet environments"),
      optionDetail("Silent", "No sound", "Completely silent wake without audible acknowledgement"),
      optionDetail("Custom Chime Audio", "User audio", "Plays custom audio from flash partition chime_data")
    ],
    presetAudios = @[
      ("Modern Chime", "sounds/modern-chime.mp3", "sounds/modern-chime.wav"),
      ("Crystal Glass", "sounds/crystal-glass.mp3", "sounds/crystal-glass.wav"),
      ("Warm Kalimba", "sounds/warm-kalimba.mp3", "sounds/warm-kalimba.wav"),
      ("Meditation Bell", "sounds/meditation-bell.mp3", "sounds/meditation-bell.wav")
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
    options = @["Spinner", "Pulse", "Sonar", "Tick", "Typewriter", "Clockwork", "Water Droplets", "Silent", "Custom"],
    defaultVal = "Spinner",
    description = "Acoustic feedback rhythm played while the assistant is processing speech",
    hasAudioPreview = true,
    optionDetails = @[
      optionDetail("Spinner", "120ms cadence", "Fast rhythmic progress ticking for rapid feedback"),
      optionDetail("Pulse", "250ms cadence", "Subtle undulating heartbeat pattern for ambient presence"),
      optionDetail("Sonar", "800ms cadence", "Periodic nautical acoustic ping for deliberate tracking"),
      optionDetail("Tick", "500ms cadence", "Mechanical clockwork pulse for steady pacing"),
      optionDetail("Typewriter", "Mechanical rhythm", "Soft acoustic typewriter keystrokes and mechanical chatter during LLM processing"),
      optionDetail("Clockwork", "Watchmaker escapement", "Modern minimalist precision escapement tick-tock with subtle gear movement"),
      optionDetail("Water Droplets", "Bubbly acoustic resonance", "Organic acoustic water droplets dripping into a calm pool"),
      optionDetail("Silent", "No sound", "Completely silent processing for zero distraction"),
      optionDetail("Custom", "User audio", "Loops custom audio from flash partition sound_data")
    ],
    presetAudios = @[
      ("Typewriter", "sounds/typewriter.mp3", "sounds/typewriter.wav"),
      ("Clockwork", "sounds/clockwork.mp3", "sounds/clockwork.wav"),
      ("Water Droplets", "sounds/water-droplets.mp3", "sounds/water-droplets.wav")
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
