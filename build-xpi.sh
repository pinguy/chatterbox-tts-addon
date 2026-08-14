#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ADDON="$ROOT/chatterbox-tts-addon"
DIST="$ROOT/dist"

command -v python3 >/dev/null || { echo "Python 3 is required" >&2; exit 1; }
command -v zip >/dev/null || { echo "zip is required" >&2; exit 1; }

VERSION=$(python3 - "$ADDON/manifest.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    manifest = json.load(handle)

gecko = manifest.get('browser_specific_settings', {}).get('gecko', {})
collection = gecko.get('data_collection_permissions', {})
if not collection.get('required') and not collection.get('optional'):
    raise SystemExit(
        'manifest.json is missing browser_specific_settings.gecko.'
        'data_collection_permissions required by current Firefox AMO validation'
    )

print(manifest['version'])
PY
)

mkdir -p "$DIST"
TARGET="$DIST/chatterbox-tts-addon-${VERSION}-unsigned.xpi"
rm -f "$TARGET"

(
    cd "$ADDON"
    zip -q -r "$TARGET" \
        manifest.json \
        background.js content.js popup.js player.js welcome.js \
        popup.html player.html welcome.html styles.css \
        icons/
)

echo "$TARGET"
