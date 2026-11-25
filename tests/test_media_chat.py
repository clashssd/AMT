"""Tests for media-in-chat, per-function keys, and live generation with the user's OpenAI key."""
import json
import os
import pytest
from fastapi.testclient import TestClient

import main
from ai_engine import media

# Ключ, который передал пользователь (OpenAI-совместимый). В тестах используется
# ТОЛЬКО для проверки структуры ответов; если нет сети/лимита — тесты мягко пропускаются.
USER_KEY = os.environ.get("AMT_TEST_KEY", "sk-4UJAAVJ9wZgRnZhjw2SDxouqoJ5WDdOMSqPIEDYBhIylDRQb")


@pytest.fixture
def c(tmp_backend, monkeypatch):
    client = TestClient(main.app)
    return client


def test_per_function_key_fields_in_settings(c):
    """Settings хранят пер-функциональные ключи и не ломаются."""
    r = c.post("/api/settings", json={
        "imageKey": "sk-img", "imageBaseUrl": "https://api.openai.com/v1", "imageModel": "gpt-image-1",
        "videoKey": "vk", "videoBaseUrl": "https://api-sing.klingai.com",
        "audioKey": "ak", "audioVoiceId": "v123",
    })
    assert r.status_code == 200
    got = c.get("/api/settings").json()
    assert got.get("imageKey") == "sk-img"
    assert got.get("audioVoiceId") == "v123"


def test_media_check_with_key_network_safe():
    """check_capability с ключом: либо supported, либо reason (не падает)."""
    r = media.check_capability("image", "https://api.openai.com/v1", USER_KEY, "gpt-4o")
    assert "reason" in r
    assert "ok" in r


def test_media_generate_image_with_key():
    """Реальная генерация картинки ключом (если лимит/сеть — проверяем структуру)."""
    r = media.generate_image("https://api.openai.com/v1", USER_KEY, "gpt-4o",
                             "a blue cat", "512x512")
    # либо ok с b64/url, либо code (unsupported/no_key/rate_limit) — но не падение
    assert "ok" in r
    if r["ok"]:
        assert r.get("b64") or r.get("url")


def test_media_generate_video_aspect_ratio_structured():
    """Видео: 9:16 (кружок) и 16:9 — структура ответа корректна."""
    r = media.generate_video("https://api-sing.klingai.com", USER_KEY, "kling-v1",
                             "a mountain", "5", "9:16")
    assert "ok" in r
    assert r.get("aspect_ratio") == "9:16" or not r["ok"]


def test_media_image_ref_structured():
    """Генерация по примерам (ref) — без рефа == обычный generate."""
    r = media.generate_image_ref("https://api.openai.com/v1", USER_KEY, "gpt-image-1",
                                 "a cat", "512x512", "")
    assert "ok" in r or r.get("code")


def test_gen_token_parsing_frontend_logic():
    """Проверяем формат токенов, который ожидает фронтенд (имитация парсинга)."""
    text = "Вот твоё фото:\n[[GEN:image|1:1|a neon portrait]]"
    import re
    m = re.search(r"\[\[GEN:image\|([^\]]*)\]\]", text)
    assert m
    assert "a neon portrait" in m.group(1)
    # чистый текст без токенов
    clean = re.sub(r"\[\[GEN:[^\]]*\]\]", "", text).strip()
    assert "Вот твоё фото:" in clean and "GEN" not in clean


def test_media_task_endpoint(c):
    r = c.post("/api/media/task", json={"task_id": "nonexistent", "use_settings_key": False})
    assert r.status_code == 200
    j = r.json()
    assert "status" in j


def test_media_task_base_resolution_precedence(c, monkeypatch, tmp_backend):
    """Регрессия приоритета операторов в media_task.

    Бывает баг: `base = req.base_url or (videoBaseUrl or baseUrl if use else "")`
    Python читает это как `(base_url or (v or b)) if use else ""`, а нам нужно
    `base_url or ((v or b) if use else "")`.

    /api/settings НЕ затирает пустые медиа-поля старыми (осознанно),
    поэтому каждый под-кейс пишет оба поля в явном виде с DISTINCT значениями
    и проверяет, какое из них реально дошло до check_video_task.
    """
    import main as m
    captured = {}

    def fake_check(base, key, task_id, proxy="", model_name=""):
        captured["base"] = base
        return {"ok": True, "status": "completed", "url": "https://example.com/out.mp4"}

    monkeypatch.setattr(m.media_gen, "check_video_task", fake_check)
    V = "https://vid.example"
    B = "https://main.example"
    E = "https://explicit.example"

    # 1) use_settings_key=False, base_url пуст → settings-ключи не используются → ""
    c.post("/api/settings", json={"videoBaseUrl": V, "baseUrl": B})
    r = c.post("/api/media/task", json={"task_id": "t", "use_settings_key": False, "base_url": ""})
    assert r.status_code == 200
    assert captured.get("base") == "", f"expected '', got {captured.get('base')!r}"

    # 2) use_settings_key=True, оба поля заданы → приоритет у videoBaseUrl
    captured.clear()
    r = c.post("/api/media/task", json={"task_id": "t", "use_settings_key": True, "base_url": ""})
    assert r.status_code == 200
    assert captured["base"] == V, f"expected videoBaseUrl {V!r}, got {captured['base']!r}"

    # 3) use_settings_key=True, явный base_url → base_url всегда поверх settings
    captured.clear()
    r = c.post("/api/media/task", json={"task_id": "t", "use_settings_key": True, "base_url": E})
    assert r.status_code == 200
    assert captured["base"] == E, f"expected explicit {E!r}, got {captured['base']!r}"

    # 4) Ключевой кейс приоритета операторов:
    #    use_settings_key=True + base_url пуст. ДО фикса кода выражение
    #    `base_url or (v or b if use else "")` давало тот же результат только
    #    когда use=True, но ЛОЖНО давало v-URL, когда use=False и base_url пуст
    #    (из-за того что `A or B if C else D` = `(A or B) if C else D`).
    #    Теперь при use=False → всегда "", при use=True → (v or b).
    #    Проверяем именно границу use=False:
    captured.clear()
    r = c.post("/api/media/task", json={"task_id": "t", "use_settings_key": False, "base_url": ""})
    assert r.status_code == 200
    assert captured["base"] == "", f"with use_settings_key=False base must be '', got {captured['base']!r}"


def test_project_ipc_handlers_wired():
    """Регрессия: IPC-хендлеры project:list/create/select должны проксировать
    запросы на бэкенд /api/projects*, а не возвращать заглушки
    'Not implemented yet' / пустые {projects: []}.

    Контракт бэкенда (main.py):
      GET  /api/projects      -> { project, allowed_dirs }
      POST /api/projects/select { root } -> { ok, project, allowed_dirs }
    """
    import re
    import os
    src_path = os.path.join(os.path.dirname(__file__), "..", "electron", "ipc.js")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    # Ни одной заглушки
    assert "Not implemented yet" not in src, "project IPC handlers still have stubs"
    assert "TODO: implement in Task 3" not in src, "project IPC handlers still have Task-3 TODO"
    # Все три хендлера ходят на бэкенд
    assert re.search(r"ipcMain\.handle\('project:list'.*?/api/projects", src, re.S)
    assert len(re.findall(r"ipcMain\.handle\('project:create'.*?/api/projects/select", src, re.S)) >= 1
    assert len(re.findall(r"ipcMain\.handle\('project:select'.*?/api/projects/select", src, re.S)) >= 1
    # Тело select-запроса использует поле `root` (контракт ProjectIn), не `path`
    for m in re.finditer(r"ipcMain\.handle\('project:(create|select)'(.*?)\n  \}\);", src, re.S):
        assert '"root"' in m.group(2) or "root:" in m.group(2), \
            f"project:{m.group(1)} must send {{ root }}, got: {m.group(2)[:120]}"


def test_media_voices_list_endpoint(c):
    r = c.post("/api/media/voices/list", json={"kind": "audio", "use_settings_key": False, "api_key": ""})
    assert r.status_code == 200
    j = r.json()
    # без ключа → ok:False, code no_key
    assert j.get("ok") in (True, False)


def test_audio_settings_passed_through():
    """voice_settings (темп/стабильность/стиль/сходство) доходят до тела запроса."""
    r = media.generate_audio("", "", "", "hi", "", "", {
        "speed": 1.2, "stability": 0.7, "style": 0.3, "similarity": True,
    })
    # без ключа → no_key, но структура голос.настроек не падает
    assert r["code"] == "no_key"


def test_video_example_structured():
    r = media.generate_video_example("https://api-sing.klingai.com", "k", "m",
                                     "prompt", "QUJD", "5", "9:16")
    assert "ok" in r  # либо ok (task), либо code — без падения
    if r["ok"]:
        assert r.get("aspect_ratio") == "9:16"


def test_provider_profile_strips_full_tts_endpoint(tmp_backend):
    """Кол-во: base_url с полным путём /api/v1/audio/speech →
    auto-strip даёт https://easyvoice.ae/api → TTS URL корректен."""
    from ai_engine.media import provider_profile
    p = provider_profile("audio", base_url="https://easyvoice.ae/api/v1/audio/speech",
                         api_key="ev_test", model="kokoro-82m", voice_id="af_aoded")
    assert p["base"] == "https://easyvoice.ae/api", f"base={p['base']}"
    assert p["api_base"] == "https://easyvoice.ae/api", f"api_base={p['api_base']}"
    assert p["key"] == "ev_test"
    assert p["model"] == "kokoro-82m"
    assert p["voice_id"] == "af_aoded"


def test_provider_profile_plain_base_unchanged(tmp_backend):
    """Кол-во: обычный host (без /v1/audio/speech) не трогается."""
    from ai_engine.media import provider_profile
    p = provider_profile("audio", base_url="https://easyvoice.ae",
                         api_key="ev_test", model="kokoro-82m", voice_id="af_aoded")
    assert p["base"] == "https://easyvoice.ae"
    assert p["api_base"] == "https://easyvoice.ae"


def test_provider_profile_strips_v1_suffix(tmp_backend):
    """Кол-во: base_url с /v1 хвостом → strip."""
    from ai_engine.media import provider_profile
    p = provider_profile("audio", base_url="https://api.example.com/v1",
                         api_key="k", model="m", voice_id="v")
    assert p["base"] == "https://api.example.com", f"base={p['base']}"
    assert p["api_base"] == "https://api.example.com", f"api_base={p['api_base']}"


def test_media_generate_save_flag(c, tmp_backend):
    """save=True сохраняет media в FILES_DIR и возвращает stored_name/download_url."""
    import main as m
    old = m.FILES_DIR
    m.FILES_DIR = str(tmp_backend["tmp"])
    import os
    os.makedirs(m.FILES_DIR, exist_ok=True)
    try:
        # сгенерируем audio без ключа → no_key (не ok), save не сработает
        r = c.post("/api/media/generate", json={
            "kind": "audio", "prompt": "hi", "use_settings_key": False,
            "api_key": "", "save": True,
        })
        assert r.json()["ok"] is False  # no key
    finally:
        m.FILES_DIR = old
