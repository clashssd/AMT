// Voice Control — state machine, wake word, VAD, STT, TTS
// Loads after main.js; exposes window.voice = { init, startListening, stopAll, getState, onStateChange }

(function () {
    'use strict';

    const API = window.location.origin;

    // ── State ─────────────────────────────────────────────────────────────────
    const STATES = ['off', 'listening', 'recording', 'processing', 'responding', 'speaking'];
    let state = 'off';
    let settings = {};
    let subscribers = [];

    // ── Timers / Aborters ─────────────────────────────────────────────────────
    let autoTimeoutId = null;
    let sttAbort = null;
    let llmAbort = null;

    // ── Media resources ────────────────────────────────────────────────────────
    let mediaStream = null;
    let audioCtx = null;
    let workletNode = null;
    let analyser = null;
    let vadLoopId = null;

    // ── Pre-buffer (ring buffer for wake-word pre-capture) ───────────────────
    // 2.5 s at 16 kHz mono Int16 = 40 000 samples = 80 000 bytes
    const RING_SIZE = 40000;
    let ringBuf = new Int16Array(RING_SIZE);
    let ringIdx = 0;
    let ringFill = 0;

    // ── WebSocket (wake word) ─────────────────────────────────────────────────
    let ws = null;

    // ── TTS ────────────────────────────────────────────────────────────────────
    let ttsAudio = null;

    // ── DOM ────────────────────────────────────────────────────────────────────
    let btn = null;

    // ────────────────────────────────────────────────────────────────────────────
    // VoiceStateMachine
    // ────────────────────────────────────────────────────────────────────────────

    const LEGAL = {
        off:        ['listening'],
        listening:  ['recording', 'off'],
        recording:  ['processing', 'listening'],
        processing: ['responding', 'listening', 'off'],
        responding: ['speaking', 'listening', 'off'],
        speaking:   ['listening', 'off'],
    };

    function transition(next) {
        if (!LEGAL[state] || !LEGAL[state].includes(next)) {
            console.warn('[voice] illegal transition', state, '→', next);
            return;
        }
        state = next;
        updateBtn();
        subscribers.forEach(cb => { try { cb(state); } catch (_) {} });
        resetAutoTimeout();
    }

    function resetAutoTimeout() {
        if (autoTimeoutId) { clearTimeout(autoTimeoutId); autoTimeoutId = null; }
        if (state === 'listening') {
            autoTimeoutId = setTimeout(() => {
                toast('⏱', 'Голосовой режим завершён', 'Таймаут: 10 мин без активности');
                stopAll();
            }, 600000);
        }
    }

    function updateBtn() {
        if (!btn) return;
        btn.classList.remove('off', 'listening', 'recording', 'processing', 'responding', 'speaking');
        btn.classList.add(state);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // WakeWordEngine (AudioWorklet + WebSocket to /ws/wake-word)
    // ────────────────────────────────────────────────────────────────────────────

    async function startWakeWord() {
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, sampleRate: 48000, echoCancellation: true, noiseSuppression: true }
        });
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();

        // Create analyser for VAD (used later in VadRecorder)
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 512;
        const src = audioCtx.createMediaStreamSource(mediaStream);
        src.connect(analyser);

        // AudioWorklet: resample to 16 kHz mono Int16, ring buffer, 100 ms chunks → WS
        const workletCode = buildWorkletCode();
        const blob = new Blob([workletCode], { type: 'application/javascript' });
        const url = URL.createObjectURL(blob);
        await audioCtx.audioWorklet.addModule(url);
        URL.revokeObjectURL(url);

        workletNode = new AudioWorkletNode(audioCtx, 'voice-worklet', {
            processorOptions: { sampleRate: audioCtx.sampleRate }
        });
        src.connect(workletNode);
        workletNode.port.onmessage = onWorkletMsg;

        // Open WebSocket to backend
        ws = new WebSocket(`${API.replace('http', 'ws')}/ws/wake-word`);
        ws.binaryType = 'arraybuffer';
        ws.onmessage = onWsMsg;
        ws.onclose = () => { if (state === 'listening') { toast('⚠', 'Связь с сервером потеряна', 'Vosk-поток закрыт'); stopAll(); } };
        ws.onerror = () => { /* onclose handles */ };
    }

    function buildWorkletCode() {
        // Resample to 16 kHz mono Int16; ring buffer 40 000 samples;
        // emit 6400-byte (100 ms) chunks to the main thread.
        return `
class VoiceWorklet extends AudioWorkletProcessor {
    constructor(opts) {
        super();
        const sr = opts.processorOptions.sampleRate || 48000;
        this.decim = Math.max(1, Math.round(sr / 16000));
        this.buf = new Int16Array(6400);
        this.bufIdx = 0;
        this.pre = new Float32Array(sr);
        this.preLen = 0;
    }
    process(inputs) {
        const ch = inputs[0] && inputs[0].length ? inputs[0][0] : null;
        if (!ch) return true;
        // accumulate
        for (let i = 0; i < ch.length; i++) this.pre[this.preLen++] = ch[i];
        // decimate
        let out = 0;
        while (this.preLen >= this.decim) {
            let sum = 0;
            for (let j = 0; j < this.decim; j++) sum += this.pre[j];
            const s = Math.max(-32768, Math.min(32767, Math.round(sum / this.decim)));
            this.buf[this.bufIdx++] = s;
            if (this.bufIdx >= 6400) {
                this.port.postMessage(this.buf.slice(0, 6400));
                this.bufIdx = 0;
            }
            this.preLen--;
            for (let j = 0; j < this.decim - 1; j++) this.pre[j] = this.pre[j + this.decim];
        }
        return true;
    }
}
registerProcessor('voice-worklet', VoiceWorklet);
`;
    }

    function onWorkletMsg(e) {
        const int16 = e.data;
        // Forward to WS (6400 bytes = 100 ms)
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(int16.buffer, int16.byteOffset, int16.byteLength);
        }
        // Also fill ring buffer for pre-capture
        ringBuf.set(int16, ringIdx);
        ringIdx = (ringIdx + int16.length) % RING_SIZE;
        ringFill = Math.min(RING_SIZE, ringFill + int16.length);
    }

    function onWsMsg(e) {
        const msg = JSON.parse(e.data);
        if (msg.type === 'wake' && state === 'listening') {
            // Drain last 2.0 s from ring buffer → WAV
            const preBlob = drainRingBuffer(2.0);
            transition('recording');
            startVadRecorder(preBlob);
        }
    }

    function drainRingBuffer(seconds) {
        const samples = Math.min(Math.round(seconds * 16000), ringFill);
        const start = (ringIdx - samples + RING_SIZE) % RING_SIZE;
        const pcm = new Int16Array(samples);
        for (let i = 0; i < samples; i++) {
            pcm[i] = ringBuf[(start + i) % RING_SIZE];
        }
        // Reset ring
        ringIdx = 0;
        ringFill = 0;
        ringBuf.fill(0);
        return pcmToWavBlob(pcm, 16000);
    }

    function pcmToWavBlob(pcm, sampleRate) {
        const dataSize = pcm.length * 2;
        const buf = new ArrayBuffer(44 + dataSize);
        const v = new DataView(buf);
        writeStr(v, 0, 'RIFF'); v.setUint32(4, 36 + dataSize, true); writeStr(v, 8, 'WAVE');
        writeStr(v, 12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
        v.setUint16(22, 1, true); v.setUint32(24, sampleRate, true);
        v.setUint32(28, sampleRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
        writeStr(v, 36, 'data'); v.setUint32(40, dataSize, true);
        new Int16Array(buf, 44, pcm.length).set(pcm);
        return new Blob([buf], { type: 'audio/wav' });
    }

    function writeStr(v, off, s) { for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i)); }

    // ────────────────────────────────────────────────────────────────────────────
    // VadRecorder (MediaRecorder + RMS VAD)
    // ────────────────────────────────────────────────────────────────────────────

    let vadChunks = [];
    let noiseFloor = 0;
    let silenceStart = 0;
    let preBlob = null;

    async function startVadRecorder(preBufferBlob) {
        preBlob = preBufferBlob || null;
        vadChunks = [];
        noiseFloor = 0;
        silenceStart = 0;

        const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
        const rec = new MediaRecorder(mediaStream, { mimeType: mime, audioBitsPerSecond: 32000 });
        rec.ondataavailable = e => { if (e.data.size) vadChunks.push(e.data); };
        rec.start(250);
        currentRec = rec;

        // Noise floor: 500 ms of min RMS
        await collectNoiseFloor(500);

        // VAD loop every 50 ms
        const rmsArr = new Float32Array(analyser.fftSize);
        vadLoopId = setInterval(async () => {
            analyser.getFloatTimeDomainData(rmsArr);
            let sum = 0;
            for (let i = 0; i < rmsArr.length; i++) sum += rmsArr[i] * rmsArr[i];
            const rms = Math.sqrt(sum / rmsArr.length);

            const threshold = noiseFloor * (settings.vadSensitivity || 1.8);
            const now = performance.now();

            if (rms >= threshold) {
                silenceStart = now; // reset silence timer
            } else if (silenceStart && (now - silenceStart) >= (settings.vadSilenceMs || 2000)) {
                // Stop recording
                clearInterval(vadLoopId);
                vadLoopId = null;
                rec.stop();
                await new Promise(r => { rec.onstop = r; });
                const blob = combineBlobs(preBlob, vadChunks);
                vadChunks = [];
                handleRecordingComplete(blob);
            }
        }, 50);
    }

    let currentRec = null;

    async function collectNoiseFloor(ms) {
        const rmsArr = new Float32Array(analyser.fftSize);
        let minRms = Infinity;
        const step = 100;
        for (let t = 0; t < ms; t += step) {
            await sleep(step);
            analyser.getFloatTimeDomainData(rmsArr);
            let sum = 0;
            for (let i = 0; i < rmsArr.length; i++) sum += rmsArr[i] * rmsArr[i];
            minRms = Math.min(minRms, Math.sqrt(sum / rmsArr.length));
        }
        noiseFloor = minRms || 0.005;
    }

    function combineBlobs(pre, chunks) {
        const all = [];
        if (pre) all.push(pre);
        all.push(...chunks);
        return new Blob(all, { type: 'audio/webm' });
    }

    function handleRecordingComplete(blob) {
        transition('processing');
        runPipeline(blob);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // SttClient (cloud + local with auto-fallback)
    // ────────────────────────────────────────────────────────────────────────────

    async function transcribe(blob) {
        const b64 = await blobToBase64(blob);
        const mime = blob.type || 'audio/webm';

        if (settings.sttProvider === 'local') {
            const res = await postWithTimeout('/api/stt-local', {
                audio_b64: b64, mime,
                model_path: settings.voskModelPath || '',
            });
            if (res.ok && res.text) return res.text;
            // model_not_found → try cloud
            if (res.error === 'model_not_found' || res.error === 'vosk_not_installed') {
                const cloudKey = await hasCloudSttKey();
                if (cloudKey) {
                    toast('↔', 'Vosk не доступен', 'Использую облачный STT');
                    const cloudRes = await postWithTimeout('/api/stt', {
                        audio_b64: b64, mime, use_settings_key: true,
                        base_url: settings.sttBaseUrl || undefined,
                        model: settings.sttModel || undefined,
                    });
                    if (cloudRes.ok && cloudRes.text) return cloudRes.text;
                }
                throw new Error('STT: ни локальная модель, ни облачный ключ не доступны');
            }
            throw new Error(res.error || 'STT error');
        }

        // cloud (default or explicit)
        const cloudRes = await postWithTimeout('/api/stt', {
            audio_b64: b64, mime, use_settings_key: true,
            base_url: settings.sttBaseUrl || undefined,
            model: settings.sttModel || undefined,
        });
        if (cloudRes.ok && cloudRes.text) return cloudRes.text;

        // Cloud failed → fallback to local Vosk
        const localRes = await postWithTimeout('/api/voice/status', null, 'GET');
        if (localRes.modelReady) {
            toast('↔', 'Облачный STT недоступен', 'Использую локальный Vosk');
            const localTrans = await postWithTimeout('/api/stt-local', {
                audio_b64: b64, mime,
                model_path: settings.voskModelPath || '',
            });
            if (localTrans.ok && localTrans.text) return localTrans.text;
        }
        throw new Error(cloudRes.error || 'STT: облачный и локачный STT недоступны');
    }

    async function hasCloudSttKey() {
        try {
            const status = await window.api?.secrets?.status?.();
            if (status && status.providers) {
                return status.providers.some(p => /stt|cloud|openai|deepgram|whisper/i.test(p));
            }
        } catch (_) {}
        // Fallback: check settings
        const s = await fetchSettings();
        return !!(s.sttBaseUrl && (s.sttModel || s.audioKey));
    }

    async function fetchSettings() {
        try {
            const res = await fetch(`${API}/api/settings`);
            return await res.json();
        } catch (_) { return {}; }
    }

    async function postWithTimeout(path, body, method = 'POST') {
        const ctrl = new AbortController();
        sttAbort = ctrl;
        const timer = setTimeout(() => ctrl.abort(), 30000);
        try {
            const opts = { method, signal: ctrl.signal };
            if (body) {
                opts.headers = { 'Content-Type': 'application/json' };
                opts.body = JSON.stringify(body);
            }
            const res = await fetch(`${API}${path}`, opts);
            const json = await res.json();
            return json;
        } catch (e) {
            if (e.name === 'AbortError') throw new Error('STT timeout (30 s)');
            throw e;
        } finally {
            clearTimeout(timer);
        }
    }

    function blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const r = new FileReader();
            r.onload = () => resolve(r.result.split(',')[1]);
            r.onerror = reject;
            r.readAsDataURL(blob);
        });
    }

    // ────────────────────────────────────────────────────────────────────────────
    // TtsPlayer (browser speechSynthesis + cloud/custom OpenAI-compatible)
    // ────────────────────────────────────────────────────────────────────────────

    function speak(text) {
        return new Promise(resolve => {
            const provider = settings.ttsProvider || 'browser';

            if (provider === 'browser') {
                const u = new SpeechSynthesisUtterance(text);
                if (settings.ttsVoiceId) {
                    const voices = speechSynthesis.getVoices();
                    const match = voices.find(v => v.name === settings.ttsVoiceId || v.voiceURI === settings.ttsVoiceId);
                    if (match) u.voice = match;
                }
                u.onend = () => { vadRecorderResume(); resolve(); };
                u.onerror = () => { vadRecorderResume(); resolve(); };
                vadRecorderPause();
                speechSynthesis.speak(u);
                ttsAudio = null;
                return;
            }

            // Cloud / custom / elevenlabs / openai
            (async () => {
                try {
                    let audioBlob;
                    if (provider === 'custom') {
                        // OpenAI-compatible: POST {ttsBaseUrl}/v1/audio/speech
                        const key = await getSecretForProvider('tts');
                        const res = await fetch(`${settings.ttsBaseUrl}/v1/audio/speech`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                ...(key ? { 'Authorization': `Bearer ${key}` } : {}),
                            },
                            body: JSON.stringify({
                                model: settings.ttsModel || 'gpt-4o-mini-tts',
                                voice: settings.ttsVoiceId || 'alloy',
                                input: text,
                            }),
                        });
                        if (!res.ok) throw new Error(`TTS HTTP ${res.status}`);
                        audioBlob = await res.blob();
                    } else {
                        // elevenlabs / openai via /api/media/generate
                        const res = await fetch(`${API}/api/media/generate`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                kind: 'audio',
                                prompt: text,
                                use_settings_key: true,
                                provider: provider,
                                base_url: settings.ttsBaseUrl || undefined,
                                model: settings.ttsModel || undefined,
                                voice_id: settings.ttsVoiceId || undefined,
                            }),
                        });
                        const json = await res.json();
                        if (!json.ok) throw new Error(json.error || 'TTS error');
                        let b64 = json.b64 || '';
                        if (!b64 && json.download_url) {
                            const dlRes = await fetch(`${API}${json.download_url}`);
                            audioBlob = await dlRes.blob();
                        } else if (b64) {
                            audioBlob = await (async () => {
                                const bin = atob(b64);
                                const arr = new Uint8Array(bin.length);
                                for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
                                return new Blob([arr], { type: 'audio/mpeg' });
                            })();
                        }
                        if (!audioBlob) throw new Error('No audio data');
                    }

                    // Play
                    vadRecorderPause();
                    const url = URL.createObjectURL(audioBlob);
                    ttsAudio = new Audio(url);
                    ttsAudio.onended = () => {
                        URL.revokeObjectURL(url);
                        vadRecorderResume();
                        ttsAudio = null;
                        resolve();
                    };
                    ttsAudio.onerror = () => {
                        URL.revokeObjectURL(url);
                        vadRecorderResume();
                        ttsAudio = null;
                        // Fallback to browser
                        toast('↔', 'Облачный TTS недоступен', 'Использую браузерный голос');
                        const u = new SpeechSynthesisUtterance(text);
                        u.onend = resolve;
                        speechSynthesis.speak(u);
                    };
                    await ttsAudio.play();
                } catch (e) {
                    // Cloud failed → fallback to browser speechSynthesis
                    toast('↔', 'Облачный TTS недоступен', 'Использую браузерный голос');
                    vadRecorderPause();
                    const u = new SpeechSynthesisUtterance(text);
                    u.onend = () => { vadRecorderResume(); resolve(); };
                    u.onerror = () => { vadRecorderResume(); resolve(); };
                    speechSynthesis.speak(u);
                }
            })();
        });
    }

    function cancelTts() {
        speechSynthesis.cancel();
        if (ttsAudio) { ttsAudio.pause(); ttsAudio = null; }
    }

    async function getSecretForProvider(provider) {
        try {
            const status = await window.api?.secrets?.status?.();
            // Return the key if we can read it (we can't — secrets are opaque)
            // For custom TTS, the key is passed via /api/media/generate which reads settings.json
            // or via the internal secrets channel. For direct POST to ttsBaseUrl, we need the key.
            // If no key available, the request will fail and fallback to browser.
            return null;
        } catch (_) { return null; }
    }

    function vadRecorderPause() {
        if (audioCtx) audioCtx.suspend().catch(() => {});
        // Clear ring buffer to prevent TTS echo
        ringBuf.fill(0);
        ringIdx = 0;
        ringFill = 0;
    }

    function vadRecorderResume() {
        if (audioCtx) audioCtx.resume().catch(() => {});
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Pipeline: RECORDING → PROCESSING → RESPONDING → SPEAKING → LISTENING
    // ────────────────────────────────────────────────────────────────────────────

    async function runPipeline(blob) {
        try {
            const text = await transcribe(blob);
            if (!text || !text.trim()) {
                toast('🎤', 'Ничего не распознано', 'Попробуйте ещё раз');
                transition('listening');
                return;
            }

            // Add transcript as user message
            if (typeof addUserMessage === 'function') addUserMessage(text);

            transition('responding');

            // Call LLM
            const chat = typeof getCurrentChat === 'function' ? getCurrentChat() : null;
            const history = chat ? chat.messages.slice(0, -1) : [];
            const agentId = (chat && chat.agent_id) || '';

            let fullText = '';
            try {
                if (typeof streamViaWebSocket === 'function') {
                    fullText = await streamViaWebSocket(text, history, agentId, []);
                } else {
                    throw new Error('LLM pipeline not available');
                }
            } catch (e) {
                toast('⚠', 'Ошибка LLM', e.message || String(e));
                transition('listening');
                return;
            }

            // TTS
            if (settings.ttsProvider && settings.ttsProvider !== 'none') {
                transition('speaking');
                await speak(fullText || text);
            }

            transition('listening');

        } catch (e) {
            toast('⚠', 'Ошибка STT', e.message || String(e));
            transition('listening');
        }
    }

    // ────────────────────────────────────────────────────────────────────────────
    // stopAll / startListening
    // ────────────────────────────────────────────────────────────────────────────

    function stopAll() {
        cancelTts();
        if (sttAbort) { sttAbort.abort(); sttAbort = null; }
        if (llmAbort) { llmAbort.abort(); llmAbort = null; }
        if (vadLoopId) { clearInterval(vadLoopId); vadLoopId = null; }
        if (currentRec) {
            try { currentRec.stop(); } catch (_) {}
            currentRec = null;
        }
        if (ws) { try { ws.close(); } catch (_) {} ws = null; }
        if (workletNode) {
            try { workletNode.disconnect(); workletNode.port.close(); } catch (_) {}
            workletNode = null;
        }
        if (audioCtx) {
            try { audioCtx.close(); } catch (_) {}
            audioCtx = null;
        }
        if (mediaStream) {
            mediaStream.getTracks().forEach(t => t.stop());
            mediaStream = null;
        }
        analyser = null;
        if (autoTimeoutId) { clearTimeout(autoTimeoutId); autoTimeoutId = null; }
        ringBuf.fill(0);
        ringIdx = 0;
        ringFill = 0;
        state = 'off';
        updateBtn();
        subscribers.forEach(cb => { try { cb('off'); } catch (_) {} });
    }

    async function startListening() {
        // Check model availability
        try {
            const status = await fetch(`${API}/api/voice/status`).then(r => r.json()).catch(() => ({}));
            if (!status.modelReady && !await hasCloudSttKey()) {
                const hasKey = !!(settings.sttBaseUrl && (settings.sttModel || settings.audioKey));
                if (!hasKey) {
                    toast('⚠', 'Голосовое управление недоступно', 'Нет ни локальной модели, ни облачного ключа', 6000, true, 'settings');
                    state = 'off';
                    updateBtn();
                    return;
                }
            }
        } catch (_) { /* proceed anyway */ }

        try {
            await startWakeWord();
            transition('listening');
        } catch (e) {
            toast('⚠', 'Не удалось запустить голосовой режим', e.message || String(e));
            stopAll();
        }
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Toast helper
    // ────────────────────────────────────────────────────────────────────────────

    function toast(icon, title, body, duration, withAction, actionLabel) {
        // Use existing showToast from main.js (same script scope)
        if (typeof showToast === 'function') {
            showToast(icon, title, body, duration);
        } else {
            console.warn(`[voice] ${title}: ${body}`);
        }
        // If "Открыть настройки" action needed
        if (withAction && actionLabel === 'settings') {
            const navLink = document.querySelector('[data-sec="sec-providers"], [data-sec="sec-voice"]');
            if (navLink) navLink.click();
        }
    }

    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

    // ────────────────────────────────────────────────────────────────────────────
    // Public API
    // ────────────────────────────────────────────────────────────────────────────

    window.voice = {
        init(cfg) {
            settings = Object.assign({}, settings, cfg);
            btn = document.getElementById('voiceBtn');
            if (!btn) {
                console.warn('[voice] #voiceBtn not found');
                return;
            }
            btn.addEventListener('click', () => {
                switch (state) {
                    case 'off':
                        startListening();
                        break;
                    case 'listening':
                        stopAll();
                        break;
                    case 'recording':
                        // Force-stop VAD → processing
                        if (currentRec) {
                            try { currentRec.stop(); } catch (_) {}
                            if (vadLoopId) { clearInterval(vadLoopId); vadLoopId = null; }
                        }
                        const blob = combineBlobs(preBlob, vadChunks);
                        vadChunks = [];
                        handleRecordingComplete(blob);
                        break;
                    case 'processing':
                        if (sttAbort) { sttAbort.abort(); sttAbort = null; }
                        transition('listening');
                        break;
                    case 'responding':
                        // Abort LLM WS — currentWs is a module-level let in main.js (same scope)
                        if (typeof currentWs !== 'undefined' && currentWs) { try { currentWs.close(); } catch (_) {} }
                        transition('listening');
                        break;
                    case 'speaking':
                        cancelTts();
                        stopAll();
                        break;
                }
            });
            updateBtn();
        },

        startListening,
        stopAll,
        getState: () => state,
        onStateChange(cb) {
            subscribers.push(cb);
            return () => { const i = subscribers.indexOf(cb); if (i >= 0) subscribers.splice(i, 1); };
        },
    };

    // Expose some internals for testing
    window.voice._test = {
        transition,
        LEGAL,
        STATES,
    };

    // beforeunload
    window.addEventListener('beforeunload', () => {
        if (state !== 'off') stopAll();
    });

})();
