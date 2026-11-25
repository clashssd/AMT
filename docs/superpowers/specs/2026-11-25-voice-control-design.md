# AMT Chat — Voice Control Feature Design

> **Date:** 2026-11-25  
> **Feature:** Full voice-control pipeline: Wake Word → VAD Recording → STT → LLM → TTS + Chat UI

---

## Intent & Why

The user wants AMT Chat to be fully voice-usable: a user says a custom wake word («Астра» by default), speaks a request, the AI answers — both in the chat (text) and spoken aloud. The goal is a hands-free interaction loop on desktop without needing to click or type.

**Who:** Desktop user running AMT Chat (Electron + FastAPI).  
**Why:** Reduce friction to zero for quick queries; match the "AI assistant" feel of the app.

---

## Goals

1. **Wake Word detection** — local, offline, custom word, default «Астра»
2. **VAD-based recording** — MediaRecorder + AudioContext RMS, auto-stop after 2 s silence (configurable)
3. **STT** — local Vosk (default, needed for wake word) **or cloud** (existing `/api/stt`); user picks in Settings
4. **LLM** — existing chat pipeline (`streamViaWebSocket`)
5. **TTS** — browser `speechSynthesis` (default) / ElevenLabs / OpenAI (user picks)
6. **Chat UI** — transcript appears as a user message; AI answer appears as a bot message (typewriter already works)
7. **Mic button** in the composer tools pop-up (hidden menu near paperclip) with 5 visual states
8. **Settings** — new `sec-voice` section: STT provider, TTS provider, wake-word string, silence timeout, VAD sensitivity
9. **Secrets Architecture** — API keys never stored in `settings.json` or `localStorage`; encrypted via Electron `safeStorage` in the main process, kept in a separate `secrets.bin` in `userData`
10. **Configuration Precedence** — user-provided values override repository defaults; if a user value is invalid or missing, fall back to the default silently

## Non-Goals

- Local TTS (Silero) — v2
- Multi-language wake word — single word, configurable
- Speaker identification
- Continuous always-on listening (battery/privacy) — wake word starts the session, user can stop
- In-app model training — user provides pre-trained model files only

## Anti-Goals

- No background noise must trigger VAD start (fan, street) — threshold tuning
- No echo: mic must be muted/paused while TTS speaks
- No API keys in `settings.json` or `localStorage`
- No secrets visible in renderer after save (show only "•••••••• Saved")

---

## Constraints

- **Electron + vanilla JS** (no React/Vue)
- **Frontend served via FastAPI StaticFiles** at `127.0.0.1:8000`
- **No Node integration in renderer** (`contextIsolation: true`, `nodeIntegration: false`)
- **Mic access** requires `getUserMedia` — must be granted in Electron (works out of the box in Chromium)
- **TTS echo** — `speechSynthesis.speak()` plays from speakers; mic must be suspended during playback
- **Background noise** — VAD threshold must be above ambient noise floor
- **Secrets** — must not be readable from the renderer; only the Electron main process can decrypt them

---

## Secrets Architecture

> **Critical principle: no secrets in `settings.json`, no secrets in the renderer.**

### How it works

```
┌─────────────────────────────────────────────────────────────────┐
│  RENDERER (Electron, contextIsolation: true)                   │
│                                                                │
│  User types API key into password field in sec-voice          │
│       │                                                        │
│       ▼                                                        │
│  ipcRenderer.invoke('secrets:set', {                          │
│      provider: 'openai',                                       │
│      key: 'sk-...'                                            │
│  })                                                           │
└─────────────────────────────────────────────────────────────────┘
                           │ IPC
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  MAIN PROCESS (Electron)                                      │
│                                                                │
│  safeStorage.encryptString(key)  →  encrypted blob            │
│       │                                                        │
│       ▼                                                        │
│  Append/replace in userData/secrets.bin                       │
│  (format: JSON { provider: encryptedKey, ... })                │
│                                                                │
│  When FastAPI backend needs the key:                          │
│  main process decrypts → sends to sidecar via internal channel│
│  (localhost HTTP with one-time token, or shared memory)        │
│  Renderer NEVER sees the decrypted key.                       │
└─────────────────────────────────────────────────────────────────┘
```

### Files

| File | What |
|------|------|
| **safeStorage** — OS-level encryption | Windows: **DPAPI** (Data Protection API), macOS: Keychain, Linux: libsecret. Protects against other users on the machine, **not** against other apps running as the same user |
| `userData/secrets.bin` | Encrypted JSON: `{ "openai_key": "<base64 encrypted>", "elevenlabs_key": "..." }` — encrypted via safeStorage |
| `settings.json` | **Non-secret** settings only: providers, model paths, thresholds, voice IDs |

### IPC channels (added to `electron/ipc.js` + `electron/preload.js`)

```
// Renderer → Main
'secrets:set'    (provider: string, key: string) → { ok: true }
   main process: encrypt → secrets.bin → POST /internal/secrets to sidecar
'secrets:clear'  (provider: string)              → { ok: true }
   main process: remove from secrets.bin → DELETE /internal/secrets to sidecar
'secrets:status' ()                              → { providers: ['openai', 'elevenlabs'] }  // which keys exist (not the values)

// Main → FastAPI sidecar (internal, 127.0.0.1 only, token-protected)
POST   /internal/secrets  { provider, key }   — push decrypted key at runtime (no restart)
DELETE /internal/secrets  { provider }          — remove key at runtime
Env var AMT_INTERNAL_TOKEN — one-time token, passed to sidecar at startup
```

### Key display in UI

- After saving a key: field shows `•••••••• Saved` — never the value
- On load: `secrets:status` tells which providers have keys; renderer shows "Saved" indicator
- User can clear a key: `secrets:clear` removes it from `secrets.bin`

---

## Configuration Precedence

For every setting, the rule is: **user value (if valid) → repository default**.

| Setting | Repository default | User override | Stored in |
|---------|-------------------|---------------|-----------|
| STT provider | `local` (Vosk, auto-downloaded model) | `cloud` or `local` | `settings.json` |
| STT API key | empty → backend returns clear error | user-provided key | **`secrets.bin`** (encrypted) |
| TTS provider | `browser` (speechSynthesis) | `browser` / `elevenlabs` / `openai` | `settings.json` |
| TTS API key | empty | user-provided key | **`secrets.bin`** (encrypted) |
| TTS voice ID | system default | user-selected voice | `settings.json` |
| Vosk model path | `backend/models/vosk-model-small-ru/` (auto-downloaded on first run) | user-provided path | `settings.json` (path is not a secret) |
| Wake-word string | `«Астра»` (built-in) | user-chosen string (e.g. «Рудеус») | `settings.json` (string, not a secret) |
| Silence timeout | `2000` ms | user-adjusted (500–10000) | `settings.json` |
| VAD sensitivity | `1.8×` | user-adjusted (1.2–3.0) | `settings.json` |

**Vosk model selection logic (backend, at startup):**
```python
if settings.vosk_model_path and os.path.isdir(settings.vosk_model_path):
    model = VoskModel(settings.vosk_model_path)
else:
    model = VoskModel(DEFAULT_VOSK_MODEL_PATH)  # backend/models/vosk-model-small-ru/ (auto-downloaded on first run)
```

**Custom wake-word string:** the user types a custom word (e.g. «Рудеус») in Settings. No model file needed — the Vosk engine checks the transcript for the string. No in-app training.

---

## Approaches Considered

### A. Wake Word Engine

> **Critical decision (2026-11-25):** Porcupine Free Tier was discontinued on 30.06.2026.
> Remaining access is a 7-day trial + paid plans from $6,000/year.
> Since the requirement is **fully free**, Porcupine is **excluded** from the primary path.

| Option | Pros | Cons |
|--------|------|------|
| **Vosk string-match in transcript** | Free, uses same model as local STT, no extra deps | Requires continuous STT stream (more CPU); detection = keyword match, not acoustic model |
| **Porcupine (if paid)** | Accurate acoustic wake word | Not free as of June 2026; trial only |
| **openWakeWord** | Open, ONNX models | Needs pre-trained custom model (harder to obtain) |
| **Browser SpeechRecognition** | Zero deps | Not custom-word, online only, unreliable |

**Decision: Vosk string-match on continuous transcript.**

- Uses the same Vosk model as local STT (no extra model download)
- Continuous mode: feed audio chunks to Vosk in real-time; on each final/interim result, check if the last N words contain the wake word (case-insensitive, with normalization)
- If matched → trigger RECORDING state
- This means: **local STT (Vosk) must be the default**, not cloud — otherwise the wake word loop has no audio pipeline
- Cloud STT remains available for high-accuracy transcription of the final utterance, but the wake-word detection loop uses Vosk

> **Porcupine note:** If the user later wants to upgrade to a paid acoustic wake word engine, the architecture is compatible: swap the `WakeWordEngine` interface from Vosk-match to `@picovoice/porcupine-web`. Not in scope for v1.

### B. STT

| Option | Pros | Cons |
|--------|------|------|
| **Cloud (existing `/api/stt`)** | Already wired, works with OpenAI/Whisper/ElevenLabs keys | Needs API key, network |
| **Local Vosk** | Free, offline, auto-downloaded model (~50 MB on first run), no API key | Slightly less accurate than Whisper; small-ru may misrecognize short words like «Астра» (handled by alias + fuzzy match) |

**Decision: Both, user picks in Settings. Default: `local` (Vosk).**

- `local` (default): new backend endpoint `/api/stt-local` using Vosk; model auto-downloaded on first run (Python-side, ~50 MB); model path from `settings.json` (default: `backend/models/vosk-model-small-ru`)
- `cloud`: existing `/api/stt` + API key from `secrets.bin`; use when higher accuracy is needed or when Vosk model is unavailable
- **Why local is default:** the wake-word loop runs on the same Vosk stream — no separate acoustic model, no extra API calls for detection
- If Vosk model download fails on first run → auto-fallback to Cloud STT (show toast, user still functional)

### C. TTS

| Option | Pros | Cons |
|--------|------|------|
| **Browser `speechSynthesis`** | Zero deps, free, built-in, works offline | Robotic voices, limited voice selection |
| **Custom (OpenAI-compatible)** | Any OpenAI-compatible TTS endpoint (`{ttsBaseUrl}/v1/audio/speech` with model `ttsModel`); max flexibility | Needs API key (in `secrets.bin`), network |
| **ElevenLabs** | High quality | Needs API key (in `secrets.bin`), network |
| **OpenAI TTS** | High quality | Needs API key (in `secrets.bin`), network |

**Decision: Browser `speechSynthesis` as default**, `custom`/ElevenLabs/OpenAI as optional upgrades in Settings. API keys stored in `secrets.bin`. If cloud/custom TTS fails → auto-fallback to browser `speechSynthesis`.

### D. Settings Location

The composer tools pop-up (`#composerToolsPop`) gets the mic button. Voice settings go into a **new `sec-voice` section** in the Settings page, plus a **new `sec-providers` section** for STT/TTS provider and key management (shared with the existing media keys section but restructured to use `secrets.bin`).

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  RENDERER (Electron, contextIsolation: true)                    │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Wake Word   │  │ VAD +        │  │ TTS          │           │
│  │ (Vosk match)│→ │ MediaRecorder│→ │ (speechSynth)│           │
│  │             │  │ + RMS        │  │              │           │
│  └─────────────┘  └──────────────┘  └──────────────┘           │
│       │                 │                    │                  │
│       ▼                 ▼                    ▼                  │
│  state: listening   state: recording   state: speaking          │
│       │                 │                    │                  │
│       └────────┬────────┘                    │                  │
│                ▼                             │                  │
│  ┌──────────────────────────────────────┐    │                  │
│  │ STT: cloud (/api/stt) or local      │    │                  │
│  │ (/api/stt-local, Vosk)              │    │                  │
│  └──────────────────────────────────────┘    │                  │
│                │                             │                  │
│                ▼                             │                  │
│         ┌─────────────┐                      │                  │
│         │ LLM (existing)                    │                  │
│         │ streamViaWebSocket                  │                  │
│         └─────────────┘                      │                  │
│                │                             │                  │
│                ▼                             │                  │
│         ┌─────────────┐                      │                  │
│         │ Chat UI     │←─────────────────────┘                  │
│         │ (text + TTS)│                                          │
│         └─────────────┘                                          │
│                                                                 │
│  Secrets: renderer NEVER sees decrypted keys                   │
│  Keys stored in userData/secrets.bin (safeStorage encrypted)   │
└──────────────────────────────────────────────────────────────────┘
```

## Why Vosk on the Backend (not vosk-browser)

- **Single recognizer instance:** the wake-word stream and the batch STT call share one `KaldiRecognizer` on the backend. No duplicate model in memory, no `SharedArrayBuffer` cross-origin requirement in the renderer.
- **No `SharedArrayBuffer`:** `vosk-browser` needs `SharedArrayBuffer` for WASM, which requires COOP/COEP headers — not trivial in an Electron app served from FastAPI.
- **Simpler frontend:** the renderer just sends audio bytes over a WebSocket; all DSP stays in Python.
- **Custom wake word is a string, not a model:** the user types any phrase (e.g. «АМТ», «Рудеус») in Settings; the backend normalizes the Vosk transcript and checks for the string (or its fuzzy aliases). No per-word model files.

---

## Wake-Word Streaming Protocol

> **Problem:** `/api/stt-local` is a batch-POST with `audio_b64`. Wake word needs a **continuous stream** where `KaldiRecognizer.PartialResult()` is called on every 100 ms chunk, not on a finished file.

### Chosen: WebSocket `/ws/wake-word` (recognizer lives on the backend per session)

**Why not `vosk-browser` in the renderer:**
- Requires `SharedArrayBuffer` (COOP/COEP headers) — hard to configure in an Electron app served from FastAPI
- Duplicates the Vosk model in renderer memory; two recognizers = two 50 MB allocations
- `KaldiRecognizer` is stateful; managing state across the WASM boundary is fragile

**WebSocket protocol:**

```
Renderer → /ws/wake-word (upgrade)
  │  On open: backend creates a session-scoped KaldiRecognizer (from current model path)
  │
  │  Every ~100 ms, renderer sends a binary frame:
  │    16 kHz mono Int16, 3200 samples = 6400 bytes
  │
  │  Backend per frame:
  │    rec.AcceptWaveform(data)
  │    if rec.AcceptWaveform(data):  # final result
  │        text = json.loads(rec.Result())["text"]
  │        if wake_word_match(text, settings.wake_word_string):
  │            send back: {"type": "wake", "text": text, "alias": matchedAlias}
  │            reset rec (rec.Reset())  ← so the wake word itself doesn't leak into the next command
  │    else:  # partial
  │        text = json.loads(rec.PartialResult())["partial"]
  │        if wake_word_match(text, settings.wake_word_string):
  │            send back: {"type": "wake", "text": text, "alias": matchedAlias}
  │            rec.Reset()
  │
  │  On renderer close: backend discards the recognizer
```

**Resampling (who does it):**
- `getUserMedia` gives 44.1 kHz or 48 kHz Float32 (device sample rate)
- An **AudioWorklet** in the renderer runs a simple polyphase filter → 16 kHz Int16 mono
- The worklet writes into a `RingBuffer` (see below) and also feeds the 100 ms chunks to the WebSocket
- No `AudioContext` resampling; the worklet handles it sample-accurately

**Pre-buffer (ring buffer):**
- The AudioWorklet maintains a **2.5 s ring buffer** of Int16 samples at 16 kHz
- On wake-word detection, the renderer **drains the last 2.0 s** from the ring buffer
- Those 2 s of audio are prepended to the start of the `MediaRecorder` capture
- This catches "какая" in «Астра, какая погода?» — the word that already sounded while the wake word was still processing

**Post-detection reset:**
- After the WebSocket sends `{"type": "wake"}`, the backend calls `rec.Reset()`
- The next audio chunk starts a fresh recognition window — the wake word itself is not re-transcribed
- The renderer switches from wake-word streaming mode to VAD recording mode on the same WebSocket (or opens a new one for the command recording)

---

## Pre-Buffer (2.5 s ring buffer)

**Problem:** «Астра, какая погода?» → wake word detected after «Астра», but «какая» already sounded and would be lost.

**Solution:**

```
AudioWorklet (16 kHz Int16)
  │
  ├──► RingBuffer (2.5 s = 40 000 samples, circular)
  │       continuously overwritten
  │
  ├──► WebSocket /ws/wake-word  (100 ms chunks for Vosk streaming)
  │
  └──► MediaRecorder (started only on wake-word detection)

On wake-word detected:
  1. Drain RingBuffer.last(2.0 s) → 32 000 Int16 samples
  2. Convert to WAV (16 kHz mono Int16)
  3. Prepend to MediaRecorder capture start
  4. Start MediaRecorder (records forward from this point)
```

The pre-buffered 2 s ensures the first words of the command are not lost.

---

## TTS Echo & AudioContext Suspend

**Problem:** `AudioContext.suspend()` stops the AudioWorklet, which stops feeding the WebSocket, which stops the Vosk stream. On `resume()`, the ring buffer still contains TTS audio → the wake word could trigger on TTS tail.

**Solution:**

```
TTS start:
  1. vadRecorder.pause()          → AudioContext.suspend()
  2. ringBuffer.clear()          ← discard everything (TTS audio is in here)
  3. WebSocket stays open, but no data is sent (worklet is suspended)
  4. Backend: recognizer is NOT reset (it's idle, not receiving data)

TTS end:
  1. ringBuffer is already clear
  2. AudioContext.resume()
  3. AudioWorklet resumes → fresh audio from mic (no TTS tail)
  4. Vosk stream resumes; recognizer continues from where it left off
  5. Wake word CANNOT trigger on TTS tail because the buffer was cleared

Important: the backend recognizer is NOT recreated on resume.
           It simply receives new audio; partial results resume normally.
```

---

## State Machine (mic button)

```
  OFF (gray)
   │  user clicks mic
   ▼
  LISTENING (blue, pulsing)  ── Vosk wake-word stream active
   │  wake word detected (with 2 s pre-buffer drained)
   ▼
  RECORDING (red)            ── VAD recording, MediaRecorder running
   │  silenceMs timeout OR user clicks stop
   ▼
  PROCESSING (yellow, spinner)  ── STT in progress (cloud or local batch)
   │  transcript ready
   ▼
  RESPONDING (cyan #00cccc, subtle pulse)  ── LLM streaming via WebSocket
   │  LLM stream complete
   ▼
  SPEAKING (green)           ── TTS playing, mic suspended, ring buffer cleared
   │  TTS done
   ▼
  LISTENING (blue, pulsing)  ── back to waiting for next command
   │  user clicks X / Esc OR auto-timeout (10 min without wake word)
   ▼
  OFF (gray)
```

### Fallback Logic

- **STT:** If cloud STT fails (HTTP error, timeout, or 401/403) and local Vosk model is ready → auto-fallback to local. Toast: "Облачный STT недоступен — использую локальный Vosk"
- **TTS:** If cloud/custom TTS fails → auto-fallback to browser `speechSynthesis`. Toast: "Облачный TTS недоступен — использую браузерный голос"
- **Browser (no Electron):** `window.api` is undefined → `window.api?.secrets?.set(...)` safely no-ops; keys stored in `localStorage` with console warning. App must not crash.

### TTS Granularity

**Decision: TTS speaks the full LLM answer, not per-sentence.**

- Simpler: one `SpeechSynthesisUtterance` with the full text
- Per-sentence TTS would require splitting the stream mid-flight, which races with the WebSocket chunks
- If the answer is very long (>5 min of speech), the user can interrupt by clicking the mic button (→ OFF)

---

## Edge Cases

| Event | Behavior |
|-------|----------|
| **Empty transcript** (STT returns empty string) | Skip LLM call; show toast "Ничего не распознано"; return to LISTENING |
| **STT timeout** (>30 s no response) | Abort fetch; show toast "Ошибка STT: таймаут"; return to LISTENING |
| **User clicks mic during RESPONDING** | Abort the LLM WebSocket (`currentWs.close()`); do NOT start TTS; state → LISTENING |
| **User clicks mic during SPEAKING** | `speechSynthesis.cancel()`; state → OFF; cleanup all resources |
| **User clicks mic during PROCESSING** | Abort STT fetch (AbortController); state → LISTENING |
| **Vosk model missing AND cloud key missing** | Toast: "Голосовое управление недоступно: нет ни локальной модели, ни облачного ключа" + button «Открыть настройки»; state → OFF |
| **Vosk model missing, cloud key present** | Auto-fallback to Cloud STT; toast "Локальная модель не найдена — использую облако" |
| **Cloud STT key missing, local model present** | Use local Vosk; no error |
| **`beforeunload` / window close** | `voice.stopAll()`: for each `MediaStreamTrack` in the `MediaStream` → `track.stop()`; close AudioContext; close WebSocket; prevent zombie mic lock |
| **Auto-timeout** (no wake word for 10 min in LISTENING) | State → OFF; show toast "Голосовой режим завершён (таймаут)" |

### Mic Button Visual States (CSS classes on `.voice-btn`)

| State | Class | Color | Animation |
|-------|-------|-------|-----------|
| Off | `.voice-btn.off` | `#666` (gray) | none |
| Listening | `.voice-btn.listening` | `#4a9eff` (blue) | pulse ring |
| Recording | `.voice-btn.recording` | `#ff4444` (red) | blink |
| Processing | `.voice-btn.processing` | `#ffaa00` (yellow) | spinner overlay |
| Responding | `.voice-btn.responding` | `#00cccc` (cyan) | subtle pulse |
| Speaking | `.voice-btn.speaking` | `#44cc88` (green) | subtle pulse |

---

## New Files

| File | Responsibility |
|------|----------------|
| `frontend/js/voice.js` | All voice logic: wake-word engine (Vosk string-match), VAD, MediaRecorder, STT call, TTS, state machine, mic button events |
| `frontend/css/voice.css` | Mic button styles, state classes, pulse animations |
| `backend/stt_local.py` | Vosk-based local STT: `/api/stt-local` endpoint, model loading logic, wake-word string-match helper |
| `electron/secrets.js` | `safeStorage` encryption/decryption, `secrets.bin` read/write, IPC handlers |
| `backend/models/vosk-model-small-ru/` | Vosk model (~50 MB) — **auto-downloaded on first run** (Python-side); if download fails, fall back to Cloud STT automatically |

## Modified Files

| File | Changes |
|------|---------|
| `frontend/home.html` | Add `#voiceBtn` (SVG mic) inside `#composerToolsPop`; add `sec-voice` and `sec-providers` in Settings page |
| `frontend/js/main.js` | Import `voice.js`; add `sec-voice` to settings save/load; call `secrets:set`/`secrets:clear`/`secrets:status` IPC |
| `frontend/js/i18n.js` | Add i18n strings for voice + provider labels |
| `package.json` | `main` (Electron entry) + voice deps | `main` is `"electron/main.js"` (Electron entry point, not `./main.js`). No new npm scripts. |
| `backend/main.py` | Add non-secret voice settings to `Settings` model; wire `/api/stt-local`; pass decrypted keys to sidecar |
| `electron/main.js` | Require `electron/secrets.js`; register `secrets:*` IPC handlers; pass decrypted keys to sidecar at startup |
| `electron/ipc.js` | Add `secrets:set`, `secrets:clear`, `secrets:status` handlers |
| `electron/preload.js` | Expose `window.api.secrets = { set, clear, status }` |

---

## Voice Module API (`voice.js`)

```js
// Public API (attached to window or exported)
const voice = {
  init(settings)       // called on page load + after settings save
  startListening()     // → LISTENING state (Vosk wake-word stream active)
  stopAll()            // → OFF state (cleanup everything: mic, AudioContext, streams)
  getState()           // returns 'off'|'listening'|'recording'|'processing'|'speaking'
  onStateChange(cb)    // subscribe to state changes (for CSS class updates)
}

// In main.js init:
window.addEventListener('beforeunload', () => { voice.stopAll(); });
```

### Internal Components

1. **`WakeWordEngine`** — continuous Vosk stream: feed 16 kHz audio chunks to `/api/stt-local` in streaming mode; on each interim/final result, check if the last 5 words contain the wake-word string (case-insensitive, normalized). On match → trigger RECORDING. No separate model file needed.
2. **`VadRecorder`** — MediaRecorder + AudioContext AnalyserNode; computes RMS every ~50 ms; if RMS < threshold for `silenceMs` consecutive → stops recording, returns Blob
3. **`SttClient`** — if `sttProvider === 'local'`: `POST /api/stt-local` with `{ audio_b64, mime }`; if `'cloud'`: `POST /api/stt` with `{ audio_b64, mime, use_settings_key: true }`
4. **`TtsPlayer`** — if `ttsProvider === 'browser'`: `speechSynthesis.speak(...)`; if `'elevenlabs'`/`'openai'`: `POST /api/media/generate` (key from sidecar, not renderer); mutes mic during playback
5. **`VoiceStateMachine`** — central state; coordinates all above; emits events to mic button

### Echo Prevention

- Before TTS playback: call `vadRecorder.pause()` (suspends AudioContext)
- After TTS ends: call `vadRecorder.resume()` (restarts AudioContext)
- This ensures the mic doesn't pick up the TTS audio

### VAD Threshold Strategy

- Compute ambient noise floor on wake: take min RMS over 500 ms of silence
- Threshold = noiseFloor × `vadSensitivity` (default 1.8, configurable 1.2–3.0)
- Silence timer resets only when RMS > threshold (not on every sample)

---

## Vosk Transcript Normalization & Fuzzy Match

**Problem:** `vosk-model-small-ru` is a small model. «Астра» comes back as «а страх», «а стра», «остра» depending on audio quality. A strict `===` match will miss most real detections.

### Normalization pipeline (applied to both the wake-word string and the Vosk transcript)

```python
def normalize(s: str) -> str:
    s = s.lower()
    s = s.replace('ё', 'е')
    s = re.sub(r'[^a-zа-я\s]', '', s)  # strip punctuation, digits
    return re.sub(r'\s+', ' ', s).strip()
```

### Alias table (generated automatically, user-editable in Settings JSON)

For the default «Астра», the alias list is:

```python
ALIASES = {
    "Астра": ["астр", "а стра", "астра", "остра", "а страх", "а стра"],
}
```

- The user can add more aliases in Settings (stored in `settings.json` as `wake_word_aliases: []`)
- If `wake_word_aliases` is empty, the system auto-generates: lowercased original + top-3 Levenshtein neighbors from a small Russian word list (built-in, ~5000 words, committed to repo)

### Fuzzy match

```python
from difflib import SequenceMatcher

def wake_word_match(transcript_norm: str, target_norm: str, aliases: list[str]) -> bool:
    # Exact alias match (fast path)
    words = transcript_norm.split()
    last_5 = ' '.join(words[-5:])
    for alias in aliases + [target_norm]:
        if alias in last_5:
            return True
    # Fuzzy: Levenshtein distance ≤ 2 on last 5 words joined
    for alias in aliases + [target_norm]:
        for candidate in words[-5:]:
            if lev(candidate, alias) <= 2:
                return True
    return False

def lev(a: str, b: str) -> int:
    # Standard Levenshtein, threshold-capped (early exit at distance > 2)
    ...
```

- Threshold: **distance ≤ 2** (configurable `vad_fuzzy_threshold` in settings, default 2)
- The match is checked against the **last 5 words** of the partial result, not the whole transcript
- This keeps CPU cost low and avoids false positives on older words

---

## Backend Changes

### New: `backend/stt_local.py`

```python
from vosk import KaldiRecognizer, Model
import os

DEFAULT_VOSK_PATH = os.path.join(os.path.dirname(__file__), "models", "vosk-model-small-ru")

_model = None

def load_vosk_model(model_path: str = None):
    global _model
    path = model_path or DEFAULT_VOSK_PATH
    if os.path.isdir(path):
        _model = Model(path)
    else:
        _model = Model(DEFAULT_VOSK_PATH)
    return _model

def transcribe_local(audio_b64: str, mime: str, model_path: str = None) -> dict:
    model = load_vosk_model(model_path)
    rec = KaldiRecognizer(model, 16000)
    # decode b64 → wav bytes, feed to rec.AcceptWaveform()
    # return { ok: True, text: result }
```

### `backend/main.py` — Settings model additions (non-secret only)

```python
# Voice control — non-secret settings (persisted in settings.json)
stt_provider: str = "local"       # "cloud" | "local" (local is default — needed for wake word)
stt_base_url: str = ""            # cloud STT base URL (empty = use existing audioBaseUrl)
stt_model: str = ""               # cloud STT model (empty = use existing sttModel)
tts_provider: str = "browser"      # "browser" | "custom" | "elevenlabs" | "openai"
tts_base_url: str = ""            # OpenAI-compatible TTS base URL (for 'custom' provider)
tts_model: str = ""               # OpenAI-compatible TTS model (for 'custom' provider)
tts_voice_id: str = ""             # empty = system default
vosk_model_path: str = ""          # empty = use auto-downloaded default (backend/models/vosk-model-small-ru)
wake_word_string: str = "Астра"    # the string to match in Vosk transcript
vad_silence_ms: int = 2000
vad_sensitivity: float = 1.8
```

> **API keys are NOT in this model.** They live in `secrets.bin`, managed by the Electron main process.

### New endpoint: `POST /api/stt-local`

```python
@app.post("/api/stt-local")
async def stt_local_transcribe(req: SttLocalRequest):
    result = stt_local.transcribe_local(req.audio_b64, req.mime, settings.vosk_model_path)
    return result
```

### Vosk Model Lifecycle

**Scenario: download on first run (Python-side, not npm).**

1. `backend/stt_local.py` on startup: if `backend/models/vosk-model-small-ru/` does not exist, download `vosk-model-small-ru.zip` (~50 MB) from `https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip` to `backend/models/`
2. Progress exposed via `GET /api/voice/status` → `{ modelReady: bool, modelProgress: 0.0-1.0, error: string|null }`
3. UI polls `/api/voice/status` on voice feature init; shows progress bar in the sec-voice section while downloading
4. If download fails (no internet, CDN down):
   - `modelReady: false`, `error: "download_failed"`
   - Voice feature falls back to **Cloud STT** if a cloud key is set
   - If no cloud key either → toast: "Голосовое управление недоступно: нет ни локальной модели, ни облачного ключа" + button «Открыть настройки» → state OFF
5. Backend `load_vosk_model()`: if user-specified path valid → use it; else if `backend/models/vosk-model-small-ru/` exists → use it; else return `{ ok: false, error: "model_not_found", fallback: "cloud" }`
6. Frontend `voice.js`: if `/api/stt-local` returns `model_not_found` → check cloud key via `/api/voice/status` → switch to Cloud for this session; show toast

**Custom model:** user points `vosk_model_path` to a folder with a larger Vosk model (e.g. `vosk-model-ru-0.42`). Backend loads it on next restart or on-demand. The download is a Python `urllib`/`requests` call in `stt_local.py` — no Node script involved.

### Key injection into sidecar

**Primary: runtime secrets endpoint (no restart needed).**

The Electron main process exposes two internal endpoints to the FastAPI sidecar:

```
POST /internal/secrets      { provider: string, key: string }   ← main process pushes decrypted key
DELETE /internal/secrets    { provider: string }                 ← main process removes key
```

These are on `127.0.0.1` only, protected by a one-time token generated at sidecar startup and passed via env var `AMT_INTERNAL_TOKEN`. The renderer never calls these endpoints.

Flow:
1. User saves a key in UI → `ipcRenderer.invoke('secrets:set', { provider, key })`
2. Main process encrypts via `safeStorage`, writes to `secrets.bin`
3. Main process immediately POSTs the decrypted key to `/internal/secrets`
4. FastAPI stores it in memory; next STT/TTS call uses it — **no restart**

**Fallback: env vars at startup.**

At Electron startup, `main.js` also reads `secrets.bin` and passes existing keys as env vars:
- `AMT_OPENAI_KEY`, `AMT_ELEVENLABS_KEY`, etc.
- This ensures keys are available even if the internal endpoint is not yet up
- Env vars are a fallback; the runtime endpoint is the primary mechanism

---

## Settings UI (`sec-voice` + `sec-providers`)

### `sec-voice` — Voice Control

```
┌─────────────────────────────────────────────────────────┐
│  🎤 Voice Control                                      │
│  ─────────────────────────────────────────────────────  │
│  Wake Word:  [Астра              ]                      │
│  (string matched in Vosk transcript; change to any word) │
│                                                          │
│  VAD Silence Timeout:  [══════●══════] 2000 ms           │
│  VAD Sensitivity:      [══════●══════] 1.8×             │
│                                                          │
│  [ Save Voice Settings ]                                │
└─────────────────────────────────────────────────────────┘
```

- **Wake Word** — text input; the string to match in the Vosk transcript; no model file needed; default «Астра»; user can type any word
- **Silence Timeout** — range slider 500–10000 ms, default 2000
- **VAD Sensitivity** — range slider 1.2–3.0, default 1.8

### `sec-providers` — Speech Providers (restructures existing media keys)

```
┌─────────────────────────────────────────────────────────┐
│  🔊 Speech Providers                                   │
│  ─────────────────────────────────────────────────────  │
│                                                          │
│  STT Provider:                                          │
│    ○ Cloud (requires API key)                           │
│    ◉ Local (Vosk, offline, no key needed)               │
│                                                          │
│  [Cloud STT]                                             │
│    Base URL:   [https://api.openai.com]                 │
│    API Key:    [•••••••• Saved] [Clear]                 │
│    Model:      [whisper-1]                              │
│                                                          │
│  [Local STT]                                             │
│    Model Path: [backend/models/vosk-model-small-ru]     │
│                  (empty = auto-downloaded default)     │
│                                                          │
│  ─────────────────────────────────────────────────────  │
│                                                          │
│  TTS Provider:                                          │
│    ◉ Browser (free, robotic)                            │
│    ○ Custom (OpenAI-compatible)                         │
│    ○ ElevenLabs                                         │
│    ○ OpenAI                                             │
│                                                          │
│  TTS Base URL:  [https://api.openai.com]                │
│  TTS Model:     [gpt-4o-mini-tts]                       │
│  TTS Voice ID:  [system default ▾]                      │
│                                                          │
│  [Custom/ElevenLabs/OpenAI TTS]                         │
│    API Key:    [•••••••• Saved] [Clear]                 │
│                                                          │
│  [ Save Provider Settings ]                             │
│  [ Reset to Defaults ]                                  │
└─────────────────────────────────────────────────────────┘
```

- **API Key fields** — password input; on save, calls `secrets:set(provider, key)`; shows "•••••••• Saved" after; "Clear" button calls `secrets:clear(provider)`
- **STT Provider radio** — switches between cloud/local; local shows model path field instead of API key
- **TTS Provider dropdown** — browser/elevenlabs/openai; if not browser, shows API key field
- **"Reset to Defaults"** — clears all user overrides; restores repository defaults

---

## i18n Strings (RU/EN)

```
voice.section         → "Голосовое управление" / "Voice Control"
voice.wakeWord        → "Слово-активатор" / "Wake Word"
voice.wakeWordHint    → "(строка в транскрипте Vosk; можно любое слово)" / "(string in Vosk transcript; any word)"
voice.silence         → "Пауза VAD (мс)" / "VAD Silence (ms)"
voice.vad             → "Чувствительность VAD" / "VAD Sensitivity"
voice.save            → "Сохранить голосовые настройки" / "Save Voice Settings"

providers.section     → "Голосовые провайдеры" / "Speech Providers"
providers.stt         → "Распознавание (STT)" / "Speech Recognition (STT)"
providers.sttCloud    → "Облако (нужен ключ)" / "Cloud (requires API key)"
providers.sttLocal    → "Локально (Vosk, офлайн)" / "Local (Vosk, offline)"
providers.sttBaseUrl  → "URL" / "URL"
providers.sttKey      → "Ключ API" / "API Key"
providers.sttModel    → "Модель" / "Model"
providers.sttModelPath → "Путь к модели Vosk" / "Vosk Model Path"
providers.tts         → "Озвучивание (TTS)" / "Text to Speech (TTS)"
providers.ttsBrowser  → "Браузер (бесплатно)" / "Browser (free)"
providers.ttsKey      → "Ключ API" / "API Key"
providers.voiceId     → "Идентификатор голоса" / "Voice ID"
providers.save        → "Сохранить провайдеров" / "Save Provider Settings"
providers.reset       → "Сбросить к базовым" / "Reset to Defaults"
providers.saved       → "Сохранён" / "Saved"
providers.clear       → "Очистить" / "Clear"
providers.noKey       → "Ключ не задан" / "No key set"

voice.btn.off         → "Голос выключен" / "Voice off"
voice.btn.listening   → "Слушаю… Скажите «{wakeWord}»" / "Listening… Say «{wakeWord}»"
voice.btn.recording   → "Запись… Говорите" / "Recording… Speak now"
voice.btn.processing  → "Распознаю…" / "Processing…"
voice.btn.speaking    → "Отвечаю…" / "Speaking…"
```

---

## Mic Button HTML (added to `#composerToolsPop`)

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

---

## Test Plan

### Unit Tests (node, in `tests/`)

| Test File | What it covers |
|-----------|----------------|
| `tests/test_voice_state.js` | VoiceStateMachine transitions: off→listening→recording→processing→speaking→listening |
| `tests/test_voice_vad.js` | VAD RMS threshold logic: mock AnalyserNode data, verify silence timer fires after `silenceMs` |
| `tests/test_voice_stt.js` | SttClient: verify correct endpoint (`/api/stt` vs `/api/stt-local`) based on `sttProvider` setting; verify request shape |
| `tests/test_voice_tts.js` | TtsPlayer: mock speechSynthesis, verify mic pause/resume during playback |
| `tests/test_secrets.js` | Mock `safeStorage` + `secrets.bin`: verify encrypt/decrypt round-trip; verify `secrets:status` returns provider list not values |
| `tests/test_vosk_local.py` | `stt_local.transcribe_local`: mock Vosk, verify model path selection (user vs auto-downloaded) |

### Integration Checks (manual)

- [ ] Click mic → Vosk streaming starts, button turns blue with pulse
- [ ] Say «Астра» → button turns red, VAD recording starts
- [ ] Say a request, stop speaking for 2 s → recording stops, button turns yellow
- [ ] STT (local or cloud) returns transcript → appears as user message in chat
- [ ] AI responds → appears as bot message, TTS speaks, button turns green
- [ ] TTS ends → button back to blue (listening)
- [ ] Click mic again → button turns gray (off), all resources cleaned up
- [ ] Set STT provider to Local → verify Vosk model loads (or auto-downloads on first run)
- [ ] Point Vosk model path to a custom model → verify it loads instead of auto-downloaded default
- [ ] Save an API key → field shows "•••••••• Saved", key NOT in settings.json
- [ ] Clear an API key → field shows "Ключ не задан", key removed from secrets.bin
- [ ] Change API key while app is running → next STT/TTS call uses new key (no restart)
- [ ] Invalid model path → warning toast, falls back to auto-downloaded model
- [ ] Vosk model missing → auto-fallback to Cloud STT, toast shown
- [ ] Empty transcript (silence recorded) → toast "Ничего не распознано", back to LISTENING
- [ ] STT timeout (>30 s) → toast "Ошибка STT: таймаут", back to LISTENING
- [ ] Click mic during SPEAKING → TTS interrupted, state → OFF
- [ ] Close window while voice active → `beforeunload` cleans up mic, no zombie lock
- [ ] Background fan noise → does NOT trigger VAD recording

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| DPAPI (Windows safeStorage) protects against other users but **not** against other apps running as the same user | Acceptable for local desktop app; document limitation; keys are encrypted at rest, not in transit |
| User points to invalid model path | Show clear warning toast; fall back to auto-downloaded model; never crash |
| API key invalid/expired | Backend returns clear error message; renderer shows "Ошибка STT: невалидный ключ" |
| `speechSynthesis` not available (rare Electron build) | Fallback: text-only, no TTS |
| `getUserMedia` denied | Show toast: "Доступ к микрофону отклонён" |
| High background noise resets VAD | Adjustable `vadSensitivity` (1.2–3.0×); user tunes in Settings |
| TTS echoes into mic | AudioContext suspended during TTS playback |
| Long STT response (slow network) | 30 s timeout; show "Ошибка STT: таймаут" |
| `safeStorage` unavailable (non-Electron context) | Fallback: show error, disable voice feature |
| `secrets.bin` corrupted | On read failure: treat as empty; show "Не удалось прочитать секреты"; user re-enters keys |
| Continuous Vosk WebSocket stream in LISTENING state = measurable CPU load (16 kHz mono, 100 ms chunks, ~3–5 % core) | Auto-timeout: after **10 minutes** in LISTENING with no wake word detected → state → OFF (mic stopped, WebSocket closed); user can re-enable by clicking mic button. Add note in sec-voice UI: "Голосовое управление активно ~10 мин без команды — отключается для экономии CPU". |

---

## Out of Scope (v2)

- Local TTS via Silero (needs ONNX runtime in backend)
- Multi-word wake phrases
- Speaker verification
- Audio playback history / transcripts
- In-app model training (user always provides pre-trained files)
