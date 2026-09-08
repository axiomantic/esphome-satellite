## `tests/test_version_sync.nim`: Ensures project versions remain 100% synchronized across all metadata files.

import std/[unittest, strutils, json, os]

proc getExpectedVersion(): string =
  let nimbleText = readFile("esphome_satellite.nimble")
  for line in nimbleText.splitLines():
    let trimmed = line.strip()
    if trimmed.startsWith("version"):
      let parts = trimmed.split('=')
      if parts.len == 2:
        return parts[1].strip().strip(chars = {'"', ' '})
  raise newException(ValueError, "Could not find version in esphome_satellite.nimble")

suite "Version Synchronization Invariant Suite":
  let expectedVersion = getExpectedVersion()

  test "esphome_satellite.nimble has valid semver":
    check expectedVersion.len > 0
    check expectedVersion.contains('.')

  test "packages/respeaker_xvf3800.yaml version substitution matches nimble":
    let yamlText = readFile("packages/respeaker_xvf3800.yaml")
    var foundVersion = ""
    for line in yamlText.splitLines():
      let trimmed = line.strip()
      if trimmed.startsWith("version:"):
        let parts = trimmed.split(':')
        if parts.len == 2:
          foundVersion = parts[1].strip().strip(chars = {'"', ' ', '\''})
          break
    check foundVersion == expectedVersion

  test "web/manifest.json version matches nimble":
    let jsonText = readFile("web/manifest.json")
    let parsed = parseJson(jsonText)
    check parsed.hasKey("version")
    check parsed["version"].getStr().startsWith(expectedVersion)

  test "web/version.json matches nimble if present":
    if fileExists("web/version.json"):
      let jsonText = readFile("web/version.json")
      let parsed = parseJson(jsonText)
      check parsed.hasKey("version")
      check parsed["version"].getStr() == expectedVersion

  test "CHANGELOG.md contains expected release section":
    let changelogText = readFile("CHANGELOG.md")
    let header = "## [" & expectedVersion & "]"
    check changelogText.contains(header)

  test "web/index.html BASE_MANIFEST version matches nimble":
    let htmlText = readFile("web/index.html")
    check ("version: \"" & expectedVersion & "\"") in htmlText
    check ("esphome-satellite v" & expectedVersion) in htmlText

  test "web/index.html includes dynamic version synchronization script":
    let htmlText = readFile("web/index.html")
    check "syncDynamicManifestVersion" in htmlText

  test "web/manifest.json uses discrete partition flashing skipping NVS":
    let jsonText = readFile("web/manifest.json")
    let parsed = parseJson(jsonText)
    check parsed.hasKey("builds")
    check parsed["builds"].len > 0
    let parts = parsed["builds"][0]["parts"]
    check parts.len == 4

    var paths: seq[string] = @[]
    var offsets: seq[int] = @[]
    for p in parts:
      paths.add(p["path"].getStr())
      offsets.add(p["offset"].getInt())
      # NVS partition is at 0x9000 (36864) to 0xE000 (57344)
      check p["offset"].getInt() < 36864 or p["offset"].getInt() >= 57344

    check paths.contains("bootloader.bin")
    check paths.contains("partitions.bin")
    check paths.contains("ota_data_initial.bin")
    check paths.contains("firmware-ota.bin")
    check offsets == @[0, 32768, 57344, 65536]

  test "web/index.html BASE_MANIFEST uses discrete partition flashing":
    let htmlText = readFile("web/index.html")
    check "bootloader.bin" in htmlText
    check "partitions.bin" in htmlText
    check "ota_data_initial.bin" in htmlText
    check "firmware-ota.bin" in htmlText

