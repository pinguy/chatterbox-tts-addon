.PHONY: validate firefox-xpi chrome-zip clean

validate: clean
	python3 -m py_compile chatterbox_nano_server.py openwebui_audio_bridge.py chatterbox_voice_app.py chatterbox-tts-addon/server.py
	python3 -c 'p=open("chatterbox_voice_app.py",encoding="utf-8").read(); assert "ACCELERATOR_SERVICE" in p and "write_dropin(service, reference)" in p and "restore_dropin(service, backup)" in p'
	python3 -m json.tool chatterbox-tts-addon/manifest.json >/dev/null
	python3 -m json.tool chatterbox-tts-addon-chrome/manifest.json >/dev/null
	bash -n chatterbox-tts-addon/install.sh build-xpi.sh chatterbox-tts-addon-chrome/build-zip.sh chatterbox-tts-addon-chrome/build-crx.sh
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
	! grep -RInE --exclude='*.xpi' --exclude='*.crx' --exclude='*.zip' --exclude='Makefile' --exclude-dir='.git' '(/home/|/500GB|RTX [0-9]+|Antoni|Norman)' .
	test -z "$$(find . -type f \( -name '*.pem' -o -name '*.key' \) -print -quit)"
	./build-xpi.sh >/dev/null
	./chatterbox-tts-addon-chrome/build-zip.sh >/dev/null
	python3 -c 'import glob,zipfile; f=glob.glob("dist/chatterbox-tts-addon-*-unsigned.xpi"); assert len(f)==1; z=zipfile.ZipFile(f[0]); assert "manifest.json" in z.namelist()'
	python3 -c 'import glob,zipfile; f=glob.glob("chatterbox-tts-addon-chrome/dist/chatterbox-tts-chrome-*.zip"); assert len(f)==1; z=zipfile.ZipFile(f[0]); assert "manifest.json" in z.namelist(); assert not any(n.endswith((".pem",".key")) for n in z.namelist())'

firefox-xpi:
	./build-xpi.sh

chrome-zip:
	./chatterbox-tts-addon-chrome/build-zip.sh

clean:
	rm -rf dist chatterbox-tts-addon-chrome/dist __pycache__ chatterbox-tts-addon/__pycache__
