"""Check if find_element_by_text + window_click + window_send_keys(skip_ctrl_l=True)
actually types into the browser's search field.

This is a real end-to-end test: open Bing, find search field, click it,
type text, submit. Only 1 browser instance.
"""
import sys, os, time

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")).replace("\\", "/")
sys.path.insert(0, _backend_dir)
os.environ["AMT_HEADLESS"] = "0"

from ai_engine.desktop_tools import DesktopSandbox

sandbox = DesktopSandbox()

# Detect browser
browser = sandbox._get_default_browser() or "edge"
print(f"Browser: {browser}")

# Step 1: Open Bing
print(f"\n=== Step 1: Open https://www.bing.com in {browser} ===")
res = sandbox.open_url("https://www.bing.com", browser)
print(f"  ok={res.get('ok')}, browser={res.get('browser')}")
time.sleep(4)  # Wait for page to load

# Step 2: Try find_element_by_text for search field
print(f"\n=== Step 2: find_element_by_text('search', {browser}) ===")
res = sandbox.find_element_by_text("search", browser)
print(f"  found={res.get('found')}, scanned={res.get('scanned', 0)}")
if res.get("found"):
    el = res.get("element", {})
    coords = res.get("coords", {})
    print(f"  element: \"{el.get('name', '')[:60]}\" ({el.get('control_type')})")
    print(f"  coords: ({coords.get('cx', 0)}, {coords.get('cy', 0)})")
else:
    print(f"  NOT FOUND: {res.get('note', '')}")
    # Fallback: use window_ui_recon to see what's available
    print(f"\n=== Step 2b: window_ui_recon({browser}) ===")
    recon = sandbox.window_ui_recon(browser)
    els = recon.get("elements", [])
    print(f"  {len(els)} elements")
    for el in els[:15]:
        print(f"    {el.get('control_type', '?')}: \"{el.get('name', '')[:60]}\"")

# Step 3: Try page_recon (HTTP-based, works for any site)
print(f"\n=== Step 3: page_recon(https://www.bing.com) ===")
res = sandbox.page_recon("https://www.bing.com")
print(f"  ok={res.get('ok')}, title={res.get('title', '')[:50]}")
elements = res.get("elements", [])
print(f"  {len(elements)} elements")
for el in elements[:10]:
    print(f"    {el.get('tag', '?')}: id={el.get('id', '')}, name={el.get('name', '')}, placeholder={el.get('placeholder', '')}")

# Step 4: Try the full flow: find search input via page_recon, click, type
if elements:
    # Look for an input with "search" in its name/id/placeholder
    search_input = None
    for el in elements:
        tag = el.get("tag", "").lower()
        if tag == "input":
            name_val = (el.get("name", "") + el.get("id", "") + el.get("placeholder", "")).lower()
            if "search" in name_val or "q" in name_val:
                search_input = el
                break

    if search_input:
        print(f"\n=== Step 4: Found search input: {search_input} ===")
        print("  (To click it, we need its coordinates from window_ui_recon,")
        print("   which requires the browser window to expose UIA elements.)")
    else:
        print("\n=== Step 4: No search input found in page_recon ===")

# Step 5: Test the actual typing — use window_send_keys with skip_ctrl_l=True
# This types into the CURRENTLY FOCUSED element.
# First, let's try Ctrl+L (address bar) then type a search URL
print(f"\n=== Step 5: Test window_send_keys(skip_ctrl_l=False) — address bar ===")
res = sandbox.window_send_keys("https://www.bing.com/search?q=AMT+test", browser, skip_ctrl_l=False)
print(f"  ok={res.get('ok')}, error={res.get('error', '')}")
time.sleep(3)

# Step 6: Screenshot to verify
print(f"\n=== Step 6: Screenshot ===")
res = sandbox.window_screenshot(browser)
if res.get("ok"):
    print(f"  Screenshot: {res.get('path', '')}")

print("\nDone.")
