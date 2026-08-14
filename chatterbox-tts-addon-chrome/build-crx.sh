#!/usr/bin/env bash
set -euo pipefail

# Packs a signed CRX3. Chrome does the signing; this script stages an explicit
# runtime payload and keeps the private key outside the repository by default.
#
# A bare .crx is not normally drag-installable into consumer Chrome. Use Load
# unpacked for local work, the Web Store ZIP for Chrome Web Store submission,
# or self-host the CRX with an update manifest and enterprise policy.

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DIST="$ROOT/dist"
DEFAULT_KEY_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}/chatterbox-tts"
KEY="${CRX_KEY:-$DEFAULT_KEY_ROOT/chrome-signing.pem}"
CHROME="${CHROME_BIN:-/usr/bin/google-chrome-stable}"

command -v python3 >/dev/null || { echo "Python 3 is required" >&2; exit 1; }
command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }
[ -x "$CHROME" ] || { echo "Chrome not found at $CHROME (set CHROME_BIN)" >&2; exit 1; }

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

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
PAYLOAD="$STAGE/chatterbox-tts-chrome"
mkdir -p "$PAYLOAD"
for item in manifest.json \
            background.js content.js popup.js offscreen.js welcome.js \
            popup.html offscreen.html welcome.html styles.css icons; do
    cp -r "$ROOT/$item" "$PAYLOAD/"
done

mkdir -p "$DIST" "$(dirname -- "$KEY")"
chmod 700 "$(dirname -- "$KEY")" 2>/dev/null || true
TARGET="$DIST/chatterbox-tts-chrome-${VERSION}.crx"
rm -f "$TARGET"

if [ -f "$KEY" ]; then
    "$CHROME" --pack-extension="$PAYLOAD" --pack-extension-key="$KEY" \
        --no-message-box >/dev/null 2>&1 || true
else
    echo "No signing key at $KEY — generating one. Keep it private: it fixes the extension ID."
    "$CHROME" --pack-extension="$PAYLOAD" --no-message-box >/dev/null 2>&1 || true
    [ -f "$PAYLOAD.pem" ] && mv "$PAYLOAD.pem" "$KEY" && chmod 600 "$KEY"
fi

[ -f "$PAYLOAD.crx" ] || { echo "Chrome did not produce a .crx" >&2; exit 1; }
mv "$PAYLOAD.crx" "$TARGET"

EXT_ID=$(openssl rsa -in "$KEY" -pubout -outform DER 2>/dev/null \
    | openssl dgst -sha256 -binary \
    | head -c 16 \
    | python3 -c 'import sys; print("".join(chr(ord("a")+b) for byte in sys.stdin.buffer.read() for b in (byte>>4, byte&15)))')

echo "$TARGET"
echo "key:          $KEY (private — do not commit or share)"
echo "extension id: $EXT_ID"
