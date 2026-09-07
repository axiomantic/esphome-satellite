#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: $0 <new_version>" >&2
    echo "Example: $0 0.4.1" >&2
    exit 1
fi

NEW_VERSION="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

OLD_VERSION=$(grep -E '^\s*version\s*=' esphome_satellite.nimble | head -n 1 | sed -E 's/.*"([^"]+)".*/\1/')
echo "Bumping version from v$OLD_VERSION to v$NEW_VERSION across all project descriptors..."

# 1. Update esphome_satellite.nimble
sed -i '' -E "s/version[[:space:]]*=[[:space:]]*\"[^\"]+\"/version       = \"$NEW_VERSION\"/" esphome_satellite.nimble

# 2. Update packages/respeaker_xvf3800.yaml substitutions
sed -i '' -E "s/version:[[:space:]]*\"[^\"]+\"/version: \"$NEW_VERSION\"/" packages/respeaker_xvf3800.yaml

# 3. Regenerate web/index.html and web/manifest.json
nim r --path:../nim-esphome/src scripts/generate_web.nim

# 4. Run version sync validation test
nim r tests/test_version_sync.nim

echo "=== Version successfully bumped and verified to v$NEW_VERSION! ==="
