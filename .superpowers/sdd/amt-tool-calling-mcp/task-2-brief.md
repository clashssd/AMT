### Task 2: `call_ai_api()` Tool-Calling Loop + Settings Flag

**Files:**
- Modify: `backend/main.py` (Settings model ~line 216, `call_ai_api()` ~lines 556-1544, request_body construction ~line 1244, MEDIA_CAPABILITY block ~lines 1111-1199)
- Create: `tests/test_chat_tool_calls.py`

**Interfaces:**
- Consumes: `tool_registry` singleton from `ai_engine/tool_registry.py` (Task 1)
- Produces:
  - `Settings.toolCalling: bool` (default `True`) вЂ” persisted in `settings.json`
  - `call_ai_api()` return type expanded: `{"text": str, "usage": dict, "tool_events": list[dict]}` where each event is `{"type": "tool_call_start"|"tool_call_result", "tool": str, "args": dict?, "result": str?}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chat_tool_calls.py
import pytest, json, httpx, asyncio
from unittest.mock import patch, AsyncMock

def test_settings_has_toolcalling_flag(tmp_backend):
    import main
    from main import Settings
    s = Settings(**tmp_backend["settings"])
    assert hasattr(s, "toolCalling")
    assert s.toolCalling is True

def test_request_body_includes_tools_when_enabled(tmp_backend, monkeypatch):
    import main
    captured = {}

    async def fake_post(url, **kwargs):
        captured["body"] = kwargs.get("json", {})
        resp = httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
        return resp

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    settings = main.Settings(**tmp_backend["settings"])
    settings.toolCalling = True
    result = asyncio.run(main.call_ai_api("hi", [], settings))
    assert "tools" in captured["body"]
    assert len(captured["body"]["tools"]) >= 4  # native tools

def test_request_body_omits_tools_when_disabled(tmp_backend, monkeypatch):
    import main
    captured = {}

    async def fake_post(url, **kwargs):
        captured["body"] = kwargs.get("json", {})
        resp = httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
        return resp

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    settings = main.Settings(**tmp_backend["settings"])
    settings.toolCalling = False
    result = asyncio.run(main.call_ai_api("hi", [], settings))
    assert "tools" not in captured["body"]

def test_tool_calls_trigger_execution_loop(tmp_backend, monkeypatch):
    import main

    responses = iter([
        # First response: LLM wants to call a tool
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
        # Second response: LLM gives final answer
        {
            "choices": [{"message": {"role": "assistant", "content": "Here is your cat image."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        },
    ])

    call_count = 0

    async def fake_post(url, **kwargs):
        nonlocal call_count
        call_count += 1
        data = next(responses)
        return httpx.Response(200, json=data)

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    # Mock the native tool handler so it doesn't hit the network
    async def fake_image_handler(prompt, **kw):
        return json.dumps({"type": "media", "kind": "image", "data": {"b64": "fake_b64"}})

    import ai_engine.tool_registry as tr
    monkeypatch.setattr(tr.tool_registry.get("generate_image").handler, fake_image_handler, raising=False)
    # Re-register with the mock handler
    from ai_engine.tool_registry import ToolDef
    tr.tool_registry._tools["generate_image"] = ToolDef(
        name="generate_image", description="mock", parameters={},
        handler=fake_image_handler, source="native",
    )

    settings = main.Settings(**tmp_backend["settings"])
    settings.toolCalling = True
    result = asyncio.run(main.call_ai_api("make a cat image", [], settings))

    assert call_count == 2  # two LLM calls (tool call + final)
    assert "tool_events" in result
    assert len(result["tool_events"]) >= 2  # start + result events
    assert result["text"] == "Here is your cat image."

def test_tool_call_error_appended(tmp_backend, monkeypatch):
    import main
    import ai_engine.tool_registry as tr

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

    call_count = 0
    async def fake_post(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=next(responses))

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    settings = main.Settings(**tmp_backend["settings"])
    settings.toolCalling = True
    result = asyncio.run(main.call_ai_api("test error", [], settings))
    assert call_count == 2
    # The tool event should contain an error
    error_events = [e for e in result["tool_events"] if e["type"] == "tool_call_result" and "error" in e.get("result", "").lower()]
    assert len(error_events) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chat_tool_calls.py -v`
Expected: FAIL вЂ” `Settings` has no `toolCalling` attribute; `call_ai_api` doesn't handle tool_calls.

- [ ] **Step 3: Add `toolCalling` to Settings model and modify `call_ai_api()`**

In `backend/main.py`:

1. **Settings model (~line 216):** Add `toolCalling: bool = True` field to the pydantic `Settings` class.

2. **Import at top of `main.py`:** Add `from ai_engine.tool_registry import tool_registry` (after existing `ai_engine` imports).

3. **MEDIA_CAPABILITY block (~lines 1111-1199):** Wrap the block so it's only appended to the system prompt when `settings.toolCalling` is `False`:
```python
if not settings.toolCalling:
    combined_prompt += MEDIA_CAPABILITY
```

4. **Request body construction (~line 1244):** After building `request_body`, add:
```python
if settings.toolCalling:
    request_body["tools"] = tool_registry.schemas()
```

5. **Post-response tool-calling loop (~line 1320, after `data = response.json()` and extracting `text`):** Before the `finish_reason == "length"` continuation, insert:
```python
tool_events: list[dict] = []
msg = data["choices"][0]["message"]

if settings.toolCalling and msg.get("tool_calls"):
    for iteration in range(MAX_TOOL_ITERATIONS):
        # Append the assistant message with tool_calls to history
        assistant_msg = {"role": "assistant", "content": msg.get("content")}
        if msg.get("tool_calls"):
            assistant_msg["tool_calls"] = msg["tool_calls"]
        messages.append(assistant_msg)

        for tc in msg["tool_calls"]:
            tc_name = tc["function"]["name"]
            try:
                tc_args = json.loads(tc["function"].get("arguments", "{}"))
            except json.JSONDecodeError:
                tc_args = {}
            tool_events.append({"type": "tool_call_start", "tool": tc_name, "args": tc_args})

            try:
                tc_result = await tool_registry.execute(tc_name, tc_args)
            except Exception as e:
                tc_result = json.dumps({"error": str(e)}, ensure_ascii=False)

            tool_events.append({"type": "tool_call_result", "tool": tc_name, "result": tc_result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tc_result,
            })

        # Re-call LLM with updated messages
        resp2 = await client.post(f"{settings.effective_base_url}/chat/completions", json=request_body)
        if resp2.status_code == 400 and "tools" in resp2.text:
            log.warning("Provider rejected tools field, disabling for this request")
            request_body.pop("tools", None)
            resp2 = await client.post(f"{settings.effective_base_url}/chat/completions", json=request_body)
        data = resp2.json()
        msg = data["choices"][0]["message"]
        if not msg.get("tool_calls"):
            break

if not settings.toolCalling or not msg.get("tool_calls"):
    text = msg.get("content") or ""
else:
    text = msg.get("content") or ""
```

6. **Return value (~line 1544):** Change from `return {"text": text, "usage": usage}` to:
```python
return {"text": text, "usage": usage, "tool_events": tool_events}
```

7. **400 fallback:** When the first `tools`-enabled call returns 400 mentioning "tools", log a warning, remove `tools` from `request_body`, and retry without tools (one-shot fallback per request).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chat_tool_calls.py tests/test_tool_registry.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_chat_tool_calls.py
git commit -m "feat: add tool-calling loop to call_ai_api with toolCalling settings flag"
```

---

