path = "C:/Users/berds/Desktop/AMT/backend/main.py"
lines = open(path, encoding="utf-8").readlines()

target_idx = None
for i, line in enumerate(lines):
    if "Убираем" in line and "task_spec" in line:
        target_idx = i
        break

assert target_idx is not None, "Could not find task_spec cleanup line"

# The insert block - written as a single string with explicit \n
block = (
    '\n'
    '    # [[SYS:find_element_by_text|<text>|<app>?]] - generic UIA element finder by text\n'
    '    while True:\n'
    '        m = SYS_FIND_ELEMENT_RE.search(out)\n'
    '        if not m:\n'
    '            break\n'
    '        text = (m.group(1) or "").strip()\n'
    '        app = (m.group(2) or "").strip()\n'
    '        try:\n'
    '            res = tools_sandbox.execute("find_element_by_text", text=text, app=app)\n'
    '            if res.get("ok") and res.get("found"):\n'
    '                coords = res.get("coords", {})\n'
    '                el = res.get("element", {})\n'
    '                cx = coords.get("cx", 0)\n'
    '                cy = coords.get("cy", 0)\n'
    '                res_text = (\n'
    '                    "[Found element: " + el.get("name", "")[:80] + "\n'
    '                    " (type: " + el.get("control_type", "?") + ") "\n'
    '                    + "coords: (" + str(cx) + ", " + str(cy) + ")]\\n"\n'
    '                    + "[[SYS:window_click|" + str(cx) + "|" + str(cy) + "|" + app + "]]"\n'
    '                )\n'
    '                log_chat_event("SYS_FIND_ELEMENT_DONE", {"text": text[:50], "app": app, "status": "found"})\n'
    '            elif res.get("ok"):\n'
    '                res_text = "[Element not found: " + text + ". " + res.get("note", "") + "]"\n'
    '                log_chat_event("SYS_FIND_ELEMENT_DONE", {"text": text[:50], "app": app, "status": "not_found"})\n'
    '            else:\n'
    '                res_text = "[Error: " + res.get("error", "could not find element") + "]"\n'
    '                log_chat_event("SYS_FIND_ELEMENT_DONE", {"text": text[:50], "app": app, "status": "error"})\n'
    '        except Exception as e:\n'
    '            res_text = "[Error finding element: " + str(e) + "]"\n'
    '            log_chat_event("SYS_FIND_ELEMENT_DONE", {"text": text[:50], "app": app, "status": "exception"})\n'
    '        out = out[:m.start()] + res_text + out[m.end():]\n'
    '\n'
)

new_lines = lines[:target_idx] + [block] + lines[target_idx:]
open(path, "w", encoding="utf-8").writelines(new_lines)
print(f"Inserted find_element_by_text block before line {target_idx + 1}")
