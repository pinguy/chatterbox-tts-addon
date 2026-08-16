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
SYSTEMD_USER_ROOT = Path(os.environ.get("CHATTERBOX_SYSTEMD_USER_DIR", str(Path.home() / ".config/systemd/user"))).expanduser()
LEGACY_CPU_DROPIN_DIR = os.environ.get("CHATTERBOX_DROPIN_DIR", "").strip()
BACKUP_ROOT = Path(os.environ.get("CHATTERBOX_VOICE_BACKUP_ROOT", str(BASE / "backups/voice-lab"))).expanduser()

CPU_SERVICE = os.environ.get("CHATTERBOX_SERVICE", "chatterbox-nano.service").strip() or "chatterbox-nano.service"
CPU_URL = os.environ.get("CHATTERBOX_BASE", "http://127.0.0.1:8020").rstrip("/")
ACCELERATOR_SERVICE = os.environ.get("CHATTERBOX_ACCELERATOR_SERVICE", "chatterbox-nano-accelerator.service").strip() or "chatterbox-nano-accelerator.service"
ACCELERATOR_URL = os.environ.get("CHATTERBOX_ACCELERATOR_BASE", "http://127.0.0.1:8021").rstrip("/")
ACCELERATOR_ENABLED = os.environ.get("CHATTERBOX_ACCELERATOR_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
API_KEY = os.environ.get("CHATTERBOX_API_KEY", "local-dev-key")

MAX_UPLOAD = 500 * 1024 * 1024
REFERENCE_DURATIONS = {10, 15, 20, 30, 45, 60}
DEFAULT_REFERENCE_DURATION = 30
DROPIN_NAME = "20-voice-app-default.conf"

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


def service_dropin(service: str) -> Path:
    if service == CPU_SERVICE and LEGACY_CPU_DROPIN_DIR:
        return Path(LEGACY_CPU_DROPIN_DIR).expanduser() / DROPIN_NAME
    return SYSTEMD_USER_ROOT / f"{service}.d" / DROPIN_NAME


def service_exists(service: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show", service, "--property=LoadState", "--value"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() not in {"", "not-found"}
    except (OSError, subprocess.TimeoutExpired):
        return False


def service_active(service: str) -> bool:
    try:
        return subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", service],
            timeout=10,
            check=False,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def managed_backends() -> list[tuple[str, str]]:
    targets = [(CPU_SERVICE, CPU_URL)]
    if ACCELERATOR_ENABLED or service_exists(ACCELERATOR_SERVICE):
        targets.append((ACCELERATOR_SERVICE, ACCELERATOR_URL))
    return targets


def backend_reference(url: str) -> str:
    try:
        response = requests.get(f"{url}/health", timeout=3)
        response.raise_for_status()
        return str(response.json().get("reference_wav", ""))
    except Exception:
        return ""


def configured_default_for(service: str) -> str:
    dropin = service_dropin(service)
    if not dropin.is_file():
        return ""
    try:
        for line in dropin.read_text().splitlines():
            line = line.strip()
            prefixes = (
                "Environment=CHATTERBOX_REFERENCE_WAV=",
                'Environment="CHATTERBOX_REFERENCE_WAV=',
            )
            for prefix in prefixes:
                if line.startswith(prefix):
                    value = line.removeprefix(prefix).strip()
                    if prefix.endswith('"CHATTERBOX_REFERENCE_WAV=') and value.endswith('"'):
                        value = value[:-1]
                    return value.replace('\\"', '"').replace('\\\\', '\\')
    except OSError:
        pass
    return ""


def current_default() -> str:
    return backend_reference(CPU_URL)


def configured_default() -> str:
    return configured_default_for(CPU_SERVICE)


def effective_default() -> str:
    return current_default() or configured_default()


def all_default_references() -> set[str]:
    refs: set[str] = set()
    for service, url in managed_backends():
        live = backend_reference(url)
        configured = configured_default_for(service)
        if live:
            refs.add(live)
        if configured:
            refs.add(configured)
    return refs


def backend_status() -> list[dict]:
    result = []
    for service, url in managed_backends():
        result.append({
            "service": service,
            "url": url,
            "active": service_active(service),
            "current_default": backend_reference(url),
            "configured_default": configured_default_for(service),
        })
    return result


def backup_dropin(service: str, backup: Path) -> None:
    dropin = service_dropin(service)
    saved = backup / f"{service}.{DROPIN_NAME}"
    if dropin.exists():
        shutil.copy2(dropin, saved)
    else:
        (backup / f"{service}.dropin-was-absent").touch()


def restore_dropin(service: str, backup: Path) -> None:
    dropin = service_dropin(service)
    saved = backup / f"{service}.{DROPIN_NAME}"
    if saved.exists():
        dropin.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, dropin)
    else:
        dropin.unlink(missing_ok=True)


def write_dropin(service: str, reference: Path) -> None:
    dropin = service_dropin(service)
    dropin.parent.mkdir(parents=True, exist_ok=True)
    temp = dropin.with_suffix(dropin.suffix + ".tmp")
    escaped = str(reference).replace("\\", "\\\\").replace('"', '\\"')
    temp.write_text(f'[Service]\nEnvironment="CHATTERBOX_REFERENCE_WAV={escaped}"\n')
    os.replace(temp, dropin)


def wait_for_reference(url: str, reference: Path, timeout: float = 90) -> str:
    expected = str(reference)
    deadline = time.time() + timeout
    observed = ""
    while time.time() < deadline:
        observed = backend_reference(url)
        if observed == expected:
            return observed
        time.sleep(1)
    return observed


@app.get("/")
def index():
    return render_template("chatterbox_voice_app.html", voices=voices(), current_default=effective_default())


@app.get("/api/status")
def status():
    return jsonify({
        "ok": True,
        "voices": voices(),
        "current_default": effective_default(),
        "backends": backend_status(),
    })


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
        subprocess.run(["systemctl", "--user", "start", CPU_SERVICE], check=False)
        response = requests.post(f"{CPU_URL}/v1/audio/speech", headers={"Authorization": f"Bearer {API_KEY}"}, json={"input": text, "model": "chatterbox-nano", "reference_audio": str(path / "reference.wav")}, timeout=300)
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
    if str(reference) in all_default_references():
        return jsonify({"error": "This voice is a configured default on at least one Chatterbox backend. Select another default before deleting it."}), 409
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

    targets = managed_backends()
    if not targets:
        return jsonify({"error": "No Chatterbox backend services are configured"}), 500

    stamp = time.strftime("%Y%m%dT%H%M%S%z")
    backup = BACKUP_ROOT / stamp
    backup.mkdir(parents=True)
    previous = effective_default()
    active_before = {service: service_active(service) for service, _ in targets}

    for service, _ in targets:
        backup_dropin(service, backup)
        write_dropin(service, reference)

    try:
        run(["systemctl", "--user", "daemon-reload"], timeout=30)
        for service, url in targets:
            run(["systemctl", "--user", "restart", service], timeout=60)
            observed = wait_for_reference(url, reference)
            if observed != str(reference):
                raise RuntimeError(f"{service} did not load requested reference (reported {observed!r})")
            if not active_before[service]:
                subprocess.run(["systemctl", "--user", "stop", service], check=False)
    except Exception as exc:
        for service, _ in targets:
            restore_dropin(service, backup)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        for service, _ in targets:
            action = "restart" if active_before[service] else "stop"
            subprocess.run(["systemctl", "--user", action, service], check=False)
        return jsonify({"error": f"Default switch rolled back: {exc}"}), 500

    return jsonify({
        "ok": True,
        "name": metadata(path)["name"],
        "reference_path": str(reference),
        "previous_default": previous,
        "updated_services": [service for service, _ in targets],
        "rollback": str(backup),
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("CHATTERBOX_VOICE_APP_PORT", "8030")), threaded=True)
