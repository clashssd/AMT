"""Tests for web_scraper.py — YouTube/Twitch channel page parsing."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_yt_html(channel_title="Test Channel", video_ids=None, live=False, viewers=None):
    """Build a minimal ytInitialData JSON block that the scraper will parse."""
    if video_ids is None:
        video_ids = ["abc123", "def456"]
    videos_json = []
    for vid in video_ids:
        entry = {
            "videoRenderer": {
                "videoId": vid,
                "title": {"runs": [{"text": f"Video {vid}"}]},
                "thumbnail": {"thumbnails": [{"url": f"https://i.ytimg.com/vi/{vid}/default.jpg"}]},
            }
        }
        if live:
            entry["videoRenderer"]["liveBroadcastDetails"] = {"viewers": viewers or 100}
        videos_json.append(entry)
    data = {
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "content": {
                                "richGridRenderer": {"contents": videos_json}
                            }
                        }
                    }
                ]
            }
        }
    }
    html = f'<html><head></head><body><script>var ytInitialData = {json.dumps(data)};</script></body></html>'
    return html


def test_parse_youtube_videos():
    """The scraper extracts video IDs, titles, thumbnails from ytInitialData."""
    from backend.ai_engine.web_scraper import _parse_yt_videos
    html = _make_yt_html(video_ids=["vid1", "vid2"])
    results = _parse_yt_videos(html)
    assert len(results) == 2
    assert results[0]["id"] == "vid1"
    assert results[0]["title"] == "Video vid1"
    assert "thumb" in results[0]


def test_parse_youtube_live():
    """Live videos have liveBroadcastDetails -> live=True."""
    from backend.ai_engine.web_scraper import _parse_yt_videos
    html = _make_yt_html(video_ids=["live1"], live=True, viewers=500)
    results = _parse_yt_videos(html)
    assert results[0].get("live") is True


def test_parse_youtube_empty():
    """No videos -> empty list."""
    from backend.ai_engine.web_scraper import _parse_yt_videos
    assert _parse_yt_videos("<html></html>") == []


def test_parse_twitch_channel():
    """Twitch HTML parsing extracts live status and title."""
    from backend.ai_engine.web_scraper import _parse_twitch_channel
    html = '''<html><body>
    <div class="stream-container is-live">
      <span class="tw-text-label">Live: 1234 viewers</span>
      <h1 class="channel-header-offline-title">Test Stream</h1>
    </div>
    <meta property="og:image" content="https://static-cdn.jtvnw.net/jtv_user_pictures/avatar.png">
    </body></html>'''
    result = _parse_twitch_channel(html)
    assert result["live"] is True
    assert result["title"] == "Test Stream"
    assert result["viewers"] == 1234


def test_parse_twitch_offline():
    """Offline Twitch channel returns live=False."""
    from backend.ai_engine.web_scraper import _parse_twitch_channel
    html = '''<html><body>
    <div class="stream-container">
      <h1 class="channel-header-offline-title">Some Channel</h1>
    </div>
    </body></html>'''
    result = _parse_twitch_channel(html)
    assert result["live"] is False
    assert result["title"] == "Some Channel"
