# Media Endpoint Paths in Settings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 optional endpoint-path fields (text→media, image→media, text+image→media, voice) to the "Медиа-ключи" settings page, persist them through the Settings model + `/api/settings` GET/POST, and have in-chat media generation always send them so the `generate_media` facade routes to the right endpoint (empty → `DEFAULT_PATH_*`).

**Architecture:** Per-kind layout — each path input sits directly under its kind's block (image path under "Картинки", video path under "Видео", voice path under "Голос"). The 4 camelCase settings fields flow `home.html` input → `buildSettingsFromInputs` → `toBackendSettings` → `Settings` pydantic model → `/api/settings` GET/POST → `loadSettings`/`loadMediaKeysUI` setVal. `renderGenInChat` (and the inline TTS call) build a `paths` object from the 4 settings values and include it in every `/api/media/generate` body; empty values resolve to `DEFAULT_PATH_*` inside the facade.

**Tech Stack:** Python 3 / FastAPI / Pydantic (backend), vanilla JS + HTML (frontend), pytest.

**Spec:** `docs/superpowers/specs/2026-11-25-media-facade-design.md` (facade design; this plan extends it with the settings surface for `user_paths`).

## Global Constraints

- **Provider-neutral.** All 4 new Settings fields default to `""` (empty). Empty means "use `DEFAULT_PATH_*`" in the facade. No hardcoded provider.
- **Optional fields.** A user who leaves a path empty gets the default path; a user who fills it in gets that value sent verbatim to the endpoint.
- **Always send `paths`.** JS always includes the `paths` object in `/api/media/generate` bodies (per user decision). The facade's `_get_path` + `generate_media` already handle an all-empty `paths` dict by falling back to `DEFAULT_PATH_*`.
- **Preserve existing signatures.** No public `media.py` function changes; no change to the 5 existing dispatch functions in `main.py`. Only the Settings model + `/api/settings` + the new `paths` request field already present are touched.
- **camelCase frontend / snake_case-ish Settings model.** Follow the existing pattern: `home.html`/`main.js` use camelCase (`imageKey`, `imageBaseUrl`, …); the `Settings` pydantic model uses the same camelCase field names (confirmed: `imageKey`, `audioModel`, `sttModel` are all camelCase in `main.py` line 216-272).

## Review Focus

Five input classes / failure modes the spec implies but no single task's tests exercise outright — add the listed test to the owning task:

- **Empty paths dict in `/api/media/generate` body.** JS sends `{paths: {text_to_media:"", image_to_media:"", text_image_to_media:"", voice:""}}` → facade returns `DEFAULT_PATH_*` behavior, not an error. Test in Task 4 (backend endpoint test) — POST to `/api/media/generate` with all-empty paths and assert no exception + the existing 5-function dispatch still runs.
- **Per-kind path set on one kind only.** User fills only the image path (`text_image_to_media` empty, `image_to_media` set) → `generate_media` uses the set value for the image branch and `DEFAULT_PATH_*` for the others. Test in Task 4 (facade call with a partial paths dict).
- **Settings round-trip (GET returns the 4 fields).** A `POST /api/settings` with the 4 paths, then `GET /api/settings` returns them. Test in Task 2 (TestClient).
- **Settings POST preserve-if-empty.** `POST /api/settings` with empty paths when the server already has paths set → server's values are preserved (the `for f in (...)` copy loop). Test in Task 2.
- **Frontend `renderGenInChat` includes `paths` key on the image POST.** Inspect the POST body construction: assert a `paths` key is present when any path is set, and absent/empty-object when none. This is a JS behavior; pin it by visual inspection of the constructed object (Task 3) — no automated JS test in this repo, so add a note + a manual check command.

---

## File Map

| File | Responsibility |
|------|----------------|
| `frontend/home.html` (#sec-media, lines 802-828) | Add 4 path inputs under each kind's block |
| `frontend/js/main.js` | `buildSettingsFromInputs` (4 fields), `toBackendSettings` (4 fields), `loadSettings`/`loadMediaKeysUI` setVal (4 fields), `renderGenInChat` + inline TTS POST `paths` object |
| `backend/main.py` | `Settings` model (4 camelCase fields, `str = ""`), `/api/settings` GET dict (4 fields), `/api/settings` POST preserve loop (4 fields) |
| `tests/test_media_facade.py` or new `tests/test_settings_paths.py` | Backend endpoint tests (Settings round-trip, preserve-if-empty, empty-paths POST) |

---

### Task 1: Backend — Settings model + `/api/settings` GET/POST

**Files:**
- Modify: `backend/main.py:216-272` (Settings model), `backend/main.py:504-519` (GET dict), `backend/main.py:530-532` (POST preserve loop)
- Test: `tests/test_settings_paths.py` (create)

**Interfaces:**
- Produces: `Settings.mediaPathText`, `Settings.mediaPathImage`, `Settings.mediaPathTextImage`, `Settings.mediaPathVoice` (all `str = ""`); the 4 camelCase keys in `/api/settings` GET response; the 4 fields preserved on POST.

- [ ] **Step 1: Write failing tests**

Create `tests/test_settings_paths.py`:

```python
from fastapi.testclient import TestClient
import main as app_mod

def _client():
    app_mod.server_settings = app_mod.Settings()  # reset
    return TestClient(app_mod.app)

def test_settings_get_has_path_fields():
    c = _client()
    r = c.get("/api/settings")
    assert r.status_code == 200
    for k in ("mediaPathText", "mediaPathImage", "mediaPathTextImage", "mediaPathVoice"):
        assert k in r.json(), f"missing {k}"

def test_settings_post_preserves_paths_when_empty():
    c = _client()
    # seed: set a path via direct model mutation
    app_mod.server_settings.mediaPathText = "seed/text/path"
    # POST with empty paths -> server's value preserved
    r = c.post("/api/settings", json={"mediaPathText": ""})
    assert r.status_code == 200
    assert app_mod.server_settings.mediaPathText == "seed/text/path"

def test_settings_post_sets_paths():
    c = _client()
    r = c.post("/api/settings", json={"mediaPathVoice": "v1/audio/custom"})
    assert r.status_code == 200
    assert app_mod.server_settings.mediaPathVoice == "v1/audio/custom"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_settings_paths.py -v`
Expected: FAIL (keys missing / `Settings` has no `mediaPathText` attr)

- [ ] **Step 3: Implement in `backend/main.py`**

1. In the `Settings` pydantic model (~line 240-272), after the existing media fields, add:
   ```python
   mediaPathText: str = ""        # text->media endpoint path
   mediaPathImage: str = ""       # image->media endpoint path
   mediaPathTextImage: str = ""   # text+image->media endpoint path
   mediaPathVoice: str = ""       # voice/TTS endpoint path
   ```
2. In `/api/settings` GET response dict (~line 504-519), add the 4 camelCase keys:
   ```python
   "mediaPathText": server_settings.mediaPathText,
   "mediaPathImage": server_settings.mediaPathImage,
   "mediaPathTextImage": server_settings.mediaPathTextImage,
   "mediaPathVoice": server_settings.mediaPathVoice,
   ```
3. In the `/api/settings` POST preserve-if-empty loop (~line 530-532), add the 4 fields to the tuple:
   ```python
   for f in ("imageKey", "imageBaseUrl", "imageModel", "videoKey", "videoBaseUrl",
             "videoModel", "audioKey", "audioBaseUrl", "audioModel", "audioVoiceId",
             "sttModel", "codingKey", "codingBaseUrl", "codingModel",
             "mediaPathText", "mediaPathImage", "mediaPathTextImage", "mediaPathVoice"):
   ```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_settings_paths.py -v`
Expected: PASS

- [ ] **Step 5: Run existing provider-neutral test to confirm no regression**

Run: `pytest tests/test_provider_neutral.py -v`
Expected: PASS (Settings defaults still empty for base_url/model; new fields are also empty → no baked-in provider)

- [x] **Step 6: Commit**

```bash
git add backend/main.py tests/test_settings_paths.py
git commit -m "feat(settings): add 4 media endpoint-path fields (mediaPath*)"
```
_(done: commit caf4903, tests/test_settings_paths.py + test_provider_neutral.py → 9/9 PASS)_

---

### Task 2: Frontend — `home.html` inputs + `main.js` wiring

**Files:**
- Modify: `frontend/home.html:802-828` (#sec-media form-groups)
- Modify: `frontend/js/main.js` — `buildSettingsFromInputs` (~1092), `toBackendSettings` (~1167), `loadSettings` (~1085), `loadMediaKeysUI` (~3287)
- Test: manual (JS, no automated test) + `node --check`

**Interfaces:**
- Consumes: the 4 camelCase settings keys from Task 1 (`mediaPathText`, `mediaPathImage`, `mediaPathTextImage`, `mediaPathVoice`).
- Produces: 4 new `home.html` input ids (`mediaPathText`, `mediaPathImage`, `mediaPathTextImage`, `mediaPathVoice`); the 4 fields in `buildSettingsFromInputs` and `toBackendSettings`; the 4 setVal calls in `loadSettings`/`loadMediaKeysUI`.

- [ ] **Step 1: Add the 4 inputs to `home.html` #sec-media**

Per-kind layout (each path input directly under its kind's block). After line 806 (`imageModel` input), inside the "Картинки" form-group, add:
```html
<input type="text" id="mediaPathTextImage" class="opt-input" style="margin-top:8px" placeholder="Путь: текст+изображение → медиа (пусто = дефолт)">
```
After line 806 (the image block already has image→media implied; add the dedicated image-only path under the image block too — but the facade keys are `text_image_to_media` for image+text and `image_to_media` for image-only; place both under "Картинки"):
```html
<input type="text" id="mediaPathImage" class="opt-input" style="margin-top:8px" placeholder="Путь: только изображение → медиа (пусто = дефолт)">
```
After the image block, add the pure-text path under a new "Текст" mini-group (or under "Картинки" if you prefer grouping by output):
```html
<input type="text" id="mediaPathText" class="opt-input" style="margin-top:8px" placeholder="Путь: текст → медиа (пусто = дефолт)">
```
After line 819 (`audioVoiceId` input), inside the "Голос" form-group, add:
```html
<input type="text" id="mediaPathVoice" class="opt-input" style="margin-top:8px" placeholder="Путь: голос/TTS (пусто = дефолт)">
```
**Note:** the video kind reuses the same `text_image_to_media` / `image_to_media` endpoint paths as image (the facade doesn't distinguish video from image for path selection — the kind only affects model/base_url). If you want a separate video path, add a `mediaPathVideo` input and map it in `buildSettingsFromInputs` → but the facade's `_get_path` keys are fixed (`text_to_media`, `image_to_media`, `text_image_to_media`, `voice`). For now, video uses the same path fields as image. Add a `<small>` note under the "Видео" block: "Пути видео используют те же поля, что и картинки (фасад не различает пути по виду медиа)."

- [ ] **Step 2: Wire `buildSettingsFromInputs` (line ~1092-1131)**

After the existing media field reads (line 1120 `imageModel`), add:
```js
mediaPathText: document.getElementById('mediaPathText')?.value.trim() || '',
mediaPathImage: document.getElementById('mediaPathImage')?.value.trim() || '',
mediaPathTextImage: document.getElementById('mediaPathTextImage')?.value.trim() || '',
mediaPathVoice: document.getElementById('mediaPathVoice')?.value.trim() || '',
```

- [ ] **Step 3: Wire `toBackendSettings` (line ~1167-1202)**

After line 1194 (`audioModel`), add:
```js
mediaPathText: s.mediaPathText || '',
mediaPathImage: s.mediaPathImage || '',
mediaPathTextImage: s.mediaPathTextImage || '',
mediaPathVoice: s.mediaPathVoice || '',
```

- [ ] **Step 4: Wire `loadSettings` setVal (line ~1085)**

After line 1088 (`codingModel` setVal), add:
```js
setVal('mediaPathText', settings.mediaPathText); setVal('mediaPathImage', settings.mediaPathImage);
setVal('mediaPathTextImage', settings.mediaPathTextImage); setVal('mediaPathVoice', settings.mediaPathVoice);
```

- [ ] **Step 5: Wire `loadMediaKeysUI` setVal (line ~3287-3294)**

After line 3294 (`sttModel` setVal), add:
```js
setVal('mediaPathText', s.mediaPathText); setVal('mediaPathImage', s.mediaPathImage);
setVal('mediaPathTextImage', s.mediaPathTextImage); setVal('mediaPathVoice', s.mediaPathVoice);
```

- [ ] **Step 6: Verify JS syntax**

Run: `node --check frontend/js/main.js`
Expected: exit 0

- [x] **Step 7: Commit**

```bash
git add frontend/home.html frontend/js/main.js
git commit -m "feat(media-ui): add 4 endpoint-path inputs to media keys page + wire build/load"
```
_(done: commit 64f6058, node --check → JS_OK)_

---

### Task 3: Frontend — `renderGenInChat` + inline TTS send `paths`

**Files:**
- Modify: `frontend/js/main.js` — `renderGenInChat` (the 3 POST bodies at lines ~4272, 4289, 4305) and the inline TTS call (~6008-6048).

**Interfaces:**
- Consumes: `settings.mediaPathText`, `settings.mediaPathImage`, `settings.mediaPathTextImage`, `settings.mediaPathVoice` (from Task 2, via `buildSettingsFromInputs` → `settings` global).
- Produces: a `paths` object in the POST body of every `/api/media/generate` call.

- [ ] **Step 1: Build the `paths` object helper**

Near the top of `renderGenInChat` (or as a module-scope helper), add:
```js
function buildPathsObj() {
  return {
    text_to_media: settings?.mediaPathText || '',
    image_to_media: settings?.mediaPathImage || '',
    text_image_to_media: settings?.mediaPathTextImage || '',
    voice: settings?.mediaPathVoice || '',
  };
}
```

- [ ] **Step 2: Add `paths` to the image POST body**

At the image `/api/media/generate` call (~line 4272), add `paths: buildPathsObj()` to the request body object.

- [ ] **Step 3: Add `paths` to the video POST body**

At the video `/api/media/generate` call (~line 4305), add `paths: buildPathsObj()`.

- [ ] **Step 4: Add `paths` to the audio POST body**

At the audio `/api/media/generate` call (~line 4289), add `paths: buildPathsObj()`.

- [ ] **Step 5: Add `paths` to the inline TTS call**

At the inline TTS `/api/media/generate` call (~line 6008-6016), add `paths: buildPathsObj()` to that POST body as well.

- [ ] **Step 6: Verify JS syntax**

Run: `node --check frontend/js/main.js`
Expected: exit 0

- [ ] **Step 7: Manual check — inspect a constructed POST body**

Open the app, go to the "Медиа-ключи" page, fill in only `mediaPathTextImage` (e.g. `v1/custom/images`), save, then trigger an image gen in chat. Inspect the network tab: the POST body should contain `paths: { text_to_media: "", image_to_media: "", text_image_to_media: "v1/custom/images", voice: "" }`. Confirm the backend routes through `generate_media` with that path. (No automated JS test in this repo; this is the pin.)

- [x] **Step 8: Commit**

```bash
git add frontend/js/main.js
git commit -m "feat(media-ui): always send paths object in chat media gen POSTs"
```
_(done: commit 7f520e0, node --check → JS_OK; buildPathsObj added at module scope, wired into 3 renderGenInChat POSTs + inline TTS)_

---

### Task 4: Backend — verify the facade handles the `paths` dict end-to-end

**Files:**
- Modify: `tests/test_media_facade.py` (append endpoint-level tests)
- Test: `tests/test_media_facade.py` (append)

**Interfaces:**
- Consumes: `MediaGenRequest.paths` (already present from the earlier facade work), `Settings.mediaPath*` (Task 1).
- Produces: pinned behavior that an all-empty `paths` dict and a partial `paths` dict both route through `generate_media` correctly.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_media_facade.py`:

```python
def test_generate_media_all_empty_paths_uses_defaults(monkeypatch):
    """An all-empty paths dict must resolve to DEFAULT_PATH_* for each branch."""
    import media
    up = {"text_to_media": "", "image_to_media": "", "text_image_to_media": "", "voice": ""}
    assert media._get_path(False, "p", False, up) == media.DEFAULT_PATH_TEXT_TO_MEDIA
    assert media._get_path(True, "p", False, up) == media.DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA
    assert media._get_path(True, "", False, up) == media.DEFAULT_PATH_IMAGE_TO_MEDIA
    assert media._get_path(False, "", True, up) == media.DEFAULT_PATH_VOICE

def test_generate_media_partial_paths_verbatim(monkeypatch):
    """A set path is used verbatim; an unset path falls back to DEFAULT."""
    import media
    up = {"image_to_media": "v1/my/custom/image", "text_image_to_media": "", "text_to_media": "", "voice": ""}
    # image-only branch with prompt empty -> image_to_media (custom)
    assert media._get_path(True, "", False, up) == "v1/my/custom/image"
    # text+image branch -> text_image_to_media empty -> DEFAULT
    assert media._get_path(True, "prompt", False, up) == media.DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA

def test_api_media_generate_with_paths_endpoint():
    """POST /api/media/generate with a paths dict must not 500 (routes through facade)."""
    from fastapi.testclient import TestClient
    import main as app_mod
    app_mod.server_settings = app_mod.Settings()
    c = TestClient(app_mod.app)
    r = c.post("/api/media/generate", json={
        "kind": "image", "prompt": "a cat", "use_settings_key": True,
        "paths": {"text_to_media": "", "image_to_media": "", "text_image_to_media": "", "voice": ""},
    })
    # We expect a dict response (ok: true or false), NOT an HTTP 500
    assert r.status_code in (200, 400, 502), f"unexpected status {r.status_code}"
    assert "ok" in r.json(), f"missing 'ok' key in {r.json()}"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_media_facade.py tests/test_settings_paths.py -v`
Expected: PASS (the all-empty + partial + endpoint tests confirm the facade + Settings wiring)

- [ ] **Step 3: Run the full media test suite**

Run: `pytest tests/test_media_facade.py tests/test_media_filegen.py tests/test_media_chat.py tests/test_agnes_media.py tests/test_theming_configs.py tests/test_provider_neutral.py tests/test_settings_paths.py -v`
Expected: PASS (all pre-existing + new)

- [x] **Step 4: Commit**

```bash
git add tests/test_media_facade.py
git commit -m "test(media): pin facade paths routing (empty + partial + endpoint)"
```
_(done: commit 7a481f0, media suite → 72/72 PASS)_

---

## Self-Review Notes

- **Spec coverage:** Settings model fields (T1), home.html inputs (T2), main.js build/load/paths wiring (T2+T3), backend endpoint round-trip + facade routing (T4). All sections of the user's request mapped: "под каждым пунктом видео/аудио/изображения указывали пути" → per-kind layout in T2; "если пустой — подставляется дефолт, если заполнен — точно работает в чате" → always-send-paths + facade in T3+T4.
- **Step scan:** each code step gives the exact insert point (line numbers) and the exact value. No transcript bodies.
- **Type consistency:** the 4 camelCase field names (`mediaPathText`, `mediaPathImage`, `mediaPathTextImage`, `mediaPathVoice`) are identical across T1 (Settings model + GET/POST), T2 (home.html ids + buildSettingsFromInputs + toBackendSettings + setVal), T3 (buildPathsObj keys `text_to_media`/`image_to_media`/`text_image_to_media`/`voice` — the facade's `_get_path` keys), and T4 (test assertions).
- **Review Focus:** all five failure modes pinned to T1/T4 tests (GET round-trip, POST preserve-if-empty, all-empty paths endpoint, partial paths verbatim, JS paths key present).
- **Proportion:** plan is ~ the size of the spec extension; bodies appear only at the exact insert points.
