# Chatterbox TTS for Firefox and Chrome

Local-first browser text-to-speech built around **Chatterbox-Nano**. Firefox and Chrome/Chromium share the same local backend and Voice Lab; only the browser-extension layer differs.

**Development version:** 4.2.0  
**Primary target:** Linux desktop  
**Recommended CPU:** 6+ cores  
**Acceleration:** optional; CPU always remains available

## What it does

- Speaks selected text, whole pages, or text entered in the popup.
- Firefox and Chrome/Chromium extensions.
- Context-menu and floating-speaker controls.
- Line-aware buffering so slower inference can generate ahead of playback.
- Replay and merged WAV download.
- Local Voice Lab at `http://127.0.0.1:8030/`.
- Creates reference voices from audio/video with FFmpeg.
- Bundled 30-second **Vale** and **Arbor** starter references.
- Starts Chatterbox on demand and releases resources after an idle timeout.
- Browser-selectable **Auto / CPU / GPU-accelerator** synthesis mode.

All browser traffic goes to loopback only. This project does not send page text to a hosted TTS service.

## Browser builds

| Browser | Source | Manifest | Development install |
| --- | --- | --- | --- |
| Firefox | `chatterbox-tts-addon/` | Manifest V2 | `about:debugging` |
| Chrome / Chromium | `chatterbox-tts-addon-chrome/` | Manifest V3 | **Load unpacked** in `chrome://extensions` |

Both builds use the same backend:

```text
Firefox / Chrome
    |
    v
127.0.0.1:8010  openwebui_audio_bridge.py
    |
    +--> CPU service        127.0.0.1:8020
    |
    +--> accelerator service 127.0.0.1:8021 (only when configured)

127.0.0.1:8030  chatterbox_voice_app.py (Voice Lab)
```

## Install the backend

Requirements:

- Python 3 with `venv`
- Git
- FFmpeg / FFprobe
- systemd user services
- Internet access during the first install

Clone and install:

```bash
git clone https://github.com/pinguy/chatterbox-tts-addon.git
cd chatterbox-tts-addon
bash chatterbox-tts-addon/install.sh
```

The installer uses portable paths under:

```text
~/.local/share/chatterbox-tts/
~/.config/systemd/user/
```

No user-specific home directory is hard-coded.

Useful checks:

```bash
systemctl --user status openwebui-audio-bridge.service
systemctl --user status chatterbox-voice-app.service
curl http://127.0.0.1:8010/health
```

## CPU / GPU / accelerator selection

The popup now offers:

- **Auto** — uses the configured accelerator when one is available, otherwise CPU.
- **CPU** — always uses the CPU backend.
- **GPU / accelerator** — only enabled when the backend reports an accelerator service.

The choice is stored in the browser and is honoured by popup speech, the context menu, and the in-page speaker control.

The installer always sets up CPU support. In its default `auto` mode it also checks for a usable accelerator. If the installed PyTorch runtime exposes one, a second on-demand service is created on port `8021`.

For unusual PyTorch/accelerator setups, the installer can be guided without editing source code:

```bash
CHATTERBOX_ENABLE_GPU=1 \
CHATTERBOX_TORCH_MODE=default \
bash chatterbox-tts-addon/install.sh
```

Or provide a custom PyTorch wheel index/device:

```bash
CHATTERBOX_ENABLE_GPU=1 \
CHATTERBOX_TORCH_INDEX_URL=https://example.invalid/pytorch-index \
CHATTERBOX_GPU_DEVICE=cuda \
bash chatterbox-tts-addon/install.sh
```

Replace the example index/device with whatever is appropriate for the local PyTorch platform. If accelerator setup fails, CPU remains usable.

Existing OpenAI/Open WebUI clients that do not send a device hint continue to use CPU. The browser explicitly sends `auto`, `cpu`, or `gpu`.

## Firefox

For development:

1. Open `about:debugging#/runtime/this-firefox`.
2. Select **Load Temporary Add-on**.
3. Select `chatterbox-tts-addon/manifest.json`.

Build an unsigned XPI:

```bash
./build-xpi.sh
```

Mozilla signing is required for a normal persistent release install.

## Chrome / Chromium

For local development:

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select `chatterbox-tts-addon-chrome/`.

Build the Chrome Web Store ZIP:

```bash
cd chatterbox-tts-addon-chrome
./build-zip.sh
```

A CRX can also be produced for archive/self-host/managed deployments:

```bash
./build-crx.sh
```

The CRX private key is stored outside the repository by default. **Never commit a private `.pem`/`.key` file.**

## Voices

Bundled starter references live under `chatterbox-tts-addon/samples/voices/`. Voice Lab can create additional references from audio or video and stores managed voices under:

```text
~/.local/share/chatterbox-tts/voices/
```

## Stop behaviour

Stop immediately halts browser playback and cancels queued work. A synthesis request already executing inside Chatterbox is not forcibly killed mid-generation; its result is discarded if no longer needed and the service exits normally after the idle timeout.

## Optional Whisper STT

`openwebui_audio_bridge.py` can also expose an OpenAI-compatible transcription endpoint. Whisper is optional and is not required by either browser extension.

Configure it with environment variables rather than local paths:

```bash
export WHISPER_MODEL=/path/to/model
export WHISPER_WORKER=/path/to/whisper_worker.py
# optional
export WHISPER_PYTHON=/path/to/python
```

Without those values, TTS works normally and STT reports itself as unconfigured.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `CHATTERBOX_INSTALL_ROOT` | `~/.local/share/chatterbox-tts` | Backend install directory |
| `CHATTERBOX_MODEL_DIR` | `<install>/models/chatterbox-nano` | Model directory |
| `CHATTERBOX_REFERENCE_ROOT` | `<install>/voices` | Managed voice library |
| `CHATTERBOX_IDLE_SECONDS` | `1200` | Backend idle-exit delay |
| `CHATTERBOX_CHUNK_CHARS` | `500` | Internal TTS chunk size |
| `CHATTERBOX_ENABLE_GPU` | `auto` | Enable/disable accelerator setup |
| `CHATTERBOX_TORCH_MODE` | `auto` | PyTorch install mode: `auto`, `cpu`, `default` |
| `CHATTERBOX_TORCH_INDEX_URL` | unset | Optional custom PyTorch package index |
| `CHATTERBOX_GPU_DEVICE` | auto-detected | Optional explicit PyTorch accelerator device |
| `BRIDGE_API_KEY` | `local-dev-key` | Loopback bridge token |

## Validation

```bash
make validate
```

This checks Python, shell, manifests, Firefox/Chrome JavaScript, Firefox XPI packaging, Chrome ZIP packaging, and guards against accidentally committing private keys or machine-specific paths.

## Repository layout

```text
.
├── chatterbox-tts-addon/          # Firefox MV2 source + installer + voices
├── chatterbox-tts-addon-chrome/   # Chrome MV3 source + build helpers
├── templates/                     # Voice Lab template
├── chatterbox_nano_server.py      # CPU/accelerator Chatterbox service
├── openwebui_audio_bridge.py      # Loopback routing bridge
├── chatterbox_voice_app.py        # Voice Lab backend
├── build-xpi.sh                   # Firefox XPI builder
└── Makefile                       # Cross-browser validation
```

## Licence

Apache License 2.0. See [`LICENSE`](LICENSE).

Chatterbox is an upstream Resemble AI dependency and retains its own upstream licence/notices.
