(function () {
    'use strict';
    let startBuffer = 2;
    let selectedText = '';
    let playerFrame, speakButton, stopButton, noticeTimer;
    let queue = [];
    let playing = false;
    let producerComplete = false;
    let stopped = false;
    let ownerToken = null;
    let completionSent = false;

    function validStartBuffer(value) {
        const parsed = Number.parseInt(value, 10);
        return Number.isInteger(parsed) && parsed >= 1 && parsed <= 10 ? parsed : 2;
    }

    browser.storage.local.get('startBuffer').then(saved => {
        startBuffer = validStartBuffer(saved.startBuffer);
    }).catch(() => {});
    browser.storage.onChanged.addListener((changes, area) => {
        if (area === 'local' && changes.startBuffer) {
            startBuffer = validStartBuffer(changes.startBuffer.newValue);
        }
    });

    function ensurePlayer() {
        if (playerFrame) return;
        playerFrame = document.createElement('iframe');
        playerFrame.id = 'chatterbox-tts-player-iframe';
        playerFrame.src = browser.runtime.getURL('player.html');
        Object.assign(playerFrame.style, { display: 'none', width: '1px', height: '1px', border: '0' });
        document.documentElement.appendChild(playerFrame);
    }

    function showNotice(message, type = 'info') {
        let notice = document.getElementById('chatterbox-tts-notification');
        if (!notice) {
            notice = document.createElement('div');
            notice.id = 'chatterbox-tts-notification';
            document.documentElement.appendChild(notice);
        }
        notice.textContent = message;
        notice.dataset.type = type;
        notice.style.display = 'block';
        clearTimeout(noticeTimer);
        noticeTimer = setTimeout(() => { notice.style.display = 'none'; }, 3000);
    }

    function ensureButtons() {
        if (speakButton) return;
        speakButton = document.createElement('div');
        speakButton.id = 'chatterbox-tts-float-btn';
        speakButton.textContent = '💬';
        speakButton.title = 'Speak with Chatterbox TTS';
        speakButton.addEventListener('click', (event) => {
            event.stopPropagation();
            generateSpeech(selectedText);
            speakButton.style.display = 'none';
        });
        stopButton = document.createElement('button');
        stopButton.id = 'chatterbox-tts-stop-btn';
        stopButton.type = 'button';
        stopButton.textContent = '⏹ Stop';
        stopButton.addEventListener('click', (event) => { event.stopPropagation(); stopSpeech(); });
        document.documentElement.append(speakButton, stopButton);
    }

    function setActive(active) {
        ensureButtons();
        stopButton.style.display = active ? 'flex' : 'none';
    }

    function resetQueue() {
        queue = [];
        playing = false;
        producerComplete = false;
        stopped = false;
        completionSent = false;
    }

    async function stopSpeech(notify = true) {
        stopped = true;
        queue = [];
        playing = false;
        ensurePlayer();
        playerFrame.contentWindow.postMessage({ action: 'stopAudio' }, '*');
        await browser.runtime.sendMessage({ action: 'stopTTS' }).catch(() => {});
        setActive(false);
        if (notify) showNotice('Speech stopped and Chatterbox unloaded', 'info');
    }

    function playNext() {
        if (stopped || playing) return;
        if (queue.length) {
            playing = true;
            playerFrame.contentWindow.postMessage({ action: 'playAudio', audioUrl: queue.shift() }, '*');
            return;
        }
        if (producerComplete) {
            setActive(false);
            showNotice('Speech completed', 'success');
            if (!completionSent && ownerToken) {
                completionSent = true;
                browser.runtime.sendMessage({ action: 'ttsPlaybackComplete', ownerToken }).catch(() => {});
            }
            return;
        }
        showNotice('Waiting for the next Chatterbox line…', 'loading');
    }

    async function generateSpeech(text) {
        if (!text || !text.trim()) return;
        await stopSpeech(false);
        resetQueue();
        setActive(true);
        showNotice('Generating Chatterbox speech…', 'loading');
        const result = await browser.runtime.sendMessage({ action: 'generateTTS', text: text.trim() });
        if (result && result.ownerToken) ownerToken = result.ownerToken;
        if (result && result.error && !result.stopped) {
            setActive(false);
            showNotice(result.error, 'error');
        }
    }

    document.addEventListener('mouseup', () => {
        setTimeout(() => {
            selectedText = window.getSelection().toString().trim();
            ensureButtons();
            speakButton.style.display = selectedText ? 'flex' : 'none';
        }, 100);
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') stopSpeech();
        else if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 's') {
            event.preventDefault();
            generateSpeech(window.getSelection().toString());
        }
    });

    window.addEventListener('message', (event) => {
        if (event.source !== (playerFrame && playerFrame.contentWindow) || !event.data) return;
        if (event.data.action === 'chatterboxPlaybackEnded') {
            playing = false;
            playNext();
        } else if (event.data.action === 'chatterboxPlaybackError') {
            stopSpeech(false);
            showNotice(event.data.error || 'Playback failed', 'error');
        }
    });

    browser.runtime.onMessage.addListener((request) => {
        if (request.target === 'popup') return undefined;
        ensurePlayer();
        if (request.action === 'showGeneratingSpeech') {
            resetQueue();
            ownerToken = request.ownerToken;
            setActive(true);
        } else if (request.action === 'queueTTSAudio') {
            queue.push(request.audioUrl);
            if (!playing && (queue.length >= startBuffer || request.total <= startBuffer)) playNext();
        } else if (request.action === 'ttsProducerComplete') {
            producerComplete = true;
            if (!playing) playNext();
        } else if (request.action === 'stopTTSAudio') {
            stopped = true;
            queue = [];
            playing = false;
            playerFrame.contentWindow.postMessage({ action: 'stopAudio' }, '*');
            setActive(false);
        } else if (request.action === 'ttsError') {
            stopSpeech(false);
            showNotice(request.error || 'Chatterbox generation failed', 'error');
        }
        return Promise.resolve({ success: true });
    });

    ensurePlayer();
    ensureButtons();
})();
