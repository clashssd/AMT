"""Tests for the Memory class (backend/ai_engine/memory.py)."""
import json
import os
import pytest
import httpx

from ai_engine.memory import Memory


@pytest.fixture
def mem(tmp_path):
    return Memory(str(tmp_path / "memory.json"))


class TestMemoryPersistence:
    def test_new_memory_empty(self, mem):
        assert mem.facts == []
        assert mem.user_prefs == {}

    def test_save_and_reload(self, tmp_path):
        path = str(tmp_path / "m.json")
        m1 = Memory(path)
        m1.add_fact("user likes python")
        # Fresh instance must load the fact
        m2 = Memory(path)
        assert any(f["text"] == "user likes python" for f in m2.facts)

    def test_add_fact_writes_file(self, mem, tmp_path):
        mem.add_fact("fact x", chat_id="c1")
        data = json.loads(open(mem.path, encoding="utf-8").read())
        assert data["facts"][0]["text"] == "fact x"
        assert data["facts"][0]["chat_id"] == "c1"
        assert "ts" in data["facts"][0]

    def test_load_corrupt_file_resets(self, tmp_path):
        path = str(tmp_path / "m.json")
        Memory(path)
        open(path, "w").write("{ not valid json ")
        m = Memory(path)
        assert m.facts == []
        assert m.user_prefs == {}

    def test_load_missing_file_is_fine(self, tmp_path):
        m = Memory(str(tmp_path / "does_not_exist.json"))
        assert m.facts == []


class TestMemorySystemPrompt:
    def test_empty_when_no_facts(self, mem):
        assert mem.get_system_prompt_append() == ""

    def test_includes_latest_20(self, mem):
        for i in range(30):
            mem.facts.append({"text": f"f{i}", "chat_id": "", "ts": 0})
        block = mem.get_system_prompt_append()
        # should start with header and contain last 20 (f10..f29)
        assert "f29" in block
        assert "f10" in block
        # f0..f9 dropped
        assert "f0:" not in block and "- f0\n" not in block
        assert "- f9" not in block
        assert block.startswith("Вот что я знаю")

    def test_wipe_clears_and_saves(self, mem, tmp_path):
        mem.add_fact("a")
        mem.add_fact("b")
        mem.wipe()
        assert mem.facts == []
        # reload confirms wiped on disk
        m2 = Memory(mem.path)
        assert m2.facts == []


class TestMemoryExtractFacts:
    @pytest.mark.asyncio
    async def test_noop_without_api_key(self, mem):
        before = len(mem.facts)
        await mem.extract_facts("hi", "hello", "http://x", "", "gpt")
        assert len(mem.facts) == before

    @pytest.mark.asyncio
    async def test_extracts_lines_from_response(self, mem, monkeypatch):
        """Mock httpx to return a fixed fact list; verify facts are added."""
        captured = {}

        class FakeResp:
            status_code = 200
            def json(self):
                return {"choices": [{"message": {"content": "любит кофе\nработает в IT\nаб"}}]}

        class FakeClient:
            def __init__(self, **kw): captured["init"] = kw
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, headers=None, json=None, **kw):
                captured["url"] = url
                captured["auth"] = headers["Authorization"]
                captured["body"] = json
                return FakeResp()

        import ai_engine.memory as mem_mod
        monkeypatch.setattr(mem_mod.httpx, "AsyncClient", FakeClient)

        await mem.extract_facts("заказ кофе", "принято", "https://api.openai.com/v1", "sk-test", "gpt-4o")

        assert "любит кофе" in [f["text"] for f in mem.facts]
        assert "работает в IT" in [f["text"] for f in mem.facts]
        # "аб" is 2 chars (< 5 threshold) -> filtered out
        assert "аб" not in [f["text"] for f in mem.facts]
        assert captured["auth"] == "Bearer sk-test"
        assert captured["url"].endswith("/chat/completions")

    @pytest.mark.asyncio
    async def test_http_error_is_silent(self, mem, monkeypatch):
        class FakeResp:
            status_code = 500
            def json(self): return {}
        class FakeClient:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, *a, **k): return FakeResp()
        import ai_engine.memory as mem_mod
        monkeypatch.setattr(mem_mod.httpx, "AsyncClient", FakeClient)
        before = len(mem.facts)
        await mem.extract_facts("q", "a", "https://x/v1", "k", "m")
        assert len(mem.facts) == before  # no crash, no facts
