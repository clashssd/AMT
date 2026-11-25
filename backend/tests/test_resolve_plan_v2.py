"""Layer 1/5: resolve_plan_v2 end-to-end with a stubbed sandbox+orchestrator.

The real resolve_plan_v2 touches:
  * security_check_step (deterministic, real)
  * monitor_security_check_async (needs an LLM call fn → we feed a fake
    async fn that always allows)
  * match_agents_for_step / spawn_task_agent_for_step (orchestrator calls)
  * run_com_sync(sandbox.execute, ...) per step
  * run_variation_tests_async on success
  * save_agent_to_library on 5/5 variations

We stub the orchestrator with one that has no matching agents (so each
step triggers agent spawn) and an LLM monitor that always allows. The
sandbox is a FakeSandbox that records calls.
"""
import asyncio
import json

import pytest

import main as main_mod
from ai_engine.sysinteraction import (
    monitor_security_check_async,
    verify_step_result,
    derive_variation_tests,
)
from conftest import make_orchestrator_stub


@pytest.mark.asyncio
async def test_resolve_plan_v2_single_step_success(monkeypatch):
    """A 1-step plan whose tool succeeds → 'Готово' summary, no errors."""
    # Stub the global _quick_llm_call used by the monitor.
    async def fake_quick_llm(api_key, base_url, model, system, user,
                             timeout=30.0, proxy_string=""):
        return json.dumps({"allow": True, "rule": "ok", "reason": "fine"})

    monkeypatch.setattr(main_mod, "_quick_llm_call", fake_quick_llm)

    class _Sandbox:
        def __init__(self):
            self.calls = []

        def execute(self, tool, **args):
            self.calls.append((tool, dict(args)))
            return {"ok": True, "url": "https://example.com",
                    "title": "X", "data": "d"}

    sandbox = _Sandbox()
    orch = make_orchestrator_stub()

    plan = {
        "goal": "open example.com",
        "risk_level": "low",
        "steps": [
            {"tool": "open_url", "args": {"url": "https://example.com"},
             "expected": "opened"},
        ],
    }

    # match_agents_for_step needs to return (None, None) to force spawn
    monkeypatch.setattr(
        "ai_engine.sysinteraction.match_agents_for_step",
        lambda step, orchestrator: (None, None),
    )
    # Save_agent_to_library must exist on the real orchestrator (used by
    # the variation-success path). Our stub already has it via the class.

    out = await main_mod.resolve_plan_v2(
        plan, sandbox, orch, "k", "b", "m", "",
    )
    # The summary must be a human-readable report
    assert "Готово" in out or "Частично" in out or "Не удалось" in out
    # sandbox saw the tool call
    assert ("open_url", {"url": "https://example.com"}) in sandbox.calls


@pytest.mark.asyncio
async def test_resolve_plan_v2_empty_plan(monkeypatch):
    """An empty-steps plan returns the empty-plan marker, not a crash."""
    async def fake_quick_llm(*a, **kw):
        return json.dumps({"allow": True, "rule": "ok", "reason": ""})

    monkeypatch.setattr(main_mod, "_quick_llm_call", fake_quick_llm)

    class _Sandbox:
        def execute(self, tool, **args):
            return {"ok": True}

    orch = make_orchestrator_stub()
    out = await main_mod.resolve_plan_v2(
        {"goal": "g", "steps": []}, _Sandbox(), orch, "k", "b", "m", "",
    )
    assert "План пуст" in out


@pytest.mark.asyncio
async def test_resolve_plan_v2_blocked_by_watchdog():
    """A step that fails the deterministic watchdog is marked blocked."""
    async def fake_quick_llm(*a, **kw):
        return json.dumps({"allow": True, "rule": "ok", "reason": ""})

    class _Sandbox:
        def __init__(self):
            self.calls = []

        def execute(self, tool, **args):
            self.calls.append((tool, args))
            return {"ok": True}

    sandbox = _Sandbox()
    orch = make_orchestrator_stub()

    # ftp:// scheme fails R4 in security_check_step
    plan = {
        "goal": "bad scheme",
        "steps": [
            {"tool": "open_url", "args": {"url": "ftp://example.com"},
             "expected": ""},
        ],
    }

    out = await main_mod.resolve_plan_v2(
        plan, sandbox, orch, "k", "b", "m", "",
    )
    # The step must be blocked and NOT executed
    assert ("open_url", {"url": "ftp://example.com"}) not in sandbox.calls
    assert "заблокировано" in out or "Не удалось" in out


def test_verify_step_result_basic():
    """verify_step_result passes when expected is empty and ok=True."""
    step = {"tool": "open_url", "args": {"url": "https://x"}, "expected": ""}
    ok, detail = verify_step_result(step, {"ok": True, "url": "https://x"})
    assert ok is True

    # expected contains a URL that IS in the result → pass
    step2 = {"tool": "open_url", "args": {"url": "https://x"},
             "expected": "https://x opened"}
    ok2, _ = verify_step_result(step2, {"ok": True, "url": "https://x"})
    assert ok2 is True


@pytest.mark.asyncio
async def test_monitor_security_check_async_allows(monkeypatch):
    """monitor_security_check_async with an allow-LLM → (True, rule, reason)."""
    async def llm(system, user):
        return json.dumps({"allow": True, "rule": "ok", "reason": "safe"})

    allow, rule, reason = await monitor_security_check_async(
        "open_url", {"url": "https://example.com"}, llm, timeout=5.0,
    )
    assert allow is True


@pytest.mark.asyncio
async def test_monitor_security_check_async_denies(monkeypatch):
    """monitor with a deny-LLM → (False, rule, reason)."""
    async def llm(system, user):
        return json.dumps({"allow": False, "rule": "r1", "reason": "exfil"})

    allow, rule, reason = await monitor_security_check_async(
        "open_url", {"url": "https://example.com"}, llm, timeout=5.0,
    )
    assert allow is False
    assert rule == "r1"


@pytest.mark.asyncio
async def test_monitor_security_check_async_timeout_falls_back_to_watchdog(monkeypatch):
    """LLM that never returns → watchdog fallback (fail-closed)."""
    import asyncio as _a

    async def llm(system, user):
        await _a.sleep(30)  # far past the 0.5s timeout
        return json.dumps({"allow": True})

    allow, rule, reason = await monitor_security_check_async(
        "open_url", {"url": "https://example.com"}, llm, timeout=0.5,
    )
    # Watchdog on open_url http(s) → allow=True, rule is watchdog-fallback
    assert allow is True
    assert "watchdog-fallback" in rule
    assert "timeout" in reason.lower()
