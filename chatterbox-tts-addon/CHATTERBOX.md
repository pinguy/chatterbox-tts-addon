# Chatterbox backend

This project uses a local Chatterbox-Nano service with CPU support always available and an optional accelerator backend.

- CPU service: `chatterbox-nano.service` on `127.0.0.1:8020`
- Optional accelerator service: `chatterbox-nano-accelerator.service` on `127.0.0.1:8021`
- Add-on/API bridge: `openwebui-audio-bridge.service` on `127.0.0.1:8010`
- Voice Lab: `chatterbox-voice-app.service` on `127.0.0.1:8030`
- Health check: `http://127.0.0.1:8010/health`

The bridge starts the requested backend on demand. Model services exit after their configured idle timeout and are started again automatically when needed.

The browser can request **Auto**, **CPU**, or **GPU / accelerator**. Auto prefers the configured accelerator and falls back to CPU when no accelerator backend is available.

Voice Lab manages one logical default reference across the available Chatterbox backends. When **Make default** is used it writes systemd drop-ins for CPU and accelerator services, restarts each backend long enough to verify `/health` reports the requested reference, then restores any backend that was previously stopped. If either backend fails verification, both configurations are rolled back together.

The add-on requests one WAV per non-empty line and uses the popup's persisted one-to-ten-line startup buffer (two by default). Temporary queue gaps wait while the producer is still alive.

Stop immediately halts browser playback and invalidates queued browser work. The bridge's cancellation epoch prevents later chunks from a cancelled job being accepted. It does **not** forcibly kill a Chatterbox inference that is already running; an unwanted result is discarded and the service exits normally after becoming idle.

The managed reference library lives under `~/.local/share/chatterbox-tts/voices/`. The bundled installer seeds the 30-second Vale and Arbor references, with Vale used as the initial default until another voice is selected.
