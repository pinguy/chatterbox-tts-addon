# Chatterbox backend

The Firefox and Chrome extensions use the same loopback bridge:

- Bridge: `127.0.0.1:8010`
- CPU Chatterbox service: `127.0.0.1:8020`
- Optional accelerator service: `127.0.0.1:8021`
- Voice Lab: `127.0.0.1:8030`

The browser can request `auto`, `cpu`, or `gpu`. Requests from OpenAI-compatible clients that do not specify a device continue to use CPU.

Both backend services are started on demand and exit after the configured idle period. Stop cancels queued browser work but does not forcibly kill an inference already executing.
