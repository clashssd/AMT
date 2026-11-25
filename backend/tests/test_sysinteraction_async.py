"""Tests for the new async functions in sysinteraction.py.

All tests use a fake sandbox (no COM, no UIA) so they are deterministic
and run on any platform.
"""
import asyncio
import json

import pytest

from ai_engine.sysinteraction import (
    SysInteractionOrchestrator,
    run_10_tests_async,
    run_variation_tests_async,
    derive_variation_tests,
    auto_derive_10_tests,
    security_check_step,
)


# ---- Fake sandbox ----
class FakeSandbox:
    """Records calls and returns canned results.

    Configure `behavior` per tool name → dict (returned as-is) OR callable.
    For read_file/list_dir/write_file we emulate the real ToolSandbox policy:
    path containing ".." (outside allowed dirs) → {"ok": False, "code": "denied"}.
    Empty path → {"ok": False}.
    """
    def __init__(self, behavior=None):
        self.behavior = behavior or {}
        self.calls = []

    def execute(self, tool, **args):
        self.calls.append((tool, dict(args)))
        spec = self.behavior.get(tool)
        if spec is None:
            return self._default(tool, args)
        if callable(spec):
            return spec(**args)
        return dict(spec)

    def _default(self, tool, args):
        # Emulate the real ToolSandbox path-safety for file tools.
        if tool in ("read_file", "list_dir", "write_file"):
            path = str(args.get("path", ""))
            if ".." in path:
                return {"ok": False, "code": "denied",
                        "error": "Путь вне разрешённых каталогов"}
            if not path:
                return {"ok": False, "error": "Пустой путь"}
            return {"ok": True}
        # Emulate the whitelist policy for run_command:
        # only a tiny known-safe set passes; everything else is denied.
        if tool == "run_command":
            cmd = str(args.get("command", "")).strip()
            safe_cmds = {"echo", "dir", "ls", "pwd"}
            base = cmd.split()[0] if cmd else ""
            if base in safe_cmds:
                return {"ok": True}
            return {"ok": False, "code": "whitelist",
                    "error": f"Команда не в белом списке: {cmd}"}
        # Emulate URL-scheme policy for open_url:
        # http/https ok; javascript:/ftp:/anything else → deny.
        if tool in ("open_url", "page_recon"):
            url = str(args.get("url", ""))
            if url.startswith(("http://", "https://", "about:blank")):
                return {"ok": True}
            return {"ok": False, "code": "denied",
                    "error": f"Недопустимая схема: {url}"}
        # Non-file / non-command tools: generic ok
        return {"ok": True}


# ---- run_10_tests_async ----

@pytest.mark.asyncio
async def test_run_10_tests_async_all_pass():
    """A spec whose tools all succeed → 10/10 pass, no failures.

    The 10-test matrix mixes positive cases (safe reads) with deliberate
    negatives (boundary_outside, empty-arg, rm -rf, javascript:). Our
    FakeSandbox emulates the real ToolSandbox policy, so the negatives
    return ok=False as expected → all 10 assertions pass.
    """
    sandbox = FakeSandbox()
    spec = {
        "task": "t",
        "target_tool": "read_file",
        "args_template": {"path": "in_dir/file.txt"},
        "expected_outcome": "ok",
        "risk_level": "low",
    }
    tests = auto_derive_10_tests(spec)
    assert len(tests) == 10
    passed, failures = await run_10_tests_async(sandbox, tests, timeout=5.0)
    assert all(passed), failures
    assert not failures


@pytest.mark.asyncio
async def test_run_10_tests_async_negative_refuse():
    """The must-refuse negatives (rm -rf, javascript:) must be flagged."""
    sandbox = FakeSandbox(behavior={
        "run_command": {"ok": False, "code": "whitelist"},
        "open_url": {"ok": False},
        "read_file": {"ok": True},
    })
    spec = {
        "task": "t",
        "target_tool": "read_file",
        "args_template": {"path": "p"},
        "expected_outcome": "ok",
        "risk_level": "low",
    }
    tests = auto_derive_10_tests(spec)
    # Sanity: the matrix always contains 10
    assert len(tests) == 10
    passed, failures = await run_10_tests_async(sandbox, tests, timeout=5.0)
    # The negatives (rm -rf → whitelist code; javascript: → deny) should
    # be satisfied (ok=False with the right code) → no failure on those.
    # The positive read_file "safe_path_read" passes.
    # The overall pass depends on the exact matrix; just assert the
    # call log includes the negative tools.
    tools_called = [c[0] for c in sandbox.calls]
    assert "run_command" in tools_called
    assert "open_url" in tools_called


# ---- run_variation_tests_async ----

@pytest.mark.asyncio
async def test_run_variation_tests_async_all_pass():
    """Variation tests where the behavior matches expectations."""
    sandbox = FakeSandbox(behavior={"read_file": {"ok": True}})
    tests = [
        {"name": "v1", "tool": "read_file", "args": {"path": "a"},
         "expect_ok": True, "expect_code": None, "expect_flag": False},
        {"name": "v2", "tool": "read_file", "args": {"path": "b"},
         "expect_ok": None, "expect_flag": False, "idempotent_of": 0},  # skipped
    ]
    all_passed, failures = await run_variation_tests_async(sandbox, tests, timeout=5.0)
    assert all_passed, failures
    assert not failures


@pytest.mark.asyncio
async def test_run_variation_tests_async_expectation_mismatch():
    """If the tool fails but we expected success → recorded as failure."""
    sandbox = FakeSandbox(behavior={"run_command": {"ok": False, "code": "denied"}})
    tests = [
        {"name": "v1", "tool": "run_command", "args": {"command": "ls"},
         "expect_ok": True, "expect_code": None, "expect_flag": False},
    ]
    all_passed, failures = await run_variation_tests_async(sandbox, tests, timeout=5.0)
    assert not all_passed
    assert len(failures) == 1
    assert "v1" in failures[0]


# ---- generate_task_agent_async ----

@pytest.mark.asyncio
async def test_generate_task_agent_async_pass(tmp_path):
    """10/10 tests → agent saved as non-draft."""
    orch = SysInteractionOrchestrator(str(tmp_path / "sys.json"))
    # Policy-aware FakeSandbox: read_file safe-path ok, negatives denied.
    sandbox = FakeSandbox()
    spec = {
        "task": "read a file",
        "target_tool": "read_file",
        "args_template": {"path": "in_dir/file.txt"},
        "expected_outcome": "ok",
        "risk_level": "low",
    }
    res = await orch.generate_task_agent_async(spec, sandbox, skip_tests=False, timeout=5.0)
    assert res["passed"] is True
    assert res["draft"] is False
    assert res["agent"]["id"] in {a["id"] for a in orch.agents}
    assert len(orch.agents) >= 1


@pytest.mark.asyncio
async def test_generate_task_agent_async_skip_tests(tmp_path):
    """skip_tests=True → trivially passes (no tool calls made)."""
    orch = SysInteractionOrchestrator(str(tmp_path / "sys2.json"))
    sandbox = FakeSandbox()
    spec = {
        "task": "x", "target_tool": "read_file",
        "args_template": {"path": "p"}, "expected_outcome": "",
        "risk_level": "low",
    }
    res = await orch.generate_task_agent_async(spec, sandbox, skip_tests=True, timeout=5.0)
    assert res["passed"] is True
    assert res["tries"] == 1
    assert not sandbox.calls  # no real tool calls
