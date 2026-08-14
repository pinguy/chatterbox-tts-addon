# Changelog

## 4.0.2

Current public release baseline.

- Chatterbox-Nano local TTS backend.
- Shared browser job ownership across tabs and popup.
- One-to-ten-line startup buffering with continued generation ahead of playback.
- Stop handling that aborts queued browser work without needlessly keeping stale synthesis alive.
- Merged multi-line WAV download.
- Local Voice Lab for preparing, previewing and selecting reference voices.
- Voice Lab support for local reference voices; release bundles may include optional starter references.
- Idle model unloading for lower background RAM use.
- Repository packaging cleanup: portable paths, root documentation, unsigned-XPI build helper and validation workflow.
