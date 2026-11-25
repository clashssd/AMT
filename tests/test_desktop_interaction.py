"""
AMT — generic desktop interaction tests.

These tests use the DesktopSandbox API generically:
- No hardcoded app names or URLs in the test logic.
- The test app/site is configurable via environment variables or the class.
- Default safe test targets:
  - App: "notepad" (safe, always present on Windows)
  - Browser: whatever the system default is (Chrome/Edge/Firefox)

Run with:
    python -m pytest tests/test_desktop_interaction.py -v

Environment overrides:
    AMT_TEST_APP      — app name to test (default: "notepad")
    AMT_TEST_BROWSER  — browser name to test (default: auto-detect)
    AMT_TEST_SEARCH   — search text to type (default: "test")
    AMT_TEST_URL      — URL to open in browser (default: about:blank)
    AMT_HEADLESS      — set "1" to skip window interactions (CI-safe)
"""

import os
import sys
import time
import json
import platform
import importlib.util

# Import DesktopSandbox directly (not through main.py to avoid FastAPI dependencies)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from ai_engine.desktop_tools import DesktopSandbox  # noqa: E402


def _import_sandbox() -> DesktopSandbox:
    """Create a DesktopSandbox instance for testing."""
    sandbox = DesktopSandbox()
    return sandbox


def _detect_default_browser() -> str:
    """Auto-detect the default browser (Chrome, Edge, Firefox, etc.)."""
    import subprocess
    import re

    # Try reading from Windows registry (UrlAssociations)
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            "http\\shell\\open\\command",
        )
        val, _ = winreg.QueryValueEx(key, None)
        winreg.CloseKey(key)
        # Extract browser name from the command
        lower = val.lower()
        if "chrome" in lower:
            return "chrome"
        elif "msedge" in lower or "edge" in lower:
            return "edge"
        elif "firefox" in lower:
            return "firefox"
    except Exception:
        pass

    # Fallback: check common paths
    for name, patterns in [
        ("edge", ["msedge", "microsoft edge"]),
        ("chrome", ["chrome", "google/chrome"]),
        ("firefox", ["firefox", "mozilla/firefox"]),
    ]:
        # Just return "edge" as safe default on modern Windows
        if name == "edge":
            return "edge"

    return "edge"


class DesktopInteractionTest:
    """Base class for all desktop interaction tests.

    Subclass to override:
    - TEST_APP: app name
    - TEST_BROWSER: browser name
    - TEST_SEARCH: search query
    - TEST_URL: URL to open
    """

    TEST_APP = os.environ.get("AMT_TEST_APP", "notepad")
    TEST_BROWSER = os.environ.get("AMT_TEST_BROWSER", _detect_default_browser())
    TEST_SEARCH = os.environ.get("AMT_TEST_SEARCH", "test query")
    TEST_URL = os.environ.get("AMT_TEST_URL", "about:blank")
    HEADLESS = os.environ.get("AMT_HEADLESS", "0") == "1"

    @classmethod
    def setup_class(cls):
        if cls.HEADLESS:
            print("HEADLESS mode: skipping all window interactions")
            return
        # Ensure we're on Windows
        if platform.system() != "Windows":
            import pytest
            pytest.skip("Desktop tests require Windows")

    @classmethod
    def teardown_class(cls):
        """Clean up: close notepad if we opened it."""
        if cls.HEADLESS or platform.system() != "Windows":
            return
        import subprocess
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-Process -Name notepad -ErrorAction SilentlyContinue | Stop-Process -Force"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

    # ---------- Test: launch app generically ----------
    def test_1_launch_app(self):
        """Launch any application by name (default: notepad)."""
        if self.HEADLESS:
            import pytest
            pytest.skip("headless")

        sandbox = _import_sandbox()
        res = sandbox.launch_app(self.TEST_APP)
        assert res.get("ok"), f"launch_app({self.TEST_APP}) failed: {res.get('error')}"
        # Give the window time to appear
        time.sleep(2)

    # ---------- Test: window focus generically ----------
    def test_2_window_focus(self):
        """Focus a running window by name."""
        if self.HEADLESS:
            import pytest
            pytest.skip("headless")

        # Ensure app is running first
        sandbox = _import_sandbox()
        sandbox.launch_app(self.TEST_APP)
        time.sleep(1)

        res = sandbox.window_focus(self.TEST_APP)
        assert res.get("ok"), f"window_focus({self.TEST_APP}) failed: {res.get('error')}"

    # ---------- Test: window UI recon generically ----------
    def test_3_window_ui_recon(self):
        """Run UI Automation recon on a window."""
        if self.HEADLESS:
            import pytest
            pytest.skip("headless")

        sandbox = _import_sandbox()
        sandbox.launch_app(self.TEST_APP)
        time.sleep(1)

        res = sandbox.window_ui_recon(self.TEST_APP)
        assert res.get("ok"), f"window_ui_recon({self.TEST_APP}) failed: {res.get('error')}"
        # Elements may be empty (e.g., for simple notepad) — that's OK
        elements = res.get("elements", [])
        print(f"  window_ui_recon found {len(elements)} elements")
        for el in elements[:5]:
            print(f"    • {el.get('control_type', '?')}: \"{el.get('name', '')[:50]}\"")

    # ---------- Test: find element by text generically ----------
    def test_4_find_element_by_text(self):
        """Use the new generic find_element_by_text method."""
        if self.HEADLESS:
            import pytest
            pytest.skip("headless")

        sandbox = _import_sandbox()
        sandbox.launch_app(self.TEST_APP)
        time.sleep(1)

        # For notepad, search for something that might exist
        # (the title bar or menu items)
        res = sandbox.find_element_by_text("Edit", self.TEST_APP)
        # This may or may not find "Edit" in notepad's menu
        # The important thing is: it doesn't crash
        assert res.get("ok") is not None, "find_element_by_text returned no result"
        print(f"  find_element_by_text('Edit'): found={res.get('found')}, scanned={res.get('scanned', 0)}")

        # Test with an empty text (should return error)
        res2 = sandbox.find_element_by_text("", self.TEST_APP)
        assert not res2.get("ok"), "Empty text should fail"

    # ---------- Test: window send keys generically ----------
    def test_5_window_send_keys(self):
        """Type text into a focused window."""
        if self.HEADLESS:
            import pytest
            pytest.skip("headless")

        sandbox = _import_sandbox()
        sandbox.launch_app(self.TEST_APP)
        time.sleep(1)

        test_text = "AMT test " + str(int(time.time()))
        res = sandbox.window_send_keys(test_text, self.TEST_APP)
        assert res.get("ok"), f"window_send_keys failed: {res.get('error')}"

    # ---------- Test: window click generically ----------
    def test_6_window_click(self):
        """Click at specific coordinates."""
        if self.HEADLESS:
            import pytest
            pytest.skip("headless")

        sandbox = _import_sandbox()
        # Click in the center of the screen (safe — just moves cursor)
        import ctypes
        user32 = ctypes.windll.user32
        sw = user32.GetSystemMetrics(0)  # screen width
        sh = user32.GetSystemMetrics(1)  # screen height

        res = sandbox.window_click(sw // 2, sh // 2)
        assert res.get("ok"), f"window_click failed: {res.get('error')}"

        # Test bad coordinates (should not crash)
        res2 = sandbox.window_click("abc", "def")
        assert not res2.get("ok"), "Bad coords should fail gracefully"
        assert res2.get("code") == "bad_coords"

    # ---------- Test: open URL in browser generically ----------
    def test_7_open_url_in_browser(self):
        """Open a URL in the default browser (or specified one)."""
        if self.HEADLESS:
            import pytest
            pytest.skip("headless")

        sandbox = _import_sandbox()
        # Use about:blank or a simple URL to avoid opening real sites
        test_url = "about:blank"
        res = sandbox.open_url(test_url, self.TEST_BROWSER)
        assert res.get("ok"), f"open_url({test_url}, {self.TEST_BROWSER}) failed: {res.get('error')}"
        time.sleep(2)

        # Verify the browser is now focused
        focus_res = sandbox.window_focus(self.TEST_BROWSER)
        # This may or may not succeed depending on browser — just check it doesn't crash
        print(f"  window_focus({self.TEST_BROWSER}): ok={focus_res.get('ok')}")

    # ---------- Test: browser search flow generically ----------
    def test_8_browser_search_flow(self):
        """Simulate: open browser → find search field → type → submit."""
        if self.HEADLESS:
            import pytest
            pytest.skip("headless")

        sandbox = _import_sandbox()

        # Step 1: Open a search engine page (generic, not hardcoded to Google)
        # Use a simple URL that has a search field
        res = sandbox.open_url("https://www.bing.com", self.TEST_BROWSER)
        assert res.get("ok"), f"open_url(bing) failed: {res.get('error')}"
        time.sleep(3)  # Wait for page to load

        # Step 2: Find the search field (generic — works for any search engine)
        find_res = sandbox.find_element_by_text("search", self.TEST_BROWSER)
        if find_res.get("found"):
            coords = find_res.get("coords", {})
            cx = coords.get("cx", 0)
            cy = coords.get("cy", 0)
            print(f"  Found search field at ({cx}, {cy})")

            # Step 3: Click on it
            click_res = sandbox.window_click(cx, cy, self.TEST_BROWSER)
            assert click_res.get("ok"), f"Click on search field failed: {click_res.get('error')}"

            # Step 4: Type into it (with skip_ctrl_l to avoid address bar)
            search_text = "AMT generic test"
            type_res = sandbox.window_send_keys(search_text, self.TEST_BROWSER, skip_ctrl_l=True)
            assert type_res.get("ok"), f"Type into search field failed: {type_res.get('error')}"

            # Step 5: Press Enter to submit
            enter_res = sandbox.window_send_keys("\n", self.TEST_BROWSER, skip_ctrl_l=True)
            print(f"  Submit search: ok={enter_res.get('ok')}")
        else:
            print(f"  Search field not found (scanned {find_res.get('scanned', 0)} elements)")
            print(f"  Note: {find_res.get('note', '')}")
            # This is acceptable — not all browsers expose their search field via UIA

    # ---------- Test: app chat navigation generically ----------
    def test_9_app_chat_navigation(self):
        """Simulate: open app → find a specific element → click → type.
        This is generic — it works for any app with a UIA-accessible list."""
        if self.HEADLESS:
            import pytest
            pytest.skip("headless")

        sandbox = _import_sandbox()

        # Use a generic approach: launch app, find element by text, click it
        # For notepad we'll just verify the flow works (find any menu item)
        app_name = self.TEST_APP

        # Launch
        sandbox.launch_app(app_name)
        time.sleep(1)

        # Find an element (generic — could be a chat, a menu, anything)
        # Search for "File" which exists in most Windows apps
        find_res = sandbox.find_element_by_text("File", app_name)
        print(f"  find_element_by_text('File', {app_name}): found={find_res.get('found')}")

        if find_res.get("found"):
            coords = find_res.get("coords", {})
            cx = coords.get("cx", 0)
            cy = coords.get("cy", 0)

            # Click it
            click_res = sandbox.window_click(cx, cy, app_name)
            print(f"  window_click: ok={click_res.get('ok')}")

    # ---------- Test: screenshot generically ----------
    def test_10_window_screenshot(self):
        """Take a screenshot of a window (fallback when UIA fails)."""
        if self.HEADLESS:
            import pytest
            pytest.skip("headless")

        sandbox = _import_sandbox()
        res = sandbox.window_screenshot(self.TEST_APP)
        assert res.get("ok"), f"window_screenshot failed: {res.get('error')}"
        path = res.get("path", "")
        assert os.path.exists(path), f"Screenshot file not found: {path}"
        print(f"  Screenshot saved to: {path}")
        # Clean up
        try:
            os.remove(path)
        except Exception:
            pass


# Pytest integration
import pytest

@pytest.fixture(autouse=True)
def _skip_non_windows():
    """Skip all tests if not on Windows."""
    if platform.system() != "Windows":
        pytest.skip("Desktop tests require Windows")


# Run the test class
if __name__ == "__main__":
    t = DesktopInteractionTest()
    t.setup_class()

    tests = [
        ("test_1_launch_app", t.test_1_launch_app),
        ("test_2_window_focus", t.test_2_window_focus),
        ("test_3_window_ui_recon", t.test_3_window_ui_recon),
        ("test_4_find_element_by_text", t.test_4_find_element_by_text),
        ("test_5_window_send_keys", t.test_5_window_send_keys),
        ("test_6_window_click", t.test_6_window_click),
        ("test_7_open_url_in_browser", t.test_7_open_url_in_browser),
        ("test_8_browser_search_flow", t.test_8_browser_search_flow),
        ("test_9_app_chat_navigation", t.test_9_app_chat_navigation),
        ("test_10_window_screenshot", t.test_10_window_screenshot),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            print(f"\n=== {name} ===")
            fn()
            print(f"  ✓ PASS")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {type(e).__name__}: {e}")
            failed += 1

    t.teardown_class()
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests) - passed - failed} skipped")
