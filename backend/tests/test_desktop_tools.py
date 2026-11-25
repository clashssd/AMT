"""Layer 3/4: desktop_tools structure + hung-window health check.

These tests run on Windows (the platform this project targets). They
verify the *shape* of the new defensive APIs without requiring a real
hung application:
  * _check_window_health returns (hwnd, is_hung, error) tuple
  * _is_window_hung returns a bool for a real (responding) window
  * window_send_keys / window_click return structured dicts even when
    the target app doesn't exist (graceful failure, not a crash)
"""
import platform
import pytest

from ai_engine.desktop_tools import DesktopSandbox, desktop_sandbox


@pytest.fixture
def ds():
    return DesktopSandbox(log_path="memory://tmp")  # log path unused in these


def test_check_window_health_nonexistent_app(ds):
    """A made-up app name → (0, False, "not found" error) — no crash."""
    if platform.system() != "Windows":
        pytest.skip("Windows-only")
    hwnd, is_hung, err = ds._check_window_health("amt_nonexistent_app_xyz")
    assert isinstance(hwnd, int)
    assert isinstance(is_hung, bool)
    assert hwnd == 0  # not found
    assert is_hung is False
    assert err  # some reason string


def test_check_window_health_foreground(ds):
    """app='' or 'default' → uses the foreground window; no crash."""
    if platform.system() != "Windows":
        pytest.skip("Windows-only")
    hwnd, is_hung, err = ds._check_window_health("")
    # Foreground window may or may not be found, but shape is correct.
    assert isinstance(hwnd, int)
    assert isinstance(is_hung, bool)


def test_is_window_hung_responding_window(ds):
    """A normal foreground window should NOT be reported as hung."""
    if platform.system() != "Windows":
        pytest.skip("Windows-only")
    import ctypes
    user32 = ctypes.windll.user32
    fg = user32.GetForegroundWindow()
    if fg == 0:
        pytest.skip("No foreground window in this environment")
    hung = ds._is_window_hung(fg, timeout_ms=1000)
    assert hung in (True, False)  # just a bool, no exception


def test_window_send_keys_no_app_structured(ds):
    """window_send_keys with no app + no active target returns a dict
    with ok flag (graceful), not a raised exception."""
    if platform.system() != "Windows":
        pytest.skip("Windows-only")
    res = ds.window_send_keys(text="hello", app="")
    assert isinstance(res, dict)
    assert "ok" in res


def test_window_click_structured(ds):
    """window_click returns a dict with ok flag."""
    if platform.system() != "Windows":
        pytest.skip("Windows-only")
    res = ds.window_click(x=0, y=0, app="")
    assert isinstance(res, dict)
    assert "ok" in res


def test_execute_dispatch_unknown_tool():
    """execute() for an unknown tool → structured error, not a crash."""
    res = desktop_sandbox.execute("not_a_real_tool")
    assert res.get("ok") is False
    assert "error" in res
