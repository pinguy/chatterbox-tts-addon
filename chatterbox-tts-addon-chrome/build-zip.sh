#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DIST="$ROOT/dist"

command -v python3 >/dev/null || { echo "Python 3 is required" >&2; exit 1; }
command -v zip >/dev/null || { echo "zip is required" >&2; exit 1; }

VERSION=$(python3 - "$ROOT/manifest.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    manifest = json.load(handle)
if manifest.get('manifest_version') != 3:
    raise SystemExit('Chrome build requires manifest_version 3')
for required in ('offscreen', 'scripting', 'storage', 'contextMenus'):
    if required not in manifest.get('permissions', []):
        raise SystemExit(f'manifest.json is missing the {required} permission')
print(manifest['version'])
PY
)

mkdir -p "$DIST"
TARGET="$DIST/chatterbox-tts-chrome-${VERSION}.zip"
rm -f "$TARGET"

(
    cd "$ROOT"
    zip -q -r "$TARGET" \
        manifest.json \
        background.js content.js popup.js offscreen.js welcome.js \
        popup.html offscreen.html welcome.html styles.css \
        icons/
)

echo "$TARGET"
