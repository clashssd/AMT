"""Debug UIA — simple CreateObject approach."""
import sys, os, ctypes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

user32 = ctypes.windll.user32
hwnd = user32.GetForegroundWindow()
print(f"Foreground HWND: {hwnd}")

import comtypes
from comtypes.client import CreateObject

# CLSID_CUIAutomation
CLSID_CUIAutomation = comtypes.GUID("{4780B56D-11B2-4A99-9E2F-4581F9E10B08}")
uia_obj = CreateObject(CLSID_CUIAutomation)
print(f"UIA object: {uia_obj}")

elem = uia_obj.ElementFromHandle(hwnd)
print(f"Element from handle: {elem}")
if elem:
    print(f"  Name: {elem.GetCurrentName()}")
    print(f"  ClassName: {elem.GetCurrentClassName()}")
    
    walker = uia_obj.GetRawViewWalker()
    print(f"  Walker: {walker}")
    
    child = walker.GetFirstChildElement(elem)
    print(f"  First child: {child}")
    count = 0
    while child and count < 20:
        try:
            print(f"    Child {count}: {child.GetCurrentName()} [{child.GetCurrentClassName()}]")
        except:
            pass
        count += 1
        child = walker.GetNextSiblingElement(child)
    print(f"  Total children found: {count}")
