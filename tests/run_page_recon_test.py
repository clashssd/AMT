import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
os.environ["AMT_HEADLESS"] = "0"
from ai_engine.desktop_tools import DesktopSandbox
s = DesktopSandbox()

# page_recon on Google
r = s.page_recon("https://www.google.com")
print(f"Google: ok={r.get('ok')}, title={r.get('title','')[:50]}, elements={len(r.get('elements',[]))}")
for el in r.get("elements", []):
    print(f"  {el.get('tag','?')}: id={el.get('id','')}, name={el.get('name','')}, placeholder={el.get('placeholder','')}")

# find_element_by_text with URL fallback
print(f"\nfind_element_by_text('q', '', url='https://www.google.com')")
r2 = s.find_element_by_text("q", "", url="https://www.google.com")
print(f"  found={r2.get('found')}")
if r2.get("found"):
    el = r2.get("element", {})
    print(f"  element: name={el.get('name','')}, id={el.get('id','')}, source={el.get('source','')}")
    print(f"  note: {r2.get('note','')[:150]}")
else:
    print(f"  error: {r2.get('error','')}")

# Also try DuckDuckGo
print(f"\nfind_element_by_text('search', '', url='https://duckduckgo.com')")
r3 = s.find_element_by_text("search", "", url="https://duckduckgo.com")
print(f"  found={r3.get('found')}")
if r3.get("found"):
    el = r3.get("element", {})
    print(f"  element: name={el.get('name','')}, id={el.get('id','')}, source={el.get('source','')}")
else:
    print(f"  error: {r3.get('error','')}")
