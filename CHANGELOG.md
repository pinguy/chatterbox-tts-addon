# Changelog

## 4.0.2

Current public release baseline.

### Shared backend

- Chatterbox-Nano local CPU TTS backend.
- One-to-ten-line startup buffering with continued generation ahead of playback.
- Stop handling that immediately halts playback and cancels queued browser work without forcibly killing an inference already running on the backend.
- Merged multi-line WAV download.
- Local Voice Lab for preparing, previewing and selecting reference voices.
- Bundled 30-second **Vale** and **Arbor** starter references, with Vale as the initial default.
- On-demand `chatterbox-nano.service` startup and idle service exit for lower background RAM use.
- Portable installer paths and systemd user-service setup.

### Firefox

- Firefox Manifest V2 add-on with shared job ownership across tabs and popup.
- Current Firefox/AMO `websiteContent` data-collection declaration.
- Desktop Firefox 140 minimum and Firefox Android 142 compatibility declaration in the submitted 4.0.2 manifest.
- Self-distribution XPI tracked at repository root.

### Chrome / Chromium

- Added Manifest V3 Chrome/Chromium port using the same local backend and Voice Lab.
- Persistent Firefox background page adapted to an MV3 service worker with UI keepalives during active jobs.
- Tab audio playback moved to an MV3 offscreen document.
- Async messaging adapted to Chrome's `sendResponse` model and script injection moved to `scripting.executeScript`.
- Added Chrome Web Store ZIP builder and CRX3 builder.
- Chrome private signing material is kept outside the repository by default; generated `dist/` output is ignored.
- Root CRX kept as the current self-distribution/archive package.

### Repository

- Cross-browser README and browser-specific documentation.
- GitHub validation now checks both Firefox MV2 and Chrome MV3 source/package structure.
