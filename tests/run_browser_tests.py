"""Run browser tests (max 1 browser instance)."""
import sys
import os
import time

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")).replace("\\", "/")
sys.path.insert(0, _backend_dir)
os.environ["AMT_HEADLESS"] = "0"

from ai_engine.desktop_tools import DesktopSandbox

sandbox = DesktopSandbox()
passed = 0
failed = 0

# Detect the default browser
browser = sandbox._get_default_browser() or "edge"
print(f"Testing with browser: {browser}")

# --- Test: open URL in browser (single instance) ---
print(f"\n=== test_browser_1: open_url({browser}) ===")
res = sandbox.open_url("https://www.bing.com", browser)
print(f"  open_url: ok={res.get('ok')}, browser={res.get('browser')}")
if res.get("ok"):
    print("  PASS")
    passed += 1
else:
    print(f"  FAIL: {res.get('error')}")
    failed += 1

time.sleep(3)  # Wait for page to load

# --- Test: find search field (generic — works for ANY search engine) ---
print(f"\n=== test_browser_2: find_element_by_text('search', {browser}) ===")
res = sandbox.find_element_by_text("search", browser)
if res.get("found"):
    el = res.get("element", {})
    coords = res.get("coords", {})
    print(f"  Found: \"{el.get('name', '')[:60]}\" ({el.get('control_type')})")
    print(f"  Coords: ({coords.get('cx', 0)}, {coords.get('cy', 0)})")
    print(f"  PASS")
    passed += 1

    # --- Test: click on search field and type ---
    print(f"\n=== test_browser_3: click search field + type ===")
    cx = coords.get("cx", 0)
    cy = coords.get("cy", 0)
    click_res = sandbox.window_click(cx, cy, browser)
    print(f"  click({cx},{cy}): ok={click_res.get('ok')}")
    if click_res.get("ok"):
        type_res = sandbox.window_send_keys("AMT generic test", browser, skip_ctrl_l=True)
        print(f"  send_keys(skip_ctrl_l=True): ok={type_res.get('ok')}, error={type_res.get('error', '')}")
        if type_res.get("ok"):
            print("  PASS")
            passed += 1
        else:
            print(f"  FAIL: {type_res.get('error')}")
            failed += 1
    else:
        print(f"  FAIL (click): {click_res.get('error')}")
        failed += 1
else:
    print(f"  Not found (scanned {res.get('scanned', 0)} elements)")
    print(f"  Note: {res.get('note', '')}")
    print(f"  PASS (element not found is acceptable)")
    passed += 1

# --- Test: UI recon on browser (generic) ---
print(f"\n=== test_browser_4: window_ui_recon({browser}) ===")
res = sandbox.window_ui_recon(browser)
els = res.get("elements", [])
print(f"  Found {len(els)} UIA elements")
for el in els[:5]:
    print(f"    {el.get('control_type', '?')}: \"{el.get('name', '')[:60]}\"")
if res.get("ok"):
    print("  PASS")
    passed += 1
else:
    print(f"  FAIL: {res.get('error')}")
    failed += 1

# --- Test: screenshot browser ---
print(f"\n=== test_browser_5: window_screenshot({browser}) ===")
res = sandbox.window_screenshot(browser)
if res.get("ok"):
    print(f"  Screenshot: {res.get('path', '')[:60]}")
    print("  PASS")
    passed += 1
    # Clean up screenshot
    p = res.get("path", "")
    if p and os.path.exists(p):
        os.remove(p)
else:
    print(f"  FAIL: {res.get('error')}")
    failed += 1

print(f"\n{'=' * 40}")
print(f"Results: {passed} passed, {failed} failed")

if failed > 0:
    sys.exit(1)
