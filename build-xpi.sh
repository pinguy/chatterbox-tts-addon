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
    print(json.load(handle)['version'])
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
