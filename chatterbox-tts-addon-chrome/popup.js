const textInput = document.getElementById('textInput');
const speakBtn = document.getElementById('speakBtn');
const stopBtn = document.getElementById('stopBtn');
const status = document.getElementById('status');
const audioPlayer = document.getElementById('audioPlayer');
const audioControls = document.getElementById('audioControls');
const downloadBtn = document.getElementById('downloadBtn');
const replayBtn = document.getElementById('replayBtn');
const startBufferSelect = document.getElementById('startBuffer');
const deviceSelect = document.getElementById('deviceSelect');
let startBuffer = 2;
let device = 'auto';
let queue = [];
let allBlobs = [];
let currentUrl = null;
let playing = false;
let producerComplete = false;
let stopped = false;
let ownerToken = null;
let completionSent = false;
let keepaliveTimer = null;

document.addEventListener('DOMContentLoaded', () => {
    speakBtn.addEventListener('click', generateSpeech);
    stopBtn.addEventListener('click', () => stopSpeech(true));
    document.getElementById('getSelection').addEventListener('click', getSelectedText);
    document.getElementById('getPage').addEventListener('click', getPageText);
    document.getElementById('clearText').addEventListener('click', () => { textInput.value = ''; });
    document.getElementById('voiceLab').addEventListener('click', openVoiceLab);
    downloadBtn.addEventListener('click', downloadAudio);
    replayBtn.addEventListener('click', replayAudio);
    audioPlayer.addEventListener('ended', () => { playing = false; playNext(); });
    startBufferSelect.addEventListener('change', saveStartBuffer);
    deviceSelect.addEventListener('change', saveDevice);
    loadStartBuffer();
    loadDevice().then(checkServer);
});

function startKeepalive() {
    if (keepaliveTimer) return;
    keepaliveTimer = setInterval(() => {
        chrome.runtime.sendMessage({ action: 'keepalive' }).catch(() => {});
    }, 20000);
}

function stopKeepalive() {
    clearInterval(keepaliveTimer);
    keepaliveTimer = null;
}

function validStartBuffer(value) {
    const parsed = Number.parseInt(value, 10);
    return Number.isInteger(parsed) && parsed >= 1 && parsed <= 10 ? parsed : 2;
}

async function loadStartBuffer() {
    const saved = await chrome.storage.local.get('startBuffer').catch(() => ({}));
    startBuffer = validStartBuffer(saved.startBuffer);
    startBufferSelect.value = String(startBuffer);
}

async function saveStartBuffer() {
    startBuffer = validStartBuffer(startBufferSelect.value);
    startBufferSelect.value = String(startBuffer);
    await chrome.storage.local.set({ startBuffer });
    showStatus(`Playback will start after ${startBuffer} buffered line${startBuffer === 1 ? '' : 's'}`, 'success');
}

function validDevice(value) {
    return ['auto', 'cpu', 'gpu'].includes(value) ? value : 'auto';
}

async function loadDevice() {
    const saved = await chrome.storage.local.get('device').catch(() => ({}));
    device = validDevice(saved.device);
    deviceSelect.value = device;
}

async function saveDevice() {
    device = validDevice(deviceSelect.value);
    deviceSelect.value = device;
    await chrome.storage.local.set({ device });
    const labels = { auto: 'Synthesis device set to Auto', cpu: 'Synthesis will use the CPU', gpu: 'Synthesis will use the configured GPU / accelerator' };
    showStatus(labels[device], 'success');
}

function showStatus(message, type = '') {
    status.textContent = message;
    status.className = `status ${type}`;
    status.style.display = 'block';
}

function setActive(active) {
    speakBtn.style.display = active ? 'none' : 'flex';
    stopBtn.style.display = active ? 'flex' : 'none';
    if (active) startKeepalive();
    else stopKeepalive();
}

function clearPlayer() {
    if (currentUrl) URL.revokeObjectURL(currentUrl);
    currentUrl = null;
    audioPlayer.pause();
    audioPlayer.removeAttribute('src');
    playing = false;
}

function reset() {
    clearPlayer();
    queue = [];
    allBlobs = [];
    producerComplete = false;
    stopped = false;
    ownerToken = null;
    completionSent = false;
    audioControls.style.display = 'none';
    replayBtn.style.display = 'none';
}

async function stopSpeech(cancelBackend = true) {
    stopped = true;
    queue = [];
    clearPlayer();
    setActive(false);
    if (cancelBackend) await chrome.runtime.sendMessage({ action: 'stopTTS' }).catch(() => {});
    showStatus('Speech stopped', 'success');
}

function finishPlayback() {
    setActive(false);
    replayBtn.style.display = allBlobs.length ? 'flex' : 'none';
    showStatus('Speech completed', 'success');
    if (!completionSent && ownerToken) {
        completionSent = true;
        chrome.runtime.sendMessage({ action: 'ttsPlaybackComplete', ownerToken }).catch(() => {});
    }
}

function playNext() {
    if (stopped || playing) return;
    if (queue.length) {
        const blob = queue.shift();
        if (currentUrl) URL.revokeObjectURL(currentUrl);
        currentUrl = URL.createObjectURL(blob);
        audioPlayer.src = currentUrl;
        audioPlayer.style.display = 'block';
        audioControls.style.display = 'block';
        playing = true;
        audioPlayer.play().catch(error => showStatus(error.message, 'error'));
        return;
    }
    if (producerComplete) finishPlayback();
    else showStatus('Waiting for the next Chatterbox line…', 'loading');
}

async function dataUrlToBlob(url) { return (await fetch(url)).blob(); }

async function generateSpeech() {
    if (!textInput.value.trim()) return showStatus('Enter some text first', 'error');
    await chrome.runtime.sendMessage({ action: 'stopTTS' }).catch(() => {});
    reset();
    setActive(true);
    ownerToken = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    showStatus('Generating Chatterbox speech…', 'loading');
    const result = await chrome.runtime.sendMessage({ action: 'generateTTS', text: textInput.value, clientToken: ownerToken, device }).catch(error => ({ success: false, error: error.message }));
    if (!result || !result.success) {
        setActive(false);
        showStatus((result && result.error) || 'Could not start speech', 'error');
    }
}

function replayAudio() {
    if (!allBlobs.length) return showStatus('No audio to replay', 'error');
    clearPlayer();
    queue = allBlobs.slice();
    stopped = false;
    producerComplete = true;
    completionSent = true;
    setActive(true);
    replayBtn.style.display = 'none';
    showStatus('Replaying generated speech…', 'loading');
    playNext();
}

function parsePcmWav(buffer) {
    const view = new DataView(buffer);
    const text = (offset, length) => String.fromCharCode(...new Uint8Array(buffer, offset, length));
    if (text(0, 4) !== 'RIFF' || text(8, 4) !== 'WAVE') throw new Error('Unexpected audio format');
    let offset = 12, format = null, pcm = null;
    while (offset + 8 <= view.byteLength) {
        const id = text(offset, 4);
        const size = view.getUint32(offset + 4, true);
        const start = offset + 8;
        if (id === 'fmt ') format = { encoding: view.getUint16(start, true), channels: view.getUint16(start + 2, true), sampleRate: view.getUint32(start + 4, true), bits: view.getUint16(start + 14, true) };
        else if (id === 'data') pcm = new Uint8Array(buffer, start, Math.min(size, view.byteLength - start));
        offset = start + size + (size % 2);
    }
    if (!format || !pcm || format.encoding !== 1 || format.bits !== 16) throw new Error('WAV is not 16-bit PCM');
    return { ...format, pcm };
}

async function mergeWavBlobs(blobs) {
    const parts = await Promise.all(blobs.map(async blob => parsePcmWav(await blob.arrayBuffer())));
    const first = parts[0];
    if (parts.some(part => part.channels !== first.channels || part.sampleRate !== first.sampleRate || part.bits !== first.bits)) throw new Error('Audio chunks use incompatible WAV formats');
    const dataSize = parts.reduce((sum, part) => sum + part.pcm.byteLength, 0);
    const output = new ArrayBuffer(44 + dataSize);
    const view = new DataView(output);
    const write = (offset, value) => [...value].forEach((char, index) => view.setUint8(offset + index, char.charCodeAt(0)));
    write(0, 'RIFF'); view.setUint32(4, 36 + dataSize, true); write(8, 'WAVE');
    write(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, first.channels, true); view.setUint32(24, first.sampleRate, true);
    const blockAlign = first.channels * first.bits / 8;
    view.setUint32(28, first.sampleRate * blockAlign, true); view.setUint16(32, blockAlign, true);
    view.setUint16(34, first.bits, true); write(36, 'data'); view.setUint32(40, dataSize, true);
    let offset = 44;
    for (const part of parts) { new Uint8Array(output, offset, part.pcm.byteLength).set(part.pcm); offset += part.pcm.byteLength; }
    return new Blob([output], { type: 'audio/wav' });
}

async function downloadAudio() {
    if (!allBlobs.length) return showStatus('No audio to download', 'error');
    try {
        const merged = await mergeWavBlobs(allBlobs);
        const link = document.createElement('a');
        link.href = URL.createObjectURL(merged);
        link.download = `chatterbox_tts_${new Date().toISOString().replace(/[:.]/g, '-')}.wav`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    } catch (error) { showStatus(`Could not merge WAV: ${error.message}`, 'error'); }
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.target !== 'popup' || request.ownerToken !== ownerToken) return undefined;
    if (request.action === 'showGeneratingSpeech') {
        setActive(true);
    } else if (request.action === 'queueTTSAudio') {
        dataUrlToBlob(request.audioUrl).then(blob => {
            if (request.ownerToken === ownerToken && !stopped) {
                queue.push(blob); allBlobs.push(blob); audioControls.style.display = 'block';
                if (!playing && (queue.length >= startBuffer || request.total <= startBuffer)) playNext();
            }
            sendResponse({ success: true });
        }).catch(() => sendResponse({ success: false }));
        return true;
    } else if (request.action === 'ttsProducerComplete') {
        producerComplete = true;
        if (!playing) playNext();
    } else if (request.action === 'stopTTSAudio') {
        stopped = true; queue = []; clearPlayer(); setActive(false);
    } else if (request.action === 'ttsError') {
        stopped = true; setActive(false); showStatus(request.error || 'Chatterbox generation failed', 'error');
    }
    sendResponse({ success: true });
    return undefined;
});

async function activeTab() { return (await chrome.tabs.query({ active: true, currentWindow: true }))[0]; }

function readSelection() { return window.getSelection().toString().trim(); }

function extractPageText() {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
            const parent = node.parentElement;
            return parent && ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(parent.tagName)
                ? NodeFilter.FILTER_REJECT
                : NodeFilter.FILTER_ACCEPT;
        }
    });
    let out = '';
    let node;
    while ((node = walker.nextNode())) {
        const text = node.textContent.trim();
        if (text) out += `${text}\n`;
    }
    return out.trim().substring(0, 5000);
}

async function inject(func) {
    const tab = await activeTab();
    const [injected] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func });
    return (injected && injected.result) || '';
}

async function getSelectedText() {
    try {
        textInput.value = await inject(readSelection);
        showStatus(textInput.value ? 'Selection captured' : 'No text selected', textInput.value ? 'success' : 'error');
    } catch (error) { showStatus(error.message, 'error'); }
}

async function getPageText() {
    try {
        textInput.value = await inject(extractPageText);
        showStatus(textInput.value ? 'Page text captured' : 'No page text found', textInput.value ? 'success' : 'error');
    } catch (error) { showStatus(error.message, 'error'); }
}

async function checkServer() {
    try {
        const response = await fetch('http://127.0.0.1:8010/health', { cache: 'no-store' });
        if (!response.ok) throw new Error();
        const health = await response.json();
        const accelerator = (health.synthesis_devices || []).find(item => item.id === 'gpu');
        const gpuOption = deviceSelect.querySelector('option[value="gpu"]');
        const available = Boolean(accelerator && accelerator.available);
        gpuOption.disabled = !available;
        gpuOption.textContent = available ? `GPU / accelerator · ${accelerator.label || 'available'}` : 'GPU / accelerator · unavailable';
        if (device === 'gpu' && !available) {
            device = 'auto';
            deviceSelect.value = device;
            await chrome.storage.local.set({ device });
            showStatus('GPU / accelerator is unavailable; switched to Auto (CPU)', 'success');
            return;
        }
        showStatus(`Chatterbox bridge connected ✓${available ? ' · accelerator available' : ' · CPU only'}`, 'success');
    } catch (_) {
        showStatus('Chatterbox bridge is not running', 'error');
    }
}

async function openVoiceLab() {
    try { const response = await fetch('http://127.0.0.1:8030/api/status', { cache: 'no-store' }); if (!response.ok) throw new Error(); await chrome.tabs.create({ url: 'http://127.0.0.1:8030/' }); }
    catch (_) { await chrome.runtime.openOptionsPage(); }
}
