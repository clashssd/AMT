# tests/test_chat_tool_calls.py
import pytest, json, httpx, asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import Response as HttpxResponse


def _make_mock_client_factory(responses_iter):
    """Returns a factory that, when called with any kwargs, yields a MockClient
    whose .post() returns the next response from responses_iter."""
    class MockClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, headers=None, json=None, **kw):
            data = next(responses_iter)
            return HttpxResponse(200, json=data)
    def factory(*a, **kw):
        return MockClient()
    return factory


def test_settings_has_toolcalling_flag(tmp_backend):
    import main
    from main import Settings
    s = Settings()
    assert hasattr(s, "toolCalling")
    assert s.toolCalling is True


def test_request_body_includes_tools_when_enabled(tmp_backend, monkeypatch):
    import main
    captured = []

    def factory(*a, **kw):
        class MC:
            async def __aenter__(self): return self
            async def __aexit__(self, *x): return False
            async def post(self, url, headers=None, json=None, **kw):
                captured.append(json)
                return HttpxResponse(200, json={
                    "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                })
        return MC()

    monkeypatch.setattr("main.httpx.AsyncClient", factory)
    settings = main.Settings()
    settings.baseUrl = "http://localhost:9999/v1"
    settings.apiKey = "sk-test"
    settings.model = "gpt-4o-mini"
    settings.toolCalling = True
    result = asyncio.run(main.call_ai_api("hi", [], settings))
    # The FIRST post is the chat completion — it must carry the tool schemas.
    # (Later posts from background tasks like memory.extract_facts may also
    # fire but are not the chat request.)
    assert captured, "no HTTP post captured"
    assert "tools" in captured[0]
    assert len(captured[0]["tools"]) >= 4


def test_request_body_omits_tools_when_disabled(tmp_backend, monkeypatch):
    import main
    captured = []

    def factory(*a, **kw):
        class MC:
            async def __aenter__(self): return self
            async def __aexit__(self, *x): return False
            async def post(self, url, headers=None, json=None, **kw):
                captured.append(json)
                return HttpxResponse(200, json={
                    "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                })
        return MC()

    monkeypatch.setattr("main.httpx.AsyncClient", factory)
    settings = main.Settings()
    settings.baseUrl = "http://localhost:9999/v1"
    settings.apiKey = "sk-test"
    settings.model = "gpt-4o-mini"
    settings.toolCalling = False
    result = asyncio.run(main.call_ai_api("hi", [], settings))
    # The FIRST post is the chat completion — with toolCalling=False it must NOT
    # carry the `tools` field (the LLM falls back to [[GEN]] tag parsing).
    assert captured, "no HTTP post captured"
    assert "tools" not in captured[0]


def test_tool_calls_trigger_execution_loop(tmp_backend, monkeypatch):
    import main

    responses = iter([
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "generate_image", "arguments": json.dumps({"prompt": "a cat"})},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
        {
            "choices": [{"message": {"role": "assistant", "content": "Here is your cat image."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        },
    ])

    monkeypatch.setattr("main.httpx.AsyncClient", _make_mock_client_factory(responses))

    async def fake_image_handler(prompt, **kw):
        return json.dumps({"type": "media", "kind": "image", "data": {"b64": "fake_b64"}})

    import ai_engine.tool_registry as tr
    from ai_engine.tool_registry import ToolDef
    tr.tool_registry._tools["generate_image"] = ToolDef(
        name="generate_image", description="mock", parameters={},
        handler=fake_image_handler, source="native",
    )

    settings = main.Settings()
    settings.baseUrl = "http://localhost:9999/v1"
    settings.apiKey = "sk-test"
    settings.model = "gpt-4o-mini"
    settings.toolCalling = True
    result = asyncio.run(main.call_ai_api("make a cat image", [], settings))

    assert "tool_events" in result
    assert len(result["tool_events"]) >= 2
    assert result["text"] == "Here is your cat image."


def test_tool_call_error_appended(tmp_backend, monkeypatch):
    import main

    responses = iter([
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "nonexistent_tool", "arguments": "{}"},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
        {
            "choices": [{"message": {"role": "assistant", "content": "Tool failed, sorry."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        },
    ])

    monkeypatch.setattr("main.httpx.AsyncClient", _make_mock_client_factory(responses))

    settings = main.Settings()
    settings.baseUrl = "http://localhost:9999/v1"
    settings.apiKey = "sk-test"
    settings.model = "gpt-4o-mini"
    settings.toolCalling = True
    result = asyncio.run(main.call_ai_api("test error", [], settings))
    error_events = [e for e in result["tool_events"] if e["type"] == "tool_call_result" and "error" in e.get("result", "").lower()]
    assert len(error_events) == 1
