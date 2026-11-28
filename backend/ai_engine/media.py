"""
Генерация картинок / видео / аудио через API провайдера, указанного пользователем.

Подход: пользователь задаёт (на странице Генерации)
  - провайдер (или произвольный base_url + модель + ключ),
  - описание (prompt) и параметры.
Мы вызываем соответствующий endpoint провайдера. Если ключ/провайдер
НЕ поддерживает функцию — честно вернём "unsupported", чтобы фронт
показал «Ваш ключ не поддерживает данную функцию, укажите другой».

Встроенные профили провайдеров (можно переопределить base_url/ключ):
  - image:  картинки (OpenAI-совместимый /images/generations или любой compatible-endpoint)
  - video:  видео (видео-API, text2video)
  - audio:  голос (TTS-API)

Все профили можно заменить произвольным OpenAI-совместимым endpoint.
"""
import os
import time
import json
import base64
import logging
from typing import Optional

import httpx

_log = logging.getLogger(__name__)

# Известные профили (структура эндпоинтов). Ключ, модель И base_url — от пользователя.
# Provider-neutral: default_base оставлен ПУСТЫМ для всех профилей — приложение
# НЕ предполагает конкретный хост провайдера, если пользователь не указал base_url.
# Конкретные адреса (OpenAI/Kling/ElevenLabs/Agnes) теперь вставляются пользователем
# в настройках или через «Хранилище» API-ключей.
PROVIDERS = {
    # картинки: OpenAI-совместимый /images/generations (любой compatible-endpoint)
    "image": {
        "label": "Картинка (OpenAI-совместимый)",
        "default_base": "",
        "endpoint": "images/generations",
        "kind": "image",
    },
    # видео: видео-API
    "video": {
        "label": "Видео (видео-API)",
        "default_base": "",
        "endpoint": "v1/videos/text2video",
        "kind": "video",
    },
    # аудио: TTS-API
    "audio": {
        "label": "Голос (TTS-API)",
        "default_base": "",
        "endpoint": "v1/text-to-speech/{voice_id}",
        "kind": "audio",
    },
    # Agnes (OpenAI-совместимый хаб): картинки + видео (асинхронные, возвращают URL)
    "agnes": {
        "label": "Agnes (картинки + видео)",
        "default_base": "",
        "endpoint": "images/generations",
        "kind": "image",
        "video_endpoint": "video/generations",  # видео: POST /v1/video/generations (нужен mode)
        "async_url": True,  # результат — URL, а не b64
    },
}
# Автоопределение провайдера по base_url. Оставляем пустым по умолчанию: приложение
# не «узнаёт» конкретные хосты провайдеров, если пользователь не указал base_url.
# (Подключите адрес через Настройки/Хранилище — автоопределение заработает по нему.)
def _load_provider_hints() -> dict:
    # Provider-neutral: auto-detect provider dialects from CONFIG, not from code.
    # Order (first hit wins):
    #   1) env AMT_PROVIDER_HINTS (JSON string)
    #   2) provider_hints.json next to this module or its parent dir
    #   3) built-in default (compatibility only).
    # New providers are added via config, never by editing this source.
    import json as _json, os as _os
    raw = _os.environ.get("AMT_PROVIDER_HINTS", "").strip()
    if raw:
        try:
            v = _json.loads(raw)
            if isinstance(v, dict):
                return v
        except Exception:
            pass
    _here = _os.path.dirname(_os.path.abspath(__file__))
    for cand in (_here, _os.path.dirname(_here)):
        p = _os.path.join(cand, "provider_hints.json")
        if _os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as _fh:
                    v = _json.load(_fh)
                if isinstance(v, dict):
                    return v
            except Exception:
                pass
    return {"agnes": "apihub.agnes-ai.com"}

_BASE_PROVIDER_HINTS = _load_provider_hints()
# Provider-neutral: запасные имена моделей, используемые ТОЛЬКО когда пользователь
# не указал model. По умолчанию ПУСТЫЕ — приложение не «угадывает» модель провайдера.
# При желании их можно задать через env AMT_DEFAULT_MEDIA_MODELS (JSON: {"image":"","audio":"","video":""}).
_FALLBACK_MODELS = {}
try:
    _FALLBACK_MODELS = json.loads(os.environ.get("AMT_DEFAULT_MEDIA_MODELS", "{}"))
except Exception:
    _FALLBACK_MODELS = {}
# Запасные модели: image / audio / video (пустые = не передавать, провайдер выберет дефолт)
_FB_IMAGE_MODEL = _FALLBACK_MODELS.get("image", "")
_FB_AUDIO_MODEL = _FALLBACK_MODELS.get("audio", "")
_FB_VIDEO_MODEL = _FALLBACK_MODELS.get("video", "")
# ElevenLabs: отдельный протокол (заголовок xi-api-key, path /v1/text-to-speech/{voice},
# body model_id, ответ voices[]). Автоопределение по base_url.
_ELEVENLABS_HOST = (os.environ.get("AMT_ELEVENLABS_HOST", "") or "").strip()
if not _ELEVENLABS_HOST:
    _ELEVENLABS_HOST = _BASE_PROVIDER_HINTS.get("elevenlabs", "") or "elevenlabs.io"

# ---------------------------------------------------------------------------
# Универсальный фасад (generate_media): дефолтные константы + helper'ы.
# Provider-neutral: ключ/URL/модель ПУСТЫЕ по умолчанию (не привязаны к
# конкретному провайдеру), переопределяются через env. Путь-константы имеют
# нейтральные OpenAI-совместимые дефолты, которые пользователь может заменить.
# ---------------------------------------------------------------------------
DEFAULT_API_KEY = os.environ.get("AMT_DEFAULT_API_KEY", "")
DEFAULT_BASE_URL = os.environ.get("AMT_DEFAULT_BASE_URL", "")
DEFAULT_MODEL = os.environ.get("AMT_DEFAULT_MODEL", "")
DEFAULT_PATH_TEXT_TO_MEDIA = os.environ.get("AMT_PATH_TEXT_TO_MEDIA", "v1/images/generations")
DEFAULT_PATH_IMAGE_TO_MEDIA = os.environ.get("AMT_PATH_IMAGE_TO_MEDIA", "v1/images/generations")
DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA = os.environ.get("AMT_PATH_TEXT_IMAGE_TO_MEDIA", "v1/images/generations")
DEFAULT_PATH_VOICE = os.environ.get("AMT_PATH_VOICE", "v1/audio/speech")
DEFAULT_PATH_VIDEO = os.environ.get("AMT_PATH_VIDEO", "v1/videos/text2video")


def _is_empty(v) -> bool:
    """None/''/только пробелы считается «не задано» -> подставляем дефолт."""
    return (v is None) or (str(v).strip() == "")


def _get_path(has_file: bool, prompt: str, is_voice: bool, user_paths: Optional[dict] = None,
              is_video: bool = False) -> str:
    """Выбирает endpoint-путь по наличию файла/голоса/видео/промпта.

    Ключи в user_paths: voice, video, text_image_to_media, image_to_media, text_to_media.
    Значение из user_paths берётся ТОЧЬ-В-ТОЧЬ (verbatim), если оно задано;
    иначе подставляется соответствующая DEFAULT_PATH_* константа.
    Приоритет: is_video и is_voice первичны (конкретный тип), затем файл+промпт.
    """
    if is_video:
        key = "video"
        default = DEFAULT_PATH_VIDEO
    elif is_voice:
        key = "voice"
        default = DEFAULT_PATH_VOICE
    elif has_file and prompt:
        key = "text_image_to_media"
        default = DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA
    elif has_file:
        key = "image_to_media"
        default = DEFAULT_PATH_IMAGE_TO_MEDIA
    else:
        key = "text_to_media"
        default = DEFAULT_PATH_TEXT_TO_MEDIA
    up = user_paths or {}
    chosen = up.get(key)
    if not _is_empty(chosen):
        return chosen  # verbatim, без trim
    return default


def _prepare_payload(prompt: str, model: str, attached_file=None,
                    voice_id=None, voice_settings=None, extra=None) -> dict:
    """Собирает JSON payload. prompt/model — ТОЧЬ-В-ТОЧЬ (без trim).

    attached_file обрабатывается по типу (фронт отправляет base64-строки,
    поэтому строка НЕ считается путём по умолчанию):
      - bytes                -> base64-кодирование
      - str "data:..." URI   -> отбросить префикс до запятой (включая), остаток = base64
      - str, путь к существующему файлу (os.path.exists) -> прочитать + base64
      - str, иначе (готовый base64) -> использовать как есть, open() НЕ вызывать

    Kind-specific fields (voice_id, voice_settings, extra) are merged into the
    payload VERBATIM when provided, so TTS/video requests carry the same fields
    the kind-specific functions (generate_audio / generate_video) would send.
    """
    payload = {"prompt": prompt, "model": model}
    if attached_file is not None:
        if isinstance(attached_file, (bytes, bytearray)):
            payload["image"] = base64.b64encode(bytes(attached_file)).decode("ascii")
        elif isinstance(attached_file, str):
            if attached_file.startswith("data:"):
                # data URI: data:<mime>;base64,<value>
                value = attached_file.split(",", 1)[1] if "," in attached_file else attached_file
                payload["image"] = value
            elif os.path.exists(attached_file):
                with open(attached_file, "rb") as fh:
                    payload["image"] = base64.b64encode(fh.read()).decode("ascii")
            else:
                # обычный base64-строка (не путь, не data URI) — используем как есть
                payload["image"] = attached_file
    # Kind-specific fields — ТОЧЬ-В-ТОЧЬ, без подмен формата.
    if voice_id is not None:
        payload["voice"] = voice_id
    if voice_settings:
        for k, v in voice_settings.items():
            if v is not None:
                payload[k] = v
    if extra:
        for k, v in extra.items():
            if k not in payload:
                payload[k] = v
    return payload


def _make_request(api_key: str, base_url: str, model: str, path: str,
                  prompt: str, attached_file=None,
                  voice_id=None, voice_settings=None, extra=None) -> dict:
    """Склеивает URL (структурная нормализация только хвост/начало), POST-ит,
    делает raise_for_status, возвращает JSON тела.
    """
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    payload = _prepare_payload(prompt, model, attached_file,
                               voice_id=voice_id, voice_settings=voice_settings,
                               extra=extra)
    resp = httpx.post(url, json=payload,
                      headers={"Authorization": f"Bearer {api_key}"},
                      timeout=60)
    resp.raise_for_status()
    return resp.json()


def generate_media(user_api_key, user_base_url, user_model, user_paths,
                   prompt, attached_file=None, is_voice=False, is_video=False,
                   voice_id=None, voice_settings=None, extra=None) -> dict:
    """Универсальный фасад генерации медиа.

    Все настройки (ключ, base_url, модель, пути) ОПЦИОНАЛЬНЫ: пустые/None/
    только пробелы подменяются DEFAULT_*; заданные значения уходят ТОЧЬ-В-ТОЧЬ.
    Алгоритм: (1) попытка с кастомными настройками; (2) при сбое — строго
    дефолтные. Возвращает ПЛОСКИЙ dict: ключи тела провайдера на верхнем
    уровне (без вложенного "result"); при двойном сбое —
    {"ok": False, "code": "api_error", "error": "..."}.
    """
    has_file = bool(attached_file)
    # путь для дефолтной попытки (строгие дефолты)
    default_path = _get_path(has_file, prompt, is_voice, is_video=is_video)
    up = user_paths or {}

    # ПОПЫТКА 1: кастомные значения (verbatim, если заданы), иначе DEFAULT_*
    active_api_key = user_api_key if not _is_empty(user_api_key) else DEFAULT_API_KEY
    active_base_url = user_base_url if not _is_empty(user_base_url) else DEFAULT_BASE_URL
    active_model = user_model if not _is_empty(user_model) else DEFAULT_MODEL
    active_path_key = "video" if is_video else \
        "voice" if is_voice else \
        "text_image_to_media" if has_file and prompt else \
        "image_to_media" if has_file else "text_to_media"
    active_path = up.get(active_path_key) if not _is_empty(up.get(active_path_key)) else default_path

    try:
        result = _make_request(active_api_key, active_base_url, active_model,
                               active_path, prompt, attached_file,
                               voice_id=voice_id, voice_settings=voice_settings,
                               extra=extra)
        out = {"ok": True}
        out.update(result if isinstance(result, dict) else {"data": result})
        return out
    except Exception as e:
        err1 = str(e)
        _log.warning("media: кастомная конфигурация не сработала, fallback на дефолты: %s", err1)
        try:
            result = _make_request(DEFAULT_API_KEY, DEFAULT_BASE_URL, DEFAULT_MODEL,
                                   default_path, prompt, attached_file,
                                   voice_id=voice_id, voice_settings=voice_settings,
                                   extra=extra)
            out = {"ok": True}
            out.update(result if isinstance(result, dict) else {"data": result})
            return out
        except Exception as e2:
            err2 = str(e2)
            return {"ok": False, "code": "api_error",
                    "error": f"Ошибка кастомного API: {err1}. Ошибка дефолтного API: {err2}"}


def provider_profile(kind: str, base_url: str = "", api_key: str = "", model: str = "",
                     voice_id: str = "", proxy: str = "") -> dict:
    p = dict(PROVIDERS.get(kind, {}))
    base = (base_url or p.get("default_base", "")).rstrip("/")
    # Если пользователь вставил полный endpoint (например,
    # https://easyvoice.ae/api/v1/audio/speech) — отрезаем хвост до /v1
    # или до host, чтобы не получилось /v1/audio/speech/v1/audio/speech.
    for suffix in ("/v1/audio/speech", "/v1/audio/transcriptions", "/v1/images/generations",
                   "/v1/video/generations", "/v1/video", "/v1", "/api"):
        if base.endswith(suffix):
            base = base[: -len(suffix)].rstrip("/")
            break
    p["base"] = base
    # base без хвоста /v1 — чтобы не получалось /v1/v1/...
    p["api_base"] = base[: -len("/v1")] if base.endswith("/v1") else base
    p["key"] = api_key
    p["model"] = model
    p["voice_id"] = voice_id
    p["proxy"] = proxy
    return p


def _missing_base_error(p: dict, feature: str) -> dict:
    """Provider-neutral guard: если base_url не задан — честный отказ, а не «случайный» хост."""
    if not (p.get("base") or "").strip():
        return {
            "ok": False,
            "code": "no_base_url",
            "error": f"Для {feature} нужен Base URL провайдера. Укажите адрес в Настройках или выберите ключ с адресом в «Хранилище».",
        }
    return None


def _gen_video_body(prompt: str, duration: str, aspect_ratio: str, model: str, extra: dict) -> dict:
    """Generic text2video body. Provider-neutral: forward user's model only if set.
    Extra merges last (user can override)."""
    body = {"prompt": prompt, "duration": duration, "aspect_ratio": aspect_ratio}
    if (model or "").strip():
        body["model"] = model
    if extra:
        body.update({k: v for k, v in extra.items()})
    return body


def _client(proxy: str, timeout: float = 120.0):
    kwargs = {"timeout": timeout}
    if proxy:
        try:
            kwargs["proxy"] = proxy
        except Exception:
            kwargs["proxies"] = proxy
    return httpx.Client(**kwargs)


# ===== Проверка: поддерживает ли ключ функцию =====
def check_capability(kind: str, base_url: str = "", api_key: str = "", model: str = "",
                      voice_id: str = "", proxy: str = "") -> dict:
    """
    Универсальная проверка: пробуем несколько OpenAI-совместимых эндпоинтов
    и возвращаем {ok, reason, endpoints} — какие работают.
    Это позволяет ЛЮБОМУ провайдеру (не только Agnes/ElevenLabs) работать
    с base_url + api_key + model.
    """
    p = provider_profile(kind, base_url, api_key, model, voice_id, proxy)
    if not p["key"]:
        return {"ok": False, "reason": "Ключ не указан"}
    base = p["base"]
    api_base = p["api_base"]
    key = p["key"]
    results = {}
    # OpenAI-compatible image endpoint
    try:
        with _client(proxy, timeout=30.0) as c:
            r = c.post(f"{base}/images/generations",
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": model or _FB_IMAGE_MODEL, "prompt": "test", "n": 1, "size": "256x256"})
            results["image"] = (r.status_code in (200, 201, 202),
                                "поддерживается" if r.status_code in (200, 201, 202) else f"HTTP {r.status_code}")
    except Exception as e:
        results["image"] = (False, str(e)[:80])
    # OpenAI-compatible audio endpoint
    try:
        with _client(proxy, timeout=30.0) as c:
            r = c.post(f"{api_base}/v1/audio/speech",
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": model or _FB_AUDIO_MODEL, "voice": voice_id or "alloy", "input": "test"})
            results["audio"] = (r.status_code in (200, 201, 202),
                                "поддерживается" if r.status_code in (200, 201, 202) else f"HTTP {r.status_code}")
    except Exception as e:
        results["audio"] = (False, str(e)[:80])
    # Video endpoint (Agnes-style or OpenAI-style)
    is_agnes = any(h in base for h in _BASE_PROVIDER_HINTS)
    if is_agnes:
        try:
            with _client(proxy, timeout=30.0) as c:
                _vid_model = model if "video" in (model or "").lower() else (_FB_VIDEO_MODEL or model or "video")
                r = c.post(f"{base}/videos",
                           headers={"Authorization": f"Bearer {key}"},
                           json={"model": _vid_model, "prompt": "test",
                                  "mode": "text", "seconds": "5", "size": "720P", "aspect_ratio": "16:9"})
                results["video"] = (r.status_code in (200, 201, 202),
                                    "поддерживается" if r.status_code in (200, 201, 202) else f"HTTP {r.status_code}")
        except Exception as e:
            results["video"] = (False, str(e)[:80])
    else:
        try:
            with _client(proxy, timeout=30.0) as c:
                r = c.post(f"{api_base}/v1/videos/text2video",
                           headers={"Authorization": f"Bearer {key}"},
                           json={"prompt": "test", "duration": "5", "aspect_ratio": "16:9"})
                results["video"] = (r.status_code in (200, 201, 202),
                                    "поддерживается" if r.status_code in (200, 201, 202) else f"HTTP {r.status_code}")
        except Exception as e:
            results["video"] = (False, str(e)[:80])
    any_ok = any(v[0] for v in results.values())
    working = [k for k, v in results.items() if v[0]]
    reason = "поддерживается" if any_ok else "ни один эндпоинт не работает"
    return {"ok": any_ok, "reason": reason, "endpoints": results, "working": working}


def generate_image(base_url: str = "", api_key: str = "", model: str = "", prompt: str = "",
                   size: str = "1024x1024", proxy: str = "", extra: dict = None) -> dict:
    """Обычная генерация картинки (по промпту). Для рефа — generate_image_ref."""
    return generate_image_ref(base_url, api_key, model, prompt, size, "", proxy, extra)


def check_video_task(base_url: str = "", api_key: str = "", task_id: str = "", proxy: str = "",
                     model_name: str = "") -> dict:
    p = provider_profile("video", base_url, api_key, model_name, proxy=proxy)
    _nb = _missing_base_error(p, "видео (статус задачи)")
    if _nb:
        # check_video_task возвращает dict со полем "status" — сохраняем контракт.
        return {"ok": False, "status": "error", "code": "no_base_url",
                "error": _nb["error"]}
    is_agnes = any(h in p["base"] for h in _BASE_PROVIDER_HINTS)
    try:
        with _client(proxy) as c:
            if is_agnes:
                # Agnes (документированный): GET <host>/agnesapi?video_id=<ID>&model_name=<model>
                # host = base без /v1. При status=completed — top-level url.
                host = p["base"]
                if host.endswith("/v1"):
                    host = host[: -len("/v1")]
                # model_name: явный параметр > fallback > пустая (провайдер выберет дефолт)
                _mn = model_name or _FB_VIDEO_MODEL or ""
                url = f"{host}/agnesapi?video_id={task_id}"
                if _mn:
                    url += f"&model_name={_mn}"
                r = c.get(url, headers={"Authorization": f"Bearer {p['key']}"})
                if r.status_code >= 400:
                    return {"status": "error", "error": f"{r.status_code} {r.text[:200]}"}
                d = r.json()
                st = d.get("status", "")  # queued|processing|completed|failed
                out = {"status": st, "progress": d.get("progress", "")}
                if st in ("completed", "succeeded"):
                    out["url"] = d.get("url", "") or ""
                if st in ("failed", "error"):
                    out["error"] = (d.get("error") or "Видео не удалось сгенерировать")
                return out
            r = c.get(f"{p['api_base']}/v1/videos/text2video/{task_id}",
                       headers={"Authorization": f"Bearer {p['key']}"})
        if r.status_code >= 400:
            return {"status": "error", "error": f"{r.status_code} {r.text[:200]}"}
        d = r.json()
        data = d.get("data") or {}
        st = data.get("task_status", "")
        out = {"status": st}
        if st == "succeed":
            out["url"] = (data.get("task_result") or [{}])[0].get("url", "")
        return out
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


def generate_audio(base_url: str = "", api_key: str = "", model: str = "", text: str = "",
                   voice_id: str = "", proxy: str = "", voice_settings: dict = None, extra: dict = None) -> dict:
    """TTS → audio bytes. voice_settings: скорость/стабильность/стиль/сходство.

    Универсально по провайдеру (base_url + api_key + model):
      * OpenAI-совместимый endpoint /v1/audio/speech (Bearer) — по умолчанию;
      * ElevenLabs-диалект (xi-api-key + /v1/text-to-speech/{voice} + model_id),
        если base_url указывает на elevenlabs.io — сохраняя дефолтный голос/параметры.
    """
    p = provider_profile("audio", base_url, api_key, model, voice_id=voice_id, proxy=proxy)
    is_eleven = _ELEVENLABS_HOST in (p["base"] or "")
    if is_eleven:
        return _generate_audio_elevenlabs(p, text, proxy, voice_settings, extra)
    # ---- Универсальный OpenAI-совместимый TTS ----
    if not p["key"]:
        return {"ok": False, "code": "no_key", "error": "Укажите API-ключ для генерации голоса"}
    _nb = _missing_base_error(p, "голоса")
    if _nb:
        return _nb
    # api_base — base без хвоста /v1, чтобы не получалось /v1/v1
    vid = voice_id  # provider-neutral: пустая = провайдер выберет голос по умолчанию
    body = {"model": model or _FB_AUDIO_MODEL, "voice": vid, "input": text}
    if extra:
        for k, v in extra.items():
            if k not in body:
                body[k] = v
    if voice_settings:
        # Универсальные подсказки (не все провайдеры поддерживают; безвредно)
        if voice_settings.get("speed") is not None:
            body["speed"] = voice_settings["speed"]
        if voice_settings.get("stability") is not None:
            body["stability"] = voice_settings["stability"]
        if voice_settings.get("style") is not None:
            body["style"] = voice_settings["style"]
        if voice_settings.get("similarity") is not None:
            body["use_speaker_boost"] = bool(voice_settings["similarity"])
        if voice_settings.get("output_format"):
            body["response_format"] = voice_settings["output_format"]
    try:
        with _client(proxy, timeout=300.0) as c:
            r = c.post(f"{p['api_base']}/v1/audio/speech",
                       headers={"Authorization": f"Bearer {p['key']}"}, json=body)
        if r.status_code >= 400:
            return {"ok": False, "code": "unsupported", "error": f"Провайдер: {r.status_code} {r.text[:200]}"}
        return {"ok": True, "mime": "audio/mpeg", "b64": _b64_bytes(r.content), "voice_id": vid}
    except Exception as e:
        return {"ok": False, "code": "error", "error": str(e)[:200]}


def _generate_audio_elevenlabs(p: dict, text: str, proxy: str, voice_settings: dict, extra: dict) -> dict:
    """ElevenLabs-диалект TTS (для base_url = elevenlabs.io). Дефолт-голос/параметры."""
    vid = p.get("voice_id") or "21m00Tcm4TlvDq8ikT7d"
    if not p["key"]:
        return {"ok": False, "code": "no_key", "error": "Укажите API-ключ для генерации голоса"}
    body = {"text": text, "model_id": p.get("model") or "eleven_multilingual_v2"}
    if extra:
        for k, v in extra.items():
            if k not in body:
                body[k] = v
    if voice_settings:
        vs = {}
        if voice_settings.get("speed") is not None:
            vs["speed"] = voice_settings["speed"]            # ~0.7..1.2
        if voice_settings.get("stability") is not None:
            vs["stability"] = voice_settings["stability"]    # 0..1
        if voice_settings.get("style") is not None:
            vs["style"] = voice_settings["style"]            # 0..1
        if voice_settings.get("similarity") is not None:
            vs["use_speaker_boost"] = bool(voice_settings["similarity"])
        if vs:
            body["voice_settings"] = vs
        if voice_settings.get("output_format"):
            body["output_format"] = voice_settings["output_format"]
    # p["api_base"] — base без хвоста /v1, чтобы не получалось /v1/v1.
    try:
        with _client(proxy, timeout=300.0) as c:
            r = c.post(f"{p['api_base']}/v1/text-to-speech/{vid}",
                       headers={"xi-api-key": p["key"]}, json=body)
        if r.status_code >= 400:
            return {"ok": False, "code": "unsupported", "error": f"Провайдер: {r.status_code} {r.text[:200]}"}
        return {"ok": True, "mime": "audio/mpeg", "b64": _b64_bytes(r.content), "voice_id": vid}
    except Exception as e:
        return {"ok": False, "code": "error", "error": str(e)[:200]}


def transcribe_audio(base_url: str = "", api_key: str = "", model: str = "",
                      audio_b64: str = "", mime: str = "audio/webm", proxy: str = "",
                      fallback_key: str = "", fallback_base: str = "",
                      fallback_model: str = "whisper-1") -> dict:
    """STT (Whisper/аудио-модель) → текст. audio_b64: base64 аудио.

    Провайдер — OpenAI-совместимый endpoint /v1/audio/transcriptions.
    Если основной запрос вернул 4xx/5xx, а передан fallback (ключ+адрес+модель
    из глобальных настроек) — пробуем его. Это спасает от провайдеров,
    у которых нет STT (например, Agnes-хаб с audio-ключом).

    ВАЖНО: webm-записи от MediaRecorder конвертируются в mp3 перед отправкой,
    т.к. большинство STT-провайдеров не поддерживают webm (opus codec).
    """
    p = provider_profile("audio", base_url, api_key, model, proxy=proxy)
    if not p["key"]:
        return {"ok": False, "code": "no_key", "error": "Укажите API-ключ для распознавания голоса"}
    if not audio_b64:
        return {"ok": False, "code": "no_audio", "error": "Пустое аудио"}
    import base64, io
    raw = base64.b64decode(audio_b64)
    ext = {"audio/wav": "wav", "audio/mp3": "mp3", "audio/mpeg": "mp3",
           "audio/ogg": "ogg", "audio/x-wav": "wav", "audio/webm": "webm",
           "audio/flac": "flac"}.get(mime, "webm")
    fname = f"audio.{ext}"

    # Webm → MP3 конвертация (MediaRecorder записывает webm/opus,
    # большинство STT-провайдеров принимают только mp3/wav/ogg/flac)
    if ext == "webm":
        try:
            raw, mime, ext, fname = _webm_to_mp3(raw, proxy)
        except Exception as e:
            return {"ok": False, "code": "convert_error",
                    "error": f"Не удалось конвертировать webm→mp3: {str(e)[:150]}"}

    def _post(base, key, model_name):
        """Один запрос к /v1/audio/transcriptions. Возвращает (ok, text, error)."""
        if not key:
            return False, "", "no key"
        api_base = base.rstrip("/")
        if api_base.endswith("/v1"):
            api_base = api_base[: -len("/v1")]
        try:
            with _client(proxy, timeout=300.0) as c:
                fields = {"model": model_name or "whisper-1", "language": "ru"}
                files = {"file": (fname, io.BytesIO(raw), mime)}
                r = c.post(f"{api_base}/v1/audio/transcriptions",
                           headers={"Authorization": f"Bearer {key}"},
                           files=files, data=fields)
            if r.status_code >= 400:
                # Parse error message from JSON if available
                err_msg = f"Провайдер: {r.status_code}"
                try:
                    j = r.json()
                    if isinstance(j, dict):
                        err = j.get("error") or j.get("message") or ""
                        if isinstance(err, str) and err:
                            err_msg += f" — {err[:200]}"
                        elif isinstance(err, dict):
                            err_msg += f" — {str(err)[:200]}"
                except Exception:
                    err_body = r.text[:200]
                    if "<html" in err_body.lower() or "<!doctype" in err_body.lower():
                        err_body = "(HTML-страница, endpoint не поддерживает STT)"
                    err_msg += f" {err_body}"
                return False, "", err_msg
            try:
                j = r.json()
                return True, (j.get("text") or "").strip(), ""
            except Exception:
                return True, r.text.strip(), ""
        except Exception as e:
            return False, "", f"Сетевая ошибка: {str(e)[:200]}"

    ok, text, err = _post(p["api_base"], p["key"], model or "whisper-1")
    if ok:
        return {"ok": True, "text": text, "provider": "primary"}
    # fallback: глобальный ключ/адрес/модель из настроек
    if fallback_key and fallback_base:
        ok2, text2, err2 = _post(fallback_base, fallback_key, fallback_model or "whisper-1")
        if ok2:
            return {"ok": True, "text": text2, "provider": "fallback",
                    "note": f"Первичный провайдер не поддержал STT ({err}); использован запасной ключ"}
        return {"ok": False, "code": "unsupported",
                "error": f"STT недоступен: основной — {err}; запасной — {err2}"}
    return {"ok": False, "code": "unsupported", "error": err}


def _webm_to_mp3(webm_bytes: bytes, proxy: str = "") -> tuple:
    """Конвертирует webm/opus → mp3 через ffmpeg (если установлен).

    Возвращает (mp3_bytes, 'audio/mp3', 'mp3', 'audio.mp3').
    Если ffmpeg не найден — возвращает (webm_bytes, 'audio/webm', 'webm', 'audio.webm')
    и даёт провайдеру шанс обработать webm как есть.
    """
    import subprocess, shutil, tempfile, os
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        # Try common Windows locations
        for path in [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
        ]:
            if os.path.isfile(path):
                ffmpeg = path
                break
    if not ffmpeg:
        # No ffmpeg — return original webm (provider might still handle it)
        return webm_bytes, "audio/webm", "webm", "audio.webm"

    tmp_in = tempfile.mktemp(suffix=".webm")
    tmp_out = tempfile.mktemp(suffix=".mp3")
    try:
        with open(tmp_in, "wb") as f:
            f.write(webm_bytes)
        cmd = [ffmpeg, "-y", "-i", tmp_in, "-acodec", "libmp3lame", "-ab", "128k",
               "-ar", "16000", "-ac", "1", tmp_out]
        if proxy:
            env = os.environ.copy()
            env["http_proxy"] = proxy
            env["https_proxy"] = proxy
        else:
            env = None
        subprocess.run(cmd, capture_output=True, timeout=60, env=env)
        if os.path.isfile(tmp_out):
            with open(tmp_out, "rb") as f:
                mp3 = f.read()
            if mp3 and len(mp3) > 100:
                return mp3, "audio/mpeg", "mp3", "audio.mp3"
    finally:
        for p in (tmp_in, tmp_out):
            try:
                if os.path.exists(p): os.unlink(p)
            except OSError:
                pass
    # ffmpeg failed — return original
    return webm_bytes, "audio/webm", "webm", "audio.webm"


def _b64_bytes(b: bytes) -> str:
    import base64
    return base64.b64encode(b).decode("ascii")


# ===== Голоса: список + клонирование =====
def list_voices(base_url: str = "", api_key: str = "", proxy: str = "") -> dict:
    p = provider_profile("audio", base_url, api_key, "", proxy=proxy)
    if not p["key"]:
        return {"ok": False, "code": "no_key", "error": "Нужен ключ для голоса"}
    # ElevenLabs: GET /v1/voices, заголовок xi-api-key, ответ voices[]
    if _ELEVENLABS_HOST in (p["base"] or ""):
        try:
            with _client(proxy) as c:
                r = c.get(f"{p['base']}/v1/voices", headers={"xi-api-key": p["key"]})
            if r.status_code >= 400:
                return {"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:200]}"}
            data = r.json()
            voices = data.get("voices", [])
            return {"ok": True, "voices": [
                {"id": v.get("voice_id"), "name": v.get("name"), "category": v.get("category"),
                 "labels": v.get("labels", {})} for v in voices]}
        except Exception as e:
            return {"ok": False, "code": "error", "error": str(e)[:200]}
    # Универсальный OpenAI-совместимый: GET /v1/voices (Bearer). Не все провайдеры
    # имеют такой эндпоинт — честно вернём unsupported.
    try:
        with _client(proxy) as c:
            r = c.get(f"{p['api_base']}/v1/voices", headers={"Authorization": f"Bearer {p['key']}"})
        if r.status_code >= 400:
            return {"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:200]}"}
        data = r.json()
        voices = data.get("voices", []) if isinstance(data, dict) else data
        return {"ok": True, "voices": voices}
    except Exception as e:
        return {"ok": False, "code": "error", "error": str(e)[:200]}


def clone_voice(base_url: str = "", api_key: str = "", audio_b64: str = "",
                name: str = "", proxy: str = "") -> dict:
    """Клонирование голоса: из аудио-файла → новый голос."""
    p = provider_profile("audio", base_url, api_key, "", proxy=proxy)
    if not p["key"]:
        return {"ok": False, "code": "no_key", "error": "Нужен ключ для голоса"}
    try:
        import base64 as _b64
        raw = _b64.b64decode(audio_b64)
        if len(raw) < 10_000:
            return {"ok": False, "code": "error", "error": "Аудио слишком короткое для клонирования (нужно > 10 КБ)"}
        if _ELEVENLABS_HOST in (p["base"] or ""):
            # ElevenLabs: POST /v1/voices/add (xi-api-key)
            with _client(proxy, timeout=300.0) as c:
                r = c.post(f"{p['base']}/v1/voices/add",
                           headers={"xi-api-key": p["key"], "Content-Type": "application/json"},
                           json={"name": name or "Cloned voice", "files": [audio_b64], "description": "Instant clone"})
        else:
            # Универсальный OpenAI-совместимый: POST /v1/voices (Bearer).
            with _client(proxy, timeout=300.0) as c:
                r = c.post(f"{p['api_base']}/v1/voices",
                           headers={"Authorization": f"Bearer {p['key']}", "Content-Type": "application/json"},
                           json={"name": name or "Cloned voice", "audio": audio_b64, "type": "clone"})
        if r.status_code >= 400:
            return {"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:200]}"}
        d = r.json()
        return {"ok": True, "voice_id": d.get("id"), "name": d.get("name", name)}
    except Exception as e:
        return {"ok": False, "code": "error", "error": str(e)[:200]}


# ===== Изображения: по промпту + примерам (reference) =====
def generate_image_ref(base_url: str = "", api_key: str = "", model: str = "",
                       prompt: str = "", size: str = "1024x1024",
                       ref_image_b64: str = "", proxy: str = "", extra: dict = None) -> dict:
    """Генерация с примером (reference). Для OpenAI DALL·E-3 / Sora — ref через images.edit."""
    p = provider_profile("image", base_url, api_key, model, proxy=proxy)
    if not p["key"]:
        return {"ok": False, "code": "no_key", "error": "Укажите API-ключ для картинок"}
    _nb = _missing_base_error(p, "картинок")
    if _nb:
        return _nb
    is_agnes = any(h in p["base"] for h in _BASE_PROVIDER_HINTS)
    # Дialect base: OpenAI-совместимый (по умолчанию, работает у любого провайдера).
    # Agnes-хаб требует /v1 в пути — авто-опознанный диалект, дописываем только для него.
    _img_base = p["base"]
    if is_agnes and not _img_base.endswith("/v1"):
        _img_base = f"{_img_base}/v1"

    def _parse_image_resp(r) -> dict:
        if r.status_code >= 400:
            return {"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:300]}"}
        data = r.json()
        item = data.get("data", [{}])[0] if isinstance(data.get("data"), list) else {}
        b64 = item.get("b64_json", "")
        url = item.get("url", "")
        if b64:
            return {"ok": True, "mime": "image/png", "b64": b64}
        if url:
            return {"ok": True, "mime": "image/png", "url": url}
        return {"ok": False, "code": "error", "error": "Не получено изображение"}

    def _is_transient(out: dict) -> bool:
        # Транзитные ошибки провайдера («Failed to reach upstream», 5xx) — ретраим.
        s = str(out.get("error", ""))
        return "upstream" in s.lower() or s.startswith("5")

    def _try_agnes_ref(client, ref_b64: str) -> dict:
        # Agnes: image-to-image через extra_body (RAW base64 или публичный URL).
        # ВАЖНО: НЕ data-URI. Agnes-хаб валидирует extra_body.image как
        # «public http(s) URL or valid image base64» — data:-префикс (data:...)
        # считается невалидным б64 и даёт 400 «extra_body.image is not a valid
        # image base64». Передаём ЧИСТЫЙ base64 (без data:-префикса).
        jbody = {"model": model or _FB_IMAGE_MODEL, "prompt": prompt, "size": size,
                 "extra_body": {"image": [ref_b64], "response_format": "url"}}
        if extra:
            jbody.update(extra)
        return _parse_image_resp(client.post(f"{_img_base}/images/generations",
                                             headers={"Authorization": f"Bearer {p['key']}"},
                                             json=jbody))

    def _try_edits(client, raw: bytes) -> dict:
        # Provider-neutral: OpenAI /images/edits (multipart). Основной путь для ref —
        # работает у любого OpenAI-совместимого провайдера (не только agnes).
        # Мultipart-тело собираем вручную (без urllib3 — он не в зависимостях).
        fields = {"model": model or _FB_IMAGE_MODEL, "prompt": prompt, "size": size}
        if extra:
            fields.update({k: str(v) for k, v in extra.items()})
        boundary = "----amtmedia" + base64.b32encode(os.urandom(8)).decode().lower()
        parts = []
        for k, v in fields.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}'
            )
        parts.append(
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="image[]"; filename="ref.png"\r\n'
            f'Content-Type: image/png\r\n\r\n'
        )
        head = "".join(parts).encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = head + raw + tail
        content_type = f"multipart/form-data; boundary={boundary}"
        return _parse_image_resp(client.post(f"{p['base']}/images/edits",
                                             headers={"Authorization": f"Bearer {p['key']}",
                                                      "Content-Type": content_type},
                                             content=body))

    def _try_text2img(client) -> dict:
        # Обычная генерация (без рефа) — OpenAI-совместимый /images/generations.
        jbody = {"model": model or _FB_IMAGE_MODEL, "prompt": prompt, "n": 1, "size": size}
        if is_agnes:
            # Agnes: return_base64=true → бинарный ответ в data[0].b64_json
            jbody["return_base64"] = True
        if extra:
            jbody.update(extra)
        return _parse_image_resp(client.post(f"{_img_base}/images/generations",
                                              headers={"Authorization": f"Bearer {p['key']}"},
                                              json=jbody))

    def _run_ref(client, raw: bytes, ref_b64: str) -> dict:
        out = _try_edits(client, raw)
        if out.get("ok") is False and is_agnes:
            out = _try_agnes_ref(client, ref_b64)
        if out.get("ok") is False and _is_transient(out):
            time.sleep(2.0)
            out = _try_edits(client, raw)
            if out.get("ok") is False and is_agnes:
                out = _try_agnes_ref(client, ref_b64)
        return out

    try:
        with _client(proxy, timeout=300.0) as c:
            if ref_image_b64:
                raw = base64.b64decode(ref_image_b64)
                # Чистый base64 (без data:-префикса) для agnes extra_body.image.
                # ref_image_b64 приходит из _clean_ref_base64 (уже чистый), но
                # дефензивно отрезаем возможный data:-префикс.
                _clean_ref = ref_image_b64
                if _clean_ref.startswith("data:"):
                    _clean_ref = _clean_ref.split(",", 1)[1] if "," in _clean_ref else _clean_ref
                out = _run_ref(c, raw, _clean_ref)
                if out.get("ok"):
                    return out
                # Provider-neutral fallback: this provider cannot image-edit from a local
                # ref (no /images/edits, or extra_body needs a public URL). Fall back to
                # text-to-image so the user still gets a usable result, with a clear note.
                out2 = _try_text2img(c)
                if out2.get("ok"):
                    out2["note"] = (
                        u"image-to-image not supported by this provider \u2014"
                        u" generated from the text prompt instead"
                    )
                    return out2
                return out
            return _try_text2img(c)
    except Exception as e:
        return {"ok": False, "code": "error", "error": str(e)[:200]}


def generate_video(base_url: str = "", api_key: str = "", model: str = "", prompt: str = "",
                   duration: str = "5", aspect_ratio: str = "16:9", proxy: str = "", extra: dict = None) -> dict:
    """Видео text2video. aspect_ratio: 16:9 (обычное) или 9:16 (кружок/вертикаль).
    Agnes-хаб → POST /v1/videos (создаёт задачу, возвращает video_id). Поллинг — check_video_task_agnes."""
    p = provider_profile("video", base_url, api_key, model, proxy=proxy)
    if not p["key"]:
        return {"ok": False, "code": "no_key", "error": "Укажите API-ключ для генерации видео"}
    _nb = _missing_base_error(p, "видео")
    if _nb:
        return _nb
    is_agnes = any(h in p["base"] for h in _BASE_PROVIDER_HINTS)
    # Agnes-хаб требует /v1 в пути. Если base после обрезки не содержит /v1 — допишем.
    _agnes_base = p["base"]
    if is_agnes and not _agnes_base.endswith("/v1"):
        _agnes_base = f"{_agnes_base}/v1"
    try:
        with _client(proxy, timeout=300.0) as c:
            # Provider-neutral: standard OpenAI-compatible /v1/videos/text2video first.
            # The provider-dialect path (config-hinted /videos with mode/seconds/size) is
            # only a FALLBACK when the standard endpoint 4xx/5xx and the provider is
            # auto-detected from config hints.
            r = c.post(f"{p['api_base']}/v1/videos/text2video",
                       headers={"Authorization": f"Bearer {p['key']}"},
                       json=_gen_video_body(prompt, duration, aspect_ratio, model, extra))
            if r.status_code >= 400 and is_agnes:
                _vid_model = model if "video" in (model or "").lower() else (_FB_VIDEO_MODEL or model or "video")
                _sec = str(duration or "5")
                body = {**{"model": _vid_model, "prompt": prompt,
                            "mode": "text", "seconds": _sec,
                            "size": "720P", "aspect_ratio": aspect_ratio, "n": 1},
                         **({} if not extra else extra)}
                r = c.post(f"{_agnes_base}/videos",
                           headers={"Authorization": f"Bearer {p['key']}", "Content-Type": "application/json"},
                           json=body)
        if r.status_code in (200, 201, 202):
            d = r.json()
            # Agnes: video_id; OpenAI-style: task_id / data[]
            vid = d.get("video_id") or d.get("task_id") or (d.get("data") or {}).get("task_id") or ""
            url = d.get("url", "")
            # model_name: для Agnes нужно передать при опросе
            _mn = model if "video" in (model or "").lower() else (_FB_VIDEO_MODEL or model or "")
            return {"ok": True, "task_id": vid, "video_id": vid, "url": url, "aspect_ratio": aspect_ratio,
                    "model_name": _mn,
                    "raw": d, "agnes": is_agnes,
                    "note": "Видео генерируется (задача создана)" + (" — URL готов" if url else "")}
        return {"ok": False, "code": "unsupported", "error": f"Провайдер: {r.status_code} {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "code": "error", "error": str(e)[:200]}


def generate_video_example(base_url: str = "", api_key: str = "", model: str = "", prompt: str = "",
                           example_b64: str = "", duration: str = "5",
                           aspect_ratio: str = "16:9", proxy: str = "", extra: dict = None) -> dict:
    """Видео video2video: видео по промпту + примеру-видео."""
    p = provider_profile("video", base_url, api_key, model, proxy=proxy)
    if not p["key"]:
        return {"ok": False, "code": "no_key", "error": "Укажите API-ключ для генерации видео"}
    _nb = _missing_base_error(p, "видео")
    if _nb:
        return _nb
    try:
        import base64 as _b64
        raw = _b64.b64decode(example_b64)
        fields = {"prompt": prompt, "duration": duration, "aspect_ratio": aspect_ratio}
        if extra:
            fields.update({k: str(v) for k, v in extra.items()})
        # Multipart assembled manually (no urllib3 - not in dependencies).
        boundary = "----amtmedia" + _b64.b32encode(os.urandom(8)).decode().lower()
        parts = []
        for k, v in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}')
        parts.append(
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="video[]"; filename="example.mp4"\r\n'
            f'Content-Type: video/mp4\r\n\r\n'
        )
        head = "".join(parts).encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = head + raw + tail
        content_type = f"multipart/form-data; boundary={boundary}"
        with _client(proxy, timeout=300.0) as c:
            r = c.post(f"{p['api_base']}/v1/videos/video2video",
                       headers={"Authorization": f"Bearer {p['key']}", "Content-Type": content_type},
                       content=body)
        if r.status_code in (200, 201, 202):
            d = r.json()
            tid = (d.get("data") or {}).get("task_id") or d.get("task_id") or ""
            return {"ok": True, "task_id": tid, "aspect_ratio": aspect_ratio, "raw": d,
                    "note": "Видео по примеру создано — опрашиваем статус."}
        return {"ok": False, "code": "unsupported", "error": f"Провайдер: {r.status_code} {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "code": "error", "error": str(e)[:200]}
