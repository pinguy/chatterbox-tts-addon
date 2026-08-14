# Chatterbox TTS for Firefox

A local-first Firefox text-to-speech add-on built around **Chatterbox-Nano**, with a small loopback API bridge and a browser-based **Voice Lab** for preparing and switching voice references.

Everything is designed to run on the local machine. Firefox talks to `127.0.0.1`; text and voice samples are not sent to a hosted TTS service by this project.

## Features

- Speak selected text, whole pages, or text entered in the popup.
- Context-menu and floating-speaker controls in Firefox.
- Line-aware buffering so CPU inference can generate ahead of playback.
- Stop/cancel handling shared across tabs and the popup.
- Replay and merged WAV download from the popup.
- Chatterbox Voice Lab at `http://127.0.0.1:8030/`.
- Create voice references from audio or video with FFmpeg preprocessing.
- Switch the default Chatterbox reference voice from Voice Lab.
- Voice Lab support for creating and switching local reference voices.
- Chatterbox unloads after an idle period instead of permanently occupying RAM.

## Architecture

```text
Firefox add-on
    |
    | OpenAI-compatible TTS requests
    v
127.0.0.1:8010  openwebui_audio_bridge.py
    |
    v
127.0.0.1:8020  chatterbox_nano_server.py

127.0.0.1:8030  chatterbox_voice_app.py (Voice Lab)
    |
    +-------------------------------> 127.0.0.1:8020
```

The bundled installer manages the three Python processes as **systemd user services**.

## Requirements

The installer is intended for a Linux desktop with:

- Python 3 with `venv` support
- Git
- FFmpeg / FFprobe
- systemd user services
- Firefox
- Internet access during the first install to fetch Python packages and the Chatterbox-Nano model

The default Chatterbox service is CPU-only. No CUDA setup is required.

## Install

Clone or download the repository, then run:

```bash
bash chatterbox-tts-addon/install.sh
```

The installer creates `~/.local/share/chatterbox-tts/`, installs a private Python virtual environment, downloads Chatterbox-Nano and enables:

- `chatterbox-nano.service`
- `openwebui-audio-bridge.service`
- `chatterbox-voice-app.service`

When it completes, Voice Lab is available at:

```text
http://127.0.0.1:8030/
```

### Load the Firefox add-on for testing

1. Open `about:debugging#/runtime/this-firefox` in Firefox.
2. Select **Load Temporary Add-on**.
3. Open `chatterbox-tts-addon/manifest.json` from this repository.

Temporary add-ons disappear when Firefox exits. A normal persistent install on release Firefox requires a Mozilla-signed XPI.

## Build an unsigned XPI

Run:

```bash
./build-xpi.sh
```

The package is written to `dist/`. It contains only the Firefox extension runtime files; the Python backend is installed separately from the repository with `install.sh`.

The unsigned XPI is useful for temporary loading and for submission to Mozilla's signing flow. Firefox release builds generally require Mozilla signing for permanent installation.

## Using Chatterbox TTS

- Select text on a page and use the floating speaker button.
- Right-click selected text or a page and choose a Chatterbox action.
- Use the toolbar popup to type text, capture the current selection/page, play, stop, replay, or save a merged WAV.
- Use **Voice Lab** from the add-on UI (or open port `8030` directly) to create and manage reference voices.

The popup stores a startup buffer between one and ten non-empty lines. Two lines is the default.

## Voice Lab

Voice Lab accepts an audio or video file and creates a mono 24 kHz WAV reference using FFmpeg. Reference lengths of 10, 15, 20, 30, 45 and 60 seconds are supported.

Voice data is stored under:

```text
~/.local/share/chatterbox-tts/voices/
```

Changing the default voice creates a systemd drop-in for `chatterbox-nano.service`. Backups are kept under the Chatterbox install directory so a failed switch can be rolled back.

## Optional Open WebUI STT bridge

`openwebui_audio_bridge.py` also contains an OpenAI-compatible transcription endpoint, but **Whisper STT is optional and is not required by the Firefox add-on**.

To enable it, provide at least:

```bash
export WHISPER_MODEL=/path/to/your/model
export WHISPER_WORKER=/path/to/whisper_worker.py
# Optional if the worker needs a different environment:
export WHISPER_PYTHON=/path/to/python
```

Without those settings the bridge stays fully usable for TTS and reports STT as unconfigured rather than relying on machine-specific paths.

## Configuration

Useful environment variables include:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CHATTERBOX_INSTALL_ROOT` | `~/.local/share/chatterbox-tts` | Backend install directory |
| `CHATTERBOX_MODEL_DIR` | `<install>/models/chatterbox-nano` | Local model directory |
| `CHATTERBOX_REFERENCE_ROOT` | `<install>/voices` | Managed voice library |
| `CHATTERBOX_REFERENCE_WAV` | unset | Optional default voice reference |
| `CHATTERBOX_IDLE_SECONDS` | `1200` | Model idle-unload delay |
| `CHATTERBOX_CHUNK_CHARS` | `500` | Internal TTS chunk size |
| `CHATTERBOX_PORT` | `8020` | Chatterbox service port |
| `CHATTERBOX_VOICE_APP_PORT` | `8030` | Voice Lab port |
| `BRIDGE_API_KEY` | `local-dev-key` | Loopback bridge token |

The services bind to loopback only. If you deliberately change that, replace the development API key and treat the service as a network-facing application.

## Repository layout

```text
.
├── chatterbox-tts-addon/       # Firefox extension + installer
├── templates/                  # Voice Lab HTML template
├── chatterbox_nano_server.py   # Local Chatterbox-Nano API
├── openwebui_audio_bridge.py   # Firefox/OpenAI-compatible bridge
├── chatterbox_voice_app.py     # Voice Lab backend
├── build-xpi.sh                # Build unsigned Firefox package
└── .github/workflows/          # Lightweight syntax/packaging validation
```

The older `chatterbox-tts-addon/server.py` is only a loopback health checker; it does not load another TTS model.

## Validation

Run:

```bash
make validate
```

This checks Python syntax, JavaScript syntax, shell syntax, JSON validity, and verifies that the Firefox package can be built.

## Licence

Apache License 2.0. See [`LICENSE`](LICENSE).

Chatterbox itself is an upstream dependency from Resemble AI and is installed from its own repository by the setup script; its upstream licence and notices apply to that project.
