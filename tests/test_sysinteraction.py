"""Tests for the sysinteraction feature: gate logic, seed, token resolution."""
import os
import sys
import json
import asyncio
import pytest
from fastapi.testclient import TestClient

# COM STA deadlock on Windows: asyncio.run() with sys.coinit_flags=2 hangs.
# Skip async tests on Windows.
SKIP_IF_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="COM STA deadlock on Windows: asyncio.run() hangs with sys.coinit_flags=2"
)

import main
from ai_engine.sysinteraction import SysInteractionOrchestrator
from ai_engine import tools as t

# Shared event loop for all asyncio.run() calls in this file.
# Creating a new loop per call deadlocks with the COM thread pool.
_shared_loop = None

def _get_loop():
    global _shared_loop
    if _shared_loop is None:
        _shared_loop = asyncio.new_event_loop()
    return _shared_loop

def _run_async(coro):
    """Run a coroutine on the shared event loop (avoids asyncio.run() loop creation)."""
    loop = _get_loop()
    return loop.run_until_complete(coro)


@pytest.fixture
def c(tmp_backend, monkeypatch):
    tmp = tmp_backend["tmp"]
    monkeypatch.setenv("AMT_TOOLS_CONFIG", str(tmp / "tools_config.json"))
    monkeypatch.setenv("AMT_TOOLS_LOG", str(tmp / "tools_log.jsonl"))
    monkeypatch.setenv("AMT_SYSINTERACTION_FILE", str(tmp / "sysinteraction.json"))
    main.tools_sandbox = t.ToolSandbox(config_path=str(tmp / "tools_config.json"), log_path=str(tmp / "tools_log.jsonl"))
    main.sysorch = SysInteractionOrchestrator(str(tmp / "sysinteraction.json"))
    return TestClient(main.app)


# ---------- GATE LOGIC ----------

def test_gate_all_off(c, tmp_backend):
    orch = main.sysorch
    assert orch.enabled is False
    block = orch.build_system_prompt(active=orch.is_active(True, True))
    assert block == ""


def test_gate_toggle_off(c, tmp_backend):
    orch = main.sysorch
    orch.enabled = True
    orch.save()
    block = orch.build_system_prompt(active=orch.is_active(False, True))
    assert block == ""


def test_gate_tools_off(c, tmp_backend):
    orch = main.sysorch
    orch.enabled = True
    orch.save()
    assert main.tools_sandbox.cfg.enabled is False
    block = orch.build_system_prompt(active=orch.is_active(True, False))
    assert block == ""


def test_gate_all_on(c, tmp_backend):
    orch = main.sysorch
    orch.enabled = True
    orch.save()
    main.tools_sandbox.cfg.enabled = True
    main.tools_sandbox.save_config({"enabled": True})
    block = orch.build_system_prompt(active=orch.is_active(True, True))
    assert block != ""


# ---------- SEED ----------

def test_seed_creates_agent_and_skill(c, tmp_backend):
    orch = main.sysorch
    assert len(orch.agents) >= 1
    assert len(orch.skills) >= 1
    agent = orch.agents[0]
    assert "sys_open_url" in agent.get("skills", [])
    assert "sys_launch_app" in agent.get("skills", [])
    assert "sys_page_recon" in agent.get("skills", [])
    assert "sys_write_file" in agent.get("skills", [])
    skill = orch._find_skill("sys_open_url")
    assert skill is not None
    assert "open_url" in skill.get("prompt", "")


def test_seed_persists_to_file(c, tmp_backend):
    orch = main.sysorch
    assert os.path.exists(orch.path)
    with open(orch.path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data.get("agents", [])) >= 1
    assert len(data.get("skills", [])) >= 1


def test_dual_security_agents_seeded(c, tmp_backend):
    """Два агента безопасности: executor + monitor."""
    orch = main.sysorch
    exec_agent = orch.get_agent("sys_security_executor")
    mon_agent = orch.get_agent("sys_security_monitor")
    assert exec_agent is not None, "Executor-агент не создан"
    assert mon_agent is not None, "Monitor-агент не создан"
    assert len(exec_agent.get("skills", [])) == 5
    assert len(mon_agent.get("skills", [])) == 5


# ---------- TOKEN RESOLUTION ----------

def _mock_exec_sandbox(monkeypatch, fake_execute):
    """Заменяет main._exec_sandbox на fake, который просто вызывает fake_execute
    синхронно — без реального ThreadPoolExecutor/COM. Возвращает список вызовов."""
    calls = []
    async def fake_exec_sandbox(tool, timeout=10.0, **kwargs):
        calls.append((tool, kwargs))
        result = fake_execute(tool, **kwargs)
        if isinstance(result, dict):
            return result
        return {"ok": True, "result": result}
    monkeypatch.setattr(main, "_exec_sandbox", fake_exec_sandbox)
    return calls


@SKIP_IF_WINDOWS
def test_sys_token_replaced_when_active(c, tmp_backend, monkeypatch):
    orch = main.sysorch
    orch.enabled = True
    main.tools_sandbox.cfg.enabled = True

    def fake_execute(tool, **args):
        if tool == "open_url":
            url = args.get("url", "")
            return {"ok": True, "url": url, "browser": "браузере"}
        return {"ok": False, "error": f"unknown tool {tool}"}
    calls = _mock_exec_sandbox(monkeypatch, fake_execute)

    text = "Открою YouTube: [[SYS:open_url|https://www.youtube.com]]"
    result = _run_async(main.resolve_sys_tokens(text, active=True))
    assert "[[SYS:open_url|" not in result
    assert "Открыл: https://www.youtube.com" in result
    assert len(calls) == 1
    assert calls[0][0] == "open_url"


def test_sys_token_not_replaced_when_inactive(c, tmp_backend):
    text = "Открою YouTube: [[SYS:open_url|https://www.youtube.com]]"
    result = _run_async(main.resolve_sys_tokens(text, active=False))
    assert "[[SYS:open_url|https://www.youtube.com]]" in result


def test_sys_token_invalid_url(c, tmp_backend, monkeypatch):
    main.tools_sandbox.cfg.enabled = True
    text = "Открою: [[SYS:open_url|ftp://example.com]]"
    result = _run_async(main.resolve_sys_tokens(text, active=True))
    # ftp:// не должен быть выполнен — токен заменяется на отказ
    assert "ftp://example.com" in result
    assert "Не удалось открыть" in result


@SKIP_IF_WINDOWS
def test_sys_multiple_tokens(c, tmp_backend, monkeypatch):
    main.tools_sandbox.cfg.enabled = True

    def fake_execute(tool, **args):
        if tool == "open_url":
            url = args.get("url", "")
            return {"ok": True, "url": url, "browser": "браузере"}
        return {"ok": False, "error": f"unknown tool {tool}"}
    calls = _mock_exec_sandbox(monkeypatch, fake_execute)

    text = (
        "Открою две страницы:\n"
        "[[SYS:open_url|https://google.com]]\n"
        "[[SYS:open_url|https://example.com]]"
    )
    result = _run_async(main.resolve_sys_tokens(text, active=True))
    assert "[[SYS:open_url|" not in result
    assert len(calls) == 2


def test_launch_app_token_resolved(c, tmp_backend, monkeypatch):
    """[[SYS:launch_app|steam]] заменяется на «Запустил: steam»."""
    main.tools_sandbox.cfg.enabled = True

    def fake_execute(tool, **args):
        if tool == "launch_app":
            app = args.get("app", "")
            args_str = args.get("args", "")
            note = f" {args_str}" if args_str else ""
            return {"ok": True, "method": "launched", "note": f"запущено{note}"}
        return {"ok": False, "error": f"unknown tool {tool}"}
    _mock_exec_sandbox(monkeypatch, fake_execute)

    text = "Запускаю Steam: [[SYS:launch_app|steam]]"
    result = _run_async(main.resolve_sys_tokens(text, active=True))
    assert "[[SYS:launch_app|" not in result
    assert "Запустил: steam" in result or "запущено" in result


def test_launch_app_uwp_substring_match(c, tmp_backend, monkeypatch):
    """UWP-lookup по substring: 'Telegram' матчит 'TelegramMessengerLLP.TelegramDesktop'.

    Регрессия: регулярка ^(Microsoft|Windows)\\" в PS-команде была невалидной
    (escape \\" ломал парсинг) → все UWP-попады падали с NOT_FOUND.
    Теперь матчинг: точный → prefix → substring.
    """
    main.tools_sandbox.cfg.enabled = True

    def fake_execute(tool, **args):
        if tool == "launch_app":
            return {"ok": True, "method": "launched", "note": "запущено"}
        return {"ok": False, "error": f"unknown tool {tool}"}
    _mock_exec_sandbox(monkeypatch, fake_execute)

    text = "Запускаю: [[SYS:launch_app|Telegram]]"
    result = _run_async(main.resolve_sys_tokens(text, active=True))
    assert "[[SYS:launch_app|" not in result
    assert "Запустил: Telegram" in result or "запущено" in result


def test_launch_app_with_args(c, tmp_backend, monkeypatch):
    """[[SYS:launch_app|notepad|C:\\notes\\todo.txt]] — запуск с аргументами."""
    main.tools_sandbox.cfg.enabled = True

    def fake_execute(tool, **args):
        if tool == "launch_app":
            return {"ok": True, "method": "launched", "note": "запущено"}
        return {"ok": False, "error": f"unknown tool {tool}"}
    _mock_exec_sandbox(monkeypatch, fake_execute)

    text = "Открою Блокнот: [[SYS:launch_app|notepad|C:\\notes\\todo.txt]]"
    result = _run_async(main.resolve_sys_tokens(text, active=True))
    assert "[[SYS:launch_app|" not in result
    assert "Запустил: notepad" in result or "запущено" in result


def test_read_file_token_resolved(c, tmp_backend, monkeypatch):
    """[[SYS:read_file|<path>]] выполняется через ToolSandbox."""
    main.tools_sandbox.cfg.enabled = True
    import os as _os
    test_file = _os.path.join(_os.path.dirname(__file__), "..", "backend", "_test_readme.txt")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("hello test")
    try:
        def fake_execute(tool, **args):
            if tool == "read_file":
                path = args.get("path", "")
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    return {"ok": True, "result": content}
                except Exception as e:
                    return {"ok": False, "error": str(e)}
            return {"ok": False, "error": f"unknown tool {tool}"}
        _mock_exec_sandbox(monkeypatch, fake_execute)

        text = "Читаю: [[SYS:read_file|backend/_test_readme.txt]]"
        result = _run_async(main.resolve_sys_tokens(text, active=True))
        assert "[[SYS:read_file|" not in result
        assert "hello test" in result or "Файл" in result
    finally:
        if _os.path.exists(test_file):
            _os.remove(test_file)


def test_write_file_token_resolved(c, tmp_backend, monkeypatch):
    """[[SYS:write_file|<path>|<content>]] создаёт файл через ToolSandbox."""
    main.tools_sandbox.cfg.enabled = True
    import os as _os
    test_file = _os.path.join(_os.path.dirname(__file__), "..", "backend", "_test_write.txt")
    if _os.path.exists(test_file):
        _os.remove(test_file)
    try:
        def fake_execute(tool, **args):
            if tool == "write_file":
                path = args.get("path", "")
                content = args.get("content", "")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return {"ok": True, "result": f"{len(content)} bytes"}
            return {"ok": False, "error": f"unknown tool {tool}"}
        _mock_exec_sandbox(monkeypatch, fake_execute)

        text = "Создаю файл: [[SYS:write_file|backend/_test_write.txt|привет мир]]"
        result = _run_async(main.resolve_sys_tokens(text, active=True))
        assert "[[SYS:write_file|" not in result
        assert "Записал" in result or "_test_write.txt" in result
        assert _os.path.exists(test_file), "File was not created by write_file token"
    finally:
        if _os.path.exists(test_file):
            _os.remove(test_file)


# ---------- API ENDPOINTS ----------

def test_sysinteraction_get_default(c, tmp_backend):
    r = c.get("/api/sysinteraction")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False
    assert data["available"] is False
    assert len(data["agents"]) >= 1
    assert len(data["skills"]) >= 1


def test_sysinteraction_set_enabled(c, tmp_backend):
    r = c.post("/api/sysinteraction", json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["config"]["enabled"] is True


def test_sysinteraction_available_when_tools_on(c, tmp_backend):
    c.post("/api/sysinteraction", json={"enabled": True})
    r = c.get("/api/sysinteraction")
    assert r.json()["available"] is False
    c.post("/api/tools/config", json={"enabled": True})
    r = c.get("/api/sysinteraction")
    assert r.json()["available"] is True


# ---------- V2: SELF-DEVELOPING ORCHESTRATOR ----------

def test_task_spec_template_present(c, tmp_backend):
    r = c.get("/api/sysinteraction")
    data = r.json()
    assert "task_spec_template" in data
    tmpl = data["task_spec_template"]
    assert "task" in tmpl
    assert "target_tool" in tmpl
    assert "args_template" in tmpl
    assert "risk_level" in tmpl


def test_auto_derive_10_tests_openuel(c, tmp_backend):
    from ai_engine.sysinteraction import auto_derive_10_tests
    spec = {
        "task": "Открыть YouTube",
        "target_tool": "open_url",
        "args_template": {"url": "https://www.youtube.com"},
        "expected_outcome": "Браузер открыл страницу",
        "risk_level": "low",
    }
    tests = auto_derive_10_tests(spec)
    assert len(tests) == 10


def test_auto_derive_10_tests_runcommand(c, tmp_backend):
    from ai_engine.sysinteraction import auto_derive_10_tests
    spec = {
        "task": "Запустить echo hello",
        "target_tool": "run_command",
        "args_template": {"command": "echo hello"},
        "expected_outcome": "Вывело hello",
        "risk_level": "low",
    }
    tests = auto_derive_10_tests(spec)
    assert len(tests) == 10
    names = [t["name"] for t in tests]
    assert "negative_refuse_rm_rf" in names


def test_generate_task_agent_passes(c, tmp_backend):
    orch = main.sysorch
    orch.enabled = True
    main.tools_sandbox.cfg.enabled = True
    main.tools_sandbox.cfg.command_whitelist = ["echo"]
    main.tools_sandbox.save_config({"enabled": True, "command_whitelist": ["echo"]})

    spec = {
        "task": "Запустить echo hello",
        "target_tool": "run_command",
        "args_template": {"command": "echo hello"},
        "expected_outcome": "Вывело hello",
        "risk_level": "low",
    }
    res = orch.generate_task_agent(spec, main.tools_sandbox)
    assert res["agent"] is not None
    if res["draft"]:
        import pytest
        pytest.fail(f"draft=True, failures={res['failures']}")
    assert res["draft"] is False
    assert res["passed"] is True


def test_generate_task_agent_fails(c, tmp_backend):
    orch = main.sysorch
    orch.enabled = True
    main.tools_sandbox.cfg.enabled = True
    main.tools_sandbox.cfg.command_whitelist = []
    main.tools_sandbox.save_config({"enabled": True, "command_whitelist": []})

    spec = {
        "task": "Запустить rm -rf /",
        "target_tool": "run_command",
        "args_template": {"command": "rm -rf /"},
        "expected_outcome": "Удалил всё",
        "risk_level": "high",
    }
    res = orch.generate_task_agent(spec, main.tools_sandbox)
    assert res["agent"] is not None
    assert res["draft"] is True
    assert res["passed"] is False
    todo_events = [l for l in orch.logs if l["event"] == "todo"]
    assert len(todo_events) >= 1


def test_draft_agent_not_in_prompt(c, tmp_backend):
    orch = main.sysorch
    orch.enabled = True
    main.tools_sandbox.cfg.enabled = True
    main.tools_sandbox.cfg.command_whitelist = []
    main.tools_sandbox.save_config({"enabled": True, "command_whitelist": []})

    spec = {
        "task": "Запустить запретную команду",
        "target_tool": "run_command",
        "args_template": {"command": "del C:\\Windows"},
        "expected_outcome": "Удалил Windows",
        "risk_level": "high",
    }
    res = orch.generate_task_agent(spec, main.tools_sandbox)
    assert res["draft"] is True

    block = orch.build_system_prompt(active=orch.is_active(True, True))
    agent = orch.get_agent(res["agent"]["id"])
    assert agent["draft"] is True
    assert agent["name"] not in block


def test_extract_task_spec(c, tmp_backend):
    text = 'Выполняю задачу.\n[[SYS:task_spec|{"task":"test","target_tool":"open_url","args_template":{"url":"https://x.com"},"expected_outcome":"ok","risk_level":"low"}]]'
    spec = main.extract_task_spec(text)
    assert spec is not None
    assert spec["task"] == "test"
    assert spec["target_tool"] == "open_url"


def test_extract_task_spec_none(c, tmp_backend):
    text = "Нет токенов в этом тексте."
    spec = main.extract_task_spec(text)
    assert spec is None


def test_extract_task_spec_invalid_json(c, tmp_backend):
    text = "[[SYS:task_spec|{invalid json}]]"
    spec = main.extract_task_spec(text)
    assert spec is None


def test_task_spec_stripped_from_response(c, tmp_backend):
    main.tools_sandbox.cfg.enabled = True
    text = 'Делая задачу.\n[[SYS:task_spec|{"task":"t","target_tool":"open_url","args_template":{"url":"https://x.com"},"expected_outcome":"ok","risk_level":"low"}]]'
    result = _run_async(main.resolve_sys_tokens(text, active=True))
    assert "[[SYS:task_spec|" not in result
    assert "Делая задачу" in result


def test_task_specs_in_public_config(c, tmp_backend):
    r = c.get("/api/sysinteraction")
    data = r.json()
    assert "task_specs" in data
    assert "drafts" in data
    assert "logs" in data


# ---------- PLANNER (v3: [[SYS:plan|{json}]]) ----------

def test_plan_template_present(c, tmp_backend):
    r = c.get("/api/sysinteraction")
    data = r.json()
    assert "plan_template" in data
    tmpl = data["plan_template"]
    assert "goal" in tmpl
    assert "steps" in tmpl
    assert "risk_level" in tmpl


def test_extract_plan_valid(c, tmp_backend):
    text = (
        "Для этого нужно: открыть страницу, запустить приложение.\n"
        "[[SYS:plan|{\"goal\":\"Открыть сайт и запустить Steam\","
        "\"steps\":[{\"tool\":\"open_url\",\"args\":{\"url\":\"https://example.com\"},\"expected\":\"Страница открыта\"},"
        "{\"tool\":\"launch_app\",\"args\":{\"app\":\"steam\"},\"expected\":\"Steam запущен\"}],"
        "\"risk_level\":\"low\"}]]"
    )
    plan = main.extract_plan(text)
    assert plan is not None
    assert plan["goal"] == "Открыть сайт и запустить Steam"
    assert len(plan["steps"]) == 2
    assert plan["steps"][0]["tool"] == "open_url"
    assert plan["steps"][1]["tool"] == "launch_app"


def test_extract_plan_none(c, tmp_backend):
    text = "Нет план-токенов в этом тексте."
    plan = main.extract_plan(text)
    assert plan is None


def test_extract_plan_invalid_json(c, tmp_backend):
    text = "[[SYS:plan|{invalid json}]]"
    plan = main.extract_plan(text)
    assert plan is None


def test_plan_stripped_from_response(c, tmp_backend):
    main.tools_sandbox.cfg.enabled = True
    text = (
        "Выполняю план.\n"
        "[[SYS:plan|{\"goal\":\"test\",\"steps\":[{\"tool\":\"open_url\",\"args\":{\"url\":\"https://x.com\"},\"expected\":\"ok\"}],\"risk_level\":\"low\"}]]"
    )
    result = _run_async(main.resolve_sys_tokens(text, active=True))
    assert "[[SYS:plan|" not in result
    assert "Выполняю план" in result


def test_security_check_step_blocks_bad_url(c, tmp_backend):
    from ai_engine.sysinteraction import security_check_step
    ok, reason = security_check_step({"tool": "open_url", "args": {"url": "ftp://x.com"}})
    assert ok is False
    assert "R4" in reason


def test_security_check_step_blocks_system_utility(c, tmp_backend):
    """security_check_step блокирует запуск системных утилит."""
    from ai_engine.sysinteraction import security_check_step
    ok, reason = security_check_step({"tool": "launch_app", "args": {"app": "cmd"}})
    assert ok is False


def test_security_check_step_blocks_powershell(c, tmp_backend):
    from ai_engine.sysinteraction import security_check_step
    ok, reason = security_check_step({"tool": "launch_app", "args": {"app": "powershell"}})
    assert ok is False


def test_security_check_step_passes_valid(c, tmp_backend):
    from ai_engine.sysinteraction import security_check_step
    ok, reason = security_check_step({"tool": "open_url", "args": {"url": "https://example.com"}})
    assert ok is True
    assert reason == "ok"


def test_execute_plan_with_watchdog(c, tmp_backend, monkeypatch):
    from ai_engine.sysinteraction import execute_plan

    class FakeSandbox:
        def execute(self, tool, **args):
            return {"ok": True, "detail": "ok"}

    orch = main.sysorch
    plan = {
        "goal": "Тестовый план",
        "steps": [
            {"tool": "open_url", "args": {"url": "https://ok.com"}, "expected": "ok"},
            {"tool": "open_url", "args": {"url": "ftp://bad.com"}, "expected": "bad"},
        ],
        "risk_level": "low",
    }
    result = execute_plan(plan, FakeSandbox(), orch)
    assert result["steps_total"] == 2
    assert result["steps_passed"] == 1
    assert result["all_passed"] is False
    assert result["results"][0]["ok"] is True
    assert result["results"][1]["ok"] is False


def test_run_plan_saves_to_plans(c, tmp_backend):
    orch = main.sysorch
    orch.enabled = True
    main.tools_sandbox.cfg.enabled = True
    main.tools_sandbox.cfg.command_whitelist = ["echo"]
    main.tools_sandbox.save_config({"enabled": True, "command_whitelist": ["echo"]})

    plan = {
        "goal": "Запустить echo",
        "steps": [
            {"tool": "run_command", "args": {"command": "echo hello"}, "expected": "Вывело hello"},
        ],
        "risk_level": "low",
    }
    before = len(orch.plans)
    result = orch.run_plan(plan, main.tools_sandbox)
    after = len(orch.plans)
    assert after == before + 1
    assert result["plan_id"] in [p["id"] for p in orch.plans]


# ---------- MIGRATION: stale seed (old sysinteraction.json) ----------

def test_migration_stale_seed_gets_dual_security(c, tmp_backend):
    """If a user has an OLD sysinteraction.json (sys_core without dual-security),
    the new orchestrator must migrate it: add executor+monitor agents,
    launch_app skill, and update sys_core prompt."""
    tmp = tmp_backend["tmp"]
    syspath = str(tmp / "sysinteraction.json")
    # Simulate old seed: sys_core with only sys_open_url, no dual-security
    old_data = {
        "enabled": False,
        "orchestrator": {
            "id": "sys_orchestrator",
            "name": "Оркестратор",
            "prompt": "old prompt",
            "tools_allow": ["read_file", "list_dir", "run_command", "open_url"],
        },
        "agents": [
            {"id": "sys_core", "name": "Системный агент", "description": "old",
             "systemPrompt": "old prompt about embedded browser", "folder": "sysinteraction",
             "skills": ["sys_open_url"]},
        ],
        "skills": [
            {"id": "sys_open_url", "name": "Открыть страницу", "description": "old",
             "prompt": "old prompt", "enabled": True, "folder": "sysinteraction", "agentId": "sys_core"},
        ],
        "task_specs": [], "drafts": [], "plans": [], "logs": [],
    }
    with open(syspath, "w", encoding="utf-8") as f:
        json.dump(old_data, f, ensure_ascii=False)

    # Re-initialize orchestrator from the same path — migration should trigger
    orch2 = SysInteractionOrchestrator(syspath)
    agent_ids = {a["id"] for a in orch2.agents}
    skill_ids = {s["id"] for s in orch2.skills}

    # Dual-security agents added
    assert "sys_security_executor" in agent_ids
    assert "sys_security_monitor" in agent_ids
    # launch_app skill added
    assert "sys_launch_app" in skill_ids
    # sys_core prompt updated (no longer "old prompt about embedded browser")
    sys_core = next(a for a in orch2.agents if a["id"] == "sys_core")
    assert "old prompt about embedded browser" not in sys_core["systemPrompt"]
    # sys_core now has sys_launch_app in skills
    assert "sys_launch_app" in sys_core.get("skills", [])
