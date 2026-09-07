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
    options = @[
      "Bell Ping (Default)", "Modern Chime", "Crystal Glass", "Warm Kalimba", "Meditation Bell",
      "Marimba", "Subtle Beep", "Bamboo Chime", "Tibetan Bowl", "Acoustic Harp", "Woodblock",
      "Ceramic Bell", "Neon Shimmer", "Prism Ping", "Cyber Bloom", "Quantum Beep", "Aero Chime",
      "Silent", "Custom Chime Audio"
    ],
    defaultVal = "Bell Ping (Default)",
    description = "Acoustic acknowledgement chime played immediately upon wake word detection before opening the microphone",
    hasAudioPreview = true,
    optionDetails = @[
      optionDetail("Bell Ping (Default)", "Single tone (880Hz)", "Clean, crisp resonant bell with exponential acoustic decay (CC0)"),
      optionDetail("Modern Chime", "Two-tone ascending chord", "Modern minimalist crisp ascending harmonic chime (Kenney CC0)"),
      optionDetail("Crystal Glass", "Crystal ping resonance", "Modern minimalist delicate crystal resonance ping (CC0)"),
      optionDetail("Warm Kalimba", "Dual-tine acoustic strike", "Organic acoustic thumb piano with wooden body resonance (CC0)"),
      optionDetail("Meditation Bell", "Tibetan singing bowl", "Organic acoustic singing bowl with deep harmonic decay (CC0)"),
      optionDetail("Marimba", "Harmonic triad (523Hz, 659Hz, 784Hz)", "Organic mellow wooden marimba strike for discreet ambient homes (CC0)"),
      optionDetail("Subtle Beep", "Discrete blip (600Hz, 80ms)", "Minimal unobtrusive tick tone for quiet environments (CC0)"),
      optionDetail("Bamboo Chime", "Natural bamboo wind chime", "Organic acoustic hollow bamboo tubes resonant strike (CC0)"),
      optionDetail("Tibetan Bowl", "Himalayan brass bowl (432Hz)", "Organic acoustic singing bowl with golden overtone bloom (CC0)"),
      optionDetail("Acoustic Harp", "Concert harp pluck", "Organic acoustic ascending two-string concert harp pluck (CC-BY dobroide)"),
      optionDetail("Woodblock", "Hardwood temple block", "Organic natural rosewood temple block strike (Kenney CC0)"),
      optionDetail("Ceramic Bell", "Glazed porcelain bell", "Organic crystalline earthenware bell with high-frequency glaze shimmer (CC0)"),
      optionDetail("Neon Shimmer", "Lush analog FM chord", "Modern digital warm FM synth chord with soft glowing decay (Kenney CC0)"),
      optionDetail("Prism Ping", "Glass-digital harmonic ping", "Modern digital pristine glass-synth chime with overtone sparkle (CC0)"),
      optionDetail("Cyber Bloom", "Ascending synth arpeggio", "Modern digital ascending D5-A5-D6 synth arpeggio (Kenney CC0)"),
      optionDetail("Quantum Beep", "Precision micro-tone", "Modern digital precision dual-transient interface acknowledge (Kenney CC0)"),
      optionDetail("Aero Chime", "Spatial synth swell", "Modern digital airy spatial two-tone electronic acknowledgement (CC0)"),
      optionDetail("Silent", "No sound", "Completely silent wake without audible acknowledgement"),
      optionDetail("Custom Chime Audio", "User audio", "Plays custom audio from flash partition chime_data")
    ],
    presetAudios = @[
      ("Bell Ping (Default)", "sounds/bell-ping.mp3", "sounds/bell-ping.wav"),
      ("Modern Chime", "sounds/modern-chime.mp3", "sounds/modern-chime.wav"),
      ("Crystal Glass", "sounds/crystal-glass.mp3", "sounds/crystal-glass.wav"),
      ("Warm Kalimba", "sounds/warm-kalimba.mp3", "sounds/warm-kalimba.wav"),
      ("Meditation Bell", "sounds/meditation-bell.mp3", "sounds/meditation-bell.wav"),
      ("Marimba", "sounds/marimba.mp3", "sounds/marimba.wav"),
      ("Subtle Beep", "sounds/subtle-beep.mp3", "sounds/subtle-beep.wav"),
      ("Bamboo Chime", "sounds/bamboo-chime.mp3", "sounds/bamboo-chime.wav"),
      ("Tibetan Bowl", "sounds/tibetan-bowl.mp3", "sounds/tibetan-bowl.wav"),
      ("Acoustic Harp", "sounds/acoustic-harp.mp3", "sounds/acoustic-harp.wav"),
      ("Woodblock", "sounds/woodblock.mp3", "sounds/woodblock.wav"),
      ("Ceramic Bell", "sounds/ceramic-bell.mp3", "sounds/ceramic-bell.wav"),
      ("Neon Shimmer", "sounds/neon-shimmer.mp3", "sounds/neon-shimmer.wav"),
      ("Prism Ping", "sounds/prism-ping.mp3", "sounds/prism-ping.wav"),
      ("Cyber Bloom", "sounds/cyber-bloom.mp3", "sounds/cyber-bloom.wav"),
      ("Quantum Beep", "sounds/quantum-beep.mp3", "sounds/quantum-beep.wav"),
      ("Aero Chime", "sounds/aero-chime.mp3", "sounds/aero-chime.wav")
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
    options = @[
      "Spinner", "Pulse", "Sonar", "Tick", "Typewriter", "Clockwork", "Water Droplets",
      "Raindrops", "Forest Stream", "Campfire Ember", "Shishi-Odoshi", "Soft Footsteps",
      "Radar Ping", "Data Crunch", "Telemetry Blip", "Quantum Flux", "Retro Terminal",
      "Silent", "Custom"
    ],
    defaultVal = "Spinner",
    description = "Acoustic feedback rhythm played while the assistant is processing speech",
    hasAudioPreview = true,
    optionDetails = @[
      optionDetail("Spinner", "120ms cadence", "Fast rhythmic progress ticking for rapid feedback (Kenney CC0)"),
      optionDetail("Pulse", "250ms cadence", "Subtle undulating heartbeat pattern for ambient presence (CC0)"),
      optionDetail("Sonar", "800ms cadence", "Periodic nautical acoustic ping for deliberate tracking (CC0)"),
      optionDetail("Tick", "500ms cadence", "Mechanical clockwork pulse for steady pacing (Kenney CC0)"),
      optionDetail("Typewriter", "Mechanical rhythm", "Soft acoustic typewriter keystrokes and mechanical chatter during LLM processing (CC0)"),
      optionDetail("Clockwork", "Watchmaker escapement", "Modern minimalist precision escapement tick-tock with subtle gear movement (CC0)"),
      optionDetail("Water Droplets", "Bubbly acoustic resonance", "Organic acoustic water droplets dripping into a calm pool (CC0)"),
      optionDetail("Raindrops", "Rain on foliage cadence", "Organic acoustic raindrops tapping softly on broad forest leaves (CC0)"),
      optionDetail("Forest Stream", "Mountain brook flow", "Organic gentle bubbling mountain brook stream with water eddies (CC0)"),
      optionDetail("Campfire Ember", "Wood crackle & pops", "Organic cozy woodfire crackles and soft ember pops (CC0)"),
      optionDetail("Shishi-Odoshi", "Bamboo rocker on stone", "Organic Japanese bamboo water rocker trickle and stone clack (CC-BY sonicfury)"),
      optionDetail("Soft Footsteps", "Paced footsteps on wood", "Organic subtle leather steps on hardwood indicating active thought (CC0)"),
      optionDetail("Radar Ping", "Sci-fi radar pulse", "Modern digital periodic radar sweep with resonant acoustic decay (Kenney CC0)"),
      optionDetail("Data Crunch", "Telemetry packet chatter", "Modern digital micro-packet processing chatter rhythm (CC0)"),
      optionDetail("Telemetry Blip", "Satellite tracking pulse", "Modern digital dual-harmonic instrument tracking blips (Kenney CC0)"),
      optionDetail("Quantum Flux", "LFO analog undulation", "Modern digital smooth undulating electronic rhythm (CC0)"),
      optionDetail("Retro Terminal", "Relay & tape flutter", "Modern digital vintage computer relay clicks and magnetic tape chatter (CC0)"),
      optionDetail("Silent", "No sound", "Completely silent processing for zero distraction"),
      optionDetail("Custom", "User audio", "Loops custom audio from flash partition sound_data")
    ],
    presetAudios = @[
      ("Spinner", "sounds/spinner.mp3", "sounds/spinner.wav"),
      ("Pulse", "sounds/pulse.mp3", "sounds/pulse.wav"),
      ("Sonar", "sounds/sonar.mp3", "sounds/sonar.wav"),
      ("Tick", "sounds/tick.mp3", "sounds/tick.wav"),
      ("Typewriter", "sounds/typewriter.mp3", "sounds/typewriter.wav"),
      ("Clockwork", "sounds/clockwork.mp3", "sounds/clockwork.wav"),
      ("Water Droplets", "sounds/water-droplets.mp3", "sounds/water-droplets.wav"),
      ("Raindrops", "sounds/raindrops.mp3", "sounds/raindrops.wav"),
      ("Forest Stream", "sounds/forest-stream.mp3", "sounds/forest-stream.wav"),
      ("Campfire Ember", "sounds/campfire-ember.mp3", "sounds/campfire-ember.wav"),
      ("Shishi-Odoshi", "sounds/shishi-odoshi.mp3", "sounds/shishi-odoshi.wav"),
      ("Soft Footsteps", "sounds/soft-footsteps.mp3", "sounds/soft-footsteps.wav"),
      ("Radar Ping", "sounds/radar-ping.mp3", "sounds/radar-ping.wav"),
      ("Data Crunch", "sounds/data-crunch.mp3", "sounds/data-crunch.wav"),
      ("Telemetry Blip", "sounds/telemetry-blip.mp3", "sounds/telemetry-blip.wav"),
      ("Quantum Flux", "sounds/quantum-flux.mp3", "sounds/quantum-flux.wav"),
      ("Retro Terminal", "sounds/retro-terminal.mp3", "sounds/retro-terminal.wav")
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
