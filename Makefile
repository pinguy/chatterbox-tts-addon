.PHONY: validate xpi

validate:
	python3 -m py_compile chatterbox_nano_server.py openwebui_audio_bridge.py chatterbox_voice_app.py chatterbox-tts-addon/server.py
	python3 -m json.tool chatterbox-tts-addon/manifest.json >/dev/null
	bash -n chatterbox-tts-addon/install.sh build-xpi.sh
	node --check chatterbox-tts-addon/background.js
	node --check chatterbox-tts-addon/content.js
	node --check chatterbox-tts-addon/popup.js
	node --check chatterbox-tts-addon/player.js
	node --check chatterbox-tts-addon/welcome.js
	./build-xpi.sh >/dev/null
	python3 -c 'import glob, zipfile; files=glob.glob("dist/chatterbox-tts-addon-*-unsigned.xpi"); assert len(files) == 1; z=zipfile.ZipFile(files[0]); assert "manifest.json" in z.namelist()'

xpi:
	./build-xpi.sh
