"""Асинхронная изоляция COM-зависимых desktop-функций.

Проблема: UIA (comtypes/pywinauto) требует STA-апартамент (COINIT_APARTMENTTHREADED).
Если вызывать desktop_sandbox.execute() напрямую из asyncio-потребителя (FastAPI endpoint),
COM-объекты создаются в MTA-потоке и UIA ломается (RpcException, access violation).

Решение: run_com_sync() запускает sync-функцию в dedicated STA-потоке (ThreadPoolExecutor)
и ждёт результат через asyncio.wait_for с таймаутом. Каждый поток пула — STA.

Использование:
    from ai_engine.async_utils import run_com_sync
    result = await run_com_sync(desktop_sandbox.execute, "window_ui_recon", app="chrome", timeout=10.0)
"""

import asyncio
import ctypes
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

logger = logging.getLogger("amt-async-utils")

# COINIT_APARTMENTTHREADED = 2 — устанавливаем ДО импорта pywinauto/comtypes.
# Это нужно для всех потоков, которые будут использовать COM (UIA).
sys.coinit_flags = 2

# Пул STA-потоков. Каждый поток инициализирует COM как STA.
# 4 воркера — достаточно для параллельных desktop-запросов.
_COM_THREAD_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="amt-com")


def _init_com_thread() -> None:
    """Инициализирует COM-апартамент (STA) в текущем потоке.

    Вызывается в каждом потоке пула перед первым COM-вызовом.
    CoInitialize(None) в STA-потоке → S_OK или S_FALSE (уже инициализирован).
    """
    if sys.platform == "win32":
        try:
            hr = ctypes.windll.ole32.CoInitialize(None)
            # hr == 0 (S_OK) или hr == 1 (S_FALSE — уже инициализирован)
            if hr not in (0, 1):
                logger.warning("CoInitialize returned hr=0x%X", hr)
        except Exception as e:
            logger.warning("CoInitialize failed: %s", e)


def _uninit_com_thread() -> None:
    """Финализует COM-апартамент в текущем потоке (при завершении)."""
    if sys.platform == "win32":
        try:
            ctypes.windll.ole32.CoUninitialize()
        except Exception:
            pass


class _ComThreadWrapper:
    """Обёртка над Callable, которая инициализирует COM в STA-потоке."""

    def __init__(self, fn: Callable, *args, **kwargs):
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._initialized = False

    def __call__(self) -> Any:
        if not self._initialized:
            _init_com_thread()
            self._initialized = True
        return self._fn(*self._args, **self._kwargs)

    def cleanup(self) -> None:
        """Вызывается после завершения — финализирует COM."""
        if self._initialized:
            _uninit_com_thread()


async def run_com_sync(
    fn: Callable,
    *args,
    timeout: float = 10.0,
    **kwargs,
) -> dict:
    """Запускает sync-функцию в STA-потоке с таймаутом.

    Args:
        fn: sync-функция (например, desktop_sandbox.execute).
        *args: позиционные аргументы для fn.
        timeout: таймаут в секундах (по умолчанию 10.0).
        **kwargs: именованные аргументы для fn.

    Returns:
        dict с результатом:
          Успех:  {"ok": True, "result": <return value of fn>}
          Ошибка: {"ok": False, "error": str, "code": "timeout"|"error"|"exception"}

    Пример:
        result = await run_com_sync(desktop_sandbox.execute, "window_ui_recon", app="chrome", timeout=10.0)
        if result.get("ok"):
            elements = result["result"]["elements"]
    """
    wrapper = _ComThreadWrapper(fn, *args, **kwargs)

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(_COM_THREAD_POOL, wrapper)

    try:
        raw_result = await asyncio.wait_for(future, timeout=timeout)
        # fn вернула dict (стандартный формат DesktopSandbox) — оборачиваем
        if isinstance(raw_result, dict):
            return {"ok": True, "result": raw_result}
        return {"ok": True, "result": raw_result}
    except asyncio.TimeoutError:
        # Отменяем future (если ещё не завершил)
        if not future.done():
            future.cancel()
        logger.warning("run_com_sync timeout (%.1fs): %s(%s)", timeout, fn.__name__, args)
        return {
            "ok": False,
            "code": "timeout",
            "error": f"Таймаут COM-операции ({timeout:.1f}s): {fn.__name__}",
        }
    except PermissionError as e:
        logger.warning("run_com_sync permission denied: %s", e)
        return {
            "ok": False,
            "code": "denied",
            "error": str(e),
        }
    except Exception as e:
        logger.warning("run_com_sync exception: %s", e)
        return {
            "ok": False,
            "code": "exception",
            "error": str(e),
        }
    finally:
        # Финализуем COM в потоке (безопасно, если future уже завершён)
        if future.done():
            wrapper.cleanup()


def create_com_pool(max_workers: int = 4) -> ThreadPoolExecutor:
    """Создаёт новый пул STA-потоков (для тестов / перезапуска).

    По умолчанию использует глобальный _COM_THREAD_POOL.
    """
    return ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="amt-com-pool")
