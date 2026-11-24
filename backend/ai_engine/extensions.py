"""
Задуги (extensions) backend.

Система расширений: папка `extensions/` содержит подпапки, каждая из них —
расширение. В каждом может быть:
- `manifest.json` — метаданные (name, version, description, frontend/backend flags)
- `backend.py` — опциональный Python-модуль с функцией `init(ctx)`
- `index.js` — опциональный JS для фронтенда

Безопасность: одно расширение НЕ должно ронять приложение. Каждая ошибка
ловится, логируется, расширение пропускается.
"""
import os
import json
import importlib.util
import logging
from typing import Optional

logger = logging.getLogger("amt-chat.extensions")

# Глобальный реестр загруженных расширений (по имени)
_REGISTRY: dict = {}
_LOADED = False


def _extensions_dir() -> str:
    """Корневая папка расширений. Можно переопределить через AMT_EXTENSIONS_DIR.
    В замороженном бинарнике (PyInstaller) — _internal/extensions, в dev — ../.. /extensions."""
    import sys
    if os.environ.get("AMT_EXTENSIONS_DIR"):
        return os.environ["AMT_EXTENSIONS_DIR"]
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "_internal", "extensions")
    return os.path.join(os.path.dirname(__file__), "..", "..", "extensions")


def extensions_root() -> str:
    """Публичная обёртка: абсолютный путь к корневому каталогу расширений."""
    return os.path.abspath(_extensions_dir())


def _manifest_path(ext_dir: str) -> str:
    return os.path.join(ext_dir, "manifest.json")


def _load_manifest(ext_dir: str) -> Optional[dict]:
    p = _manifest_path(ext_dir)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("extensions: bad manifest %s: %s", p, e)
        return None


def _import_backend(ext_dir: str, ctx: dict):
    """Загрузить backend.py расширения и вызвать init(ctx)."""
    backend_py = os.path.join(ext_dir, "backend.py")
    if not os.path.exists(backend_py):
        return False
    spec = importlib.util.spec_from_file_location(
        "amt_ext_" + os.path.basename(ext_dir), backend_py
    )
    if not spec or not spec.loader:
        logger.warning("extensions: cannot import %s", backend_py)
        return False
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        if hasattr(module, "init"):
            module.init(ctx)
        logger.info("extensions: loaded backend module for %s", os.path.basename(ext_dir))
        return True
    except Exception as e:
        logger.exception("extensions: failed to init %s: %s", os.path.basename(ext_dir), e)
        return False


def load_extensions() -> dict:
    """Сканирует extensions/ и загружает все backend-расширения.

    Возвращает словарь: имя -> {name, manifest, ok}
    Идемпотентно: второй вызов не повторяет init (кроме как при AMT_EXT_RELOAD=1).
    """
    global _LOADED
    if _LOADED and not os.environ.get("AMT_EXT_RELOAD"):
        return _REGISTRY

    ext_root = os.path.abspath(_extensions_dir())
    if not os.path.isdir(ext_root):
        logger.info("extensions: dir %s not found, skipping", ext_root)
        _LOADED = True
        return _REGISTRY

    # ctx передаётся в каждое расширение
    from ai_engine.tools import tools as _tools
    ctx = {
        "tools": _tools,
        "extensions_dir": ext_root,
    }

    for name in sorted(os.listdir(ext_root)):
        ext_dir = os.path.join(ext_root, name)
        if not os.path.isdir(ext_dir):
            continue
        manifest = _load_manifest(ext_dir)
        if manifest is None:
            # нет manifest — пропускаем
            continue
        ext_name = manifest.get("name", name)
        has_backend = manifest.get("backend", False)
        ok = False
        if has_backend:
            ok = _import_backend(ext_dir, ctx)
        _REGISTRY[ext_name] = {
            "name": ext_name,
            "manifest": manifest,
            "ok": ok or not has_backend,
            "dir": ext_dir,
        }

    _LOADED = True
    logger.info("extensions: loaded %d extension(s)", len(_REGISTRY))
    return _REGISTRY


def get_registry() -> dict:
    if not _LOADED:
        load_extensions()
    return _REGISTRY


# ---- Вкл/выкл расширений (persist) ----
# Состояние хранится в extensions_state.json: {name: bool}. По умолчанию все вкл.
def _state_file() -> str:
    import sys
    if os.environ.get("AMT_EXTENSIONS_STATE"):
        return os.environ["AMT_EXTENSIONS_STATE"]
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "_internal", "extensions_state.json")
    return os.path.join(os.path.dirname(__file__), "..", "..", "extensions_state.json")


def _load_state() -> dict:
    p = _state_file()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    p = _state_file()
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def is_enabled(name: str) -> bool:
    """Включено ли расширение (по умолчанию True, если не выключено явно)."""
    st = _load_state()
    return st.get(name, True)


def set_enabled(name: str, enabled: bool) -> bool:
    """Вкл/выкл расширение. Записывает состояние в extensions_state.json."""
    st = _load_state()
    st[name] = bool(enabled)
    _save_state(st)
    return enabled


def list_for_api() -> list:
    """Публичный список для GET /api/extensions/list (с флагом enabled)."""
    reg = get_registry()
    out = []
    for name, info in reg.items():
        m = info.get("manifest", {})
        out.append({
            "name": name,
            "version": m.get("version", "0.0.0"),
            "description": m.get("description", ""),
            "frontend": m.get("frontend", False),
            "backend": m.get("backend", False),
            "ok": info.get("ok", False),
            "enabled": is_enabled(name),
        })
    return out


def list_with_root_for_api() -> dict:
    """Список расширений + корневой каталог (для UI: показать путь)."""
    return {"extensions": list_for_api(), "dir": extensions_root()}


def remove_extension(name: str) -> dict:
    """Удаляет расширение: папку, запись состояния и запись в реестре.

    Returns: {"ok": bool, "error": str|None, "removed_dir": str|None}
    """
    import shutil
    reg = get_registry()
    info = reg.get(name)
    if not info:
        return {"ok": False, "error": "Неизвестное расширение", "code": "not_found"}

    ext_dir = info.get("dir")
    # Безопасность: только внутри корневого каталога расширений
    root = extensions_root()
    if ext_dir and os.path.abspath(ext_dir).startswith(os.path.abspath(root) + os.sep):
        try:
            shutil.rmtree(ext_dir)
        except Exception as e:
            logger.warning("extensions: failed to remove dir %s: %s", ext_dir, e)
            return {"ok": False, "error": f"Не удалось удалить папку: {e}"}
    # Удаляем запись состояния
    st = _load_state()
    st.pop(name, None)
    _save_state(st)
    # Убираем из реестра и пересканируем
    reg.pop(name, None)
    global _LOADED
    _LOADED = False
    load_extensions()
    return {"ok": True, "removed_dir": ext_dir}
