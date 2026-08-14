# Chatterbox TTS — Chrome port

Manifest V3 port of the Firefox add-on in `../chatterbox-tts-addon-main/`. Same
backend, same UI, same job-ownership model. The Firefox tree is untouched.

## Install

1. `chrome://extensions` → enable **Developer mode**
2. **Load unpacked** → select this directory

## Packaging

`./build-crx.sh` produces a signed CRX3 at `dist/chatterbox-tts-chrome-<version>.crx`,
generating `chatterbox-tts-chrome.pem` on first run. **Keep that key**: it fixes
the extension ID, and regenerating it produces a different extension as far as
Chrome is concerned. It is gitignored, and the packer stages an explicit file
list so the key, `dist/`, this README and the build scripts never end up inside
the package.

`./build-zip.sh` is still there because the Chrome Web Store takes a zip, not a crx.

**A .crx does not install by dragging it into `chrome://extensions`.** Chrome
refuses anything not from the Web Store with "can only be added from the Chrome
Web Store", developer mode or not. The crx is useful for two things:

- self-hosting with an update manifest plus an enterprise policy allowlist
  (`ExtensionInstallForcelist` / `ExtensionSettings`, keyed on the extension ID)
- a signed, versioned archive

For everyday local use, **Load unpacked is the route** — the crx buys nothing.

If you want the unpacked build to carry the same stable ID as the crx, add the
public key to `manifest.json` as a `"key"` field:

```bash
openssl rsa -in chatterbox-tts-chrome.pem -pubout -outform DER | base64 -w0
```

That is the public half only and is safe to commit. Verified: with the key
present, Chrome assigns the unpacked build the same ID the crx gets.

The local backend is unchanged: the bridge on `127.0.0.1:8010` and Voice Lab on
`127.0.0.1:8030`. Install it with `install.sh` from the Firefox tree.

## What had to change, and why

Four things are not cosmetic differences between the two browsers.

**Background page → service worker.** The MV2 background page was persistent and
held `activeJob` in memory. An MV3 service worker is killed when idle, which
would drop a job mid-synthesis. While a job runs, whichever context owns it
(content script or popup) pings `keepalive` every 20s to keep the worker up.

**Playback moved into an offscreen document.** The Firefox add-on played audio in
a hidden iframe injected into the page. Chrome's autoplay policy blocks that: the
user's click happens in the page, but the iframe is a different origin, so the
gesture does not carry. Tab-owned playback therefore runs in an offscreen
document created with reason `AUDIO_PLAYBACK`. The popup still plays in its own
window, where the click is a real gesture.

**`onMessage` cannot return a promise.** Firefox resolves a promise returned from
a listener; Chrome ignores it and the sender sees `undefined`. Every async branch
now answers through `sendResponse` and returns `true`.

**`tabs.executeScript` → `scripting.executeScript`.** MV3 removed the MV2 API, and
the injected code is now a real function rather than a string, so the page-text
extractor is shared instead of duplicated as a minified one-liner.

## Two traps worth knowing

**An offscreen document may only use `chrome.runtime`.** `chrome.storage` is
`undefined` there. The first build read the buffer setting directly in
`offscreen.js`; it threw at load, and because the throw happened before
`chrome.runtime.onMessage.addListener` ran, the document existed but silently
answered nothing. The service worker now reads the setting and sends it with
every message. If you add features here, assume no extension API but `runtime`.

**Owner liveness is judged on the UI channel, not the audio channel.** The
offscreen document always accepts a message, so it can never tell you the tab
went away. Delivery is probed with a `ttsProgress` message to the content script;
a rejection there aborts the job. For the same reason the offscreen document is
closed whenever no tab job is active — a lingering one would answer messages
aimed at a closed popup and mask that the popup had gone.

## Behaviour note

The Stop button no longer says "Chatterbox unloaded". Since 2026-08-14 the bridge
cancels queued synthesis but deliberately leaves the model warm, and the model
server unloads itself after 20 minutes idle. The Firefox add-on still shows the
old wording and is now inaccurate on that one string.

## Verified

Loaded into Chrome 151 via `Extensions.loadUnpacked` and driven over CDP:

- MV3 manifest accepted; service worker registers as `background.js`
- offscreen document created and closed cleanly, no leak after a job
- host permissions reach the bridge: `/health` 200, `/v1/audio/speech` 200
  returning 82,604 bytes of WAV
- full tab job: content script injected, two lines generated, offscreen played
  both, `Speech completed` shown, job cleared, offscreen closed
- CRX3 output: `Cr24` magic, format version 3, 13 payload entries matching the
  zip, no key or build files inside, stable ID across rebuilds
- extension ID derivation cross-checked against Chrome itself: both give
  `gcocpllglfmiggebcmnpioijanjnofjd` for the generated key
