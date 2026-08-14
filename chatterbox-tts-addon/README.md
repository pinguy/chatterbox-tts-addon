# Chatterbox TTS Firefox Add-on

Firefox-side source for the Chatterbox TTS project. The extension talks to the OpenAI-compatible loopback bridge at `http://127.0.0.1:8010`; the bridge starts CPU Chatterbox-Nano on port `8020` when speech is requested.

For a complete installation, use the repository root rather than copying this directory by itself.

## Backend lifecycle

The installer creates three systemd user units:

- `openwebui-audio-bridge.service` — always-available loopback bridge on `127.0.0.1:8010`.
- `chatterbox-voice-app.service` — Voice Lab on `127.0.0.1:8030`.
- `chatterbox-nano.service` — CPU TTS backend on `127.0.0.1:8020`, started on demand by the bridge.

Chatterbox exits after its configured idle timeout and is started again automatically when the next TTS request arrives.

The repository includes the **Vale** and **Arbor** 30-second starter references. `install.sh` copies them into the managed voice library and uses Vale as the initial default.

## Install for testing

From the repository root:

```bash
bash chatterbox-tts-addon/install.sh
```

Then load the extension temporarily:

1. Open `about:debugging#/runtime/this-firefox`.
2. Choose **Load Temporary Add-on**.
3. Select this directory's `manifest.json`.

Do not select the directory or a tar archive; Firefox expects the manifest or a ZIP-format XPI.

Run `../build-xpi.sh` from the repository root to create an unsigned development XPI in `../dist/`. Normal persistent installation in release Firefox requires Mozilla signing; the repository root carries the current self-distribution XPI.

## Use

- Select text and press the floating speaker button.
- Right-click selected text or a page and choose a Chatterbox action.
- Speech is generated one non-empty line at a time.
- The popup provides a one-to-ten-line startup buffer (two by default), then continues generation ahead of playback.
- The background page owns the single shared Chatterbox job across tabs and the popup, so a new request cleanly replaces the old browser-side job.
- The popup supports text entry, page/selection capture, playback, stop, replay and merged multi-line WAV download.

### Stop semantics

Stop immediately halts browser playback and invalidates queued work. The bridge cancellation epoch prevents later chunks from a cancelled job being accepted.

A Chatterbox generation already running on the backend is not forcibly terminated mid-inference. Its output can be discarded, and the service exits normally when it reaches the idle timeout.

## Privacy

Selected/page text is posted only to the local bridge at `127.0.0.1:8010` by this project. Because that hand-off leaves the Firefox extension context, the manifest truthfully declares required `websiteContent` for current AMO validation.

All synthesis remains local. The add-on does not contain or call Kokoro.
