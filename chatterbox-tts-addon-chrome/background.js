'use strict';

const TTS_URL = 'http://127.0.0.1:8010/v1/audio/speech';
const STOP_URL = 'http://127.0.0.1:8010/v1/audio/stop';
const TTS_KEY = 'local-dev-key';
const OFFSCREEN_URL = 'offscreen.html';

// Chatterbox is one shared local model, so the extension has one owner at a
// time. Keeping ownership here prevents tabs and the popup from fighting over
// the same backend.
let activeJob = null;
let offscreenLock = null;

function createContextMenuItems() {
    chrome.contextMenus.removeAll(() => {
        chrome.contextMenus.create({ id: 'chatterbox-tts-speak', title: 'Speak selected text with Chatterbox', contexts: ['selection'] });
        chrome.contextMenus.create({ id: 'chatterbox-tts-page', title: 'Speak entire page with Chatterbox', contexts: ['page'] });
    });
}

chrome.runtime.onInstalled.addListener((details) => {
    createContextMenuItems();
    if (details.reason === 'install') chrome.tabs.create({ url: chrome.runtime.getURL('welcome.html') });
});
chrome.runtime.onStartup.addListener(createContextMenuItems);

function splitLines(text) {
    return text.split(/\r?\n+/).map(line => line.trim()).filter(Boolean);
}

function bytesToBase64(bytes) {
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return btoa(binary);
}

function newToken() {
    return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

// The bridge cancels queued synthesis; it deliberately leaves the model warm so
// the next utterance does not pay a cold reload. Idle unload is the server's job.
async function cancelBackendSpeech() {
    try {
        await fetch(STOP_URL, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${TTS_KEY}` }
        });
    } catch (_) {}
}

async function offscreenExists() {
    const contexts = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
    return contexts.length > 0;
}

// Chrome blocks autoplay in a content-script iframe, so tab playback runs in an
// offscreen document created for AUDIO_PLAYBACK. The popup keeps playing in its
// own window, where the user's click is a real gesture.
async function ensureOffscreen() {
    while (offscreenLock) await offscreenLock.catch(() => {});
    if (await offscreenExists()) return;
    offscreenLock = chrome.offscreen.createDocument({
        url: OFFSCREEN_URL,
        reasons: ['AUDIO_PLAYBACK'],
        justification: 'Play locally generated Chatterbox speech without a visible tab.'
    });
    try {
        await offscreenLock;
    } catch (error) {
        // A parallel caller can win the race; anything else is a real failure.
        if (!String(error && error.message).includes('single offscreen')) throw error;
    } finally {
        offscreenLock = null;
    }
}

async function closeOffscreen() {
    // Popup ownership detection relies on sendMessage rejecting when the popup
    // is gone. A lingering offscreen document would answer instead and mask it.
    try {
        if (await offscreenExists()) await chrome.offscreen.closeDocument();
    } catch (_) {}
}

function validStartBuffer(value) {
    const parsed = Number.parseInt(value, 10);
    return Number.isInteger(parsed) && parsed >= 1 && parsed <= 10 ? parsed : 2;
}

// The offscreen document cannot read chrome.storage itself, so the current
// buffer setting rides along with every message it receives.
async function currentStartBuffer() {
    try {
        const saved = await chrome.storage.local.get('startBuffer');
        return validStartBuffer(saved.startBuffer);
    } catch (_) {
        return 2;
    }
}

async function sendToOffscreen(message) {
    await ensureOffscreen();
    const startBuffer = await currentStartBuffer();
    // createDocument can resolve marginally before the document's script has
    // registered its listener, so one retry covers the startup race.
    for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
            return await chrome.runtime.sendMessage({ ...message, target: 'offscreen', startBuffer });
        } catch (error) {
            if (attempt === 1) return null;
            await new Promise(resolve => setTimeout(resolve, 150));
        }
    }
    return null;
}

// UI channel: the content script for tab jobs, the popup window otherwise.
// A rejection here means the owner is gone and the job should be abandoned.
async function sendToOwner(job, message) {
    const payload = { ...message, ownerToken: job.token };
    try {
        if (job.owner.kind === 'tab') return await chrome.tabs.sendMessage(job.owner.tabId, payload);
        return await chrome.runtime.sendMessage({ ...payload, target: 'popup' });
    } catch (_) {
        return null;
    }
}

async function deliverAudio(job, message) {
    if (job.owner.kind === 'tab') return sendToOffscreen({ ...message, ownerToken: job.token });
    return sendToOwner(job, message);
}

async function stopActive(cancelBackend = true) {
    const job = activeJob;
    if (job) {
        activeJob = null;
        job.controller.abort();
        if (job.owner.kind === 'tab') await sendToOffscreen({ action: 'stopAudio' });
        await sendToOwner(job, { action: 'stopTTSAudio' });
    }
    if (cancelBackend) await cancelBackendSpeech();
    await closeOffscreen();
}

async function produce(job, lines) {
    try {
        for (let index = 0; index < lines.length; index += 1) {
            if (activeJob !== job) return;
            const response = await fetch(TTS_URL, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${TTS_KEY}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: 'tts-1', voice: 'rhizome', input: lines[index] }),
                signal: job.controller.signal
            });
            if (!response.ok) throw new Error(`Chatterbox server error ${response.status}: ${(await response.text()).slice(0, 180)}`);
            const wav = new Uint8Array(await response.arrayBuffer());
            if (activeJob !== job) return;
            const audioUrl = `data:audio/wav;base64,${bytesToBase64(wav)}`;
            await deliverAudio(job, { action: 'queueTTSAudio', index, total: lines.length, audioUrl });

            // Liveness is judged on the UI channel: offscreen audio always
            // accepts delivery, so it cannot tell us the tab has gone away.
            const alive = await sendToOwner(job, { action: 'ttsProgress', index, total: lines.length });
            if (alive === null && activeJob === job) {
                activeJob = null;
                job.controller.abort();
                await cancelBackendSpeech();
                await closeOffscreen();
                return;
            }
        }
        if (activeJob === job) {
            job.producerComplete = true;
            if (job.owner.kind === 'tab') await sendToOffscreen({ action: 'producerComplete', ownerToken: job.token });
            await sendToOwner(job, { action: 'ttsProducerComplete' });
        }
    } catch (error) {
        if (activeJob !== job) return;
        activeJob = null;
        if (error.name !== 'AbortError') {
            await sendToOwner(job, { action: 'ttsError', error: error.message });
            await cancelBackendSpeech();
        }
        await closeOffscreen();
    }
}

async function startSpeech(text, owner, clientToken) {
    const lines = splitLines(text || '');
    if (!lines.length) return { success: false, error: 'No text to speak' };
    await stopActive(Boolean(activeJob));
    const job = {
        controller: new AbortController(),
        owner,
        token: clientToken || newToken(),
        producerComplete: false
    };
    activeJob = job;
    if (owner.kind === 'tab') await sendToOffscreen({ action: 'reset', ownerToken: job.token });
    const delivered = await sendToOwner(job, { action: 'showGeneratingSpeech', total: lines.length });
    if (delivered === null) {
        activeJob = null;
        await closeOffscreen();
        return { success: false, error: 'The Chatterbox playback owner is unavailable' };
    }
    produce(job, lines);
    return { success: true, ownerToken: job.token };
}

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

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
    if (!tab || tab.id === undefined) return;
    if (info.menuItemId === 'chatterbox-tts-speak') {
        await startSpeech(info.selectionText, { kind: 'tab', tabId: tab.id });
        return;
    }
    if (info.menuItemId === 'chatterbox-tts-page') {
        try {
            const [injected] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: extractPageText });
            if (injected && injected.result) await startSpeech(injected.result, { kind: 'tab', tabId: tab.id });
        } catch (_) {}
    }
});

// Chrome cannot resolve a promise returned from onMessage the way Firefox does,
// so every asynchronous branch answers through sendResponse and returns true.
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.target === 'popup' || request.target === 'offscreen') return undefined;
    const tabId = sender.tab && sender.tab.id;

    if (request.action === 'generateTTS') {
        const owner = tabId !== undefined ? { kind: 'tab', tabId } : { kind: 'popup' };
        startSpeech(request.text, owner, request.clientToken).then(sendResponse);
        return true;
    }
    if (request.action === 'stopTTS') {
        stopActive(true).then(() => sendResponse({ success: true }));
        return true;
    }
    if (request.action === 'keepalive') {
        // Owners ping while a job runs so the service worker is not shut down
        // between chunks of a long synthesis.
        sendResponse({ active: Boolean(activeJob) });
        return undefined;
    }
    if (request.action === 'ttsPlaybackComplete' && activeJob && request.ownerToken === activeJob.token) {
        const job = activeJob;
        activeJob = null;
        closeOffscreen().then(() => sendResponse({ success: true }));
        if (job.owner.kind === 'tab') sendToOwner(job, { action: 'ttsUiComplete' });
        return true;
    }
    if (request.action === 'offscreenPlaybackError' && activeJob && request.ownerToken === activeJob.token) {
        const job = activeJob;
        activeJob = null;
        job.controller.abort();
        sendToOwner(job, { action: 'ttsError', error: request.error || 'Playback failed' });
        closeOffscreen();
        return undefined;
    }
    return undefined;
});
