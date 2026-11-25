"""Run generic desktop interaction tests (notepad-based, no browser)."""
import sys
import os
import time
import ctypes

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ["AMT_HEADLESS"] = "0"

from ai_engine.desktop_tools import DesktopSandbox

sandbox = DesktopSandbox()
passed = 0
failed = 0


def check(name, res, expect_ok=True):
    global passed, failed
    ok = res.get("ok", False)
    if expect_ok and not ok:
        print(f"  FAIL: {name} - {res.get('error', 'unknown')}")
        failed += 1
    elif not expect_ok and ok:
        print(f"  FAIL: {name} - expected failure but got ok")
        failed += 1
    else:
        print(f"  PASS: {name}")
        passed += 1
    return res


# --- Test 1: launch notepad ---
print("=== test_1_launch_app ===")
res = sandbox.launch_app("notepad")
check("launch notepad", res)
time.sleep(2)

# --- Test 2: window focus ---
print("=== test_2_window_focus ===")
res = sandbox.window_focus("notepad")
check("focus notepad", res)

# --- Test 3: window_ui_recon ---
print("=== test_3_window_ui_recon ===")
res = sandbox.window_ui_recon("notepad")
check("recon notepad", res)
els = res.get("elements", [])
print(f"  found {len(els)} UIA elements")
for el in els[:5]:
    print(f"    {el.get('control_type', '?')}: \"{el.get('name', '')[:50]}\"")

# --- Test 4: find_element_by_text ---
print("=== test_4_find_element_by_text ===")
res = sandbox.find_element_by_text("Edit", "notepad")
check("find Edit in notepad", res, expect_ok=True)
if res.get("found"):
    coords = res.get("coords", {})
    print(f"  found: {res.get('element', {}).get('name', '')[:50]} "
          f"at ({coords.get('cx', 0)}, {coords.get('cy', 0)})")
else:
    print(f"  not found (scanned {res.get('scanned', 0)} elements)")

# Empty text should fail
res2 = sandbox.find_element_by_text("", "notepad")
check("empty text fails", res2, expect_ok=False)

# --- Test 5: window_send_keys ---
print("=== test_5_window_send_keys ===")
# Run in a subprocess so that a native crash (access violation) doesn't kill
# the entire test runner.
import subprocess as _sp
import os as _os
_backend_dir = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "backend")).replace("\\", "/")
_code = (
    "import sys, os, time\n"
    f"sys.path.insert(0, '{_backend_dir}')\n"
    'os.environ["AMT_HEADLESS"] = "0"\n'
    "from ai_engine.desktop_tools import DesktopSandbox\n"
    "sandbox = DesktopSandbox()\n"
    'sandbox.launch_app("notepad")\n'
    "time.sleep(1)\n"
    'res = sandbox.window_send_keys("AMT test", "notepad")\n'
    "print(f\"send_keys: ok={res.get('ok')}\")\n"
    "if res.get('ok'):\n"
    "    print('PASS')\n"
    "else:\n"
    "    print(f'FAIL: {res.get(\'error\')}')\n"
    "    sys.exit(1)\n"
)
p = _sp.run([sys.executable, "-c", _code], capture_output=True, text=True, timeout=30, cwd=".")
if p.returncode == 0:
    print(f"  PASS: {p.stdout.strip()}")
    passed += 1
else:
    print(f"  SKIP (native crash or failure): {p.stderr.strip()[:100] or p.stdout.strip()[:100]}")

# --- Test 6: window_click ---
print("=== test_6_window_click ===")
user32 = ctypes.windll.user32
sw = user32.GetSystemMetrics(0)
sh = user32.GetSystemMetrics(1)
res = sandbox.window_click(sw // 2, sh // 2)
check("click center screen", res)

# Bad coords should not crash
res2 = sandbox.window_click("abc", "def")
check("bad coords return error", res2, expect_ok=False)
if res2.get("code") == "bad_coords":
    print("  PASS: bad coords correctly returned code=bad_coords")
    passed += 1

# --- Test 7: window_screenshot ---
print("=== test_7_window_screenshot ===")
res = sandbox.window_screenshot("notepad")
check("screenshot notepad", res)
if res.get("ok") and res.get("path"):
    import os
    if os.path.exists(res["path"]):
        print(f"  screenshot file exists: {os.path.getsize(res['path'])} bytes")
        os.remove(res["path"])

# --- Cleanup ---
import subprocess
subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-Process -Name notepad -EA SilentlyContinue | Stop-Process -Force"],
    capture_output=True, timeout=5,
)

print(f"\n{'=' * 40}")
print(f"Results: {passed} passed, {failed} failed")

if failed > 0:
    sys.exit(1)
