# Chatterbox TTS — Chrome / Chromium port

Manifest V3 port of the Firefox add-on in `../chatterbox-tts-addon/`. It uses the same local bridge, Chatterbox-Nano backend, Voice Lab, UI concepts and job-ownership model.

## Install for local use

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select this directory.

That is the normal local-development/install route. A bare `.crx` generally cannot be drag-installed into normal consumer Chrome.

## Build a Chrome Web Store ZIP

The Chrome Web Store accepts a ZIP rather than a CRX:

```bash
./build-zip.sh
```

Output:

```text
dist/chatterbox-tts-chrome-<version>.zip
```

The packer includes only runtime extension files.

## Build a CRX3

For self-hosting/enterprise deployment or a signed archive:

```bash
./build-crx.sh
```

Output:

```text
dist/chatterbox-tts-chrome-<version>.crx
```

Chrome does the CRX3 signing. The private key fixes the extension ID, so **do not commit, upload or share that key**.

By default the builder keeps the signing key outside the repository at:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/chatterbox-tts/chrome-signing.pem
```

Override it when needed:

```bash
CRX_KEY=/secure/path/chatterbox.pem ./build-crx.sh
```

If a CRX private key is ever published, treat it as compromised and rotate it before relying on that identity for distribution.

A self-hosted CRX normally needs an update manifest plus an enterprise policy allowlist (`ExtensionInstallForcelist` / `ExtensionSettings`). For everyday local use, **Load unpacked** is simpler.

## Stable ID for unpacked builds

If you deliberately want an unpacked build to use the same ID as a CRX, derive and add only the **public** key to `manifest.json` as a `"key"` field. Never copy the private PEM into the extension tree.

```bash
openssl rsa -in "$CRX_KEY" -pubout -outform DER | base64 -w0
```

## Backend

The Chrome port uses the same backend as Firefox:

- bridge: `http://127.0.0.1:8010`
- Chatterbox-Nano service: `http://127.0.0.1:8020`
- Voice Lab: `http://127.0.0.1:8030`

Install the backend from the repository root with:

```bash
bash chatterbox-tts-addon/install.sh
```

## What differs from Firefox

**Manifest V3 service worker.** Firefox's MV2 build uses a persistent background page. Chrome uses `background.js` as an MV3 service worker, so active UI contexts send keepalives while synthesis is running.

**Offscreen playback.** Tab-owned audio runs through `offscreen.html` / `offscreen.js` because Chrome's autoplay and extension-context rules make the Firefox hidden-frame approach unsuitable. Popup-owned audio can still play directly in the popup.

**Async messaging.** Chrome message listeners answer asynchronous branches through `sendResponse` and return `true`; Firefox can resolve a promise directly from its listener.

**Script injection.** Chrome uses `scripting.executeScript`, replacing Firefox/MV2-style script injection APIs.

## Two traps worth remembering

**Offscreen documents have a restricted extension API surface.** Keep their responsibilities narrow and route settings/state through the service worker rather than assuming normal extension APIs are available.

**Owner liveness is checked on the UI channel.** An offscreen audio document can outlive the tab that requested speech, so the service worker probes the actual content-script/popup owner before treating the job as alive.

## Stop behaviour

Stop immediately halts browser playback and cancels queued browser work. The bridge invalidates later chunks from that job, but an inference already executing in Chatterbox is not forcibly killed mid-generation. Chatterbox exits later through its normal idle timeout.

## Verified baseline

The 4.0.2 Chrome port has been exercised as an MV3 unpacked extension with:

- service-worker registration
- content-script injection
- loopback `/health` and `/v1/audio/speech` access
- multi-line tab playback through an offscreen document
- cleanup of the offscreen document after jobs complete
- CRX3 packaging with an explicit payload list

Run the repository-level validation after changes:

```bash
cd ..
make validate
```
