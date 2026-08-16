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

# Accelerator controls:
#   CHATTERBOX_ENABLE_GPU=auto|1|0    auto-detect by default
#   CHATTERBOX_TORCH_MODE=auto|cpu|default
#   CHATTERBOX_TORCH_INDEX_URL=...    optional custom PyTorch wheel index
#   CHATTERBOX_GPU_DEVICE=cuda|xpu|mps|... optional explicit torch device
ENABLE_GPU=${CHATTERBOX_ENABLE_GPU:-auto}
TORCH_MODE=${CHATTERBOX_TORCH_MODE:-auto}
TORCH_INDEX_URL=${CHATTERBOX_TORCH_INDEX_URL:-}
REQUESTED_GPU_DEVICE=${CHATTERBOX_GPU_DEVICE:-}

required=(chatterbox_nano_server.py openwebui_audio_bridge.py chatterbox_voice_app.py templates/chatterbox_voice_app.html)
for path in "${required[@]}"; do
    if [[ ! -f "$SOURCE_ROOT/$path" ]]; then
        echo "Missing backend file: $SOURCE_ROOT/$path" >&2
        echo "Use the complete repository/release bundle, not the browser package by itself." >&2
        exit 1
    fi
done

for command in python3 git ffmpeg ffprobe systemctl; do
    command -v "$command" >/dev/null || { echo "$command is required" >&2; exit 1; }
done

mkdir -p "$INSTALL_ROOT/templates" "$MODEL_ROOT" "$VOICE_ROOT" "$UNIT_ROOT"
install -m 0755 "$SOURCE_ROOT/chatterbox_nano_server.py" "$INSTALL_ROOT/"
install -m 0755 "$SOURCE_ROOT/openwebui_audio_bridge.py" "$INSTALL_ROOT/"
install -m 0755 "$SOURCE_ROOT/chatterbox_voice_app.py" "$INSTALL_ROOT/"
install -m 0644 "$SOURCE_ROOT/templates/chatterbox_voice_app.html" "$INSTALL_ROOT/templates/"

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

install_torch_cpu() {
    "$VENV/bin/pip" install --index-url https://download.pytorch.org/whl/cpu torch torchaudio
}

install_torch_default() {
    "$VENV/bin/pip" install torch torchaudio
}

if [[ -n "$TORCH_INDEX_URL" ]]; then
    echo "Installing PyTorch from CHATTERBOX_TORCH_INDEX_URL."
    "$VENV/bin/pip" install --index-url "$TORCH_INDEX_URL" torch torchaudio
elif [[ "$TORCH_MODE" == "cpu" ]]; then
    install_torch_cpu
elif [[ "$TORCH_MODE" == "default" ]]; then
    install_torch_default
elif [[ "$TORCH_MODE" == "auto" ]]; then
    # On NVIDIA systems the normal PyPI package can provide a CUDA runtime.
    # Everywhere else, keep the default install small and predictable by using
    # the CPU wheel. Other accelerator stacks can be supplied with the override
    # variables above without changing this repository.
    if [[ "$ENABLE_GPU" != "0" && "$ENABLE_GPU" != "false" ]] && command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
        echo "NVIDIA GPU detected; installing the default PyTorch package and checking accelerator support."
        install_torch_default
    else
        install_torch_cpu
    fi
else
    echo "Invalid CHATTERBOX_TORCH_MODE=$TORCH_MODE (expected auto, cpu, or default)" >&2
    exit 1
fi

"$VENV/bin/pip" install 'chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox.git' flask requests soundfile librosa huggingface-hub
"$VENV/bin/python" - <<PY
from huggingface_hub import snapshot_download
snapshot_download(repo_id="ResembleAI/chatterbox-nano", local_dir=${MODEL_ROOT@Q})
PY

ACCELERATOR_DEVICE=$(
    CHATTERBOX_GPU_DEVICE="$REQUESTED_GPU_DEVICE" "$VENV/bin/python" - <<'PY'
import os
import torch
requested = os.environ.get("CHATTERBOX_GPU_DEVICE", "").strip().lower()

def available(device):
    if device.startswith("cuda"):
        return torch.cuda.is_available()
    if device.startswith("xpu"):
        return hasattr(torch, "xpu") and torch.xpu.is_available()
    if device.startswith("mps"):
        return hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    try:
        torch.empty(1, device=device)
        return True
    except Exception:
        return False

if requested:
    if available(requested):
        print(requested)
else:
    for candidate in ("cuda", "xpu", "mps"):
        if available(candidate):
            print(candidate)
            break
PY
)

ACCELERATOR_ENABLED=0
if [[ "$ENABLE_GPU" != "0" && "$ENABLE_GPU" != "false" && -n "$ACCELERATOR_DEVICE" ]]; then
    ACCELERATOR_ENABLED=1
elif [[ "$ENABLE_GPU" == "1" || "$ENABLE_GPU" == "true" ]]; then
    echo "GPU/accelerator support was requested, but this PyTorch runtime reports no usable accelerator." >&2
    echo "CPU will still work. Install a suitable PyTorch build and rerun the installer, or set CHATTERBOX_TORCH_INDEX_URL / CHATTERBOX_GPU_DEVICE." >&2
fi

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
Environment=CHATTERBOX_DEVICE=cpu
Environment=OMP_NUM_THREADS=$THREADS
Environment=MKL_NUM_THREADS=$THREADS
Environment=OPENBLAS_NUM_THREADS=$THREADS
Environment=CHATTERBOX_INTEROP_THREADS=1
Environment=MALLOC_ARENA_MAX=2
[Install]
WantedBy=default.target
EOF

if [[ "$ACCELERATOR_ENABLED" == "1" ]]; then
    cat >"$UNIT_ROOT/chatterbox-nano-accelerator.service" <<EOF
[Unit]
Description=Chatterbox-Nano local accelerator TTS
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
Environment=CHATTERBOX_PORT=8021
Environment=CHATTERBOX_DEVICE=$ACCELERATOR_DEVICE
Environment=CHATTERBOX_INTEROP_THREADS=1
[Install]
WantedBy=default.target
EOF
else
    rm -f "$UNIT_ROOT/chatterbox-nano-accelerator.service"
fi

cat >"$UNIT_ROOT/openwebui-audio-bridge.service" <<EOF
[Unit]
Description=Chatterbox TTS browser bridge
After=network.target
[Service]
Type=simple
WorkingDirectory=$INSTALL_ROOT
ExecStart=$VENV/bin/python $INSTALL_ROOT/openwebui_audio_bridge.py
Restart=on-failure
RestartSec=2
Environment=CHATTERBOX_BASE=http://127.0.0.1:8020
Environment=CHATTERBOX_SERVICE=chatterbox-nano.service
Environment=CHATTERBOX_ACCELERATOR_BASE=http://127.0.0.1:8021
Environment=CHATTERBOX_ACCELERATOR_SERVICE=chatterbox-nano-accelerator.service
Environment=CHATTERBOX_ACCELERATOR_ENABLED=$ACCELERATOR_ENABLED
Environment=CHATTERBOX_ACCELERATOR_LABEL=${ACCELERATOR_DEVICE:-GPU / accelerator}
Environment=BRIDGE_API_KEY=local-dev-key
[Install]
WantedBy=default.target
EOF

cat >"$UNIT_ROOT/chatterbox-voice-app.service" <<EOF
[Unit]
Description=Chatterbox Voice Lab
After=network.target
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

echo "Installed Chatterbox TTS with $THREADS CPU worker threads."
if [[ "$ACCELERATOR_ENABLED" == "1" ]]; then
    echo "Accelerator backend available: $ACCELERATOR_DEVICE (selected automatically by the browser's Auto setting)."
else
    echo "No accelerator backend configured; browser Auto/GPU selection will use CPU only."
fi
if [[ -n "$DEFAULT_REFERENCE" ]]; then
    echo "Bundled starter voice installed."
else
    echo "No bundled starter WAVs found; using Chatterbox model-default voice until a Voice Lab reference is selected."
fi
echo "Voice Lab: http://127.0.0.1:8030/"
