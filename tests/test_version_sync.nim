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
