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


def test_coding_session_delete(tmp_backend, monkeypatch):
    import main

    main._load_sessions()
    original = main._coding_session_create({"name": "del", "root": "C:\\tmp"})
    assert main._coding_session_delete(original["id"]) is True
    assert all(item["id"] != original["id"] for item in main._coding_session_list())
