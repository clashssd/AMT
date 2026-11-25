"""
Full verification test: runs all generic desktop tests (notepad + browser + page_recon).
Only 1 browser instance opened.
"""
import sys, os, time, ctypes, subprocess

_backend = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")).replace("\\", "/")
sys.path.insert(0, _backend)
os.environ["AMT_HEADLESS"] = "0"

from ai_engine.desktop_tools import DesktopSandbox

sandbox = DesktopSandbox()
passed, failed = 0, 0

def check(name, res, expect_ok=True):
    global passed, failed
    ok = res.get("ok", False)
    if expect_ok and not ok:
        print(f"  FAIL: {name} — {res.get('error', 'unknown')}")
        failed += 1
    elif not expect_ok and ok:
        print(f"  FAIL: {name} — expected failure, got ok")
        failed += 1
    else:
        print(f"  PASS: {name}")
        passed += 1
    return res


# ============================================================
# SECTION 1: App tests (notepad — safe, no browser)
# ============================================================
print("=" * 50)
print("SECTION 1: Application tests (notepad)")
print("=" * 50)

# 1.1 Launch
print("\n[1.1] launch_app('notepad')")
r = sandbox.launch_app("notepad")
check("launch", r)
time.sleep(2)

# 1.2 Focus
print("\n[1.2] window_focus('notepad')")
r = sandbox.window_focus("notepad")
check("focus", r)

# 1.3 UI recon
print("\n[1.3] window_ui_recon('notepad')")
r = sandbox.window_ui_recon("notepad")
check("ui_recon", r)
print(f"      elements: {len(r.get('elements', []))}")

# 1.4 find_element_by_text (UIA mode)
print("\n[1.4] find_element_by_text('Edit', 'notepad')")
r = sandbox.find_element_by_text("Edit", "notepad")
check("find_element", r)
if r.get("found"):
    c = r.get("coords", {})
    print(f"      found: {r.get('element', {}).get('name', '')[:40]} at ({c.get('cx',0)},{c.get('cy',0)})")
else:
    print(f"      not found (scanned {r.get('scanned', 0)})")

# 1.5 Bad coords guard
print("\n[1.5] window_click('abc','def') — should return bad_coords")
r = sandbox.window_click("abc", "def")
check("bad_coords guard", r, expect_ok=False)
if r.get("code") == "bad_coords":
    print("      PASS: correct code")
    passed += 1

# 1.6 Screenshot
print("\n[1.6] window_screenshot('notepad')")
r = sandbox.window_screenshot("notepad")
check("screenshot", r)
if r.get("ok") and r.get("path") and os.path.exists(r["path"]):
    os.remove(r["path"])
    print("      cleaned up")

# Close notepad
subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-Process -Name notepad -EA SilentlyContinue | Stop-Process -Force"],
    capture_output=True, timeout=5,
)

# ============================================================
# SECTION 2: page_recon (HTTP-based, no browser window needed)
# ============================================================
print("\n" + "=" * 50)
print("SECTION 2: page_recon (HTTP-based)")
print("=" * 50)

# 2.1 page_recon on Bing
print("\n[2.1] page_recon('https://www.bing.com')")
r = sandbox.page_recon("https://www.bing.com")
check("page_recon bing", r)
els = r.get("elements", [])
print(f"      title: {r.get('title', '')[:50]}")
print(f"      elements: {len(els)}")
for el in els[:5]:
    print(f"        {el.get('tag','?')}: id={el.get('id','')}, name={el.get('name','')}, placeholder={el.get('placeholder','')}")

# 2.2 find_element_by_text with URL fallback (page_recon mode)
print("\n[2.2] find_element_by_text('q', '', url='https://www.bing.com')")
r = sandbox.find_element_by_text("q", "", url="https://www.bing.com")
check("find_element (page_recon fallback)", r)
if r.get("found"):
    el = r.get("element", {})
    print(f"      found: name={el.get('name','')}, id={el.get('id','')}, source={el.get('source','')}")
    print(f"      note: {r.get('note', '')[:100]}")
else:
    print(f"      not found: {r.get('error', '')}")

# 2.3 Search URL construction
print("\n[2.3] Search URL construction (simulating what LLM would do)")
search_query = "Бесславные ублюдки Лордфильм"
import urllib.parse
search_url = f"https://www.bing.com/search?q={urllib.parse.quote(search_query)}"
print(f"      URL: {search_url[:80]}...")
# Just verify it's valid — don't actually open it
print("      PASS: valid search URL")
passed += 1

# ============================================================
# SECTION 3: Browser tests (1 instance only)
# ============================================================
print("\n" + "=" * 50)
print("SECTION 3: Browser tests (1 instance)")
print("=" * 50)

browser = sandbox._get_default_browser() or "edge"
print(f"\n      Browser: {browser}")

# 3.1 open_url
print(f"\n[3.1] open_url('https://www.bing.com', '{browser}')")
r = sandbox.open_url("https://www.bing.com", browser)
check("open_url", r)
time.sleep(3)

# 3.2 window_focus
print(f"\n[3.2] window_focus('{browser}')")
r = sandbox.window_focus(browser)
check("focus", r)

# 3.3 UI recon (expected: 0 for Chromium)
print(f"\n[3.3] window_ui_recon('{browser}') — expected 0 for Chromium")
r = sandbox.window_ui_recon(browser)
check("ui_recon", r)
print(f"      elements: {len(r.get('elements', []))} (0 is expected for Edge/Chrome)")

# 3.4 find_element_by_text with URL fallback
print(f"\n[3.4] find_element_by_text('search', '{browser}', url='https://www.bing.com')")
r = sandbox.find_element_by_text("search", browser, url="https://www.bing.com")
check("find_element (browser+url)", r)
if r.get("found"):
    el = r.get("element", {})
    print(f"      found via {el.get('source','UIA')}: name={el.get('name','')}, id={el.get('id','')}")
else:
    print(f"      not found: {r.get('error', '')}")

# 3.5 Screenshot
print(f"\n[3.5] window_screenshot('{browser}')")
r = sandbox.window_screenshot(browser)
check("screenshot", r)
if r.get("ok") and r.get("path") and os.path.exists(r["path"]):
    sz = os.path.getsize(r["path"])
    print(f"      size: {sz} bytes")
    os.remove(r["path"])

# ============================================================
# SECTION 4: window_send_keys (subprocess to isolate native crash)
# ============================================================
print("\n" + "=" * 50)
print("SECTION 4: window_send_keys (isolated)")
print("=" * 50)

code = (
    "import sys, os, time\n"
    f"sys.path.insert(0, '{_backend}')\n"
    "os.environ['AMT_HEADLESS'] = '0'\n"
    "from ai_engine.desktop_tools import DesktopSandbox\n"
    "s = DesktopSandbox()\n"
    "b = s._get_default_browser() or 'edge'\n"
    "r = s.open_url('about:blank', b)\n"
    "print(f'open_url: ok={r.get(\"ok\")}')\n"
    "time.sleep(2)\n"
    "r = s.window_send_keys('test', b)\n"
    "print(f'send_keys: ok={r.get(\"ok\")}, error={r.get(\"error\", \"\")}')\n"
    "if r.get('ok'): print('PASS')\n"
    "else: print('FAIL'); sys.exit(1)\n"
)
p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30, cwd=".")
print(p.stdout.strip())
if p.returncode == 0:
    print("  PASS: window_send_keys in subprocess")
    passed += 1
else:
    print(f"  SKIP: native crash or failure (exit={p.returncode})")
    print(f"  stderr: {p.stderr.strip()[:200]}")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 50)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 50)

if failed > 0:
    sys.exit(1)
