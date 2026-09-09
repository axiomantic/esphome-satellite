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
