# Chatterbox TTS for Firefox and Chrome

Local-first browser text-to-speech built around **Chatterbox-Nano**. Firefox and Chrome share the same local backend and Voice Lab; only the browser-extension layer differs.

**Current release:** 4.0.2  
**Primary target:** Linux desktop  
**Firefox package:** [`chatterbox-tts-addon.xpi`](chatterbox-tts-addon.xpi)  
**Chrome/Chromium package:** [`chatterbox-tts-chrome.crx`](chatterbox-tts-chrome.crx)

## Features

- Speak selected text, whole pages, or text entered in the popup.
- Context-menu and floating-speaker controls.
- Line-aware buffering so slower CPU inference can generate ahead of playback.
- Shared job ownership across tabs and the popup.
- Stop/cancel handling for playback and queued browser work.
- Replay and correctly merged multi-line WAV download.
- Local Voice Lab at `http://127.0.0.1:8030/`.
- Create reference voices from audio or video with FFmpeg preprocessing.
- Switch the default Chatterbox reference voice from Voice Lab.
- Bundled 30-second **Vale** and **Arbor** starter references.
- Chatterbox starts only when needed and exits after an idle timeout.

## Browser builds

| Browser | Source | Manifest | Normal local install |
| --- | --- | --- | --- |
| Firefox | `chatterbox-tts-addon/` | Manifest V2 | signed XPI or `about:debugging` |
| Chrome / Chromium | `chatterbox-tts-addon-chrome/` | Manifest V3 | **Load unpacked** from `chrome://extensions` |

Both browser builds call the same loopback services:

```text
Firefox / Chrome
    |
    | local TTS requests
    v
127.0.0.1:8010  openwebui_audio_bridge.py
    |
    | starts on demand
    v
127.0.0.1:8020  chatterbox_nano_server.py

127.0.0.1:8030  chatterbox_voice_app.py (Voice Lab)
    |
    +-------------------------------> 127.0.0.1:8020
```

The installer creates three systemd user units. The bridge and Voice Lab are enabled immediately; `chatterbox-nano.service` is started by the bridge when speech is requested and exits after its configured idle period.

## Requirements

The bundled backend installer is intended for a Linux desktop with:

- Python 3 with `venv` support
- Git
- FFmpeg / FFprobe
- systemd user services
- Firefox and/or a Chromium-based browser
- Internet access during first install to fetch Python packages and the Chatterbox-Nano model

The default backend is CPU-only. CUDA is not required.

`zip` is required only when building browser packages yourself. Chrome CRX packing additionally requires Chrome/Chromium and OpenSSL.

## Quick backend install

```bash
git clone https://github.com/pinguy/chatterbox-tts-addon.git
cd chatterbox-tts-addon
bash chatterbox-tts-addon/install.sh
```

The installer creates `~/.local/share/chatterbox-tts/`, installs a private Python environment, downloads Chatterbox-Nano, seeds the bundled voice references, installs the systemd user units, and starts the bridge and Voice Lab.

Useful checks:

```bash
systemctl --user status openwebui-audio-bridge.service
systemctl --user status chatterbox-voice-app.service
curl http://127.0.0.1:8010/health
```

Voice Lab:

```text
http://127.0.0.1:8030/
```

## Firefox

### Persistent install

Use the repository-root Firefox package:

[`chatterbox-tts-addon.xpi`](chatterbox-tts-addon.xpi)

In Firefox: **Add-ons and themes → gear menu → Install Add-on From File…**

### Development install

1. Open `about:debugging#/runtime/this-firefox`.
2. Select **Load Temporary Add-on**.
3. Select `chatterbox-tts-addon/manifest.json`.

### Build an unsigned Firefox XPI

```bash
./build-xpi.sh
```

The result is written under `dist/`.

## Chrome / Chromium

The Chrome port is a **Manifest V3** extension. It uses a service worker instead of Firefox's persistent background page and an offscreen document for tab-owned audio playback.

### Recommended local install

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select `chatterbox-tts-addon-chrome/`.

This is the normal route for local use. A standalone CRX is not generally drag-installable in normal consumer Chrome.

### Chrome Web Store package

The Web Store accepts a ZIP, not a CRX:

```bash
cd chatterbox-tts-addon-chrome
./build-zip.sh
```

The ZIP is written to `chatterbox-tts-addon-chrome/dist/` and contains only extension runtime files.

### Self-hosted / enterprise CRX

A CRX is mainly useful for self-hosting with an update manifest plus enterprise policy, or as a signed archive.

```bash
cd chatterbox-tts-addon-chrome
./build-crx.sh
```

The CRX signing key is private and must **never be committed**. By default the builder stores it outside the repository under your user config directory. You can override the path with `CRX_KEY=/secure/path/key.pem`.

See [`chatterbox-tts-addon-chrome/README.md`](chatterbox-tts-addon-chrome/README.md) for the MV3 implementation details and Chrome-specific traps.

## Voices

Two 30-second starter references are included under `chatterbox-tts-addon/samples/voices/`:

- **Vale** — installed as the initial default reference.
- **Arbor** — installed alongside Vale and available from Voice Lab.

Voice Lab can also create references from audio or video. FFmpeg converts the selected source into a mono 24 kHz WAV. Supported reference lengths are 10, 15, 20, 30, 45 and 60 seconds.

Managed voices live under:

```text
~/.local/share/chatterbox-tts/voices/
```

## Stop behaviour

Stopping from either browser immediately halts playback and invalidates queued browser work. It also tells the bridge to reject later chunks belonging to the cancelled job.

An inference request already running inside Chatterbox is **not forcibly killed mid-generation**. Its result is discarded if no longer needed, and the Chatterbox service exits normally after the idle timeout.

## Privacy

The browser extension sends selected/page text to `http://127.0.0.1:8010` for local synthesis. This project does not send that text to a hosted TTS service.

Firefox/AMO still treats the localhost hand-off as transmission outside the extension itself, so the Firefox manifest declares required `websiteContent` data collection.

## Validation

Run:

```bash
make validate
```

This checks the Python backend, Firefox MV2 source and packaging, and Chrome MV3 source/manifest/ZIP packaging. The same validation runs in GitHub Actions on pushes and pull requests.

## Firefox AMO notes

The Firefox source intentionally does not hard-code a `browser_specific_settings.gecko.id`; AMO assigns the permanent ID to the signed package. Future Firefox 4.x uploads should use **Upload a New Version** from the existing Chatterbox TTS Developer Hub entry rather than submitting a new add-on.

There is currently no Firefox `update_url` in the manifest, so GitHub-hosted XPI installs require manual upgrades unless an update manifest is added later.

## Optional Open WebUI STT bridge

`openwebui_audio_bridge.py` also exposes an OpenAI-compatible transcription endpoint, but **Whisper STT is optional and is not required by either browser add-on**.

To enable it:

```bash
export WHISPER_MODEL=/path/to/your/model
export WHISPER_WORKER=/path/to/whisper_worker.py
# Optional if the worker needs a different environment:
export WHISPER_PYTHON=/path/to/python
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `CHATTERBOX_INSTALL_ROOT` | `~/.local/share/chatterbox-tts` | Backend install directory |
| `CHATTERBOX_MODEL_DIR` | `<install>/models/chatterbox-nano` | Local model directory |
| `CHATTERBOX_REFERENCE_ROOT` | `<install>/voices` | Managed voice library |
| `CHATTERBOX_REFERENCE_WAV` | bundled Vale reference after normal install | Default voice reference |
| `CHATTERBOX_IDLE_SECONDS` | `1200` | Service idle-exit delay |
| `CHATTERBOX_CHUNK_CHARS` | `500` | Internal TTS chunk size |
| `CHATTERBOX_PORT` | `8020` | Chatterbox service port |
| `CHATTERBOX_VOICE_APP_PORT` | `8030` | Voice Lab port |
| `BRIDGE_API_KEY` | `local-dev-key` | Loopback bridge token |

The services bind to loopback only. If you deliberately expose them to a network, replace the development API key and treat the bridge as a network-facing application.

## Repository layout

```text
.
├── chatterbox-tts-addon.xpi       # Firefox package
├── chatterbox-tts-chrome.crx      # Chrome CRX archive/self-host package
├── chatterbox-tts-addon/          # Firefox MV2 source + backend installer/voices
├── chatterbox-tts-addon-chrome/   # Chrome MV3 source + Chrome build helpers
├── templates/                     # Voice Lab HTML template
├── chatterbox_nano_server.py      # Local Chatterbox-Nano API
├── openwebui_audio_bridge.py      # Browser/OpenAI-compatible loopback bridge
├── chatterbox_voice_app.py        # Voice Lab backend
├── build-xpi.sh                   # Firefox XPI builder
├── Makefile                       # Cross-browser validation entry point
└── .github/workflows/             # GitHub validation workflow
```

## Licence

Apache License 2.0. See [`LICENSE`](LICENSE).

Chatterbox itself is an upstream dependency from Resemble AI and is installed from its own repository by the setup script; its upstream licence and notices apply to that project.
