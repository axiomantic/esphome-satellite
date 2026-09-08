import std/unittest
import std/math

import ../src/xvf3800_hardware

suite "XVF3800 Hardware & Animation Suite (TDD)":
  test "GPO payload generation":
    let p1 = makeGpoPayload(30'u8, 1'u8) # Mute on
    check p1[0] == 20'u8 # GPO_SERVICER_RESID
    check p1[1] == 1'u8  # GPO_CMD_WRITE_VALUE
    check p1[2] == 2'u8  # Length
    check p1[3] == 30'u8 # Pin
    check p1[4] == 1'u8  # Value

    let p2 = makeGpoPayload(31'u8, 0'u8) # Amp enable (active low)
    check p2[3] == 31'u8
    check p2[4] == 0'u8

  test "LED ring payload formatting":
    var colors: array[12, uint32]
    colors[0] = 0x00FF8800'u32 # Orange (R=FF, G=88, B=00)
    let payload = makeLedRingPayload(colors)
    check payload.len == 3 + 48
    check payload[0] == 20'u8 # resid
    check payload[1] == 18'u8 # cmd led ring
    check payload[2] == 48'u8 # byte length
    # Check color 0: B, G, R, 0
    check payload[3] == 0x00'u8 # Blue
    check payload[4] == 0x88'u8 # Green
    check payload[5] == 0xFF'u8 # Red
    check payload[6] == 0x00'u8 # Pad

  test "LED animation states - Muted produces solid red":
    let colors = computeAnimationColors("Muted", "Off", 1.0'f32, 1000'u32)
    for c in colors:
      check (c and 0x00FF0000'u32) == 0x00FF0000'u32 # Red channel 255
      check (c and 0x0000FFFF'u32) == 0'u32          # Green and Blue 0

  test "LED animation states - Listening produces pulsing cyan/blue":
    let colors = computeAnimationColors("Listening", "Off", 1.0'f32, 1000'u32)
    for c in colors:
      check (c and 0x00FF0000'u32) == 0'u32          # Red channel 0
      check (c and 0x000000FF'u32) > 0'u32          # Blue channel active
      check (c and 0x0000FF00'u32) > 0'u32          # Green channel active

  test "LED animation states - Thinking produces 12-LED rotating spinner with decay":
    let colors = computeAnimationColors("Thinking", "Off", 1.0'f32, 0'u32)
    # Head at 0 has highest brightness
    let head = colors[0]
    check head > 0'u32
    # At least some trailing LEDs are dimmer or unlit
    check colors[6] == 0'u32
