import main
from ai_engine.tool_registry import ToolRegistry, ToolDef
from ai_engine.coding_profile import ChatProfile


def test_coding_tool_schemas_are_filtered(tmp_path):
    reg = ToolRegistry()
    reg.register(ToolDef(name="generate_image", description="img", parameters={}, handler=None, source="native"))
    reg.register(ToolDef(name="fs_read", description="read file", parameters={}, handler=None, source="native"))

    general = reg.schemas_for_profile(ChatProfile(chat_mode="general", key_id="", api_key="", base_url="", model="", system_prompt_suffix=""))
    coding = reg.schemas_for_profile(ChatProfile(chat_mode="coding", key_id="", api_key="", base_url="", model="", system_prompt_suffix=""))

    import json
    assert any("generate_image" in json.dumps(s) for s in general)
    assert not any("generate_image" in json.dumps(s) for s in coding)
    assert any("fs_read" in json.dumps(s) for s in coding)


def test_coding_command_helpers(tmp_backend, monkeypatch):
    import main

    assert main._coding_command_name("/code_project") == "code_project"
    assert main._coding_command_name("/code_project C:\\Users\\berds\\Desktop") == "code_project"
    assert main._coding_command_name("hello") is None

    result = main._coding_command_result("/code_session list")
    assert result["command"] == "code_session"
    assert result["args"] == ["list"]


def test_coding_session_create_and_list(tmp_backend, tmp_path):
    import main

    main._load_sessions()
    root = str(tmp_path / "repo")
    created = main._coding_session_create(
        {"name": "coding-session", "root": root}
    )
    assert created["id"].startswith("ses_")
    assert created["root"] == root
    assert created["baseChatId"] == ""

    listed = main._coding_session_list()
    assert any(item["id"] == created["id"] for item in listed)


def test_coding_session_continue_updates_base_chat(tmp_backend, monkeypatch):
    import main

    main._load_sessions()
    session_id = main._coding_session_create({"name": "continue", "root": "C:\\tmp"})["id"]
    updated = main._coding_session_continue(session_id, base_chat_id="chat_123")

    assert updated["baseChatId"] == "chat_123"
    listed = {item["id"]: item for item in main._coding_session_list()}
    assert listed[session_id]["baseChatId"] == "chat_123"


def test_coding_session_duplicate_copies_fields_without_base_chat(tmp_backend, monkeypatch):
    import main

    main._load_sessions()
    original = main._coding_session_create(
        {"name": "orig", "root": "C:\\tmp", "keyId": "k2", "agentId": "coder"}
    )
    duplicated = main._coding_session_duplicate(original["id"])

    assert duplicated["id"] != original["id"]
    assert duplicated["name"] == "orig (копия)"
    assert duplicated["root"] == "C:\\tmp"
    assert duplicated["keyId"] == "k2"
    assert duplicated["agentId"] == "coder"
    assert duplicated["baseChatId"] == ""


def test_coding_request_registry_includes_project_scoped_tools(tmp_backend, tmp_path):
    import main

    root = str(tmp_path / "repo")
    (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
    reg = main._build_coding_request_registry(root, [])

    names = {s["function"]["name"] for s in reg.schemas_for_profile(main.ChatProfile(chat_mode="coding", key_id="", api_key="", base_url="", model="", system_prompt_suffix=""))}

    assert "fs_read" in names
    assert "run_command" in names
    assert "generate_image" not in names


def test_coding_session_delete(tmp_backend, monkeypatch):
    import main

    main._load_sessions()
    original = main._coding_session_create({"name": "del", "root": "C:\\tmp"})
    assert main._coding_session_delete(original["id"]) is True
    assert all(item["id"] != original["id"] for item in main._coding_session_list())


def test_amt_coding_mcp_preset_endpoints(tmp_backend, monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from ai_engine.mcp_manager import MCPManager

    if main.mcp_manager is None:
        main.mcp_manager = MCPManager(str(tmp_backend["tmp"]))

    client = TestClient(main.app)
    get = client.get("/api/mcp/presets/amt-coding")
    assert get.status_code == 200
    assert get.json()["id"] == "amt-coding"
    assert get.json()["transport"] == "stdio"
    assert get.json()["enabled"] is False
    assert get.json()["auto_approve"] is False

    post = client.post("/api/mcp/presets/amt-coding")
    assert post.status_code == 200
    body = post.json()
    assert body.get("config", {}).get("id", "amt-coding") == "amt-coding"
    assert "created" in body


def test_coding_tool_endpoint_runs_git_status(tmp_backend, tmp_path):
    import main
    from fastapi.testclient import TestClient

    root = tmp_path / "repo"
    root.mkdir(parents=True)
    client = TestClient(main.app)

    resp = client.post(
        "/api/coding/tool",
        json={"root": str(root), "tool": "git_status", "args": {}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok"
    assert "output" in body or "error" in body


def test_coding_tool_endpoint_rejects_missing_root(tmp_backend):
    import main
    from fastapi.testclient import TestClient

    client = TestClient(main.app)

    resp = client.post(
        "/api/coding/tool",
        json={"root": "", "tool": "git_status", "args": {}},
    )

    assert resp.status_code == 400
    assert "root" in resp.json()["detail"].lower() or "проект" in resp.json()["detail"].lower()


def test_coding_tool_endpoint_rejects_high_risk_tools(tmp_backend, tmp_path):
    import main
    from fastapi.testclient import TestClient

    root = tmp_path / "repo"
    root.mkdir(parents=True)
    client = TestClient(main.app)

    for tool in ("git_commit", "git_push", "fs_write", "fs_apply_patch", "run_command"):
        resp = client.post(
            "/api/coding/tool",
            json={"root": str(root), "tool": tool, "args": {}},
        )
        assert resp.status_code in (400, 404), f"{tool} should be restricted from direct execution"


def test_coding_tool_endpoint_run_tests_reports_missing_test_runner(tmp_backend, tmp_path):
    import main
    from fastapi.testclient import TestClient

    root = tmp_path / "repo"
    root.mkdir(parents=True)
    client = TestClient(main.app)

    resp = client.post(
        "/api/coding/tool",
        json={"root": str(root), "tool": "run_tests", "args": {}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is False
    assert "test runner" in body.get("error", "").lower()


def test_coding_tool_endpoint_allows_list_symbols(tmp_backend, tmp_path):
    import main
    from fastapi.testclient import TestClient
    root = tmp_path / "sym_proj"
    root.mkdir()
    (root / "a.py").write_text("def alpha():\n    return 1\n")
    client = TestClient(main.app)
    resp = client.post("/api/coding/tool", json={"root": str(root), "tool": "list_symbols", "args": {}})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is True
    symbols = body.get("symbols") or []
    assert any("alpha" in (s.get("text") or "") for s in symbols)


def test_coding_tool_endpoint_logs_coding_event(tmp_backend, tmp_path, monkeypatch):
    import main
    from fastapi.testclient import TestClient

    calls = []

    class FakeStructuredLogger:
        def log(self, level, category, message, trace_id=None, session_id=None, metadata=None):
            calls.append(category)

    monkeypatch.setattr(main, "structured_logger", FakeStructuredLogger())
    root = tmp_path / "log_proj"
    root.mkdir()
    client = TestClient(main.app)
    resp = client.post("/api/coding/tool", json={"root": str(root), "tool": "git_status", "args": {}})
    assert resp.status_code == 200
    assert "coding" in calls
