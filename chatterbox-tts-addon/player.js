let currentAudio = null;

function stopAudio() {
    if (!currentAudio) return;
    currentAudio.pause();
    currentAudio.removeAttribute('src');
    currentAudio.load();
    currentAudio = null;
}

window.addEventListener('message', (event) => {
    if (!event.data) return;
    if (event.data.action === 'stopAudio') {
        stopAudio();
        return;
    }
    if (event.data.action !== 'playAudio' || !event.data.audioUrl) return;
    stopAudio();
    currentAudio = new Audio(event.data.audioUrl);
    currentAudio.addEventListener('ended', () => {
        currentAudio = null;
        window.parent.postMessage({ action: 'chatterboxPlaybackEnded' }, '*');
    }, { once: true });
    currentAudio.play().catch((error) => {
        console.error('Chatterbox player error:', error);
        window.parent.postMessage({ action: 'chatterboxPlaybackError', error: error.message }, '*');
    });
});
