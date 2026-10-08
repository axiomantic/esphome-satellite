import unittest
import ../src/cancellation_matcher

suite "Cancellation Phrase Matcher Suite (TDD)":
  test "Exact matching of primary cancellation words":
    check isCancellationPhrase("stop")
    check isCancellationPhrase("nevermind")
    check isCancellationPhrase("never mind")
    check isCancellationPhrase("never-mind")
    check isCancellationPhrase("abort")
    check isCancellationPhrase("cancel")
    check isCancellationPhrase("dismiss")
    check isCancellationPhrase("quit")
    check isCancellationPhrase("shut up")

  test "Punctuation stripping and case insensitivity":
    check isCancellationPhrase("Stop.")
    check isCancellationPhrase("STOP!")
    check isCancellationPhrase("Never mind?")
    check isCancellationPhrase("\"abort\"")
    check isCancellationPhrase("cancel...")

  test "Prefix with word boundary":
    check isCancellationPhrase("stop please")
    check isCancellationPhrase("stop it")
    check isCancellationPhrase("stop talking")
    check isCancellationPhrase("nevermind that")
    check isCancellationPhrase("abort mission")
    check isCancellationPhrase("cancel that")

  test "Suffix with word boundary":
    check isCancellationPhrase("please stop")
    check isCancellationPhrase("just stop")
    check isCancellationPhrase("oh nevermind")
    check isCancellationPhrase("oh never mind")
    check isCancellationPhrase("ok abort")
    check isCancellationPhrase("please cancel")

  test "Embedded with word boundary":
    check isCancellationPhrase("please stop talking")
    check isCancellationPhrase("can you just cancel that")

  test "Non-cancellation phrases should not match":
    check not isCancellationPhrase("turn on the kitchen lights")
    check not isCancellationPhrase("what time is it")
    check not isCancellationPhrase("play some jazz music")
    check not isCancellationPhrase("stopwatch")
    check not isCancellationPhrase("nonstop flight")
    check not isCancellationPhrase("cancellation policy")
    check not isCancellationPhrase("")

  test "Custom config string parsing and override":
    check isCancellationPhrase("halt", "halt, terminate")
    check isCancellationPhrase("terminate now", "halt, terminate")
    check not isCancellationPhrase("stop", "halt, terminate")

  test "C ABI export function":
    check nim_satellite_is_cancellation("stop".cstring, nil)
    check nim_satellite_is_cancellation("Abort!".cstring, "stop, abort".cstring)
    check not nim_satellite_is_cancellation(nil, nil)
    check not nim_satellite_is_cancellation("turn on lights".cstring, nil)

  test "Conversation reset phrase matching":
    check isConversationResetPhrase("forget our conversation")
    check isConversationResetPhrase("forget my conversation")
    check isConversationResetPhrase("forget this conversation")
    check isConversationResetPhrase("clear history")
    check isConversationResetPhrase("clear the history")
    check isConversationResetPhrase("clear conversation")
    check isConversationResetPhrase("clear conversation history")
    check isConversationResetPhrase("reset conversation")
    check isConversationResetPhrase("reset the conversation")
    check isConversationResetPhrase("new conversation")
    check isConversationResetPhrase("start a new conversation")
    check isConversationResetPhrase("start new conversation")
    check isConversationResetPhrase("forget everything")
    check isConversationResetPhrase("Can you please forget our conversation?")
    check isConversationResetPhrase("Reset conversation now")
    check not isConversationResetPhrase("turn on the office desk switch")
    check not isConversationResetPhrase("what was that")
    check not isConversationResetPhrase("tell me a story about history")
    check nim_satellite_is_reset_phrase("reset conversation".cstring)
    check nim_satellite_is_reset_phrase("forget everything!".cstring)
    check not nim_satellite_is_reset_phrase("hello".cstring)
    check not nim_satellite_is_reset_phrase(nil)

  test "Satellite Volume Action Matcher Suite":
    # 1. "your volume down" matches svakDown
    let d1 = matchSatelliteVolumeAction("turn your volume down")
    check d1.action == svakDown
    let d2 = matchSatelliteVolumeAction("turn down your volume please")
    check d2.action == svakDown
    let d3 = matchSatelliteVolumeAction("lower your volume")
    check d3.action == svakDown
    let d4 = matchSatelliteVolumeAction("decrease your volume")
    check d4.action == svakDown
    let d5 = matchSatelliteVolumeAction("your volume down")
    check d5.action == svakDown
    let d6 = matchSatelliteVolumeAction("turn your sound down")
    check d6.action == svakDown
    let d7 = matchSatelliteVolumeAction("turn your speaker down")
    check d7.action == svakDown
    let d8 = matchSatelliteVolumeAction("turn down your speaker")
    check d8.action == svakDown
    let d9 = matchSatelliteVolumeAction("turn yourself down")
    check d9.action == svakDown

    # 2. "your volume up" matches svakUp
    let u1 = matchSatelliteVolumeAction("turn your volume up")
    check u1.action == svakUp
    let u2 = matchSatelliteVolumeAction("turn up your volume")
    check u2.action == svakUp
    let u3 = matchSatelliteVolumeAction("raise your volume")
    check u3.action == svakUp
    let u4 = matchSatelliteVolumeAction("increase your volume")
    check u4.action == svakUp
    let u5 = matchSatelliteVolumeAction("boost your volume")
    check u5.action == svakUp
    let u6 = matchSatelliteVolumeAction("your volume up")
    check u6.action == svakUp

    # 3. Explicit set volume: "set your volume to X"
    let s1 = matchSatelliteVolumeAction("set your volume to 50%")
    check s1.action == svakSet
    check s1.targetPercent == 50
    let s2 = matchSatelliteVolumeAction("turn your volume to 75 percent")
    check s2.action == svakSet
    check s2.targetPercent == 75
    let s3 = matchSatelliteVolumeAction("put your volume at thirty percent")
    check s3.action == svakSet
    check s3.targetPercent == 30

    # 4. Mute / unmute
    let m1 = matchSatelliteVolumeAction("mute yourself")
    check m1.action == svakMute
    let m2 = matchSatelliteVolumeAction("mute your volume")
    check m2.action == svakMute
    let um1 = matchSatelliteVolumeAction("unmute yourself")
    check um1.action == svakUnmute
    let um2 = matchSatelliteVolumeAction("unmute your volume")
    check um2.action == svakUnmute

    # Direct speech volume controls
    check matchSatelliteVolumeAction("speak softer").action == svakDown
    check matchSatelliteVolumeAction("talk softer").action == svakDown
    check matchSatelliteVolumeAction("speak quieter").action == svakDown
    check matchSatelliteVolumeAction("be quieter").action == svakDown
    check matchSatelliteVolumeAction("you are too loud").action == svakDown
    check matchSatelliteVolumeAction("you're too loud").action == svakDown
    check matchSatelliteVolumeAction("too loud").action == svakDown
    check matchSatelliteVolumeAction("turn down your voice").action == svakDown

    check matchSatelliteVolumeAction("speak louder").action == svakDown or matchSatelliteVolumeAction("speak louder").action == svakUp
    check matchSatelliteVolumeAction("speak louder").action == svakUp
    check matchSatelliteVolumeAction("talk louder").action == svakUp
    check matchSatelliteVolumeAction("speak up").action == svakUp
    check matchSatelliteVolumeAction("you are too quiet").action == svakUp
    check matchSatelliteVolumeAction("you're too quiet").action == svakUp
    check matchSatelliteVolumeAction("too quiet").action == svakUp
    check matchSatelliteVolumeAction("I can't hear you").action == svakUp

    # 5. Media player volume commands DO NOT match (must route to Home Assistant!)
    check matchSatelliteVolumeAction("turn the volume down").action == svakNone
    check matchSatelliteVolumeAction("turn down the volume").action == svakNone
    check matchSatelliteVolumeAction("lower the volume").action == svakNone
    check matchSatelliteVolumeAction("turn the volume up").action == svakNone
    check matchSatelliteVolumeAction("turn up the volume").action == svakNone
    check matchSatelliteVolumeAction("turn down the living room sonos").action == svakNone
    check matchSatelliteVolumeAction("set volume to 30%").action == svakNone
    check matchSatelliteVolumeAction("mute the tv").action == svakNone
    check matchSatelliteVolumeAction("").action == svakNone

    # 6. C ABI Export
    var targetVol: cint = 0
    let actDown = nim_satellite_match_volume_action("turn your volume down".cstring, targetVol.addr)
    check actDown == 1
    let actSet = nim_satellite_match_volume_action("set your volume to 40 percent".cstring, targetVol.addr)
    check actSet == 3
    check targetVol == 40
    let actNone = nim_satellite_match_volume_action("turn the volume down".cstring, targetVol.addr)
    check actNone == 0
    check nim_satellite_match_volume_action(nil, nil) == 0

  test "Wake Word Verification Suite":
    # Clemens tests (exact name / tokens)
    check verifyWakeWordPhrase("mr clemens what time is it", "Mr. Clemens")
    check verifyWakeWordPhrase("clemens how is the weather", "Mr. Clemens")
    check verifyWakeWordPhrase("Clemens.", "Mr. Clemens")

    # Generic custom wake words
    check verifyWakeWordPhrase("hey jarvis turn on the ac", "Jarvis")
    check verifyWakeWordPhrase("marvin play music", "Marvin")

    # Default project wake word (Okay Nabu)
    check verifyWakeWordPhrase("okay nabu turn on the lights", "Okay Nabu")
    check verifyWakeWordPhrase("ok nabu what time is it", "Okay Nabu")
    check verifyWakeWordPhrase("nabu set a timer", "Okay Nabu")

    # False wakes must REJECT
    check not verifyWakeWordPhrase("I'm sorry, I can't help you. Jake!", "Okay Nabu")
    check not verifyWakeWordPhrase("I'm sorry, I can't help you. Jake!", "Mr. Clemens")
    check not verifyWakeWordPhrase("turn on the kitchen lights", "Mr. Clemens")
    check not verifyWakeWordPhrase("commercial about car insurance", "Mr. Clemens")
    check not verifyWakeWordPhrase("today is a nice day", "Jarvis")
    check not verifyWakeWordPhrase("", "Mr. Clemens")
    check not verifyWakeWordPhrase("hello", "")

    # C ABI export
    check nim_satellite_verify_wake_word("mr clemens hello".cstring, "Mr. Clemens".cstring)
    check not nim_satellite_verify_wake_word("I'm sorry, Jake".cstring, "Mr. Clemens".cstring)
    check not nim_satellite_verify_wake_word(nil, "Mr. Clemens".cstring)
    check not nim_satellite_verify_wake_word("mr clemens".cstring, nil)

