# Voice Control Feature — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full voice-control pipeline (Wake Word → VAD Recording → STT → LLM → TTS + Chat UI) to AMT Chat, with secrets isolated in Electron safeStorage and local Vosk STT on the backend.

**Architecture:** The renderer (Electron, contextIsolation) sends audio over a WebSocket to the FastAPI sidecar where a continuous Vosk recognizer detects the wake word string. On detection, MediaRecorder captures the command; the recording is sent to either local Vosk (batch) or cloud STT. The transcript is fed into the existing `streamViaWebSocket` LLM pipeline. The AI answer is rendered in chat and spoken via `speechSynthesis` (default) or cloud TTS. API keys never touch the renderer — they live encrypted in `userData/secrets.bin` via `safeStorage` and are injected into the sidecar at runtime over a token-protected internal channel.

**Tech Stack:** Electron 45, vanilla JS frontend, Python FastAPI backend, Vosk (Python), `safeStorage` (DPAPI on Windows), AudioWorklet + MediaRecorder (Chromium), `speechSynthesis`.

**Spec:** `docs/superpowers/specs/2026-11-25-voice-control-design.md`

## Global Constraints

- No Node integration in renderer (`contextIsolation: true`, `nodeIntegration: false`)
- API keys must never appear in `settings.json` or `localStorage`; only in `secrets.bin` (safeStorage-encrypted)
- Vosk model: Python auto-download on first run to `backend/models/vosk-model-small-ru/` (~50 MB); no npm scripts
- Porcupine excluded (Free Tier dead 30.06.2026); wake word = Vosk string-match
- TTS default: browser `speechSynthesis`; mic suspended during playback
- VAD silence timeout default 2000 ms, range 500–10000; VAD sensitivity default 1.8, range 1.2–3.0
- Auto-timeout: 10 min in LISTENING with no wake word → OFF
- Frontend files served via FastAPI `StaticFiles` mount at `127.0.0.1:8000/`
- i18n: RU default, EN secondary; `{wakeWord}` interpolation in listening tooltip
- Test runner: Node for JS tests (`tests/run_js_tests.js`), pytest for Python tests

## Review Focus

1. **Empty STT transcript (silence recorded)** — the voice loop must not send an empty user message to the LLM; toast "Ничего не распознано" and return to LISTENING. Pin this to Task 7 (voice.js state machine).
2. **STT timeout (>30 s)** — AbortController must cancel the fetch; toast "Ошибка STT: таймаут"; state → LISTENING. Pin to Task 7.
3. **Mic click during RESPONDING** — must abort the LLM WebSocket and skip TTS; state → LISTENING (not OFF). Pin to Task 7.
4. **Vosk model missing AND cloud key missing** — must not silently fail; toast + "Открыть настройки" button; state → OFF. Pin to Task 5 (voice.js init).
5. **TTS echo into mic** — AudioContext must be suspended before TTS starts and resumed only after TTS ends; ring buffer must be cleared. Pin to Task 7.

---

## File Map

| File | Role |
|------|------|
| `backend/stt_local.py` **(new)** | Vosk model loading, `/api/stt-local` batch endpoint, `/ws/wake-word` streaming endpoint, `/api/voice/status` model-readiness, `normalize()` + `wake_word_match()` + `lev()` helpers, model auto-download |
| `backend/main.py` **(modify)** | Add voice fields to `Settings` pydantic model; wire `/api/stt-local`, `/ws/wake-word`, `/api/voice/status`; add `/internal/secrets` POST/DELETE |
| `electron/secrets.js` **(new)** | `safeStorage` encrypt/decrypt, `secrets.bin` read/write, `registerSecretsIpc(ipcMain)` with 3 handlers, `pushSecretToSidecar(port, provider, key)` helper |
| `electron/ipc.js` **(modify)** | Add `secrets:set`, `secrets:clear`, `secrets:status` handlers |
| `electron/preload.js` **(modify)** | Expose `window.api.secrets = { set, clear, status }` |
| `electron/main.js` **(modify)** | `require('./secrets')`; read `secrets.bin` at startup and pass keys as env vars to sidecar; generate `AMT_INTERNAL_TOKEN` |
| `frontend/js/voice.js` **(new)** | `VoiceStateMachine`, `WakeWordEngine`, `VadRecorder`, `SttClient`, `TtsPlayer`; public API `voice.init/startListening/stopAll/getState/onStateChange` |
| `frontend/css/voice.css` **(new)** | `.voice-btn` state classes, pulse/blink/spinner animations |
| `frontend/home.html` **(modify)** | Add `#voiceBtn` in `#composerToolsPop`; add `sec-voice` + `sec-providers` sections in Settings; link from subnav |
| `frontend/js/main.js` **(modify)** | Load `voice.js`; call `voice.init()` on page load + after settings save; `beforeunload` → `voice.stopAll()`; wire `sec-voice` save/load; wire `secrets:set/clear/status` IPC calls from sec-providers UI |
| `frontend/js/i18n.js` **(modify)** | Add all voice + provider i18n strings (RU/EN) |
| `requirements.txt` **(modify)** | Add `vosk` |
| `tests/run_js_tests.js` **(modify)** | Add `test_voice_state.js` to files list |
| `tests/test_voice_state.js` **(new)** | VoiceStateMachine transitions |
| `tests/test_vosk_local.py` **(new)** | `stt_local.transcribe_local` + `wake_word_match` + `normalize` |

---

### Task 1: Backend — Vosk STT Module (`stt_local.py`)

**Files:**
- Create: `backend/stt_local.py`
- Test: `tests/test_vosk_local.py`

**Interfaces:**
- Consumes: `settings.vosk_model_path` (string, may be empty), `settings.wake_word_string` (string, default "Астра"), `settings.wake_word_aliases` (list[str], may be empty), `settings.vad_fuzzy_threshold` (int, default 2)
- Produces:
  - `load_vosk_model(model_path: str | None) -> Model` — returns a Vosk `Model` instance or raises `FileNotFoundError`
  - `transcribe_local(audio_b64: str, mime: str, model_path: str | None = None) -> dict` — returns `{"ok": True, "text": str}` or `{"ok": False, "error": str, "fallback": "cloud"}`
  - `normalize(s: str) -> str` — lower, ё→е, strip non-alphanumeric (except spaces), collapse whitespace
  - `wake_word_match(transcript_norm: str, target_norm: str, aliases: list[str], threshold: int = 2) -> bool`
  - `lev(a: str, b: str, threshold: int = 2) -> int` — capped Levenshtein, early exit when distance > threshold
  - `ensure_model_downloaded() -> dict` — returns `{"modelReady": bool, "modelProgress": float, "error": str | None}`; downloads `vosk-model-small-ru.zip` from `https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip` to `backend/models/` if not present
  - `create_wake_word_recognizer(model_path: str | None = None) -> KaldiRecognizer` — factory for the WebSocket handler

- [ ] **Step 1: Write the failing test `tests/test_vosk_local.py`**

Test the pure functions that don't need a real Vosk model:
- `test_normalize_lowercase_and_e`: `normalize('ЁЖИК')` == `'ежик'`
- `test_normalize_strips_punctuation`: `normalize('привет, мир!')` == `'привет мир'`
- `test_wake_word_match_exact`: `wake_word_match('а стра', 'астр', ['астр'], 2)` → True (exact alias in last 5 words)
- `test_wake_word_match_fuzzy`: `wake_word_match('остра', 'астр', ['астр'], 2)` → True (Levenshtein distance 2)
- `test_wake_word_match_no_match`: `wake_word_match('погода', 'астр', ['астр'], 2)` → False
- `test_lev_capped`: `lev('abc', 'xyz', 2)` → 3 (capped at threshold+1, not > threshold)
- `test_lev_within_threshold`: `lev('астр', 'астро', 2)` → 1 (within threshold)
- `test_transcribe_local_returns_fallback_on_missing_model`: mock `load_vosk_model` to raise `FileNotFoundError`; call `transcribe_local('aW5n', 'audio/wav', '/nonexistent/')`; expect `{"ok": False, "error": "model_not_found", "fallback": "cloud"}`
- `test_ensure_model_downloaded_model_ready`: mock `os.path.isdir` → True for default path; expect `{"modelReady": True, "modelProgress": 1.0, "error": None}`

Run: `pytest tests/test_vosk_local.py -v`
Expected: FAIL with "module 'stt_local' not found" or "function not defined"

- [ ] **Step 2: Implement `backend/stt_local.py`**

Structure:
- Module-level `_model: Model | None` cache
- `DEFAULT_VOSK_PATH = os.path.join(os.path.dirname(__file__), "models", "vosk-model-small-ru")`
- `VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"`
- `normalize(s)`: exactly the 4-line pipeline from the spec
- `lev(a, b, threshold)`: standard 2-row DP; early exit when min row value > threshold
- `wake_word_match(transcript_norm, target_norm, aliases, threshold)`: check last 5 words against `aliases + [target_norm]` (exact substring, then fuzzy per-word)
- `transcribe_local(audio_b64, mime, model_path)`: decode b64 → WAV bytes → `KaldiRecognizer` → `AcceptWaveform` loop → `Result()` → return dict; on `FileNotFoundError` → fallback dict
- `ensure_model_downloaded()`: check `os.path.isdir(DEFAULT_VOSK_PATH)`; if missing, download zip with `urllib.request`, extract with `zipfile`, track progress via a module-level dict; return status dict
- `create_wake_word_recognizer(model_path)`: call `load_vosk_model`, return `KaldiRecognizer(model, 16000)`

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_vosk_local.py -v`
Expected: PASS (all tests)

- [ ] **Step 4: Commit**

```bash
git add backend/stt_local.py tests/test_vosk_local.py
git commit -m "feat: add Vosk local STT module with wake-word matching"
```

---

### Task 2: Backend — Wire Vosk Endpoints + Voice Settings into `main.py`

**Files:**
- Modify: `backend/main.py` (Settings model + endpoint wiring + `/internal/secrets`)

**Interfaces:**
- Consumes: `stt_local` module (from Task 1), existing `Settings` pydantic model, existing `app` FastAPI instance
- Produces:
  - `Settings` model gains fields: `stt_provider: str = "local"`, `tts_provider: str = "browser"`, `tts_voice_id: str = ""`, `vosk_model_path: str = ""`, `wake_word_string: str = "Астра"`, `vad_silence_ms: int = 2000`, `vad_sensitivity: float = 1.8`, `wake_word_aliases: list[str] = []`, `vad_fuzzy_threshold: int = 2`
  - `POST /api/stt-local` — body `{ audio_b64: str, mime: str, model_path?: str }` → delegates to `stt_local.transcribe_local`
  - `GET /api/voice/status` → `{ modelReady: bool, modelProgress: float, error: str | null }`
  - `POST /internal/secrets` — body `{ provider: str, key: str }`; validates `AMT_INTERNAL_TOKEN` from env; stores in in-memory dict; returns `{ ok: true }`
  - `DELETE /internal/secrets` — body `{ provider: str }`; removes from in-memory dict; returns `{ ok: true }`
  - `/internal/secrets` endpoints read the in-memory secret store; if key not present, fall back to `settings` model fields (existing `audioKey` etc.)

- [ ] **Step 1: Add voice fields to `Settings` pydantic model in `backend/main.py`**

Find the existing `Settings` class (the one persisted to `settings.json`). Add the 9 new fields listed above. These are non-secret; they persist to `settings.json`.

- [ ] **Step 2: Add `POST /api/stt-local` and `GET /api/voice/status` endpoints**

`POST /api/stt-local`: accepts `audio_b64`, `mime`, optional `model_path` (defaults to `settings.vosk_model_path`). Calls `stt_local.transcribe_local`. Returns the dict directly.

`GET /api/voice/status`: calls `stt_local.ensure_model_downloaded()`. Returns the status dict. This endpoint is also used to trigger the download if the model is not yet present.

- [ ] **Step 3: Add `POST /internal/secrets` and `DELETE /internal/secrets`**

Both require header `X-Internal-Token` matching `AMT_INTERNAL_TOKEN` env var. If token mismatch → 401.

Module-level `_in_memory_secrets: dict[str, str] = {}`.

`POST /internal/secrets`: store `req.key` in `_in_memory_secrets[req.provider]`.
`DELETE /internal/secrets`: pop `req.provider` from `_in_memory_secrets`.

Modify `transcribe_audio` in `ai_engine/media.py` (or wherever STT/TTS key resolution happens): if a provider key exists in `_in_memory_secrets`, use it; otherwise fall back to `settings` model fields. This is the runtime key injection path.

- [ ] **Step 4: Run backend tests**

Run: `pytest tests/ -k "not vosk" -v` (skip vosk tests that need a real model)
Expected: PASS — no regressions

- [ ] **Step 5: Commit**

```bash
git add backend/main.py requirements.txt
git commit -m "feat: wire voice settings, stt-local endpoint, internal secrets into backend"
```

---

### Task 3: Backend — WebSocket `/ws/wake-word` Streaming Endpoint

**Files:**
- Modify: `backend/main.py` (add WebSocket handler)

**Interfaces:**
- Consumes: `stt_local.create_wake_word_recognizer()` (Task 1), `settings.wake_word_string`, `settings.wake_word_aliases`, `settings.vad_fuzzy_threshold`
- Produces:
  - `WebSocket /ws/wake-word` — on connection: create session-scoped `KaldiRecognizer`; per binary frame (6400 bytes = 100 ms at 16 kHz mono Int16): `AcceptWaveform` → if final: `Result()` → `wake_word_match` → send `{"type": "wake", "text": str, "alias": str}` if matched + `rec.Reset()`; if partial: `PartialResult()` → same check. On disconnect: discard recognizer.

- [ ] **Step 1: Add `WebSocket /ws/wake-word` handler in `backend/main.py`**

```python
@app.websocket("/ws/wake-word")
async def ws_wake_word(websocket: WebSocket):
    await websocket.accept()
    rec = stt_local.create_wake_word_recognizer(settings.vosk_model_path or None)
    target_norm = stt_local.normalize(settings.wake_word_string)
    aliases = settings.wake_word_aliases  # may be empty
    threshold = settings.vad_fuzzy_threshold
    try:
        while True:
            data = await websocket.receive_bytes()
            # data is 6400 bytes = 100 ms of 16 kHz mono Int16
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result())["text"]
                if stt_local.wake_word_match(stt_local.normalize(text), target_norm, aliases, threshold):
                    await websocket.send_text(json.dumps({"type": "wake", "text": text, "alias": target_norm}))
                    rec.Reset()
            else:
                text = json.loads(rec.PartialResult())["partial"]
                if stt_local.wake_word_match(stt_local.normalize(text), target_norm, aliases, threshold):
                    await websocket.send_text(json.dumps({"type": "wake", "text": text, "alias": target_norm}))
                    rec.Reset()
    except WebSocketDisconnect:
        pass
```

Note: `settings` here refers to the app-level settings object loaded from `settings.json` at startup. For runtime wake-word changes, the frontend would need to reload settings or the backend would need a settings reload endpoint (out of scope for v1 — document this).

- [ ] **Step 2: Run backend tests**

Run: `pytest tests/ -k "not vosk" -v`
Expected: PASS — no regressions

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: add /ws/wake-word WebSocket endpoint for continuous Vosk streaming"
```

---

### Task 4: Electron — Secrets Module (`electron/secrets.js`)

**Files:**
- Create: `electron/secrets.js`
- Modify: `electron/main.js` (require secrets, pass env vars to sidecar, generate AMT_INTERNAL_TOKEN)
- Modify: `electron/ipc.js` (add secrets:* handlers)
- Modify: `electron/preload.js` (expose `window.api.secrets`)

**Interfaces:**
- Consumes: `safeStorage` (Electron built-in), `fs`, `path`, `app` (Electron), `ipcMain`, `contextBridge`
- Produces:
  - `secrets.js` exports: `registerSecretsIpc(ipcMain, getSidecarPort)` — registers 3 handlers
  - `secrets.js` exports: `readSecrets() -> Promise<Record<string, string>>` — decrypts all keys from `secrets.bin`
  - `secrets.js` exports: `writeSecrets(obj) -> Promise<void>` — encrypts and writes to `secrets.bin`
  - `secrets.js` exports: `pushSecretToSidecar(port, provider, key)` — POST to `/internal/secrets` with `X-Internal-Token`
  - `secrets.js` exports: `clearSecretFromSidecar(port, provider)` — DELETE to `/internal/secrets`
  - `preload.js`: `window.api.secrets = { set, clear, status }` where:
    - `set({ provider, key })` → `ipcRenderer.invoke('secrets:set', ...)`
    - `clear({ provider })` → `ipcRenderer.invoke('secrets:clear', ...)`
    - `status()` → `ipcRenderer.invoke('secrets:status')` → `{ providers: string[] }`
  - `main.js` startup: generate `AMT_INTERNAL_TOKEN` (crypto.randomUUID()), pass as env var to sidecar spawn; read `secrets.bin` and set `AMT_OPENAI_KEY` / `AMT_ELEVENLABS_KEY` env vars as fallback

- [ ] **Step 1: Implement `electron/secrets.js`**

- `secretsFile()` → `path.join(app.getPath('userData'), 'secrets.bin')`
- `readSecrets()`: read file, JSON.parse, decrypt each value via `safeStorage.decryptString(Buffer.from(val, 'base64'))`; on read/parse failure → return `{}`
- `writeSecrets(obj)`: encrypt each value via `safeStorage.encryptString(val).toString('base64')`; JSON.stringify; write to `secrets.bin`
- `registerSecretsIpc(ipcMain, getPort, getToken)`:
  - `'secrets:set'`: `{ provider, key }` → `writeSecrets` (upsert) → `pushSecretToSidecar(getPort(), provider, key, getToken())`
  - `'secrets:clear'`: `{ provider }` → remove from `readSecrets()` → `writeSecrets` → `clearSecretFromSidecar(getPort(), provider, getToken())`
  - `'secrets:status'`: `readSecrets()` → `{ providers: Object.keys(obj) }` (never the values)

- [ ] **Step 2: Modify `electron/main.js`**

- `require('./secrets')`
- Before `startSidecar()`: generate `AMT_INTERNAL_TOKEN = crypto.randomUUID()`; store in module scope
- Pass `AMT_INTERNAL_TOKEN` + any existing secrets as env vars to the sidecar spawn call
- After sidecar is up: call `pushSecretToSidecar` for each key in `secrets.bin` (runtime injection, no restart)

- [ ] **Step 3: Add `secrets:*` handlers to `electron/ipc.js`**

Import `registerSecretsIpc` from `./secrets`. Call it in `registerIpc(sidecar)` with `sidecar.port` getter and the token.

- [ ] **Step 4: Expose `window.api.secrets` in `electron/preload.js`**

Add to the `contextBridge.exposeInMainWorld` object:
```js
secrets: {
  set: (opts) => ipcRenderer.invoke('secrets:set', opts),
  clear: (opts) => ipcRenderer.invoke('secrets:clear', opts),
  status: () => ipcRenderer.invoke('secrets:status'),
}
```

- [ ] **Step 5: Commit**

```bash
git add electron/secrets.js electron/main.js electron/ipc.js electron/preload.js
git commit -m "feat: add safeStorage secrets module with IPC and sidecar injection"
```

---

### Task 5: Frontend — `voice.js` Core Module

**Files:**
- Create: `frontend/js/voice.js`

**Interfaces:**
- Consumes:
  - `window.api.secrets` (from Task 4) — for STT/TTS key status
  - `fetch` (proxied via `window.api.fetch` in Electron, or native `fetch` in dev) — for `/api/stt`, `/api/stt-local`, `/api/voice/status`, `/api/media/generate`
  - `streamViaWebSocket(userText, history, agentId, attachments)` — existing in `main.js` (called via `window.streamViaWebSocket`)
  - `addUserMessage(text)` — existing in `main.js` (called via `window.addUserMessage`)
  - `appendBotContent(el, chunk)` — existing in `main.js`
  - Settings object: `{ sttProvider, ttsProvider, ttsVoiceId, wakeWordString, vadSilenceMs, vadSensitivity }`
- Produces (public API on `window.voice`):
  - `voice.init(settings)` — called on page load and after settings save; sets up the state machine, attaches click handler to `#voiceBtn`
  - `voice.startListening()` — → LISTENING state; opens `/ws/wake-word`; starts AudioWorklet + ring buffer
  - `voice.stopAll()` — → OFF state; stops all tracks, closes AudioContext, closes WebSocket, clears timers
  - `voice.getState()` → `'off'|'listening'|'recording'|'processing'|'responding'|'speaking'`
  - `voice.onStateChange(cb)` — subscribe; cb receives new state string
  - Internal: `WakeWordEngine`, `VadRecorder`, `SttClient`, `TtsPlayer`, `VoiceStateMachine`

**State machine transitions (from spec):**
```
OFF → LISTENING → RECORDING → PROCESSING → RESPONDING → SPEAKING → LISTENING → OFF
      ↑_________________________________↓ (click during RESPONDING/SPEAKING/PROCESSING has specific behavior)
```

- [ ] **Step 1: Implement `VoiceStateMachine` class in `voice.js`**

- State enum: `'off'`, `'listening'`, `'recording'`, `'processing'`, `'responding'`, `'speaking'`
- `transition(newState)` — validates legal transitions (per spec edge cases); emits to all subscribers
- Auto-timeout: if in `LISTENING` for > 10 min with no wake word → transition to `OFF`; show toast
- Mic click behavior per state:
  - `off` → `startListening()`
  - `listening` → `stopAll()` (user-initiated off)
  - `recording` → stop VAD → `PROCESSING`
  - `processing` → abort STT fetch → `LISTENING`
  - `responding` → abort LLM WS → `LISTENING` (skip TTS)
  - `speaking` → cancel TTS → `OFF` (full cleanup)

- [ ] **Step 2: Implement `WakeWordEngine` in `voice.js`**

- `start()`: `getUserMedia({ audio: true })` → create `AudioContext` → create `AudioWorklet` (inline or separate file `frontend/js/voice-worklet.js`) that:
  - Resamples input to 16 kHz mono Int16 (polyphase filter or simple linear interpolation)
  - Writes to a 2.5 s ring buffer (40 000 samples)
  - Sends 100 ms chunks (6400 bytes) to `WebSocket /ws/wake-word`
- On WebSocket `onmessage`: parse JSON; if `type === 'wake'`:
  1. Drain last 2.0 s from ring buffer → convert to WAV (16 kHz mono Int16)
  2. Prepend to MediaRecorder capture
  3. Start `MediaRecorder` (webm/opus)
  4. Transition to `RECORDING`
- `stop()`: close WebSocket, stop worklet

- [ ] **Step 3: Implement `VadRecorder` in `voice.js`**

- `start(preBufferBlob)`: create `MediaRecorder` on the `MediaStream`; if `preBufferBlob` exists, record it first (or prepend to final Blob); start `AudioContext` + `AnalyserNode`
- RMS loop every ~50 ms: read `AnalyserNode.getFloatTimeDomainData()`, compute RMS
- Noise floor: on start, take min RMS over 500 ms of silence
- Threshold = `noiseFloor × vadSensitivity`
- If RMS < threshold for `vadSilenceMs` consecutive → stop recording
- `stop()`: stop `MediaRecorder`, return combined `Blob` (preBuffer + recorded)
- `pause()`: `AudioContext.suspend()` + `ringBuffer.clear()` (echo prevention)
- `resume()`: `AudioContext.resume()` (ring buffer already clear)

- [ ] **Step 4: Implement `SttClient` in `voice.js`**

- `transcribe(blob, settings)`: 
  - If `settings.sttProvider === 'local'`: convert Blob → base64 → `POST /api/stt-local` `{ audio_b64, mime: 'audio/webm' }`
  - If `settings.sttProvider === 'cloud'`: convert Blob → base64 → `POST /api/stt` `{ audio_b64, mime: 'audio/webm', use_settings_key: true }`
  - 30 s timeout via `AbortController`
  - On response: if `ok` → return text; if `error === 'model_not_found'` and `sttProvider === 'local'` → check cloud key via `window.api.secrets.status()` → if cloud key present, retry with cloud; else → throw with specific error message

- [ ] **Step 5: Implement `TtsPlayer` in `voice.js`**

- `speak(text, settings)`:
  - If `settings.ttsProvider === 'browser'`: `new SpeechSynthesisUtterance(text)`; set `voice` from `settings.ttsVoiceId` (or default); `speechSynthesis.speak()`; return `onend` promise
  - If `'elevenlabs'` or `'openai'`: `POST /api/media/generate` `{ kind: 'audio', prompt: text, use_settings_key: true, provider: settings.ttsProvider }` → get audio blob → play via `Audio` element; return `onended` promise
  - Before speak: call `vadRecorder.pause()` (suspends AudioContext + clears ring buffer)
  - After speak ends: call `vadRecorder.resume()`
- `cancel()`: `speechSynthesis.cancel()` or stop Audio element

- [ ] **Step 6: Wire the full pipeline in `voice.js`**

On `RECORDING` complete (VAD stop):
1. Transition → `PROCESSING`
2. Call `SttClient.transcribe(blob, settings)`
3. If transcript empty → toast "Ничего не распознано" → `LISTENING`
4. If STT error/timeout → toast → `LISTENING`
5. Call `window.addUserMessage(transcript)` — transcript appears in chat
6. Transition → `RESPONDING`
7. Call `window.streamViaWebSocket(transcript, history, agentId, null)` — existing LLM pipeline
8. On LLM stream complete → if `ttsProvider !== 'none'`: transition → `SPEAKING`; call `TtsPlayer.speak(fullAnswer, settings)`
9. On TTS end → transition → `LISTENING`

On model+key both missing (detected during `init` or first `startListening`):
1. Toast: "Голосовое управление недоступно: нет ни локальной модели, ни облачного ключа"
2. Show "Открыть настройки" button in toast
3. Transition → `OFF`

- [ ] **Step 7: Implement `init()` and attach to `#voiceBtn`**

- `voice.init(settings)`: store settings; check `#voiceBtn` exists; attach click handler; check `getUserMedia` availability; call `GET /api/voice/status` to check model readiness
- `beforeunload` → `voice.stopAll()` (called from `main.js`)

- [ ] **Step 8: Commit**

```bash
git add frontend/js/voice.js frontend/js/voice-worklet.js
git commit -m "feat: add voice.js module with state machine, wake word, VAD, STT, TTS"
```

---

### Task 6: Frontend — CSS, HTML, i18n, and Settings UI

**Files:**
- Create: `frontend/css/voice.css`
- Modify: `frontend/home.html` (add `#voiceBtn` + `sec-voice` + `sec-providers`)
- Modify: `frontend/js/i18n.js` (add all voice + provider strings)
- Modify: `frontend/js/main.js` (load `voice.css` + `voice.js`; wire `sec-voice` save/load; wire `secrets` IPC from sec-providers UI; `beforeunload` cleanup)

**Interfaces:**
- Consumes: `voice.js` public API (Task 5), `window.api.secrets` (Task 4), existing settings save/load pattern in `main.js`
- Produces:
  - `#voiceBtn` in `#composerToolsPop` with SVG mic icon + 6 state classes
  - `sec-voice` section: wake word input, VAD silence slider, VAD sensitivity slider, save button
  - `sec-providers` section: STT provider radio (cloud/local), cloud base URL + API key + model, local model path, TTS provider dropdown, TTS voice ID, TTS API key, save + reset buttons
  - i18n keys: all `voice.*` and `providers.*` strings from spec §i18n

- [ ] **Step 1: Create `frontend/css/voice.css`**

- `.voice-btn` base: same as `.attach-btn` but with state-specific colors
- `.voice-btn.off` — `color: #666`
- `.voice-btn.listening` — `color: #4a9eff; animation: voice-pulse 1.5s infinite`
- `.voice-btn.recording` — `color: #ff4444; animation: voice-blink 0.6s infinite`
- `.voice-btn.processing` — `color: #ffaa00; ::after spinner`
- `.voice-btn.responding` — `color: #00cccc; animation: voice-subtle-pulse 2s infinite`
- `.voice-btn.speaking` — `color: #44cc88; animation: voice-subtle-pulse 2s infinite`
- `@keyframes voice-pulse` — scale 1.0→1.15→1.0 + opacity ring
- `@keyframes voice-blink` — opacity 1→0.3→1
- `@keyframes voice-subtle-pulse` — scale 1.0→1.05→1.0
- Import `voice.css` from `home.html` (add `<link>`) and load `voice.js` (add `<script>`)

- [ ] **Step 2: Add `#voiceBtn` to `#composerToolsPop` in `home.html`**

Insert after the last existing button (`#sysInteractionToggle`):
```html
<button id="voiceBtn" class="attach-btn voice-btn off" title="Голосовое управление">
  <svg class="ic" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
    <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
    <line x1="12" y1="19" x2="12" y2="23"/>
    <line x1="8" y1="23" x2="16" y2="23"/>
  </svg>
</button>
```

- [ ] **Step 3: Add `sec-voice` and `sec-providers` sections in `home.html`**

Add to settings subnav (after `sec-media`):
```html
<a href="#" data-sec="sec-voice" data-i18n="s_voice">Голос</a>
<a href="#" data-sec="sec-providers" data-i18n="s_providers">Провайдеры</a>
```

Add two `<section>` elements following the existing pattern (e.g. `sec-media`):

**`sec-voice`:**
- `#wakeWordInput` (text, default "Астра", `data-i18n="voice.wakeWord"`)
- `#vadSilenceSlider` (range 500–10000, default 2000, shows value)
- `#vadSensitivitySlider` (range 1.2–3.0 step 0.1, default 1.8, shows value)
- `#voiceSaveBtn` — save button

**`sec-providers`:**
- STT Provider radio: `#sttProviderCloud` / `#sttProviderLocal` (default: local)
- Cloud STT: `#cloudSttBaseUrl` (text), `#cloudSttKey` (password, shows "•••••••• Saved"), `#cloudSttModel` (text, default "whisper-1")
- Local STT: `#localSttModelPath` (text, empty = auto)
- TTS Provider dropdown: `#ttsProvider` (browser/elevenlabs/openai, default browser)
- TTS Voice ID: `#ttsVoiceId` (text/select)
- TTS API Key: `#ttsKey` (password, shows "•••••••• Saved")
- `#providersSaveBtn`, `#providersResetBtn`

- [ ] **Step 4: Add i18n strings to `frontend/js/i18n.js`**

Add all `voice.*` and `providers.*` keys to both `ru` and `en` objects in the `I18N` constant. Include `{wakeWord}` interpolation placeholder in `voice.btn.listening`.

- [ ] **Step 5: Wire settings save/load in `frontend/js/main.js`**

- On page load: read `sec-voice` + `sec-providers` values from `settings.json` (via existing settings load); populate DOM
- On `#voiceSaveBtn` click: read DOM → save to `settings.json` via existing settings save; call `voice.init(newSettings)`
- On `#providersSaveBtn` click: read DOM; for API keys → call `window.api.secrets.set({ provider, key })`; for non-secret fields → save to `settings.json`
- On `#providersResetBtn` click: reset all to defaults; clear keys via `window.api.secrets.clear`
- On API key fields: on load, call `window.api.secrets.status()` → show "Saved" indicator if provider key exists
- `beforeunload` listener: call `voice.stopAll()`

- [ ] **Step 6: Commit**

```bash
git add frontend/css/voice.css frontend/home.html frontend/js/i18n.js frontend/js/main.js
git commit -m "feat: add voice UI, settings sections, i18n strings, and main.js wiring"
```

---

### Task 7: Frontend — `voice.js` Edge Cases + Integration Tests

**Files:**
- Modify: `frontend/js/voice.js` (edge case handling from spec)
- Create: `tests/test_voice_state.js`
- Modify: `tests/run_js_tests.js` (add `test_voice_state.js`)

**Interfaces:**
- Consumes: `voice.js` public API (Task 5), `VoiceStateMachine` (Task 5)
- Produces: passing state machine test; all edge cases from spec §Edge Cases handled

**Edge cases to implement/verify (from spec):**

| Event | Behavior | Where in voice.js |
|-------|----------|-------------------|
| Empty transcript | Toast "Ничего не распознано" → LISTENING | After STT call in pipeline |
| STT timeout (>30 s) | AbortController → toast "Ошибка STT: таймаут" → LISTENING | SttClient.transcribe |
| Mic click during RESPONDING | Abort LLM WS → LISTENING (no TTS) | VoiceStateMachine click handler |
| Mic click during SPEAKING | `speechSynthesis.cancel()` → OFF + cleanup | VoiceStateMachine click handler |
| Mic click during PROCESSING | Abort STT fetch → LISTENING | VoiceStateMachine click handler |
| Model+key both missing | Toast + "Открыть настройки" → OFF | voice.init / startListening |
| beforeunload | `track.stop()` per track → close AudioContext → close WS | voice.stopAll |
| Auto-timeout 10 min in LISTENING | → OFF + toast "Голосовой режим завершён (таймаут)" | VoiceStateMachine timer |

- [ ] **Step 1: Write `tests/test_voice_state.js`**

Test the state machine transitions (mock all external deps):
- `test_off_to_listening`: `state = 'off'`; call `startListening()`; expect `state === 'listening'`
- `test_listening_to_recording`: mock wake word event; expect `state === 'recording'`
- `test_recording_to_processing`: mock VAD stop; expect `state === 'processing'`
- `test_processing_to_responding`: mock STT success; expect `state === 'responding'`
- `test_responding_to_speaking`: mock LLM complete; expect `state === 'speaking'`
- `test_speaking_to_listening`: mock TTS end; expect `state === 'listening'`
- `test_click_during_responding`: mock state `responding`; click → expect `state === 'listening'` and WS aborted
- `test_click_during_speaking`: mock state `speaking`; click → expect `state === 'off'` and TTS cancelled
- `test_click_during_processing`: mock state `processing`; click → expect `state === 'listening'` and fetch aborted
- `test_empty_transcript_stays_listening`: mock STT return `""`; expect toast + `state === 'listening'`
- `test_stt_timeout_stays_listening`: mock STT timeout; expect toast + `state === 'listening'`
- `test_auto_timeout_10min`: mock 10 min in listening; expect `state === 'off'`
- `test_stop_all_stops_tracks`: mock `MediaStream` with 2 tracks; call `stopAll()`; expect both `track.stop()` called
- `test_model_key_both_missing`: mock `/api/voice/status` → `modelReady: false`, `secrets.status` → `{ providers: [] }`; expect toast + `state === 'off'`

Run: `node tests/run_js_tests.js`
Expected: FAIL (test file doesn't exist yet in runner)

- [ ] **Step 2: Add `test_voice_state.js` to `tests/run_js_tests.js`**

Add to the files array: `test_voice_state.js`

- [ ] **Step 3: Implement missing edge cases in `voice.js`**

Verify all 8 edge cases from the table above are handled. Add any missing:
- Empty transcript check after STT
- AbortController for STT fetch (30 s)
- Mic click handlers per state (already in Task 5 Step 1, verify completeness)
- `stopAll()`: iterate `mediaStream.getTracks()` → `track.stop()` for each; close `AudioContext`; close WebSocket; clear auto-timeout timer
- Auto-timeout: `setInterval` or `setTimeout` (600000 ms) in LISTENING; reset on wake word detection; on fire → `stopAll()` + toast

- [ ] **Step 4: Run all JS tests**

Run: `node tests/run_js_tests.js`
Expected: PASS (all test files including `test_voice_state.js`)

- [ ] **Step 5: Commit**

```bash
git add tests/test_voice_state.js tests/run_js_tests.js frontend/js/voice.js
git commit -m "feat: implement voice edge cases and add state machine tests"
```

---

### Task 8: `requirements.txt` + Final Verification

**Files:**
- Modify: `requirements.txt` (add `vosk`)

- [ ] **Step 1: Add `vosk` to `requirements.txt`**

Run: `pip install vosk` (verify it installs cleanly on the project's Python)
Expected: success (vosk wheel available for Windows)

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v && node tests/run_js_tests.js`
Expected: all PASS

- [ ] **Step 3: Manual integration check (spec §Integration Checks)**

- [ ] Click mic → Vosk streaming starts, button turns blue with pulse
- [ ] Say «Астра» → button turns red, VAD recording starts
- [ ] Say a request, stop speaking for 2 s → recording stops, button turns yellow
- [ ] STT returns transcript → appears as user message in chat
- [ ] AI responds → bot message + TTS speaks, button turns green
- [ ] TTS ends → button back to blue (listening)
- [ ] Click mic again → button turns gray (off), all resources cleaned up
- [ ] Save an API key → field shows "•••••••• Saved", key NOT in `settings.json`
- [ ] Clear an API key → field shows "Ключ не задан", key removed from `secrets.bin`
- [ ] Invalid model path → warning toast, falls back to auto-downloaded model
- [ ] Close window while voice active → `beforeunload` cleans up mic, no zombie lock
- [ ] Background fan noise → does NOT trigger VAD recording

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add vosk to requirements"
```
