#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SOURCE_ROOT=${CHATTERBOX_SOURCE_ROOT:-$(cd -- "$SCRIPT_DIR/.." && pwd)}
INSTALL_ROOT=${CHATTERBOX_INSTALL_ROOT:-"$HOME/.local/share/chatterbox-tts"}
UNIT_ROOT=${XDG_CONFIG_HOME:-"$HOME/.config"}/systemd/user
VENV="$INSTALL_ROOT/venv"
MODEL_ROOT="$INSTALL_ROOT/models/chatterbox-nano"
VOICE_ROOT="$INSTALL_ROOT/voices"
THREADS=$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 2)
THREADS=$(( THREADS > 1 ? THREADS - 1 : 1 ))

required=(chatterbox_nano_server.py openwebui_audio_bridge.py chatterbox_voice_app.py templates/chatterbox_voice_app.html)
for path in "${required[@]}"; do
    if [[ ! -f "$SOURCE_ROOT/$path" ]]; then
        echo "Missing backend file: $SOURCE_ROOT/$path" >&2
        echo "Use the complete release bundle, not the XPI by itself." >&2
        exit 1
    fi
done
command -v python3 >/dev/null || { echo "Python 3 is required" >&2; exit 1; }
command -v git >/dev/null || { echo "Git is required (pip installs Chatterbox from its upstream repository)" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "FFmpeg is required (install the ffmpeg package first)" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "FFprobe is required (normally provided by the ffmpeg package)" >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd/systemctl is required by the bundled installer" >&2; exit 1; }

mkdir -p "$INSTALL_ROOT/templates" "$MODEL_ROOT" "$VOICE_ROOT" "$UNIT_ROOT"
install -m 0644 "$SOURCE_ROOT/chatterbox_nano_server.py" "$INSTALL_ROOT/"
install -m 0644 "$SOURCE_ROOT/openwebui_audio_bridge.py" "$INSTALL_ROOT/"
install -m 0644 "$SOURCE_ROOT/chatterbox_voice_app.py" "$INSTALL_ROOT/"
install -m 0644 "$SOURCE_ROOT/templates/chatterbox_voice_app.html" "$INSTALL_ROOT/templates/"

# Seed bundled release voices when they are present. Source-only GitHub checkouts
# may omit the large WAV samples; Chatterbox then starts with its model-default
# voice and Voice Lab can create/select a reference normally.
DEFAULT_REFERENCE=""
for voice_id in 6dfc8d33cdb7 af2cdd2b38c1; do
    sample_root="$SCRIPT_DIR/samples/voices/$voice_id"
    target_root="$VOICE_ROOT/$voice_id"
    if [[ -f "$sample_root/reference.wav" && -f "$sample_root/voice.json" ]]; then
        if [[ ! -e "$target_root" ]]; then
            mkdir -p "$target_root"
            install -m 0644 "$sample_root/reference.wav" "$target_root/reference.wav"
            python3 - "$sample_root/voice.json" "$target_root/voice.json" "$target_root/reference.wav" <<'PY'
import json, pathlib, sys
source, target, reference = map(pathlib.Path, sys.argv[1:])
data = json.loads(source.read_text())
data["reference_path"] = str(reference.resolve())
target.write_text(json.dumps(data, indent=2) + "\n")
PY
        fi
        if [[ -z "$DEFAULT_REFERENCE" && -f "$target_root/reference.wav" ]]; then
            DEFAULT_REFERENCE="$target_root/reference.wav"
        fi
    fi
done

python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel setuptools
"$VENV/bin/pip" install --index-url https://download.pytorch.org/whl/cpu torch torchaudio
"$VENV/bin/pip" install 'chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox.git' flask requests soundfile librosa huggingface-hub
"$VENV/bin/python" - <<PY
from huggingface_hub import snapshot_download
snapshot_download(repo_id="ResembleAI/chatterbox-nano", local_dir=${MODEL_ROOT@Q})
PY

cat >"$UNIT_ROOT/chatterbox-nano.service" <<EOF
[Unit]
Description=Chatterbox-Nano local CPU TTS
After=network.target
[Service]
Type=simple
WorkingDirectory=$INSTALL_ROOT
ExecStart=$VENV/bin/python $INSTALL_ROOT/chatterbox_nano_server.py
Restart=on-failure
RestartSec=3
Environment=CHATTERBOX_MODEL_DIR=$MODEL_ROOT
Environment=CHATTERBOX_REFERENCE_ROOT=$VOICE_ROOT
${DEFAULT_REFERENCE:+Environment=CHATTERBOX_REFERENCE_WAV=$DEFAULT_REFERENCE}
Environment=CHATTERBOX_API_KEY=local-dev-key
Environment=CHATTERBOX_PORT=8020
Environment=OMP_NUM_THREADS=$THREADS
Environment=MKL_NUM_THREADS=$THREADS
Environment=OPENBLAS_NUM_THREADS=$THREADS
Environment=CHATTERBOX_INTEROP_THREADS=1
Environment=MALLOC_ARENA_MAX=2
[Install]
WantedBy=default.target
EOF

cat >"$UNIT_ROOT/openwebui-audio-bridge.service" <<EOF
[Unit]
Description=Chatterbox TTS browser bridge
After=network.target chatterbox-nano.service
[Service]
Type=simple
WorkingDirectory=$INSTALL_ROOT
ExecStart=$VENV/bin/python $INSTALL_ROOT/openwebui_audio_bridge.py
Restart=on-failure
RestartSec=2
Environment=CHATTERBOX_BASE=http://127.0.0.1:8020
Environment=BRIDGE_API_KEY=local-dev-key
[Install]
WantedBy=default.target
EOF

cat >"$UNIT_ROOT/chatterbox-voice-app.service" <<EOF
[Unit]
Description=Chatterbox Voice Lab
After=network.target chatterbox-nano.service
[Service]
Type=simple
WorkingDirectory=$INSTALL_ROOT
ExecStart=$VENV/bin/python $INSTALL_ROOT/chatterbox_voice_app.py
Restart=on-failure
RestartSec=2
Environment=CHATTERBOX_INSTALL_ROOT=$INSTALL_ROOT
Environment=CHATTERBOX_REFERENCE_ROOT=$VOICE_ROOT
Environment=CHATTERBOX_BASE=http://127.0.0.1:8020
Environment=CHATTERBOX_API_KEY=local-dev-key
Environment=CHATTERBOX_VOICE_APP_PORT=8030
[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now openwebui-audio-bridge.service chatterbox-voice-app.service
echo "Installed Chatterbox TTS with $THREADS worker threads."
if [[ -n "$DEFAULT_REFERENCE" ]]; then
    echo "Bundled starter voice installed."
else
    echo "No bundled starter WAVs found; using Chatterbox model-default voice until a Voice Lab reference is selected."
fi
echo "Voice Lab: http://127.0.0.1:8030/"
