"""Test window_ui_recon with a real window."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from ai_engine.desktop_tools import desktop_sandbox

# Get foreground window
import ctypes
user32 = ctypes.windll.user32
hwnd = user32.GetForegroundWindow()
print(f"Foreground HWND: {hwnd}")

result = desktop_sandbox.window_ui_recon("")
print(f"OK: {result.get('ok')}")
print(f"Elements: {len(result.get('elements', []))}")
for el in result.get("elements", [])[:10]:
    print(f"  {el}")
