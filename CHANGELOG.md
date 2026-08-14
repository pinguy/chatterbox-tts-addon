# Changelog

## 4.0.2

Current public release baseline.

- Chatterbox-Nano local CPU TTS backend.
- Shared browser job ownership across tabs and popup.
- One-to-ten-line startup buffering with continued generation ahead of playback.
- Stop handling that immediately halts playback and cancels queued browser work without forcibly killing an inference already running on the backend.
- Merged multi-line WAV download.
- Local Voice Lab for preparing, previewing and selecting reference voices.
- Bundled 30-second **Vale** and **Arbor** starter references, with Vale as the initial default.
- On-demand `chatterbox-nano.service` startup and idle service exit for lower background RAM use.
- Portable installer paths and systemd user-service setup.
- Current Firefox/AMO `websiteContent` data-collection declaration.
- Desktop Firefox 140 minimum and Firefox Android 142 compatibility declaration in the submitted 4.0.2 manifest.
- Root documentation, unsigned-XPI build helper and GitHub validation workflow.
- Self-distribution XPI tracked at repository root.
