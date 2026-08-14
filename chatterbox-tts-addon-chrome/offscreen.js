'use strict';

// Playback consumer for tab-owned jobs. The queue and the startup buffer live
// here rather than in the content script, because this document is what
// actually holds the Audio element.
//
// An offscreen document may only use chrome.runtime — chrome.storage is
// undefined here, and touching it throws before any listener is registered.
// The service worker therefore reads the setting and sends it with each job.
let startBuffer = 2;
let queue = [];
let currentAudio = null;
let playing = false;
let producerComplete = false;
let stopped = false;
let ownerToken = null;
let completionSent = false;

function validStartBuffer(value) {
    const parsed = Number.parseInt(value, 10);
    return Number.isInteger(parsed) && parsed >= 1 && parsed <= 10 ? parsed : 2;
}

function stopAudio() {
    if (!currentAudio) return;
    currentAudio.pause();
    currentAudio.removeAttribute('src');
    currentAudio.load();
    currentAudio = null;
}

function reset(token) {
    stopAudio();
    queue = [];
    playing = false;
    producerComplete = false;
    stopped = false;
    completionSent = false;
    ownerToken = token || null;
}

function playNext() {
    if (stopped || playing) return;
    if (queue.length) {
        playing = true;
        stopAudio();
        currentAudio = new Audio(queue.shift());
        currentAudio.addEventListener('ended', () => {
            currentAudio = null;
            playing = false;
            playNext();
        }, { once: true });
        currentAudio.play().catch(error => {
            playing = false;
            chrome.runtime.sendMessage({ action: 'offscreenPlaybackError', ownerToken, error: error.message }).catch(() => {});
        });
        return;
    }
    if (producerComplete && !completionSent && ownerToken) {
        completionSent = true;
        chrome.runtime.sendMessage({ action: 'ttsPlaybackComplete', ownerToken }).catch(() => {});
    }
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.target !== 'offscreen') return undefined;
    if (request.startBuffer !== undefined) startBuffer = validStartBuffer(request.startBuffer);
    if (request.action === 'reset') {
        reset(request.ownerToken);
    } else if (request.action === 'queueTTSAudio') {
        if (request.ownerToken !== ownerToken || stopped) return sendResponse({ success: false });
        queue.push(request.audioUrl);
        if (!playing && (queue.length >= startBuffer || request.total <= startBuffer)) playNext();
    } else if (request.action === 'producerComplete') {
        producerComplete = true;
        if (!playing) playNext();
    } else if (request.action === 'stopAudio') {
        stopped = true;
        queue = [];
        playing = false;
        stopAudio();
    }
    sendResponse({ success: true });
    return undefined;
});
