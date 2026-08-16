# Chatterbox TTS — Firefox extension

Firefox Manifest V2 frontend for the shared local Chatterbox-Nano backend.

## Install for development

1. Install the backend from the repository root with `bash chatterbox-tts-addon/install.sh`.
2. Open `about:debugging#/runtime/this-firefox`.
3. Choose **Load Temporary Add-on**.
4. Select this directory's `manifest.json`.

The popup lets you choose **Auto**, **CPU**, or **GPU / accelerator**. Auto uses an accelerator only when the bridge reports one as available; otherwise it uses CPU.

The backend is local on `127.0.0.1:8010`. Voice Lab is local on `127.0.0.1:8030`.

Run `../build-xpi.sh` to create an unsigned development XPI.
