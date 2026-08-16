# Changelog

## 4.2.0

- Reworked CPU/GPU selection to be machine-independent: **Auto / CPU / GPU-accelerator** instead of naming a specific graphics card.
- Browser queries bridge capabilities and disables the accelerator option when none is configured.
- Saved device selection now applies consistently to popup, context menu and in-page controls in both Firefox and Chrome.
- Added a generic optional accelerator service on port `8021`; CPU remains the universal fallback on port `8020`.
- Installer can auto-detect a usable PyTorch accelerator and supports environment overrides for custom PyTorch/device setups.
- Removed user-specific Python shebangs, home-directory paths, model paths and hardware labels.
- Optional Whisper STT now requires explicit environment configuration instead of local machine paths.
- Validation now guards against committed private keys and common machine-specific paths.
- Fixed Voice Lab default-voice switching so the selected reference is applied and verified on both CPU and accelerator backends instead of leaving the accelerator pinned to the original starter voice.
- Voice deletion now refuses to remove a reference that is still configured as the default on either backend.

## 4.1.1

- Fixed device selection being ignored by context-menu and in-page speech entry points.

## 4.1.0

- Added browser-selectable CPU/GPU synthesis routing.

## 4.0.2

- Chatterbox-Nano local TTS backend.
- Firefox and Chrome browser integration, Voice Lab, buffering, WAV download and idle backend shutdown.
