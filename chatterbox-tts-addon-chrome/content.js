(function () {
    'use strict';
    let selectedText = '';
    let speakButton, stopButton, noticeTimer, keepaliveTimer;
    let ownerToken = null;

    function startKeepalive() {
        // An MV3 service worker is shut down when idle. A long synthesis is
        // mostly waiting on fetch, so the owner pings to keep the job alive.
        if (keepaliveTimer) return;
        keepaliveTimer = setInterval(() => {
            chrome.runtime.sendMessage({ action: 'keepalive' }).catch(() => {});
        }, 20000);
    }

    function stopKeepalive() {
        clearInterval(keepaliveTimer);
        keepaliveTimer = null;
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
        if (active) startKeepalive();
        else stopKeepalive();
    }

    async function stopSpeech(notify = true) {
        setActive(false);
        ownerToken = null;
        await chrome.runtime.sendMessage({ action: 'stopTTS' }).catch(() => {});
        if (notify) showNotice('Speech stopped', 'info');
    }

    async function generateSpeech(text) {
        if (!text || !text.trim()) return;
        setActive(true);
        showNotice('Generating Chatterbox speech…', 'loading');
        const result = await chrome.runtime.sendMessage({ action: 'generateTTS', text: text.trim() }).catch(() => null);
        if (result && result.ownerToken) ownerToken = result.ownerToken;
        if (!result || result.error) {
            setActive(false);
            showNotice((result && result.error) || 'Chatterbox is unavailable', 'error');
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

    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.target === 'popup' || request.target === 'offscreen') return undefined;
        if (request.action === 'showGeneratingSpeech') {
            ownerToken = request.ownerToken;
            setActive(true);
            showNotice('Generating Chatterbox speech…', 'loading');
        } else if (request.action === 'ttsProgress') {
            // Also the liveness probe: answering proves this tab still exists.
            setActive(true);
        } else if (request.action === 'ttsProducerComplete') {
            showNotice('Speech generated, finishing playback…', 'loading');
        } else if (request.action === 'ttsUiComplete') {
            setActive(false);
            showNotice('Speech completed', 'success');
        } else if (request.action === 'stopTTSAudio') {
            setActive(false);
        } else if (request.action === 'ttsError') {
            setActive(false);
            showNotice(request.error || 'Chatterbox generation failed', 'error');
        }
        sendResponse({ success: true });
        return undefined;
    });

    ensureButtons();
})();
