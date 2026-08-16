#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DIST="$ROOT/dist"
CONFIG_ROOT=${XDG_CONFIG_HOME:-"$HOME/.config"}/chatterbox-tts
KEY=${CRX_KEY:-"$CONFIG_ROOT/chrome-signing.pem"}
CHROME=${CHROME_BIN:-}

command -v python3 >/dev/null || { echo "Python 3 is required" >&2; exit 1; }
command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }

if [[ -z "$CHROME" ]]; then
    for candidate in google-chrome-stable google-chrome chromium chromium-browser; do
        if command -v "$candidate" >/dev/null 2>&1; then
            CHROME=$(command -v "$candidate")
            break
        fi
    done
fi
[[ -n "$CHROME" && -x "$CHROME" ]] || { echo "Chrome/Chromium not found (set CHROME_BIN)" >&2; exit 1; }

VERSION=$(python3 - "$ROOT/manifest.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    manifest = json.load(handle)
if manifest.get('manifest_version') != 3:
    raise SystemExit('Chrome build requires manifest_version 3')
print(manifest['version'])
PY
)

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
PAYLOAD="$STAGE/chatterbox-tts-chrome"
mkdir -p "$PAYLOAD" "$DIST" "$(dirname -- "$KEY")"
for item in manifest.json background.js content.js popup.js offscreen.js welcome.js popup.html offscreen.html welcome.html styles.css icons; do
    cp -r "$ROOT/$item" "$PAYLOAD/"
done

TARGET="$DIST/chatterbox-tts-chrome-${VERSION}.crx"
rm -f "$TARGET"

if [[ -f "$KEY" ]]; then
    "$CHROME" --pack-extension="$PAYLOAD" --pack-extension-key="$KEY" --no-message-box >/dev/null 2>&1 || true
else
    echo "No signing key found; generating one at $KEY"
    "$CHROME" --pack-extension="$PAYLOAD" --no-message-box >/dev/null 2>&1 || true
    [[ -f "$PAYLOAD.pem" ]] || { echo "Chrome did not create a signing key" >&2; exit 1; }
    mv "$PAYLOAD.pem" "$KEY"
    chmod 600 "$KEY"
fi

[[ -f "$PAYLOAD.crx" ]] || { echo "Chrome did not produce a CRX" >&2; exit 1; }
mv "$PAYLOAD.crx" "$TARGET"

EXT_ID=$(openssl rsa -in "$KEY" -pubout -outform DER 2>/dev/null \
    | openssl dgst -sha256 -binary \
    | head -c 16 \
    | python3 -c 'import sys; print("".join(chr(ord("a")+n) for b in sys.stdin.buffer.read() for n in (b>>4,b&15)))')

echo "$TARGET"
echo "signing key: $KEY (private; do not commit)"
echo "extension id: $EXT_ID"
