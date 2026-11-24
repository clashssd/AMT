"""Tests for the Logs Dashboard: AGENT_SKILLS event + /api/logs/dashboard aggregation.

Task 1: log_agent_skills() writes an [AGENT_SKILLS] line to today's chat log.
Task 2: build_dashboard() groups log lines into tasks + stats; /api/logs/dashboard exposes it.
"""
import os
import datetime
import pytest


@pytest.fixture
def api_c(tmp_backend):
    """Fresh main import with isolated data dirs."""
    import importlib
    import main as m
    importlib.reload(m)
    from fastapi.testclient import TestClient
    client = TestClient(m.app)
    yield {"main": m, "client": client, "tmp": tmp_backend}


def _today_log_path(tmp_path):
    d = datetime.date.today().isoformat()
    return tmp_path / "logs" / f"chat_{d}.log"


# ---------------------------------------------------------------------------
# Task 1: log_agent_skills
# ---------------------------------------------------------------------------

def test_log_agent_skills_writes_line(api_c):
    """log_agent_skills(agent_id, extra_skills) writes an [AGENT_SKILLS] line
    with agent, agent_name and skills csv into today's chat log."""
    m = api_c["main"]
    tmp = api_c["tmp"]
    m.agents_mgr.agents.append({
        "id": "dev", "name": "Dev Agent", "systemPrompt": "sp", "model": "",
        "skills": ["s1", "s2"],
    })
    m.agents_mgr.skills.append({"id": "s1", "name": "Review", "prompt": "p", "enabled": True})
    m.agents_mgr.skills.append({"id": "s2", "name": "Explain", "prompt": "p", "enabled": True})
    log_path = _today_log_path(tmp["tmp"])
    if log_path.exists():
        log_path.write_text("", encoding="utf-8")

    m.log_agent_skills("dev", ["s3"])

    text = log_path.read_text(encoding="utf-8")
    assert "[AGENT_SKILLS]" in text
    assert "agent=dev" in text
    assert "agent_name=Dev Agent" in text
    assert "Review" in text
    assert "Explain" in text
    assert "s3" in text


def test_log_agent_skills_none_when_no_agent(api_c):
    """With agent_id None -> agent=none, agent_name=none, skills=none."""
    m = api_c["main"]
    tmp = api_c["tmp"]
    log_path = _today_log_path(tmp["tmp"])
    if log_path.exists():
        log_path.write_text("", encoding="utf-8")

    m.log_agent_skills(None, None)

    text = log_path.read_text(encoding="utf-8")
    assert "[AGENT_SKILLS]" in text
    assert "agent=none" in text
    assert "agent_name=none" in text
    assert "skills=none" in text


def test_call_ai_api_logs_agent_skills(api_c, monkeypatch):
    """Integration: call_ai_api with an agent logs AGENT_SKILLS."""
    import asyncio
    m = api_c["main"]
    tmp = api_c["tmp"]
    m.agents_mgr.agents.append({
        "id": "a1", "name": "Helper", "systemPrompt": "sp", "model": "",
        "skills": ["sk1"],
    })
    m.agents_mgr.skills.append({"id": "sk1", "name": "Skill X", "prompt": "p", "enabled": True})

    m.server_settings.apiKey = "sk-test"
    from tests.test_keys import _fake_httpx
    _fake_httpx(monkeypatch)

    log_path = _today_log_path(tmp["tmp"])
    if log_path.exists():
        log_path.write_text("", encoding="utf-8")

    asyncio.run(m.call_ai_api(
        "Привет", [], m.server_settings, agent_id="a1", extra_skills=["sk2"],
    ))

    text = log_path.read_text(encoding="utf-8")
    assert "[AGENT_SKILLS]" in text
    assert "agent=a1" in text
    assert "Skill X" in text


# ---------------------------------------------------------------------------
# Task 2: build_dashboard
# ---------------------------------------------------------------------------

def _write_log(tmp_path, lines):
    p = _today_log_path(tmp_path)
    p.parent.mkdir(exist_ok=True)
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_build_dashboard_groups_tasks(api_c):
    """Two tasks: first completed (RESPONSE), second failed (ERROR)."""
    m = api_c["main"]
    tmp = api_c["tmp"]
    lines = [
        "2026-11-22 10:00:00  [SESSION_CREATED] session=s1",
        "2026-11-22 10:00:00  [AGENT_SKILLS]  agent=dev  agent_name=Dev  skills=Review,Explain",
        "2026-11-22 10:00:01  [Orchestrator]  [EVENT] MONITOR  latency_s=1.2  success=True",
        "2026-11-22 10:00:02  [REQUEST]  model=gpt-4o-mini  history_len=3  msg_preview=Привет  key_id=k1",
        "2026-11-22 10:00:05  [RESPONSE]  model=gpt-4o-mini  latency_s=4.0  prompt_tokens=10  completion_tokens=20  total_tokens=30",
        "2026-11-22 10:05:00  [SESSION_CREATED] session=s2",
        "2026-11-22 10:05:01  [REQUEST]  model=gpt-4o-mini  history_len=1  msg_preview=Привет 2  key_id=k1",
        "2026-11-22 10:05:02  [ERROR]  detail=DNS fail",
    ]
    _write_log(tmp["tmp"], lines)

    dash = m.build_dashboard(m._read_log_lines(400))
    tasks = dash["tasks"]
    assert len(tasks) == 2
    t1, t2 = tasks[0], tasks[1]
    assert t1["status"] == "completed"
    assert t2["status"] == "failed"
    assert t1["prompt"] == "Привет"
    assert t2["prompt"] == "Привет 2"
    assert t1["agent"] == "dev"
    assert t1["agent_name"] == "Dev"
    assert "Review" in t1["skills"]
    assert "Explain" in t1["skills"]
    assert t1["duration_s"] == 4.0
    assert any(e["tag"] == "AGENT_SKILLS" for e in t1["events"])
    assert any(e["tag"] == "RESPONSE" for e in t1["events"])
    st = dash["stats"]
    assert st["total"] == 2
    assert st["errors"] == 1
    assert st["agent_runs"] == 1
    assert st["skill_counts"].get("Review") == 1
    assert st["skill_counts"].get("Explain") == 1


def test_build_dashboard_running_when_no_response(api_c):
    m = api_c["main"]
    tmp = api_c["tmp"]
    lines = [
        "2026-11-22 11:00:00  [SESSION_CREATED] session=s3",
        "2026-11-22 11:00:01  [REQUEST]  model=m  history_len=0  msg_preview=hi  key_id=k",
    ]
    _write_log(tmp["tmp"], lines)
    dash = m.build_dashboard(m._read_log_lines(400))
    assert len(dash["tasks"]) == 1
    assert dash["tasks"][0]["status"] == "running"


def test_build_dashboard_empty_log(api_c):
    m = api_c["main"]
    dash = m.build_dashboard([])
    assert dash["tasks"] == []
    assert dash["stats"]["total"] == 0
    assert dash["stats"]["errors"] == 0
    assert dash["stats"]["skill_counts"] == {}


def test_build_dashboard_skills_none_no_junk(api_c):
    m = api_c["main"]
    tmp = api_c["tmp"]
    lines = [
        "2026-11-22 12:00:00  [SESSION_CREATED] session=s4",
        "2026-11-22 12:00:00  [AGENT_SKILLS]  agent=none  agent_name=none  skills=none",
        "2026-11-22 12:00:01  [REQUEST]  model=m  history_len=0  msg_preview=hi  key_id=k",
        "2026-11-22 12:00:02  [RESPONSE]  model=m  latency_s=0.5",
    ]
    _write_log(tmp["tmp"], lines)
    dash = m.build_dashboard(m._read_log_lines(400))
    t = dash["tasks"][0]
    assert t["skills"] == []
    assert "none" not in t["skills"]


def test_dashboard_endpoint_returns_200(api_c):
    client = api_c["client"]
    tmp = api_c["tmp"]
    lines = [
        "2026-11-22 13:00:00  [SESSION_CREATED] session=s5",
        "2026-11-22 13:00:01  [REQUEST]  model=m  history_len=0  msg_preview=hello  key_id=k",
        "2026-11-22 13:00:02  [RESPONSE]  model=m  latency_s=1.0",
    ]
    _write_log(tmp["tmp"], lines)
    r = client.get("/api/logs/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert "tasks" in body and "stats" in body
    assert body["stats"]["total"] == 1
    assert body["tasks"][0]["status"] == "completed"


# ---------------------------------------------------------------------------
# Task 4+5: calls[] (все агенты) + tree (оркестратор → агенты → скиллы)
# ---------------------------------------------------------------------------

def test_build_dashboard_collects_all_agents_in_calls(api_c):
    """Несколько AGENT_SKILLS в одной задаче (primary + core) → все попадают в calls[].
    Скиллы объединяются (дедуп), primary-агент = первый валидный."""
    m = api_c["main"]
    tmp = api_c["tmp"]
    lines = [
        "2026-11-22 14:00:00  [SESSION_CREATED] session=s6",
        "2026-11-22 14:00:00  [AGENT_SKILLS]  agent=dev  agent_name=Dev  skills=Review,Explain",
        "2026-11-22 14:00:00  [AGENT_SKILLS]  agent=core_web  agent_name=Веб  skills=Search",
        "2026-11-22 14:00:00  [AGENT_SKILLS]  agent=core_thinker  agent_name=Аналитик  skills=Explain,Reason",
        "2026-11-22 14:00:01  [REQUEST]  model=m  history_len=0  msg_preview=hi  key_id=k",
        "2026-11-22 14:00:05  [RESPONSE]  model=m  latency_s=4.0",
    ]
    _write_log(tmp["tmp"], lines)
    dash = m.build_dashboard(m._read_log_lines(400))
    t = dash["tasks"][0]
    # 3 вызова агента
    assert len(t["calls"]) == 3
    # primary = первый валидный агент
    assert t["agent"] == "dev"
    assert t["agent_name"] == "Dev"
    # роли: первый primary, остальные core
    assert t["calls"][0]["role"] == "primary"
    assert t["calls"][1]["role"] == "core"
    assert t["calls"][2]["role"] == "core"
    # скиллы объединены (дедуп): Review, Explain, Search, Reason
    assert set(t["skills"]) == {"Review", "Explain", "Search", "Reason"}
    # stats: всего 3 вызова агентов
    assert dash["stats"]["agent_call_count"] == 3
    assert dash["stats"]["agent_id_counts"].get("dev") == 1
    assert dash["stats"]["agent_id_counts"].get("core_web") == 1


def test_build_dashboard_tree_orchestrator_agents_skills(api_c):
    """Дерево: корень-оркестратор (если есть ORCH_ события) → агенты → скиллы."""
    m = api_c["main"]
    tmp = api_c["tmp"]
    lines = [
        "2026-11-22 15:00:00  [SESSION_CREATED] session=s7",
        "2026-11-22 15:00:00  [Orchestrator]  [EVENT] MONITOR  latency_s=1.2  success=True",
        "2026-11-22 15:00:00  [AGENT_SKILLS]  agent=dev  agent_name=Dev  skills=Review,Explain",
        "2026-11-22 15:00:00  [AGENT_SKILLS]  agent=core_web  agent_name=Веб  skills=Search",
        "2026-11-22 15:00:01  [REQUEST]  model=m  history_len=0  msg_preview=hi  key_id=k",
        "2026-11-22 15:00:05  [RESPONSE]  model=m  latency_s=4.0",
    ]
    _write_log(tmp["tmp"], lines)
    dash = m.build_dashboard(m._read_log_lines(400))
    t = dash["tasks"][0]
    tree = t["tree"]
    # корень = оркестратор (есть ORCH_ событие)
    assert tree["label"] == "Оркестратор"
    assert tree["kind"] == "orchestrator"
    # дети = 2 агента
    kids = tree["children"]
    assert len(kids) == 2
    dev, web = kids[0], kids[1]
    assert dev["kind"] == "agent" and dev["label"] == "Dev"
    assert web["kind"] == "agent" and web["label"] == "Веб"
    # скиллы как дети агента
    assert [c["label"] for c in dev["children"]] == ["Review", "Explain"]
    assert [c["label"] for c in web["children"]] == ["Search"]
    assert all(c["kind"] == "skill" for c in dev["children"])


def test_build_dashboard_tree_without_orchestrator(api_c):
    """Без ORCH_ событий корень = «Запрос», а не «Оркестратор»."""
    m = api_c["main"]
    tmp = api_c["tmp"]
    lines = [
        "2026-11-22 16:00:00  [SESSION_CREATED] session=s8",
        "2026-11-22 16:00:00  [AGENT_SKILLS]  agent=dev  agent_name=Dev  skills=Review",
        "2026-11-22 16:00:01  [REQUEST]  model=m  history_len=0  msg_preview=hi  key_id=k",
        "2026-11-22 16:00:05  [RESPONSE]  model=m  latency_s=4.0",
    ]
    _write_log(tmp["tmp"], lines)
    dash = m.build_dashboard(m._read_log_lines(400))
    t = dash["tasks"][0]
    assert t["tree"]["label"] == "Запрос"
    assert t["tree"]["kind"] == "orchestrator"
    assert len(t["tree"]["children"]) == 1


def test_build_dashboard_tree_no_agents_has_chat_events(api_c):
    """Без агентов → дети корня = события чата (видна, «от чего идёт» запрос)."""
    m = api_c["main"]
    tmp = api_c["tmp"]
    lines = [
        "2026-11-22 17:00:00  [SESSION_CREATED] session=s9",
        "2026-11-22 17:00:01  [REQUEST]  model=m  history_len=0  msg_preview=hi  key_id=k",
        "2026-11-22 17:00:05  [RESPONSE]  model=m  latency_s=4.0",
    ]
    _write_log(tmp["tmp"], lines)
    dash = m.build_dashboard(m._read_log_lines(400))
    t = dash["tasks"][0]
    tree = t["tree"]
    # нет calls → дети = события чата
    assert len(tree["children"]) >= 2  # REQUEST + RESPONSE
    kinds = [c["kind"] for c in tree["children"]]
    assert "event" in kinds


def test_dashboard_stats_agent_call_count_in_response(api_c):
    """В /api/logs/dashboard присутствует новое поле agent_call_count."""
    m = api_c["main"]
    tmp = api_c["tmp"]
    lines = [
        "2026-11-22 18:00:00  [SESSION_CREATED] session=s10",
        "2026-11-22 18:00:00  [AGENT_SKILLS]  agent=dev  agent_name=Dev  skills=Review",
        "2026-11-22 18:00:01  [REQUEST]  model=m  history_len=0  msg_preview=hi  key_id=k",
        "2026-11-22 18:00:05  [RESPONSE]  model=m  latency_s=4.0",
    ]
    _write_log(tmp["tmp"], lines)
    r = api_c["client"].get("/api/logs/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert "agent_call_count" in body["stats"]
    assert "agent_id_counts" in body["stats"]
    assert "tree" in body["tasks"][0]
    assert "calls" in body["tasks"][0]
