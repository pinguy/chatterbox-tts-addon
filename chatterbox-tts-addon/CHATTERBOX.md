# Chatterbox backend

This build uses the machine's established CPU Chatterbox-Nano service. GPU setup is intentionally outside the add-on and is not required.

- Model service: `chatterbox-nano.service` on `127.0.0.1:8020`
- Add-on/API bridge: `openwebui-audio-bridge.service` on `127.0.0.1:8010`
- Health check: `http://127.0.0.1:8010/health`

The add-on requests one WAV per non-empty line and uses the popup's persisted one-to-ten-line startup buffer (two by default). Temporary queue gaps wait while the producer is alive. Stop aborts the browser request, halts playback, and calls the authenticated bridge stop endpoint to terminate and unload Chatterbox itself.
