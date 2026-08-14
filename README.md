# Chatterbox TTS for Firefox

Local-first Firefox text-to-speech built around **Chatterbox-Nano**. The browser add-on talks to a small loopback bridge, which starts the local Chatterbox service on demand and exposes a browser-based **Voice Lab** for preparing and switching reference voices.

**Current release:** 4.0.2  
**Primary target:** Firefox desktop on Linux  
**Current self-distribution package:** [`chatterbox-tts-addon.xpi`](chatterbox-tts-addon.xpi)

## Features

- Speak selected text, whole pages, or text entered in the popup.
- Context-menu and floating-speaker controls in Firefox.
- Line-aware buffering so slower CPU inference can generate ahead of playback.
- Shared job ownership across tabs and the popup.
- Stop/cancel handling for playback and queued browser work.
- Replay and correctly merged multi-line WAV download.
- Local Voice Lab at `http://127.0.0.1:8030/`.
- Create reference voices from audio or video with FFmpeg preprocessing.
- Switch the default Chatterbox reference voice from Voice Lab.
- Bundled 30-second **Vale** and **Arbor** starter references.
- Chatterbox starts only when needed and exits after an idle timeout.

## Architecture

```text
Firefox add-on
    |
    | OpenAI-compatible TTS requests
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

The bundled installer is intended for a Linux desktop with:

- Python 3 with `venv` support
- Git
- FFmpeg / FFprobe
- systemd user services
- Firefox
- Internet access during first install to fetch Python packages and the Chatterbox-Nano model

The default backend is CPU-only. CUDA is not required.

`zip` is only needed if you want to build an unsigned XPI yourself.

## Quick install

Clone the repository and install the local backend:

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

Voice Lab should then be available at:

```text
http://127.0.0.1:8030/
```

### Install the Firefox add-on

For a normal persistent Firefox install, use the current self-distribution package at the repository root:

[`chatterbox-tts-addon.xpi`](chatterbox-tts-addon.xpi)

In Firefox you can install a signed XPI from **Add-ons and themes → gear menu → Install Add-on From File…**.

For development instead:

1. Open `about:debugging#/runtime/this-firefox`.
2. Select **Load Temporary Add-on**.
3. Select `chatterbox-tts-addon/manifest.json`.

Temporary add-ons disappear when Firefox exits.

## Voices

Two 30-second starter references are included under `chatterbox-tts-addon/samples/voices/`:

- **Vale** — installed as the initial default reference.
- **Arbor** — installed alongside Vale and available from Voice Lab.

Voice Lab can also create references from audio or video. FFmpeg converts the selected source into a mono 24 kHz WAV. Supported reference lengths are 10, 15, 20, 30, 45 and 60 seconds.

Managed voices live under:

```text
~/.local/share/chatterbox-tts/voices/
```

Changing the default voice creates a systemd drop-in for `chatterbox-nano.service`. Voice Lab keeps backups so a failed switch can be rolled back.

## Stop behaviour

Stopping from Firefox immediately halts playback and invalidates queued browser work. It also tells the bridge to reject later chunks belonging to the cancelled job.

An inference request already running inside Chatterbox is **not forcibly killed mid-generation**. Its result is discarded if no longer needed, and the Chatterbox service exits normally after the idle timeout. This avoids turning Stop into a service-killing hammer.

## Privacy and the Firefox data declaration

The extension sends selected/page text to `http://127.0.0.1:8010` for local synthesis. It does not send that text to a hosted TTS service in this project.

Firefox/AMO still treats that as transmission outside the extension itself, so the manifest declares required `websiteContent` data collection. The declaration is there to describe the localhost hand-off accurately, not because this project uploads page contents to a remote service.

## Build an unsigned XPI

Install `zip`, then run:

```bash
./build-xpi.sh
```

The package is written to `dist/` and contains only the Firefox extension runtime files. The Python backend, model and voice library are deliberately separate.

The builder also checks that the current Firefox data-collection declaration is present before packaging.

For a full source check:

```bash
make validate
```

This validates Python syntax, JavaScript syntax, shell syntax, JSON and XPI packaging. The same check runs in GitHub Actions on pushes and pull requests.

### Add-on ID / future AMO uploads

The source is Manifest V2 and intentionally does not hard-code a `browser_specific_settings.gecko.id`. AMO assigns the permanent ID to the signed package.

For future 4.x updates, use **Upload a New Version** from the existing Chatterbox TTS entry in the AMO Developer Hub. Do **not** submit it again as a new add-on.

If the project later moves to Manifest V3 or switches to API/`web-ext` signing, pinning the permanent ID in the source manifest becomes useful/required for that workflow.

## Self-distribution and updates

The repository root carries the current self-distribution XPI. There is currently no `update_url` in the manifest, so GitHub-hosted installs do not automatically discover a newer XPI. Until an update manifest is added, upgrades are manual: download/install the newer signed package over the existing version.

## Optional Open WebUI STT bridge

`openwebui_audio_bridge.py` also exposes an OpenAI-compatible transcription endpoint, but **Whisper STT is optional and is not required by the Firefox add-on**.

To enable it, provide at least:

```bash
export WHISPER_MODEL=/path/to/your/model
export WHISPER_WORKER=/path/to/whisper_worker.py
# Optional if the worker needs a different environment:
export WHISPER_PYTHON=/path/to/python
```

Without those settings the bridge remains fully usable for TTS and reports STT as unconfigured.

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
├── chatterbox-tts-addon.xpi    # Current self-distribution Firefox package
├── chatterbox-tts-addon/       # Firefox source, installer and starter voices
├── templates/                  # Voice Lab HTML template
├── chatterbox_nano_server.py   # Local Chatterbox-Nano API
├── openwebui_audio_bridge.py   # Firefox/OpenAI-compatible loopback bridge
├── chatterbox_voice_app.py     # Voice Lab backend
├── build-xpi.sh                # Build unsigned Firefox package
├── Makefile                    # Local validation entry point
└── .github/workflows/          # GitHub validation workflow
```

`chatterbox-tts-addon/server.py` is only a loopback health checker; it does not load another TTS model.

## Licence

Apache License 2.0. See [`LICENSE`](LICENSE).

Chatterbox itself is an upstream dependency from Resemble AI and is installed from its own repository by the setup script; its upstream licence and notices apply to that project.
