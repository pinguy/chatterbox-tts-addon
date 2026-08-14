.PHONY: validate xpi chrome-zip

validate:
	python3 -m py_compile chatterbox_nano_server.py openwebui_audio_bridge.py chatterbox_voice_app.py chatterbox-tts-addon/server.py
	python3 -m json.tool chatterbox-tts-addon/manifest.json >/dev/null
	python3 -m json.tool chatterbox-tts-addon-chrome/manifest.json >/dev/null
	bash -n chatterbox-tts-addon/install.sh build-xpi.sh chatterbox-tts-addon-chrome/build-crx.sh chatterbox-tts-addon-chrome/build-zip.sh
	node --check chatterbox-tts-addon/background.js
	node --check chatterbox-tts-addon/content.js
	node --check chatterbox-tts-addon/popup.js
	node --check chatterbox-tts-addon/player.js
	node --check chatterbox-tts-addon/welcome.js
	node --check chatterbox-tts-addon-chrome/background.js
	node --check chatterbox-tts-addon-chrome/content.js
	node --check chatterbox-tts-addon-chrome/popup.js
	node --check chatterbox-tts-addon-chrome/offscreen.js
	node --check chatterbox-tts-addon-chrome/welcome.js
	./build-xpi.sh >/dev/null
	python3 -c 'import glob, zipfile; files=glob.glob("dist/chatterbox-tts-addon-*-unsigned.xpi"); assert len(files) == 1; z=zipfile.ZipFile(files[0]); assert "manifest.json" in z.namelist()'
	./chatterbox-tts-addon-chrome/build-zip.sh >/dev/null
	python3 -c 'import glob, json, zipfile; files=glob.glob("chatterbox-tts-addon-chrome/dist/chatterbox-tts-chrome-*.zip"); assert len(files) == 1; z=zipfile.ZipFile(files[0]); names=set(z.namelist()); assert "manifest.json" in names; m=json.loads(z.read("manifest.json")); assert m["manifest_version"] == 3; assert not any(name.endswith(".pem") for name in names)'

xpi:
	./build-xpi.sh

chrome-zip:
	./chatterbox-tts-addon-chrome/build-zip.sh
