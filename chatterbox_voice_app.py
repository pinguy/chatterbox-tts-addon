#!/usr/bin/env python3
"""Local voice-preparation and Chatterbox-Nano preview UI."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

BASE = Path(os.environ.get("CHATTERBOX_INSTALL_ROOT", str(Path(__file__).resolve().parent))).expanduser()
VOICE_ROOT = Path(os.environ.get("CHATTERBOX_REFERENCE_ROOT", str(BASE / "chatterbox-voices"))).expanduser()
DROPIN_DIR = Path(os.environ.get("CHATTERBOX_DROPIN_DIR", str(Path.home() / ".config/systemd/user/chatterbox-nano.service.d"))).expanduser()
DROPIN = DROPIN_DIR / "20-voice-app-default.conf"
BACKUP_ROOT = Path(os.environ.get("CHATTERBOX_VOICE_BACKUP_ROOT", str(BASE / "backups/voice-lab"))).expanduser()
CHATTERBOX_URL = os.environ.get("CHATTERBOX_BASE", "http://127.0.0.1:8020")
API_KEY = os.environ.get("CHATTERBOX_API_KEY", "local-dev-key")
MAX_UPLOAD = 500 * 1024 * 1024
REFERENCE_DURATIONS = {10, 15, 20, 30, 45, 60}
DEFAULT_REFERENCE_DURATION = 30

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD
VOICE_ROOT.mkdir(parents=True, exist_ok=True)
BACKUP_ROOT.mkdir(parents=True, exist_ok=True)


def run(command: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=True)


def voice_dir(voice_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", voice_id):
        raise ValueError("invalid voice id")
    path = (VOICE_ROOT / voice_id).resolve()
    path.relative_to(VOICE_ROOT.resolve())
    return path


def metadata(path: Path) -> dict:
    return json.loads((path / "voice.json").read_text())


def voices() -> list[dict]:
    found = []
    for item in VOICE_ROOT.iterdir():
        if item.is_dir() and (item / "voice.json").is_file() and (item / "reference.wav").is_file():
            try:
                found.append(metadata(item))
            except (OSError, json.JSONDecodeError):
                continue
    return sorted(found, key=lambda row: row.get("created_at", ""), reverse=True)


def current_default() -> str:
    try:
        health = requests.get(f"{CHATTERBOX_URL}/health", timeout=3).json()
        return str(health.get("reference_wav", ""))
    except Exception:
        return ""


def configured_default() -> str:
    if not DROPIN.is_file():
        return ""
    try:
        for line in DROPIN.read_text().splitlines():
            prefix = "Environment=CHATTERBOX_REFERENCE_WAV="
            if line.startswith(prefix):
                return line.removeprefix(prefix).strip()
    except OSError:
        pass
    return ""


def effective_default() -> str:
    return current_default() or configured_default()


@app.get("/")
def index():
    return render_template("chatterbox_voice_app.html", voices=voices(), current_default=effective_default())


@app.get("/api/status")
def status():
    return jsonify({"ok": True, "voices": voices(), "current_default": effective_default()})


@app.post("/api/voices")
def create_voice():
    upload = request.files.get("media")
    name = (request.form.get("name") or "New voice").strip()[:80]
    try:
        requested_duration = int(request.form.get("duration") or DEFAULT_REFERENCE_DURATION)
    except (TypeError, ValueError):
        return jsonify({"error": "Choose a valid reference length"}), 400
    if requested_duration not in REFERENCE_DURATIONS:
        return jsonify({"error": "Reference length must be 10, 15, 20, 30, 45 or 60 seconds"}), 400
    if not upload or not upload.filename:
        return jsonify({"error": "Choose an audio or video file"}), 400
    voice_id = uuid.uuid4().hex[:12]
    target = voice_dir(voice_id)
    target.mkdir(mode=0o750)
    source_name = secure_filename(upload.filename) or "source-media"
    source = target / source_name
    reference = target / "reference.wav"
    try:
        upload.save(source)
        audio_filter = (
            "highpass=f=65:p=2,lowpass=f=10500:p=2,adeclick=w=20:o=75:a=2,"
            "silenceremove=start_periods=1:start_duration=0.15:start_threshold=-48dB:"
            "stop_periods=-1:stop_duration=0.5:stop_threshold=-48dB,"
            "loudnorm=I=-18:TP=-2:LRA=7"
        )
        run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vn", "-t", str(requested_duration), "-af", audio_filter, "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(reference)])
        probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(reference)])
        duration = float(probe.stdout.strip())
        if duration < 5.1:
            raise ValueError("Cleaned speech is under 5 seconds; use a longer sample")
        info = {"id": voice_id, "name": name, "source_name": source_name, "reference_path": str(reference), "duration_seconds": round(duration, 2), "requested_duration_seconds": requested_duration, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        (target / "voice.json").write_text(json.dumps(info, indent=2) + "\n")
        return jsonify(info), 201
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
        shutil.rmtree(target, ignore_errors=True)
        detail = exc.stderr[-800:] if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        return jsonify({"error": f"Could not prepare voice: {detail}"}), 400


@app.get("/api/voices/<voice_id>/reference")
def reference_audio(voice_id: str):
    return send_file(voice_dir(voice_id) / "reference.wav", mimetype="audio/wav", conditional=True)


@app.post("/api/voices/<voice_id>/preview")
def preview(voice_id: str):
    path = voice_dir(voice_id)
    if not (path / "reference.wav").is_file():
        return jsonify({"error": "Voice not found"}), 404
    body = request.get_json(silent=True) or {}
    text = str(body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Enter some text"}), 400
    try:
        subprocess.run(["systemctl", "--user", "start", "chatterbox-nano.service"], check=False)
        response = requests.post(f"{CHATTERBOX_URL}/v1/audio/speech", headers={"Authorization": f"Bearer {API_KEY}"}, json={"input": text, "model": "chatterbox-nano", "reference_audio": str(path / "reference.wav")}, timeout=300)
        response.raise_for_status()
    except requests.RequestException as exc:
        detail = getattr(exc.response, "text", "")[-600:] if getattr(exc, "response", None) else str(exc)
        return jsonify({"error": f"Preview failed: {detail}"}), 502
    with tempfile.TemporaryDirectory(prefix="chatterbox-preview-") as temp_dir:
        raw = Path(temp_dir) / "raw.wav"
        normalised = Path(temp_dir) / "clone-normalised.wav"
        raw.write_bytes(response.content)
        try:
            run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-af", "loudnorm=I=-19:TP=-2:LRA=7", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(normalised)])
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            detail = exc.stderr[-600:] if isinstance(exc, subprocess.CalledProcessError) else str(exc)
            return jsonify({"error": f"Preview normalisation failed: {detail}"}), 502
        voice_name = re.sub(r"[^A-Za-z0-9._-]+", "-", metadata(path)["name"]).strip("-") or "voice"
        result = send_file(normalised, mimetype="audio/wav", as_attachment=False, download_name=f"{voice_name}-clone-normalised.wav")
        result.headers["X-Chatterbox-Generate-Seconds"] = response.headers.get("X-Chatterbox-Generate-Seconds", "")
        result.headers["X-Chatterbox-Audio-Seconds"] = response.headers.get("X-Chatterbox-Audio-Seconds", "")
        return result


@app.delete("/api/voices/<voice_id>")
def delete_voice(voice_id: str):
    path = voice_dir(voice_id)
    reference = path / "reference.wav"
    if not reference.is_file():
        return jsonify({"error": "Voice not found"}), 404
    if str(reference) in {current_default(), configured_default()}:
        return jsonify({"error": "This is Chatterbox's current default. Select another default before deleting its library copy."}), 409
    name = metadata(path).get("name", voice_id)
    try:
        run(["gio", "trash", str(path)], timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = exc.stderr[-600:] if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        return jsonify({"error": f"Could not move library copy to Trash: {detail}"}), 500
    return jsonify({"ok": True, "id": voice_id, "name": name, "library_copy_trashed": True, "original_untouched": True})


@app.post("/api/voices/<voice_id>/make-default")
def make_default(voice_id: str):
    path = voice_dir(voice_id)
    reference = path / "reference.wav"
    if not reference.is_file():
        return jsonify({"error": "Voice not found"}), 404
    stamp = time.strftime("%Y%m%dT%H%M%S%z")
    backup = BACKUP_ROOT / stamp
    backup.mkdir(parents=True)
    if DROPIN.exists():
        shutil.copy2(DROPIN, backup / DROPIN.name)
    else:
        (backup / "dropin-was-absent").touch()
    previous = current_default()
    DROPIN_DIR.mkdir(parents=True, exist_ok=True)
    temp = DROPIN.with_suffix(".tmp")
    temp.write_text(f"[Service]\nEnvironment=CHATTERBOX_REFERENCE_WAV={reference}\n")
    os.replace(temp, DROPIN)
    try:
        run(["systemctl", "--user", "daemon-reload"], timeout=30)
        run(["systemctl", "--user", "restart", "chatterbox-nano.service"], timeout=60)
        deadline = time.time() + 90
        observed = ""
        while time.time() < deadline:
            observed = current_default()
            if observed == str(reference):
                break
            time.sleep(1)
        if observed != str(reference):
            raise RuntimeError(f"service did not load requested reference (reported {observed!r})")
    except Exception as exc:
        if (backup / DROPIN.name).exists():
            shutil.copy2(backup / DROPIN.name, DROPIN)
        else:
            DROPIN.unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "restart", "chatterbox-nano.service"], check=False)
        return jsonify({"error": f"Default switch rolled back: {exc}"}), 500
    return jsonify({"ok": True, "name": metadata(path)["name"], "reference_path": str(reference), "previous_default": previous, "rollback": str(backup)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("CHATTERBOX_VOICE_APP_PORT", "8030")), threaded=True)
