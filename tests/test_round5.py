"""Round-5: channels VOD/live fallback, web links in player, filters panel fix, fullscreen."""
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(BASE, "backend", "main.py")
MAIN_JS = os.path.join(BASE, "frontend", "js", "main.js")
PB_JS = os.path.join(BASE, "frontend", "js", "media", "player-browser.js")
STYLE_CSS = os.path.join(BASE, "frontend", "css", "style.css")
WEB_SCRAPER = os.path.join(BASE, "backend", "ai_engine", "web_scraper.py")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


# ---------- 1. Twitch VOD via GraphQL (web_scraper.py) ----------

class TestTwitchVodGraphQL:
    def test_fetch_twitch_vods_function_exists(self):
        src = _read(WEB_SCRAPER)
        assert "async def _fetch_twitch_vods" in src

    def test_uses_gql_endpoint(self):
        src = _read(WEB_SCRAPER)
        assert "gql.twitch.tv/gql" in src

    def test_extracts_auth_token(self):
        src = _read(WEB_SCRAPER)
        assert 'authToken' in src and "a-f0-9" in src

    def test_vod_thumbnails(self):
        src = _read(WEB_SCRAPER)
        assert "static-cdn.jtvnw.net" in src and "preview-496x280.jpg" in src

    def test_vods_fetched_always_even_when_live(self):
        src = _read(WEB_SCRAPER)
        # The call site must NOT be conditional on 'not live'
        m = re.search(r"result\[\"videos\"\]\s*=\s*await _fetch_twitch_vods\(channel, html, proxy\)", src)
        assert m, "VODs must be fetched regardless of live status"


# ---------- 2. YouTube fallback scraping (web_scraper.py) ----------

class TestYtFallbackScrape:
    def test_watch_v_fallback(self):
        src = _read(WEB_SCRAPER)
        assert "/watch?v=" in src and "data-video-title" in src

    def test_ytimg_thumb_fallback(self):
        src = _read(WEB_SCRAPER)
        assert "i.ytimg.com" in src

    def test_fallback_runs_when_ytinitialdata_empty(self):
        src = _read(WEB_SCRAPER)
        assert "if not videos:" in src


# ---------- 3. Channel endpoints fallback (main.py) ----------

class TestChannelEndpoints:
    def test_yt_channel_web_search_fallback(self):
        src = _read(MAIN_PY)
        m = re.search(r"@app\.get\(\"/api/yt/channel\"\)\nasync def yt_channel.*?return result", src, re.DOTALL)
        assert m, "yt_channel endpoint must exist"
        assert "web_search_fallback" in m.group(0)

    def test_twitch_channel_vod_web_search_fallback(self):
        src = _read(MAIN_PY)
        m = re.search(r"@app\.get\(\"/api/twitch/channel\"\)\nasync def twitch_channel.*?return result", src, re.DOTALL)
        assert m, "twitch_channel endpoint must exist"
        assert "web_search_fallback" in m.group(0)


# ---------- 4. Twitch VOD iframe in player (player-browser.js) ----------

class TestTwitchVodIframe:
    def test_vod_embed_url(self):
        src = _read(PB_JS)
        assert "player.twitch.tv/?video=" in src

    def test_vod_id_from_url(self):
        src = _read(PB_JS)
        assert "twitch.tv/videos/" in src

    def test_twitch_vod_card_passes_url(self):
        src = _read(PB_JS)
        m = re.search(r"loadVideoIntoMain\(mainEl, \{ \.\.\.first, url: 'https://www\.twitch\.tv/videos/'", src)
        assert m, "Twitch VOD auto-load must pass the VOD URL"


# ---------- 5. Web links open IN the player (player-browser.js) ----------

class TestWebLinksInPlayer:
    def test_web_branch_iframe_attempt(self):
        src = _read(PB_JS)
        # web branch now tries iframe first, with 4s fallback card
        m = re.search(r"vid\.platform === 'web' \|\| \(!vid\.id && vid\.url\)", src)
        assert m, "web result detection for in-player loading"

    def test_web_blocked_timeout(self):
        src = _read(PB_JS)
        assert "setTimeout(showBlocked, 4000)" in src

    def test_web_fallback_card_with_open_btn(self):
        src = _read(PB_JS)
        assert "X-Frame-Options" in src and "Открыть в браузере" in src

    def test_web_card_shown_inside_main_el(self):
        src = _read(PB_JS)
        # web branch must append to wrap which is added to mainEl
        m = re.search(r"if \(vid\.platform === 'web' \|\| \(!vid\.id && vid\.url\)\) \{.*?mainEl\.appendChild\(wrap\);", src, re.DOTALL)
        assert m, "web link card must live inside the player main area"


# ---------- 6. Filters panel: fixed position + active state ----------

class TestFiltersPanel:
    def test_panel_position_fixed(self):
        src = _read(STYLE_CSS)
        m = re.search(r"\.media-filters\s*{[^}]*position:\s*fixed", src)
        assert m, ".media-filters must be position:fixed so it shows above the overlay in full mode"

    def test_panel_zindex_above_overlay(self):
        src = _read(STYLE_CSS)
        m = re.search(r"\.media-filters\s*{[^}]*z-index:\s*(\d+)", src)
        assert m and int(m.group(1)) > 10000, "panel z-index must exceed overlay (10000)"

    def test_toggle_active_class(self):
        src = _read(MAIN_JS)
        assert "playerFiltersToggle" in src
        m = re.search(r"filtersToggle\.classList\.toggle\('active'", src)
        assert m, "filters toggle button must get an 'active' state"

    def test_active_style(self):
        src = _read(STYLE_CSS)
        assert "#playerFiltersToggle.active" in src


# ---------- 7. Twitch live-no-VOD branch in channel tab ----------

class TestTwitchLiveBranch:
    def test_live_with_videos_shows_vods(self):
        src = _read(PB_JS)
        assert "VOD" in src

    def test_live_only_opens_stream_iframe(self):
        src = _read(PB_JS)
        m = re.search(r"else if \(data\.live && platform === 'twitch'\)", src)
        assert m, "live channel without VODs must open the stream iframe in the player"
