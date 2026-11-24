"""Tests for the web agent's real search tool: /api/web/search, parsers, and [[WEBSEARCH]] token resolution.

Network calls are mocked (httpx); parser + token logic is tested with fixture HTML.
"""
import asyncio
import json
import pytest
from fastapi.testclient import TestClient

import main


# ---------- Parser fixtures ----------
# Minimal realistic YouTube search HTML: ytInitialData with a videoRenderer block.
_YT_HTML = """
var ytInitialData = {"contents":{"twoColumnBrowseResultsRenderer":{"tabs":[{"tabRenderer":{"content":{"sectionListRenderer":{"contents":[{"itemSectionRenderer":{"contents":[{"gridVideoRenderer":{"videoRenderer":{"videoId":"AbCd1234567","title":{"runs":[{"text":"МОЁ ВИДЕО ТИТЛ"}]}},"ownerText":{"runs":[{"text":"Канал"}]}},"viewCountText":{"simpleText":"10K"}}}]}]}}}]}}}]}}};
"""

_DDG_HTML = """
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=abc">Some &amp; Title</a>
</div>
"""


class TestParsers:
    def test_yt_parser_extracts_video(self):
        res = main._yt_parse_results(_YT_HTML, 8)
        vids = [r for r in res if r["type"] == "video"]
        assert any(r["url"] == "https://www.youtube.com/watch?v=AbCd1234567" for r in vids)
        # заголовок корректно декодирован (кириллица без mojibake)
        v = next(r for r in vids if r["url"].endswith("AbCd1234567"))
        assert v["title"] == "МОЁ ВИДЕО ТИТЛ"
        assert v["source"] == "YouTube"

    def test_yt_parser_empty(self):
        assert main._yt_parse_results("<html>nothing</html>", 8) == []

    def test_ddg_parser_decodes_redirect(self):
        res = main._ddg_parse_results(_DDG_HTML, 8)
        assert len(res) == 1
        assert res[0]["url"] == "https://example.com/page"
        assert res[0]["title"] == "Some & Title"
        assert res[0]["source"] == "DuckDuckGo"

    def test_ddg_parser_empty(self):
        assert main._ddg_parse_results("<html></html>", 8) == []


class TestWebSearchEndpoint:
    @pytest.fixture
    def client(self, tmp_backend, monkeypatch):
        main.agents_mgr = main.AgentSkillManager(str(tmp_backend["tmp"] / "agents.json"))
        c = TestClient(main.app)
        yield c

    def test_endpoint_with_yt_results(self, client, monkeypatch):
        """/api/web/search без сети: httpx смонкан, результаты из фикстурного HTML."""
        monkeypatch.setattr(main.httpx, "AsyncClient", lambda *a, **k: _FakeClientYt())
        r = client.post("/api/web/search", json={"query": "рекремт", "kind": "auto", "limit": 5})
        body = r.json()
        assert body["ok"] is True
        # видео должны быть первыми при kind=auto
        assert body["results"][0]["source"] == "YouTube"
        assert "watch?v=" in body["results"][0]["url"]
        assert body["count"] >= 1

    def test_empty_query(self, client):
        r = client.post("/api/web/search", json={"query": "   "})
        assert r.json()["ok"] is False


class TestTokenResolution:
    def test_no_tokens_passthrough(self):
        out = asyncio.run(main.resolve_websearch_tokens("просто текст без токенов", True))
        assert out == "просто текст без токенов"

    def test_inactive_passthrough(self):
        out = asyncio.run(main.resolve_websearch_tokens("[[WEBSEARCH:q|youtube|8]]", False))
        assert out == "[[WEBSEARCH:q|youtube|8]]"

    def test_token_replaced_by_results(self, monkeypatch):
        monkeypatch.setattr(main.httpx, "AsyncClient", lambda *a, **k: _FakeClientYt())
        text = "Смотри: [[WEBSEARCH:рекремт|youtube|5]] вот."
        out = asyncio.run(main.resolve_websearch_tokens(text, True))
        assert "[[WEBSEARCH" not in out
        assert "watch?v=" in out or "Не удалось" in out

    def test_token_error_graceful(self, monkeypatch):
        class Boom:
            def __init__(self, *a, **k):
                pass
            async def __aenter__(self):
                raise RuntimeError("нет сети")
        monkeypatch.setattr(main.httpx, "AsyncClient", lambda *a, **k: Boom())
        out = asyncio.run(main.resolve_websearch_tokens("[[WEBSEARCH:x|youtube|3]]", True))
        assert "[[WEBSEARCH" not in out


# ---------- helpers: фейковый httpx.AsyncClient без сети ----------
class _FakeResp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text


class _FakeClientYt:
    """Имитация httpx.AsyncClient: get -> YouTube HTML, post -> DDG HTML."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, *a, **k):
        return _FakeClientYt._get(_YT_HTML)

    def post(self, *a, **k):
        return _FakeClientYt._post(_DDG_HTML)

    @staticmethod
    async def _get(html):
        return _FakeResp(200, html)

    @staticmethod
    async def _post(html):
        return _FakeResp(200, html)
