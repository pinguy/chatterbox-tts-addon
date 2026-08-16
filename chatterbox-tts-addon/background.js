const TTS_URL = 'http://127.0.0.1:8010/v1/audio/speech';
const STOP_URL = 'http://127.0.0.1:8010/v1/audio/stop';
const TTS_KEY = 'local-dev-key';

// The browser has one active playback/generation owner at a time. CPU and
// accelerator backends may be separate processes, but browser jobs still replace
// one another cleanly instead of competing for playback.
let activeJob = null;

function createContextMenuItems() {
    browser.contextMenus.removeAll().then(() => {
        browser.contextMenus.create({ id: 'chatterbox-tts-speak', title: 'Speak selected text with Chatterbox', contexts: ['selection'] });
        browser.contextMenus.create({ id: 'chatterbox-tts-page', title: 'Speak entire page with Chatterbox', contexts: ['page'] });
    });
}

browser.runtime.onInstalled.addListener((details) => {
    createContextMenuItems();
    if (details.reason === 'install') browser.tabs.create({ url: browser.runtime.getURL('welcome.html') });
});
browser.runtime.onStartup.addListener(createContextMenuItems);
createContextMenuItems();

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

async function cancelBackendSpeech() {
    try {
        await fetch(STOP_URL, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${TTS_KEY}` }
        });
    } catch (_) {}
}

async function sendToOwner(job, message) {
    const payload = { ...message, ownerToken: job.token };
    try {
        if (job.owner.kind === 'tab') return await browser.tabs.sendMessage(job.owner.tabId, payload);
        return await browser.runtime.sendMessage({ ...payload, target: 'popup' });
    } catch (_) {
        return null;
    }
}

async function stopActive(killModel = true) {
    const job = activeJob;
    if (job) {
        activeJob = null;
        job.controller.abort();
        await sendToOwner(job, { action: 'stopTTSAudio' });
    }
    if (killModel) await cancelBackendSpeech();
}

async function produce(job, lines) {
    try {
        for (let index = 0; index < lines.length; index += 1) {
            if (activeJob !== job) return;
            const response = await fetch(TTS_URL, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${TTS_KEY}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: 'tts-1', voice: 'rhizome', input: lines[index], device: job.device }),
                signal: job.controller.signal
            });
            if (!response.ok) throw new Error(`Chatterbox server error ${response.status}: ${(await response.text()).slice(0, 180)}`);
            const wav = new Uint8Array(await response.arrayBuffer());
            if (activeJob !== job) return;
            const delivered = await sendToOwner(job, {
                action: 'queueTTSAudio',
                index,
                total: lines.length,
                audioUrl: `data:audio/wav;base64,${bytesToBase64(wav)}`
            });
            if (delivered === null && activeJob === job) {
                activeJob = null;
                job.controller.abort();
                await cancelBackendSpeech();
                return;
            }
        }
        if (activeJob === job) {
            job.producerComplete = true;
            await sendToOwner(job, { action: 'ttsProducerComplete' });
        }
    } catch (error) {
        if (activeJob !== job) return;
        activeJob = null;
        if (error.name !== 'AbortError') {
            await sendToOwner(job, { action: 'ttsError', error: error.message });
            await cancelBackendSpeech();
        }
    }
}

function validDevice(value) {
    return ['auto', 'cpu', 'gpu'].includes(value) ? value : 'auto';
}

async function storedDevice() {
    // Every entry point (context menu, in-page button, popup) honours the same
    // saved choice. Auto lets the bridge pick an accelerator when one exists.
    const saved = await browser.storage.local.get('device').catch(() => ({}));
    return validDevice(saved.device);
}

async function startSpeech(text, owner, clientToken, device) {
    const lines = splitLines(text || '');
    if (!lines.length) return { success: false, error: 'No text to speak' };
    await stopActive(Boolean(activeJob));
    const resolvedDevice = validDevice(device || await storedDevice());
    const job = {
        controller: new AbortController(),
        owner,
        token: clientToken || newToken(),
        device: resolvedDevice,
        producerComplete: false
    };
    activeJob = job;
    const delivered = await sendToOwner(job, { action: 'showGeneratingSpeech', total: lines.length });
    if (delivered === null) {
        activeJob = null;
        return { success: false, error: 'The Chatterbox playback owner is unavailable' };
    }
    produce(job, lines);
    return { success: true, ownerToken: job.token };
}

browser.contextMenus.onClicked.addListener(async (info, tab) => {
    if (info.menuItemId === 'chatterbox-tts-speak') {
        return startSpeech(info.selectionText, { kind: 'tab', tabId: tab.id });
    }
    if (info.menuItemId === 'chatterbox-tts-page') {
        const results = await browser.tabs.executeScript(tab.id, { code: `(function(){const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{acceptNode(n){const p=n.parentElement;return p&&['SCRIPT','STYLE','NOSCRIPT'].includes(p.tagName)?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT}});let out='',n;while(n=w.nextNode()){const t=n.textContent.trim();if(t)out+=t+'\n'}return out.trim().substring(0,5000)})()` });
        if (results && results[0]) return startSpeech(results[0], { kind: 'tab', tabId: tab.id });
    }
});

browser.runtime.onMessage.addListener((request, sender) => {
    if (request.target === 'popup') return undefined;
    const tabId = sender.tab && sender.tab.id;
    if (request.action === 'generateTTS') {
        const owner = tabId ? { kind: 'tab', tabId } : { kind: 'popup' };
        return startSpeech(request.text, owner, request.clientToken, request.device);
    }
    if (request.action === 'stopTTS') {
        return stopActive(true).then(() => ({ success: true }));
    }
    if (request.action === 'ttsPlaybackComplete' && activeJob && request.ownerToken === activeJob.token) {
        activeJob = null;
        return Promise.resolve({ success: true });
    }
    return undefined;
});
