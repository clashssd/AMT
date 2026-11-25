"""Layer 1 (async isolation) at the main.py level.

`_exec_sandbox` is the single choke-point for all sandbox calls in async
context. It must:
  * route through run_com_sync (STA pool)
  * unwrap the result on success → raw dict
  * on COM timeout/exception → return structured {"ok": False, "code", "error"}
"""
import asyncio
import re

import pytest

# main.py import (module-level side effects isolated by conftest._isolate_main)
import main as main_mod
from ai_engine.async_utils import run_com_sync
from conftest import make_sandbox_stub


# ---- _exec_sandbox ----

def test_exec_sandbox_success_passthrough():
    """A successful sandbox.execute result is unwrapped to the raw dict."""
    # Point the real global tools_sandbox at a stub that always returns ok.
    original = main_mod.tools_sandbox
    main_mod.tools_sandbox = make_sandbox_stub()
    try:
        res = asyncio.run(main_mod._exec_sandbox("read_file", timeout=5.0, path="x"))
        assert res.get("ok") is True
        assert res.get("echo", {}).get("read_file", {}).get("path") == "x"
    finally:
        main_mod.tools_sandbox = original


def test_exec_sandbox_timeout_returns_structured_error():
    """When the underlying call times out in the STA pool, we must
    get a structured error dict (not an exception, not a hang)."""
    # A stub whose execute blocks past the timeout.
    def _block(**kwargs):
        import time as _t
        _t.sleep(2.0)
        return {"ok": True}

    main_mod.tools_sandbox = make_sandbox_stub()
    # Override the execute with the blocking one
    main_mod.tools_sandbox.execute = lambda tool, **kw: _block(**kw)
    try:
        res = asyncio.run(main_mod._exec_sandbox("read_file", timeout=0.1, path="x"))
        assert res.get("ok") is False
        assert res.get("code") in ("timeout", "exception")
    finally:
        main_mod.tools_sandbox = make_sandbox_stub()


# ---- resolve_sys_tokens (async) ----

def test_resolve_sys_tokens_inert_when_inactive():
    """active=False → tokens stay in the text untouched."""
    text = "Hi [[SYS:open_url|https://example.com]]"
    out = asyncio.run(main_mod.resolve_sys_tokens(text, active=False))
    assert out == text


def test_resolve_sys_tokens_strips_task_spec_and_plan_when_active():
    """Even with no executable tokens, active=True must strip the
    [[SYS:task_spec]] and [[SYS:plan]] markers (handled upstream)."""
    main_mod.tools_sandbox = make_sandbox_stub()
    try:
        text = (
            "Hello [[SYS:task_spec|{\"task\":\"x\",\"target_tool\":\"read_file\","
            "\"args_template\":{},\"expected_outcome\":\"\",\"risk_level\":\"low\"}]] "
            "[[SYS:plan|{\"goal\":\"g\",\"steps\":[]}]] world"
        )
        out = asyncio.run(main_mod.resolve_sys_tokens(text, active=True))
        assert "task_spec" not in out
        assert "SYS:plan" not in out
        assert "Hello" in out
        assert "world" in out
    finally:
        main_mod.tools_sandbox = make_sandbox_stub()


def test_resolve_sys_tokens_open_url_invalid_scheme():
    """A non-http(s) URL must not be executed — LLM gets a clear error."""
    main_mod.tools_sandbox = make_sandbox_stub()
    try:
        text = "x [[SYS:open_url|ftp://example.com/file]] y"
        out = asyncio.run(main_mod.resolve_sys_tokens(text, active=True))
        assert "некорректный URL" in out
        assert "ftp://" not in out.replace("ftp://example.com", "")  # token was replaced
        # The raw FTP token should be gone (replaced with the error text)
        assert "[[SYS:open_url|ftp" not in out
    finally:
        main_mod.tools_sandbox = make_sandbox_stub()


def test_resolve_sys_tokens_open_url_success():
    """A valid http URL is executed and replaced with a human summary."""
    def _open_url(**kw):
        return {"ok": True, "browser": "Edge", "url": kw.get("url")}

    main_mod.tools_sandbox = make_sandbox_stub()
    main_mod.tools_sandbox.execute = lambda tool, **kw: (
        _open_url(**kw) if tool == "open_url" else {"ok": True}
    )
    try:
        text = "a [[SYS:open_url|https://example.com|Edge]] b"
        out = asyncio.run(main_mod.resolve_sys_tokens(text, active=True))
        assert "Открыл" in out
        assert "https://example.com" in out
        assert "[[SYS:open_url" not in out
    finally:
        main_mod.tools_sandbox = make_sandbox_stub()


def test_resolve_sys_tokens_window_click_bad_coords():
    """Non-integer coords must be rejected with a clear message."""
    main_mod.tools_sandbox = make_sandbox_stub()
    try:
        text = "c [[SYS:window_click|abc|def]] d"
        out = asyncio.run(main_mod.resolve_sys_tokens(text, active=True))
        assert "Некорректные координаты" in out
        assert "[[SYS:window_click" not in out
    finally:
        main_mod.tools_sandbox = make_sandbox_stub()
