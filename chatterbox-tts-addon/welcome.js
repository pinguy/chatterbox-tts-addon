const statusBox = document.getElementById('status');
const installBox = document.getElementById('install');
async function probe(url) { try { return (await fetch(url, { cache: 'no-store' })).ok; } catch (_) { return false; } }
async function check() {
    statusBox.textContent = 'Checking local services…';
    const [tts, lab] = await Promise.all([probe('http://127.0.0.1:8010/health'), probe('http://127.0.0.1:8030/api/status')]);
    statusBox.className = `card ${tts ? 'ok' : 'bad'}`;
    statusBox.textContent = tts ? `Chatterbox TTS is ready.${lab ? ' Voice Lab is ready.' : ' Voice Lab is not running.'}` : 'Chatterbox backend was not detected.';
    installBox.hidden = tts;
}
document.getElementById('recheck').addEventListener('click', check);
document.getElementById('lab').addEventListener('click', () => browser.tabs.create({ url: 'http://127.0.0.1:8030/' }));
check();
