# Chatterbox TTS Firefox Add-on

Local selected-text and page-text speech through the existing Chatterbox-Nano service.

## Runtime

The extension calls the OpenAI-compatible loopback bridge at `http://127.0.0.1:8010`.
The bridge starts CPU Chatterbox-Nano on port `8020` when needed and stops it after its configured idle period.
Source-only GitHub checkouts may omit the large starter WAV references; Chatterbox then starts with its model-default voice and Voice Lab can create/select a local reference normally.

```bash
systemctl --user start openwebui-audio-bridge.service
python3 server.py
```

`server.py` is now only a health checker. It does not load another TTS model.

## Install for testing

1. Open Firefox `about:debugging#/runtime/this-firefox`.
2. Choose **Load Temporary Add-on**.
3. Select the actual `manifest.json` file from this directory. Do not select the directory or `Archive.tar.gz`; Firefox requires a manifest file or a ZIP-format XPI.

Run `../build-xpi.sh` from the repository root to create an unsigned development XPI in `../dist/`. Firefox can load it temporarily through `about:debugging`; normal permanent installation requires Mozilla signing.

For a new machine, distribute the complete source tree, not only the XPI. Run `bash install.sh` from this directory. Firefox cannot execute that script itself; the first-run page detects the backend and explains this boundary.

## Use

- Select text and press the floating speaker button.
- Right-click selected text or a page and choose a Chatterbox action.
- Speech is generated one non-empty line at a time. The popup lets the user choose a one-to-ten-line startup buffer (two by default), then generation continues ahead of playback. A temporary empty queue waits while its producer request is still alive instead of killing healthy slow CPU inference.
- Press the visible **Stop** button or `Escape` to halt playback, abort queued work, terminate active inference and unload Chatterbox.
- The background page owns the single shared Chatterbox job across tabs and the popup, so starting a new request cleanly replaces the old owner.
- The popup supports text entry, page/selection capture, playback, stop, replay and a correctly merged multi-line WAV download.

All synthesis remains local. The add-on no longer contains or calls Kokoro.
