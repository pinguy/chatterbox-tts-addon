#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import sys
import wave
from pathlib import Path
from threading import Lock, Timer

import requests
from flask import Flask, Response, jsonify, request

app = Flask(__name__)
CHATTERBOX_BASE = os.environ.get('CHATTERBOX_BASE', 'http://127.0.0.1:8020')
BASE_DIR = Path(__file__).resolve().parent
WHISPER_PYTHON = os.environ.get('WHISPER_PYTHON', sys.executable).strip()
WHISPER_MODEL = os.environ.get('WHISPER_MODEL', '').strip()
WHISPER_WORKER = os.environ.get('WHISPER_WORKER', str(BASE_DIR / 'whisper_worker.py')).strip()
BRIDGE_API_KEY = os.environ.get('BRIDGE_API_KEY', 'local-dev-key')
CHATTERBOX_SERVICE = os.environ.get('CHATTERBOX_SERVICE', 'chatterbox-nano.service')
STARTUP_WAIT_SECONDS = float(os.environ.get('CHATTERBOX_STARTUP_WAIT_SECONDS', '45'))
HEALTH_POLL_INTERVAL = float(os.environ.get('CHATTERBOX_HEALTH_POLL_INTERVAL', '0.4'))
WHISPER_MODEL_IDLE_SECONDS = float(os.environ.get('WHISPER_MODEL_IDLE_SECONDS', '300'))
CHATTERBOX_CHUNK_CHARS = int(os.environ.get('CHATTERBOX_CHUNK_CHARS', '500'))
_chatterbox_start_lock = Lock()
_tts_epoch_lock = Lock()
_tts_cancel_epoch = 0
_whisper_worker_lock = Lock()
_whisper_decode_lock = Lock()
_whisper_worker: subprocess.Popen[str] | None = None
_whisper_unload_timer: Timer | None = None


def split_tts_text(text: str, limit: int = CHATTERBOX_CHUNK_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining); break
        window = remaining[: limit + 1]
        boundaries = [m.end() for m in re.finditer(r'(?<=[.!?])\s+|\n+|\s+', window)]
        cut = max((pos for pos in boundaries if pos <= limit), default=limit)
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return [chunk for chunk in chunks if chunk]


def normalize_tts_chunk(text: str) -> str:
    text = re.sub(r'^["“”]+\s*', '', text.strip())
    return re.sub(r'\s*["“”]+$', '', text).strip()


def join_wav_parts(parts: list[bytes]) -> bytes:
    output = io.BytesIO(); expected = None; frames: list[bytes] = []
    for part in parts:
        with wave.open(io.BytesIO(part), 'rb') as source:
            params = (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype())
            if expected is None: expected = params
            elif params != expected: raise ValueError(f'incompatible WAV part: {params} != {expected}')
            frames.append(source.readframes(source.getnframes()))
    if expected is None: raise ValueError('no WAV parts to join')
    channels, sample_width, frame_rate, compression = expected
    with wave.open(output, 'wb') as target:
        target.setnchannels(channels); target.setsampwidth(sample_width); target.setframerate(frame_rate); target.setcomptype(compression, 'not compressed')
        for frame_block in frames: target.writeframesraw(frame_block)
    return output.getvalue()


def check_auth():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '): return False, jsonify({'error': 'missing bearer token'}), 401
    if auth.split(' ', 1)[1].strip() != BRIDGE_API_KEY: return False, jsonify({'error': 'invalid api key'}), 401
    return True, None, 200


def wait_for_chatterbox(timeout_s: float = STARTUP_WAIT_SECONDS) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if requests.get(f'{CHATTERBOX_BASE}/health', timeout=1.5).ok: return True
        except Exception: pass
        time.sleep(HEALTH_POLL_INTERVAL)
    return False


def cancel_active_tts() -> int:
    global _tts_cancel_epoch
    with _tts_epoch_lock:
        _tts_cancel_epoch += 1
        return _tts_cancel_epoch


def tts_cancelled(epoch: int) -> bool:
    with _tts_epoch_lock: return _tts_cancel_epoch != epoch


def ensure_chatterbox_running() -> bool:
    with _chatterbox_start_lock:
        if wait_for_chatterbox(1.0): return True
        subprocess.run(['systemctl', '--user', 'start', CHATTERBOX_SERVICE], check=False, capture_output=True, text=True)
        return wait_for_chatterbox()


def executable_available(command: str) -> bool:
    if not command: return False
    return Path(command).expanduser().is_file() if '/' in command else shutil.which(command) is not None


def whisper_configured() -> bool:
    return bool(WHISPER_MODEL and executable_available(WHISPER_PYTHON) and Path(WHISPER_WORKER).expanduser().is_file())


def get_whisper_worker() -> subprocess.Popen[str]:
    global _whisper_worker
    if not whisper_configured(): raise RuntimeError('Whisper STT is not configured; set WHISPER_MODEL and WHISPER_WORKER')
    if _whisper_worker is not None and _whisper_worker.poll() is None: return _whisper_worker
    env = os.environ.copy(); env['WHISPER_MODEL'] = WHISPER_MODEL; env.setdefault('WHISPER_COMPUTE_TYPE', 'int8'); env.setdefault('WHISPER_CPU_THREADS', '16')
    _whisper_worker = subprocess.Popen([WHISPER_PYTHON, str(Path(WHISPER_WORKER).expanduser())], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
    ready = _whisper_worker.stdout.readline() if _whisper_worker.stdout else ''
    if not ready or not json.loads(ready).get('ready'):
        error = _whisper_worker.stderr.read()[-1200:] if _whisper_worker.stderr else ''
        raise RuntimeError(f'Whisper worker failed to become ready: {error}')
    return _whisper_worker


def unload_whisper_model_if_idle() -> None:
    global _whisper_worker, _whisper_unload_timer
    with _whisper_worker_lock:
        worker, _whisper_worker = _whisper_worker, None; _whisper_unload_timer = None
        if worker is not None and worker.poll() is None:
            worker.terminate()
            try: worker.wait(timeout=10)
            except subprocess.TimeoutExpired: worker.kill(); worker.wait(timeout=5)


def schedule_whisper_unload() -> None:
    global _whisper_unload_timer
    if WHISPER_MODEL_IDLE_SECONDS <= 0: return
    with _whisper_worker_lock:
        if _whisper_unload_timer is not None: _whisper_unload_timer.cancel()
        _whisper_unload_timer = Timer(WHISPER_MODEL_IDLE_SECONDS, unload_whisper_model_if_idle); _whisper_unload_timer.daemon = True; _whisper_unload_timer.start()


def transcribe_whisper_audio(audio_path: Path) -> str:
    worker = get_whisper_worker()
    if worker.stdin is None or worker.stdout is None: raise RuntimeError('Whisper worker pipes unavailable')
    worker.stdin.write(json.dumps({'audio_path': str(audio_path)}) + '\n'); worker.stdin.flush()
    response = json.loads(worker.stdout.readline())
    if 'error' in response: raise RuntimeError(response['error'])
    return response.get('text', '').strip()


@app.get('/health')
def health():
    chatterbox_ok = False; chatterbox_idle = None; chatterbox_idle_limit = None
    try:
        r = requests.get(f'{CHATTERBOX_BASE}/health', timeout=3); chatterbox_ok = r.ok
        if r.ok:
            detail = r.json(); chatterbox_idle = detail.get('idle_seconds'); chatterbox_idle_limit = detail.get('idle_shutdown_seconds')
    except Exception: pass
    return jsonify({'ok': True, 'tts_backend': 'chatterbox-nano', 'chatterbox_ok': chatterbox_ok, 'chatterbox_loaded': chatterbox_ok, 'chatterbox_idle_seconds': chatterbox_idle, 'chatterbox_idle_unload_seconds': chatterbox_idle_limit, 'default_stt_backend': 'whisper' if whisper_configured() else None, 'whisper_configured': whisper_configured(), 'whisper_model': WHISPER_MODEL, 'whisper_model_loaded': _whisper_worker is not None and _whisper_worker.poll() is None, 'whisper_model_idle_unload_seconds': WHISPER_MODEL_IDLE_SECONDS})


@app.get('/models')
@app.get('/v1/models')
def list_models():
    now = int(time.time())
    return jsonify({'object': 'list', 'data': ([{'id': 'whisper', 'object': 'model', 'created': now, 'owned_by': 'local'}] if whisper_configured() else [])})


@app.post('/audio/speech')
@app.post('/v1/audio/speech')
def tts_speech():
    ok, err, status = check_auth()
    if not ok: return err, status
    body = request.get_json(silent=True) or {}; text = body.get('input') or body.get('text') or ''
    if not text.strip(): return jsonify({'error': "'input' text is required"}), 400
    if not ensure_chatterbox_running(): return jsonify({'error': 'chatterbox not ready after startup wait'}), 502
    with _tts_epoch_lock: epoch = _tts_cancel_epoch
    audio_parts: list[bytes] = []
    for raw_chunk in split_tts_text(text):
        chunk = normalize_tts_chunk(raw_chunk)
        if not chunk: continue
        if tts_cancelled(epoch): return jsonify({'error': 'cancelled'}), 409
        payload = {'input': chunk, 'model': 'chatterbox-nano', 'voice': 'rhizome'}
        try:
            r = requests.post(f'{CHATTERBOX_BASE}/v1/audio/speech', json=payload, headers={'Authorization': f'Bearer {BRIDGE_API_KEY}'}, timeout=300); r.raise_for_status()
        except Exception:
            if not ensure_chatterbox_running(): return jsonify({'error': 'chatterbox request failed and service is still not healthy'}), 502
            try:
                r = requests.post(f'{CHATTERBOX_BASE}/v1/audio/speech', json=payload, headers={'Authorization': f'Bearer {BRIDGE_API_KEY}'}, timeout=300); r.raise_for_status()
            except Exception as exc:
                detail = r.text[:300] if 'r' in locals() else ''
                return jsonify({'error': f'chatterbox request failed: {exc}', 'detail': detail}), 502
        audio_parts.append(r.content)
    try: audio = audio_parts[0] if len(audio_parts) == 1 else join_wav_parts(audio_parts)
    except Exception as exc: return jsonify({'error': f'failed to join chatterbox audio: {exc}'}), 502
    return Response(audio, mimetype='audio/wav')


@app.post('/audio/stop')
@app.post('/v1/audio/stop')
def tts_stop():
    ok, err, status = check_auth()
    if not ok: return err, status
    return jsonify({'ok': True, 'cancelled': True, 'epoch': cancel_active_tts(), 'chatterbox_stopped': False})


@app.post('/audio/transcriptions')
@app.post('/v1/audio/transcriptions')
def stt_transcribe():
    ok, err, status = check_auth()
    if not ok: return err, status
    f = request.files.get('file')
    if not f: return jsonify({'error': "multipart field 'file' is required"}), 400
    if not whisper_configured(): return jsonify({'error': 'Whisper STT is not configured on this installation'}), 501
    with tempfile.TemporaryDirectory(prefix='whisper_stt_') as td:
        src = Path(td) / (f.filename or 'input_audio'); src.write_bytes(f.read()); started = time.monotonic()
        try:
            with _whisper_decode_lock:
                text = transcribe_whisper_audio(src); schedule_whisper_unload()
        except Exception as e: return jsonify({'error': f'whisper transcription failed: {e}'}), 500
    return jsonify({'text': text, 'backend': 'whisper', 'duration_seconds': round(time.monotonic() - started, 3), 'whisper_model_loaded': _whisper_worker is not None and _whisper_worker.poll() is None})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8010)
