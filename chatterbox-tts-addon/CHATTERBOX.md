# Chatterbox backend

This project uses a local CPU Chatterbox-Nano service. GPU setup is intentionally outside the add-on and is not required.

- Model service: `chatterbox-nano.service` on `127.0.0.1:8020`
- Add-on/API bridge: `openwebui-audio-bridge.service` on `127.0.0.1:8010`
- Voice Lab: `chatterbox-voice-app.service` on `127.0.0.1:8030`
- Health check: `http://127.0.0.1:8010/health`

The bridge starts `chatterbox-nano.service` on demand when a TTS request arrives. The model service exits after its configured idle timeout and is started again automatically when needed.

The add-on requests one WAV per non-empty line and uses the popup's persisted one-to-ten-line startup buffer (two by default). Temporary queue gaps wait while the producer is still alive.

Stop immediately halts browser playback and invalidates queued browser work. The bridge's cancellation epoch prevents later chunks from a cancelled job being accepted. It does **not** forcibly kill a Chatterbox inference that is already running; an unwanted result is discarded and the service exits normally after becoming idle.

The managed reference library lives under `~/.local/share/chatterbox-tts/voices/`. The bundled installer seeds the 30-second Vale and Arbor references, with Vale used as the initial default.
