#!/usr/bin/env python3
"""CPU-only OpenAI-compatible Chatterbox-Nano service for Open WebUI."""
from __future__ import annotations

import io
import os
import site
import time
from pathlib import Path
from threading import Lock, Thread

import soundfile as sf
import torch
from flask import Flask, Response, jsonify, request

EXTRA_SITE_PACKAGES = os.environ.get("CHATTERBOX_EXTRA_SITE_PACKAGES", "")
if EXTRA_SITE_PACKAGES:
    site.addsitedir(EXTRA_SITE_PACKAGES)

from chatterbox.tts_turbo import ChatterboxTurboTTS

MODEL_DIR = Path(os.environ.get("CHATTERBOX_MODEL_DIR", str(Path(__file__).resolve().parent / "models/chatterbox-nano"))).expanduser()
REFERENCE_WAV_RAW = os.environ.get("CHATTERBOX_REFERENCE_WAV", "").strip()
REFERENCE_WAV = Path(REFERENCE_WAV_RAW).expanduser() if REFERENCE_WAV_RAW else None
REFERENCE_ROOT = Path(os.environ.get("CHATTERBOX_REFERENCE_ROOT", str(Path(__file__).resolve().parent / "chatterbox-voices"))).resolve()
API_KEY = os.environ.get("CHATTERBOX_API_KEY", "local-dev-key")
MAX_INPUT_CHARS = int(os.environ.get("CHATTERBOX_MAX_INPUT_CHARS", "4000"))
TORCH_INTEROP_THREADS = int(os.environ.get("CHATTERBOX_INTEROP_THREADS", "1"))
DEVICE = os.environ.get("CHATTERBOX_DEVICE", "cpu")
IDLE_SHUTDOWN_SECONDS = float(os.environ.get("CHATTERBOX_IDLE_SECONDS", "1200"))
IDLE_POLL_SECONDS = float(os.environ.get("CHATTERBOX_IDLE_POLL_SECONDS", "30"))

if not MODEL_DIR.is_dir():
    raise SystemExit(f"Chatterbox model directory missing: {MODEL_DIR}")
if REFERENCE_WAV is not None and not REFERENCE_WAV.is_file():
    raise SystemExit(f"Chatterbox reference audio missing: {REFERENCE_WAV}")

app = Flask(__name__)
generate_lock = Lock()
started_at = time.time()
torch.set_num_interop_threads(TORCH_INTEROP_THREADS)
model = ChatterboxTurboTTS.from_local(MODEL_DIR, DEVICE, nano=True)
if REFERENCE_WAV is not None:
    with torch.inference_mode():
        model.prepare_conditionals(str(REFERENCE_WAV))
active_reference = str(REFERENCE_WAV) if REFERENCE_WAV is not None else "model-default"

activity_lock = Lock()
last_activity = time.time()
active_requests = 0

def mark_activity(delta: int = 0) -> None:
    global last_activity, active_requests
    with activity_lock:
        active_requests += delta
        last_activity = time.time()

def idle_seconds() -> float:
    with activity_lock:
        if active_requests > 0:
            return 0.0
        return time.time() - last_activity

def idle_watchdog() -> None:
    while True:
        time.sleep(IDLE_POLL_SECONDS)
        if idle_seconds() < IDLE_SHUTDOWN_SECONDS:
            continue
        with generate_lock:
            idle = idle_seconds()
            if idle < IDLE_SHUTDOWN_SECONDS:
                continue
            app.logger.warning("Chatterbox idle for %.0fs; unloading model and exiting", idle)
            os._exit(0)

def authorised() -> bool:
    return request.headers.get("Authorization", "") == f"Bearer {API_KEY}"

def allowed_reference(raw_path: object) -> Path | None:
    if not raw_path:
        return None
    candidate = Path(str(raw_path)).expanduser().resolve()
    try:
        candidate.relative_to(REFERENCE_ROOT)
    except ValueError:
        raise ValueError("reference_audio must be inside the managed voice library")
    if not candidate.is_file() or candidate.suffix.lower() != ".wav":
        raise ValueError("reference_audio must be an existing WAV file")
    return candidate

@app.get("/health")
def health():
    return jsonify({"ok": True, "backend": "chatterbox-nano", "device": DEVICE, "model_dir": str(MODEL_DIR), "reference_wav": str(REFERENCE_WAV) if REFERENCE_WAV is not None else "", "active_reference": active_reference, "sample_rate": model.sr, "torch_num_threads": torch.get_num_threads(), "torch_interop_threads": torch.get_num_interop_threads(), "uptime_seconds": round(time.time() - started_at, 1), "idle_seconds": round(idle_seconds(), 1), "idle_shutdown_seconds": IDLE_SHUTDOWN_SECONDS, "active_requests": active_requests})

@app.get("/v1/models")
def models():
    return jsonify({"object": "list", "data": [{"id": "chatterbox-nano", "object": "model", "created": int(started_at), "owned_by": "local"}]})

@app.post("/v1/audio/speech")
@app.post("/audio/speech")
def speech():
    global active_reference
    if not authorised():
        return jsonify({"error": "invalid bearer token"}), 401
    body = request.get_json(silent=True) or {}
    text = str(body.get("input") or body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "'input' text is required"}), 400
    if len(text) > MAX_INPUT_CHARS:
        return jsonify({"error": f"input exceeds {MAX_INPUT_CHARS} characters"}), 400
    try:
        reference_audio = allowed_reference(body.get("reference_audio"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    seed = body.get("seed")
    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            return jsonify({"error": "seed must be an integer"}), 400
    started = time.monotonic()
    mark_activity(+1)
    try:
        with generate_lock, torch.inference_mode():
            try:
                if seed is not None:
                    torch.manual_seed(seed)
                if reference_audio is not None:
                    active_reference = str(reference_audio)
                wav = model.generate(text, audio_prompt_path=str(reference_audio) if reference_audio else None)
            finally:
                if reference_audio is not None and REFERENCE_WAV is not None:
                    model.prepare_conditionals(str(REFERENCE_WAV))
                    active_reference = str(REFERENCE_WAV)
    except Exception as exc:
        app.logger.exception("Chatterbox generation failed")
        return jsonify({"error": f"chatterbox generation failed: {exc}"}), 500
    finally:
        mark_activity(-1)
    samples = wav.squeeze().detach().cpu().numpy()
    output = io.BytesIO()
    sf.write(output, samples, model.sr, format="WAV", subtype="PCM_16")
    response = Response(output.getvalue(), mimetype="audio/wav")
    response.headers["X-Chatterbox-Generate-Seconds"] = f"{time.monotonic() - started:.3f}"
    response.headers["X-Chatterbox-Audio-Seconds"] = f"{len(samples) / model.sr:.3f}"
    return response

if IDLE_SHUTDOWN_SECONDS > 0:
    Thread(target=idle_watchdog, name="idle-watchdog", daemon=True).start()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("CHATTERBOX_PORT", "8020")), threaded=True)
