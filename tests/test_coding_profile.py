import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def test_general_request_does_not_use_coding_key(tmp_backend, monkeypatch):
    import main
    monkeypatch.setattr(main.server_settings, "codingKey", "coding-key")
    monkeypatch.setattr(main.server_settings, "codingModel", "coding-model")

    from ai_engine.coding_profile import resolve_chat_profile
    profile = resolve_chat_profile(main.ChatRequest(message="write code", settings=main.Settings()), keys_mgr=main.keys_mgr, server_settings=main.server_settings)

    assert profile.chat_mode == "general"
    assert profile.model != "coding-model"
    assert profile.api_key != "coding-key"


def test_coding_request_prefers_coding_role_key(tmp_backend, monkeypatch):
    import main
    from ai_engine.coding_profile import resolve_chat_profile
    main.keys_mgr.keys = [
        {"id": "k1", "label": "general", "baseUrl": "https://general", "apiKey": "g", "model": "g-m", "role": "general"},
        {"id": "k2", "label": "coding", "baseUrl": "https://coding", "apiKey": "c", "model": "c-m", "role": "coding"},
    ]
    main.keys_mgr.active_key_id = "k1"
    main.server_settings.codingKey = ""
    main.server_settings.codingModel = ""

    profile = resolve_chat_profile(main.ChatRequest(message="hi", settings=main.Settings(), chat_mode="coding", key_id=""), keys_mgr=main.keys_mgr, server_settings=main.server_settings)

    assert profile.chat_mode == "coding"
    assert profile.api_key == "c"
    assert profile.model == "c-m"
