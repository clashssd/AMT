import asyncio
import json
import os
import sys

sys.path.insert(0, "backend")


async def _fake_llm(prompt: str, context: dict):
    role = context.get("role", "")
    if role == "planner":
        return json.dumps({"tasks": [{"id": "t1", "title": "add file", "files": ["a.txt"], "steps": ["write"], "acceptance": "a.txt exists"}]})
    if role == "coder":
        return json.dumps({"summary": "wrote file", "files": [{"path": "a.txt", "action": "write", "content": "hello"}], "commands": []})
    if role == "reviewer":
        return json.dumps({"approved": True, "issues": []})
    return "{}"


def test_coding_orchestrator_runs_planner_coder_reviewer(tmp_path):
    from ai_engine.coding_orchestrator import CodingOrchestrator
    from ai_engine.permissions import ApprovalGate

    root = tmp_path / "repo"
    root.mkdir()
    orch = CodingOrchestrator(str(root), storage_path=str(tmp_path / "sessions.json"), default_policy=[{"action": "*", "resource": "*", "effect": "allow"}])
    result = orch.run_goal("add file", _fake_llm)
    import asyncio
    outcome = asyncio.run(result)

    assert outcome["status"] == "completed"
    assert (root / "a.txt").read_text(encoding="utf-8") == "hello"
    assert [child["role"] for child in outcome["children"]] == ["planner", "coder", "reviewer"]
    assert outcome["reviewer_approved"] is True


def test_coding_orchestrator_reviewer_rejects_second_round(tmp_path):
    from ai_engine.coding_orchestrator import CodingOrchestrator

    root = tmp_path / "repo"
    root.mkdir()

    calls = {"reviewer": 0}

    async def llm(prompt, context):
        role = context.get("role", "")
        if role == "planner":
            return json.dumps({"tasks": [{"id": "t1", "title": "task", "files": ["b.txt"], "steps": ["write"], "acceptance": "b.txt exists"}]})
        if role == "coder":
            calls["coder"] = calls.get("coder", 0) + 1
            content = "hello" if calls["coder"] == 1 else "hello world"
            return json.dumps({"summary": "ok", "files": [{"path": "b.txt", "action": "write", "content": content}], "commands": []})
        if role == "reviewer":
            calls["reviewer"] = calls.get("reviewer", 0) + 1
            if calls["reviewer"] == 1:
                return json.dumps({"approved": False, "issues": ["add more content"]})
            return json.dumps({"approved": True, "issues": []})
        return "{}"

    orch = CodingOrchestrator(str(root), storage_path=str(tmp_path / "sessions.json"), default_policy=[{"action": "*", "resource": "*", "effect": "allow"}])
    outcome = asyncio.run(orch.run_goal("task", llm))

    assert outcome["status"] == "completed"
    assert calls["reviewer"] == 2
    assert (root / "b.txt").read_text(encoding="utf-8") == "hello world"
    assert [child["role"] for child in outcome["children"]] == ["planner", "coder", "reviewer", "coder", "reviewer"]


def test_coding_orchestrator_endpoint_rejects_missing_root(tmp_backend, monkeypatch):
    import main
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    res = client.post("/api/coding/orchestrator", json={"root": "", "goal": "do it"})
    assert res.status_code == 400
    assert "root" in res.json()["detail"]


def test_coding_orchestrator_endpoint_uses_llm_call(tmp_backend, monkeypatch, tmp_path):
    import main
    from fastapi.testclient import TestClient

    calls = []

    async def fake_call_ai_api(prompt, history, settings=None, **kwargs):
        calls.append(prompt)
        if prompt.startswith("[ROLE: planner]"):
            return {"text": '{"tasks":[{"id":"1","title":"t","files":["a.txt"],"steps":["s"],"acceptance":"done"}]}'}
        if prompt.startswith("[ROLE: coder]"):
            return {"text": '{"summary":"wrote","files":[{"path":"a.txt","action":"write","content":"ok"}],"commands":[]}'}
        return {"text": '{"approved":true,"issues":[]}'}

    monkeypatch.setattr(main, "call_ai_api", fake_call_ai_api)
    client = TestClient(main.app)
    res = client.post("/api/coding/orchestrator", json={"root": str(tmp_path), "goal": "do it"})
    assert res.status_code == 200
    assert res.json()["run"]["status"] == "completed"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "ok"