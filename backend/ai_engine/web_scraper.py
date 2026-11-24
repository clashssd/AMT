"""
web_scraper.py — YouTube/Twitch channel page scrapers.

Provides:
- fetch_youtube_channel(channel, proxy) -> dict
- fetch_twitch_channel(channel, proxy) -> dict
- _parse_yt_videos(html) -> list[dict]
- _parse_twitch_channel(html) -> dict

Uses httpx async with in-memory cache (5 min TTL) and per-channel throttle (1 req/sec).
"""
import asyncio
import json
import re
import time
from typing import Any

import httpx

# --- In-memory cache: {key: (timestamp, data)} ---
_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 300  # 5 minutes

# --- Per-channel throttle: last fetch time ---
_throttle: dict[str, float] = {}
_THROTTLE_INTERVAL = 1.0  # 1 sec


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, data: Any):
    _cache[key] = (time.time(), data)


def _throttle_wait(channel_key: str):
    """Wait if we fetched this channel < 1 sec ago."""
    last = _throttle.get(channel_key, 0)
    wait = last + _THROTTLE_INTERVAL - time.time()
    if wait > 0:
        time.sleep(wait)
    _throttle[channel_key] = time.time()


# ===================== YouTube Parsing =====================

def _parse_yt_videos(html: str) -> list[dict]:
    """Extract video list from YouTube channel page HTML (ytInitialData)."""
    # Find ytInitialData JSON
    m = re.search(r"var ytInitialData\s*=\s*(\{.+?\});", html, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, IndexError):
        return []

    videos = []
    # Navigate to richGridRenderer.contents
    try:
        tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
        for tab in tabs:
            contents = tab.get("tabRenderer", {}).get("content", {}).get("richGridRenderer", {}).get("contents", [])
            for item in contents:
                # videoRenderer or lockupViewModel
                vr = item.get("videoRenderer")
                if vr:
                    vid = vr.get("videoId", "")
                    if not vid:
                        continue
                    title_runs = vr.get("title", {}).get("runs", [])
                    title = "".join(r.get("text", "") for r in title_runs) if title_runs else ""
                    thumbs = vr.get("thumbnail", {}).get("thumbnails", [])
                    thumb = thumbs[0].get("url", "") if thumbs else ""
                    entry: dict[str, Any] = {"id": vid, "title": title, "thumb": thumb}
                    # Live check
                    if "liveBroadcastDetails" in vr:
                        entry["live"] = True
                        viewers = vr["liveBroadcastDetails"].get("viewers")
                        if viewers:
                            entry["viewers"] = viewers
                    # Duration
                    dur = vr.get("lengthText", {}).get("simpleText", "")
                    if dur:
                        entry["duration"] = dur
                    videos.append(entry)
                # lockupViewModel (newer YouTube layout)
                lv = item.get("lockupViewModel")
                if lv:
                    # Try to extract videoId from context or content
                    vid = ""
                    try:
                        vid = lv.get("content", {}).get("lockupMetadataViewModel", {}).get("title", {}).get("content", "")
                        # This is not the videoId — we need the videoId from context
                        ctx = lv.get("contextualMenuViewModel", {}).get("menu", {}).get("menuViewModel")
                        if not vid:
                            # Fallback: look for videoId in the item's keys
                            for k, v in lv.items():
                                if isinstance(v, dict) and "videoId" in v:
                                    vid = v["videoId"]
                                    break
                    except (AttributeError, KeyError):
                        pass
                    if not vid:
                        continue
                    # Title
                    title = ""
                    try:
                        md = lv.get("metadata", {}).get("lockupMetadataViewModel", {})
                        title = md.get("title", {}).get("content", "")
                    except (AttributeError, KeyError):
                        pass
                    # Thumbnail
                    thumb = ""
                    try:
                        thumb = lv.get("contentImage", {}).get("thumbnail", {}).get("sources", [{}])[0].get("url", "")
                    except (AttributeError, IndexError, KeyError):
                        pass
                    entry = {"id": vid, "title": title, "thumb": thumb}
                    videos.append(entry)
            if videos:
                break
    except (AttributeError, KeyError, TypeError):
        pass

    return videos


def _parse_yt_channel_meta(html: str) -> dict:
    """Extract channel title, avatar, description from YouTube HTML."""
    meta: dict[str, Any] = {}
    # Title from og:title
    m = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', html)
    if m:
        meta["title"] = m.group(1).replace(" - YouTube", "").strip()
    # Avatar from og:image
    m = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', html)
    if m:
        meta["avatar"] = m.group(1)
    # Description from meta description
    m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
    if m:
        meta["description"] = m.group(1)
    # Subscriber count from ytInitialData
    m = re.search(r'var ytInitialData\s*=\s*(\{.+?\});', html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            # Try to find subscriberCountText
            def find_subscribers(obj, depth=0):
                if depth > 6:
                    return None
                if isinstance(obj, dict):
                    if "subscriberCountText" in obj:
                        return obj["subscriberCountText"]
                    for v in obj.values():
                        r = find_subscribers(v, depth + 1)
                        if r:
                            return r
                elif isinstance(obj, list):
                    for item in obj:
                        r = find_subscribers(item, depth + 1)
                        if r:
                            return r
                return None

            subs = find_subscribers(data)
            if subs:
                text = subs.get("simpleText", "") or subs.get("accessibility", {}).get("accessibilityData", {}).get("label", "")
                meta["subscribers"] = text
        except (json.JSONDecodeError, AttributeError, KeyError):
            pass
    return meta


async def fetch_youtube_channel(channel: str, proxy: str = "") -> dict:
    """Fetch YouTube channel page and extract video list + metadata."""
    # Clean channel name
    channel = channel.strip().lstrip("@").replace("youtube.com/", "").split("?")[0]
    cache_key = f"yt_channel_{channel}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    _throttle_wait(cache_key)

    url = f"https://www.youtube.com/@{channel}/videos"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        client_kwargs: dict[str, Any] = {"timeout": 20.0}
        if proxy:
            client_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            if resp.status_code != 200:
                return {"ok": False, "channel": channel, "error": f"http_{resp.status_code}", "videos": []}
            html = resp.text
    except Exception as e:
        return {"ok": False, "channel": channel, "error": str(e), "videos": []}

    videos = _parse_yt_videos(html)

    # Fallback: ytInitialData разберается не всегда (A/B-развёртывания, новые лейауты).
    # Достаём видео прямо из HTML: /watch?v=ID + data-video-title + i.ytimg.com/...jpg
    if not videos:
        for m in re.finditer(
            r'/watch\?v=([A-Za-z0-9_-]{11})[^"\']*?(?:\s+data-video-title="([^"]*)")?',
            html,
        ):
            vid = m.group(1)
            title = m.group(2) or ""
            tm = re.search(rf'((?:https?:)?//i\.ytimg\.com/vi/{vid}/[a-z0-9]+\.jpg)', html)
            entry: dict[str, Any] = {"id": vid, "title": title}
            if tm:
                entry["thumb"] = tm.group(1).replace("//", "https://")
            elif title:
                entry["thumb"] = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            if title or tm:
                if not any(v["id"] == vid for v in videos):
                    videos.append(entry)
            if len(videos) >= 30:
                break

    meta = _parse_yt_channel_meta(html)

    result: dict[str, Any] = {
        "ok": True,
        "channel": channel,
        "videos": videos,
    }
    result.update(meta)
    if not videos:
        result["error"] = "parse_failed"

    _cache_set(cache_key, result)
    return result


# ===================== Twitch Parsing =====================

def _parse_twitch_channel(html: str) -> dict:
    """Parse Twitch channel page HTML for live status, title, viewers, avatar."""
    result: dict[str, Any] = {"live": False, "title": "", "viewers": None, "avatar": ""}

    # Live check: is-live class or "live" in stream data
    is_live = bool(re.search(r'class="[^"]*stream-container[^"]*is-live', html)) or \
              bool(re.search(r'"live"\s*:\s*true', html)) or \
              bool(re.search(r'class="[^"]*LiveBadge', html))
    result["live"] = is_live

    # Title
    m = re.search(r'<h1[^>]*class="[^"]*channel-header[^"]*title[^"]*"[^>]*>([^<]*)</h1>', html)
    if m:
        result["title"] = m.group(1).strip()
    else:
        m = re.search(r'<title>([^<]*)</title>', html)
        if m:
            result["title"] = m.group(1).strip()

    # Viewers
    if is_live:
        m = re.search(r'(\d[\d,]*)\s*(?:viewers|зрител)', html, re.IGNORECASE)
        if m:
            result["viewers"] = int(m.group(1).replace(",", ""))

    # Avatar
    m = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', html)
    if m:
        result["avatar"] = m.group(1)

    return result


async def fetch_twitch_channel(channel: str, proxy: str = "") -> dict:
    """Fetch Twitch channel page and extract live status + metadata."""
    channel = channel.strip().replace("twitch.tv/", "").lstrip("/")
    cache_key = f"tw_channel_{channel}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    _throttle_wait(cache_key)

    url = f"https://www.twitch.tv/{channel}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        client_kwargs: dict[str, Any] = {"timeout": 15.0}
        if proxy:
            client_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            if resp.status_code != 200:
                return {"ok": False, "channel": channel, "live": False, "error": f"http_{resp.status_code}"}
            html = resp.text
    except Exception as e:
        return {"ok": False, "channel": channel, "live": False, "error": str(e)}

    parsed = _parse_twitch_channel(html)
    result: dict[str, Any] = {
        "ok": True,
        "channel": channel,
    }
    result.update(parsed)

    # VOD-ы: Twitch не отдаёт их в HTML-странице (нужен GraphQL). Пытаемся через
    # публичный GraphQL-эндпоинт (token из HTML). VOD'ы показываем всегда —
    # даже у live-канала они есть, и стример часто смотрит VOD'ы.
    result["videos"] = await _fetch_twitch_vods(channel, html, proxy)

    _cache_set(cache_key, result)
    return result


async def _fetch_twitch_vods(channel: str, page_html: str, proxy: str = "", limit: int = 12) -> list[dict]:
    """VOD-ы канала через публичный Twitch GraphQL (token из HTML страницы)."""
    import json as _json
    m = re.search(r'"authToken"\s*:\s*"([a-f0-9]{20,})"', page_html)
    if not m:
        return []
    token = m.group(1)
    gql = """
    query($login: String!) {
      user(login: $login) {
        vodChannel(limit: $limit) {
          segments {
            video { id title durationSeconds createdAt broadcastType }
          }
        }
      }
    }
    """
    try:
        client_kwargs: dict[str, Any] = {"timeout": 12.0}
        if proxy:
            client_kwargs["proxy"] = proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.post(
                "https://gql.twitch.tv/gql",
                headers={
                    "Client-Id": "kimne78kx3nc3n355nlvmawoxi",  # официальный anonymous client-id
                    "Client-Token": token,
                    "Content-Type": "application/json",
                },
                json={"query": gql, "variables": {"login": channel, "limit": limit}},
            )
            data = resp.json()
    except Exception:
        return []
    vods = []
    try:
        segs = data["data"]["user"]["vodChannel"]["segments"]
        for s in segs:
            v = s.get("video") or {}
            vid = v.get("id", "")
            if not vid:
                continue
            dur_s = v.get("durationSeconds")
            dur = ""
            if dur_s:
                h, rem = divmod(int(dur_s), 3600)
                mnt, sec = divmod(rem, 60)
                dur = f"{h}:{mnt:02d}:{sec:02d}" if h else f"{mnt}:{sec:02d}"
            vods.append({
                "id": vid,
                "title": v.get("title", ""),
                "thumb": f"https://static-cdn.jtvnw.net/v1/vids/{vid}/preview-496x280.jpg",
                "duration": dur,
            })
    except (KeyError, TypeError, AttributeError):
        pass
    return vods
