"""Unit tests for run_com_sync (async_utils.py) — Layer 1.1.

run_com_sync must:
  * run the function in a STA thread
  * return {"ok": True, "result": <raw>} on success
  * return {"ok": False, "code": "timeout", "error": "..."} when the fn
    exceeds `timeout` (without hanging the caller)
  * return {"ok": False, "code": "exception", "error": "..."} when the fn
    raises
"""
import asyncio
import time

import pytest

from ai_engine.async_utils import run_com_sync


def _add(a, b):
    return a + b


def _sleep(n):
    time.sleep(n)
    return "slept"


def _raise():
    raise RuntimeError("boom")


def test_run_com_sync_success():
    async def run():
        out = await run_com_sync(_add, 2, 3, timeout=2.0)
        return out

    res = asyncio.run(run())
    assert res == {"ok": True, "result": 5}


def test_run_com_sync_timeout():
    async def run():
        out = await run_com_sync(_sleep, 5.0, timeout=0.1)
        return out

    t0 = time.time()
    res = asyncio.run(run())
    dt = time.time() - t0
    assert res["ok"] is False
    assert res["code"] == "timeout"
    assert "Таймаут" in res["error"] or "timeout" in res["error"].lower()
    # Should NOT have waited 5s — should have returned fast.
    assert dt < 3.0


def test_run_com_sync_exception():
    async def run():
        out = await run_com_sync(_raise, timeout=2.0)
        return out

    res = asyncio.run(run())
    assert res["ok"] is False
    assert res["code"] == "exception"
    assert "boom" in res["error"]


def test_run_com_sync_kwargs():
    """kwargs must reach the wrapped fn (used by _exec_sandbox)."""
    captured = {}

    def _capture(a, b=0):
        captured["a"] = a
        captured["b"] = b
        return "done"

    async def run():
        return await run_com_sync(_capture, "x", b=99, timeout=1.0)

    res = asyncio.run(run())
    assert res == {"ok": True, "result": "done"}
    assert captured == {"a": "x", "b": 99}


def test_sys_coinit_flags_set():
    """sys.coinit_flags must be 2 (STA) before COM imports."""
    import sys
    assert sys.coinit_flags == 2
