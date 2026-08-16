# Chatterbox TTS — Chrome / Chromium

Manifest V3 frontend for the same local Chatterbox-Nano backend used by the Firefox extension.

## Install for development

1. Install the backend from the repository root with `bash chatterbox-tts-addon/install.sh`.
2. Open `chrome://extensions`.
3. Enable **Developer mode**.
4. Choose **Load unpacked** and select this directory.

The popup offers **Auto**, **CPU**, and **GPU / accelerator**. The accelerator option is enabled only when the local bridge reports an accelerator backend.

## Packaging

Chrome Web Store ZIP:

```bash
./build-zip.sh
```

CRX archive/self-host package:

```bash
./build-crx.sh
```

The CRX private signing key is stored outside this repository by default at:

```text
${XDG_CONFIG_HOME:-~/.config}/chatterbox-tts/chrome-signing.pem
```

Override it with `CRX_KEY=/secure/path/key.pem`. Never commit a private signing key.

A standalone CRX is not generally drag-installable in normal consumer Chrome. **Load unpacked** is the straightforward local-development route; the Web Store expects a ZIP.

## MV3 differences

The Chrome port uses:

- a service worker instead of Firefox's persistent MV2 background page;
- an offscreen document for tab-owned audio playback;
- callback/sendResponse message handling where Chrome does not accept Firefox-style returned promises;
- `scripting.executeScript` for page-text extraction.

The backend remains on loopback: bridge `127.0.0.1:8010`, Voice Lab `127.0.0.1:8030`.
