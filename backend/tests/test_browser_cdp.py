"""Layer 2 (browser CDP) tests.

Without a real browser running on port 9222 these tests exercise the
graceful-degradation path: cdp_recon/cdp_click/cdp_fill return a
structured {"ok": False, "code": "cdp_unavailable"} when the CDP
endpoint is unreachable — exactly the behavior the LLM relies on to
fall back to page_recon (Fix 2.3).
"""
import pytest

from ai_engine import browser_cdp as bcdp


def test_is_chromium_detection():
    """CHROMIUM_BROWSERS is a detection list, not a restriction."""
    for name in ("edge", "chrome", "brave", "opera", "yandex"):
        assert bcdp._is_chromium(name) is True
    # Non-Chromium names must not be detected
    for name in ("firefox", "safari", "ie"):
        assert bcdp._is_chromium(name) is False


def test_chromium_browsers_list_shape():
    """Each entry has name + exe (for _find_chromium_exe)."""
    for b in bcdp.CHROMIUM_BROWSERS:
        assert "name" in b
        assert "exe" in b


def test_cdp_recon_degrades_gracefully_when_no_browser():
    """No browser on 9222 → structured cdp_unavailable error, not crash."""
    res = bcdp.cdp_recon()
    # Either we got a real page (a CDP browser happens to be running) or
    # the structured unavailable error. Both are acceptable; the contract
    # is "dict with ok flag, never an exception".
    assert isinstance(res, dict)
    assert "ok" in res
    if res["ok"] is False:
        assert res.get("code") == "cdp_unavailable"


def test_cdp_click_degrades_gracefully():
    res = bcdp.cdp_click("#nonexistent")
    assert isinstance(res, dict)
    assert "ok" in res


def test_cdp_fill_degrades_gracefully():
    res = bcdp.cdp_fill("#field", "text")
    assert isinstance(res, dict)
    assert "ok" in res


def test_cdp_press_degrades_gracefully():
    res = bcdp.cdp_press("Enter")
    assert isinstance(res, dict)
    assert "ok" in res


def test_cdp_navigate_degrades_gracefully():
    res = bcdp.cdp_navigate("https://example.com")
    assert isinstance(res, dict)
    assert "ok" in res


def test_cdp_screenshot_degrades_gracefully():
    res = bcdp.cdp_screenshot()
    # cdp_screenshot returns Optional[str] (path) — None when no CDP.
    assert res is None or isinstance(res, str)


def test_cdp_endpoint_default():
    """Default endpoint is 127.0.0.1:9222/json/version."""
    assert bcdp.CDP_ENDPOINT == "http://127.0.0.1:9222"
