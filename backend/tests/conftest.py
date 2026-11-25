"""Shared pytest fixtures for AMT backend tests.

Importing `backend.main` has module-level side effects (log dir, data files,
orchestrator instances). To keep tests isolated and not pollute the real
project directory, we point the AMT_* data-path env vars at a temporary
directory BEFORE importing main.
"""
import os
import sys
import tempfile

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture(autouse=True)
def _isolate_main(tmp_path, monkeypatch):
    """Route every AMT_* data path into a fresh temp dir.

    Must run before any test imports backend.main. Since `import main`
    happens inside the test function (after this fixture), the env vars
    are already set at import time.
    """
    base = tmp_path / "amt"
    for name in (
        "AMT_LOG_DIR", "AMT_SETTINGS_FILE", "AMT_AGENTS_FILE",
        "AMT_KEYS_FILE", "AMT_SYSINTERACTION_FILE", "AMT_FILES_DIR",
        "AMT_CHATS_DIR", "AMT_SESSIONS_FILE", "AMT_BG_DIR",
        "AMT_CONFIGS_DIR", "AMT_MEMORY_FILE", "AMT_EXTENSIONS_DIR",
        "AMT_PROJECTS_CURRENT", "AMT_CHANGELOG_FILE",
    ):
        monkeypatch.setenv(name, str(base / name.lower()))
    yield base


@pytest.fixture
def _make_sandbox_stub():
    return make_sandbox_stub


def make_sandbox_stub(mapping=None):
    """A ToolSandbox stand-in with `execute` returning canned results.

    `execute` is what `run_com_sync` actually calls; it must be a plain
    callable (it is) and may be sync. The fake records the calls so
    assertions can inspect them.
    """
    from ai_engine.tools import ToolSandbox  # noqa: F401  (type hint only)

    calls: list[tuple] = []

    class _Sandbox:
        def execute(self, tool, **kwargs):
            calls.append((tool, kwargs))
            # default: ok=True with an echo
            if mapping and tool in mapping:
                return mapping[tool](**kwargs) if callable(mapping[tool]) else mapping[tool]
            return {"ok": True, "echo": {tool: kwargs}}

    _Sandbox.calls = calls
    return _Sandbox()


@pytest.fixture
def _make_orchestrator_stub():
    return make_orchestrator_stub


def make_orchestrator_stub():
    """A minimal SysInteractionOrchestrator stand-in used by plan-v2 tests.

    Provides just the surface that resolve_plan_v2 / monitor / agent spawn
    touch: _log_event, save, agents/skills lists, add_skill, _find_skill,
    match_agents_for_step, generate_task_agent_async.
    """

    class _Orch:
        def __init__(self):
            self.agents = []
            self.skills = []
            self.task_specs = []
            self.drafts = []
            self.plans = []
            self.logs = []

        def _log_event(self, event, detail):
            self.logs.append((event, detail))

        def save(self):
            pass

        def _find_skill(self, skill_id):
            for s in self.skills:
                if s.get("id") == skill_id:
                    return s
            return None

        def add_skill(self, skill, agent_id):
            self.skills.append(skill)
            return skill

        async def generate_task_agent_async(self, spec, sandbox, skip_tests=False, timeout=30.0):
            agent = {
                "id": "sys_test_agent",
                "skills": [],
            }
            self.agents.append(agent)
            return {"agent": agent, "passed": True, "tries": 1,
                    "draft": False, "failures": [], "passed_count": 10}

    return _Orch()
