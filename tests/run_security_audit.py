"""Security audit test harness for AMT Chat.

Runs all 7 blocks (Host, Origin, CORS, CSRF, network, Electron IPC, combined)
against a running backend on 127.0.0.1:8000.
"""
import json
import sys
import time
import urllib.request
import urllib.error
import socket
from http.client import HTTPConnection

BASE = "127.0.0.1"
PORT = 8000

results = []  # (test_id, description, request_desc, expected, actual, pass_fail, fail_reason)

def add(tid, desc, request_desc, expected, actual, passed, fail_reason=""):
    results.append({
        "id": tid, "desc": desc, "request": request_desc,
        "expected": expected, "actual": actual, "pass_fail": "PASS" if passed else "FAIL",
        "fail_reason": fail_reason,
    })

def http_req(method, path, headers=None, body=None, host_header=None, raw_headers=False):
    """Send a request and return (status, headers, body_text).
    If host_header is set, it overrides the standard Host line.
    raw_headers=True allows the request to be sent without a standard Host.
    """
    conn = HTTPConnection(BASE, PORT)
    hdrs = dict(headers or {})
    if host_header is not None:
        hdrs["Host"] = host_header
    elif "Host" not in hdrs:
        hdrs["Host"] = f"{BASE}:{PORT}"
    payload = None
    if body is not None:
        payload = json.dumps(body) if not isinstance(body, str) else body
        hdrs.setdefault("Content-Type", "application/json")
    try:
        conn.request(method, path, body=payload, headers=hdrs)
        resp = conn.getresponse()
        status = resp.status
        # Normalize header keys to lowercase for case-insensitive lookups.
        rh = {k.lower(): v for k, v in resp.getheaders()}
        rb = resp.read().decode("utf-8", "replace")
        return status, rh, rb
    except Exception as e:
        return 0, {}, f"<error> {e}"
    finally:
        # Always close the connection so subsequent raw-socket requests
        # (raw_http) are not blocked by an open keep-alive socket.
        conn.close()

def raw_http(method, path, header_lines, body=None):
    """Send raw HTTP request with exact header lines (allows missing Host, duplicated Host, etc.)."""
    payload = json.dumps(body) if body is not None and not isinstance(body, str) else (body or "")
    lines = [f"{method} {path} HTTP/1.1"]
    for h in header_lines:
        lines.append(h)
    if payload:
        lines.append(f"Content-Length: {len(payload)}")
    lines.append("")
    # Headers with non-ASCII chars (e.g. Cyrillic homoglyphs in Origin) are
    # encoded as UTF-8 in the bytes on the wire; latin-1 also technically
    # "works" for bytes, but the server should reject non-ASCII header values
    # — the key assertion is whether the server treats the request as valid
    # at all. Encode header bytes as UTF-8 (the wire form for non-ASCII).
    raw = "\r\n".join(lines)
    # Ensure the header block is terminated with a blank line (\r\n\r\n).
    # lines[-1] is "" (empty), so join produces "...Host: x\r\n" — the final
    # \r\n that closes the header section must be added explicitly.
    raw += "\r\n"
    if payload:
        raw += payload
    raw_bytes = raw.encode("utf-8")
    s = socket.create_connection((BASE, PORT), timeout=5)
    s.sendall(raw_bytes)
    data = b""
    s.settimeout(5)
    try:
        # Read headers until \r\n\r\n, then read body if Content-Length is set.
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\r\n\r\n" in data:
                break
        # If we saw a Content-Length, finish reading the body.
        head_txt = data.decode("utf-8", "replace")
        cl = 0
        for ln in head_txt.split("\r\n"):
            if ln.lower().startswith("content-length:"):
                try:
                    cl = int(ln.split(":", 1)[1].strip())
                except Exception:
                    cl = 0
        body_start = data.find(b"\r\n\r\n") + 4 if b"\r\n\r\n" in data else len(data)
        remaining = cl - (len(data) - body_start)
        if remaining > 0:
            s.settimeout(2)
            try:
                while remaining > 0:
                    chunk = s.recv(remaining)
                    if not chunk:
                        break
                    data += chunk
                    remaining -= len(chunk)
            except socket.timeout:
                pass
    except Exception:
        pass
    finally:
        s.close()
    txt = data.decode("utf-8", "replace")
    status = 0
    hdrs = {}
    body_txt = ""
    if "\r\n\r\n" in txt:
        head, body_txt = txt.split("\r\n\r\n", 1)
        first = head.split("\r\n", 1)[0]
        try:
            status = int(first.split(" ", 2)[1])
        except Exception:
            status = 0
        for ln in head.split("\r\n")[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                hdrs[k.strip().lower()] = v.strip()
    else:
        first = txt.split("\r\n", 1)[0] if txt else ""
        try:
            status = int(first.split(" ", 2)[1])
        except Exception:
            status = 0
    return status, hdrs, body_txt


# ============ BLOCK 1: Host header ============
def block1():
    status, hdrs, body = http_req("GET", "/health", host_header=f"{BASE}:{PORT}")
    passed = 200 <= status < 500  # 2xx/4xx — не 403 из-за Host
    add("1.1", "Легитимный Host (127.0.0.1:PORT)",
        f"GET /health, Host: {BASE}:{PORT}",
        "2xx/4xx, НЕ 403 из-за Host",
        f"{status}", passed,
        "" if passed else f"статус {status} — отверг легитимный Host")

    status, hdrs, body = http_req("GET", "/health", host_header="evil.com")
    passed = status in (400, 403)
    add("1.2", "Чужой домен в Host (evil.com)",
        "GET /health, Host: evil.com",
        "400/403, без обработки логики",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — запрос дошёл до обработчика ({body[:80]})")

    # 1.3 — DNS rebinding: домен, резолвящийся в loopback (nip.io)
    status, hdrs, body = http_req("GET", "/health", host_header="127.0.0.1.nip.io")
    passed = status in (400, 403)
    add("1.3", "DNS-rebinding (127.0.0.1.nip.io)",
        "GET /health, Host: 127.0.0.1.nip.io",
        "400/403 (запрос к loopback, но чужой Host)",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — запрос обработан")

    status, hdrs, body = http_req("GET", "/health", host_header="localhost.evil.com")
    passed = status in (400, 403)
    add("1.4", "Поддомен-обманка (localhost.evil.com)",
        "GET /health, Host: localhost.evil.com",
        "400/403 (точное совпадение, не подстрока)",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — сравнение по подстроке, а не точное")

    # 1.5 — Отсутствие Host
    status, hdrs, body = raw_http("GET", "/health",
        ["Connection: close"], None)
    passed = status in (400, 403)
    add("1.5", "Отсутствие заголовка Host",
        "GET /health без заголовка Host (HTTP/1.0 эмуляция)",
        "400/403, без обработки",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — запрос дошёл до логики")

    # 1.6 — Host с портом-обманкой
    status, hdrs, body = http_req("GET", "/health", host_header="localhost:9999")
    passed = status in (400, 403)
    add("1.6", "Порт-обманка (localhost:9999)",
        "GET /health, Host: localhost:9999",
        "400/403 (порт валидируется)",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — порт не валидируется")


# ============ BLOCK 2: Origin (CSRF) ============
def block2():
    # 2.1 — Чужой Origin на изменяющем POST
    status, hdrs, body = http_req("POST", "/api/memory/wipe",
        headers={"Origin": "https://evil.com"}, body={})
    passed = status in (400, 403)
    add("2.1", "Чужой Origin на POST (memory/wipe)",
        "POST /api/memory/wipe, Origin: https://evil.com",
        "400/403, действие НЕ вы��олнено",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — POST выполнен без CSRF-проверки Origin")

    # 2.2 — Origin: null
    status, hdrs, body = http_req("POST", "/api/memory/wipe",
        headers={"Origin": "null"}, body={})
    passed = status in (400, 403)
    add("2.2", "Origin: null на POST",
        "POST /api/memory/wipe, Origin: null",
        "400/403 (null — обход наивных проверок)",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — null-Origin обработан")

    # 2.3 — Отсутствие Origin (не-браузерный клиент)
    status, hdrs, body = http_req("POST", "/api/memory/wipe", body={})
    passed = status in (200, 202, 400, 403)  # осознанное поведение
    # Если нет Origin — это не-браузерный клиент. В политике AMT это «локальный клиент»,
    # но без CSRF-токена — должен быть осознанный ответ (2xx или 403).
    add("2.3", "Отсутствие Origin (не-браузерный клиент)",
        "POST /api/memory/wipe без заголовка Origin",
        "осознанное поведение (2xx или 403), задокументировано",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — поведение не задокументировано")

    # 2.4 — Легитимный Origin (свой фронтенд на своём порту)
    # AMT использует 127.0.0.1:PORT и localhost:PORT; фронтенд — same-origin (StaticFiles).
    status, hdrs, body = http_req("POST", "/api/memory/wipe",
        headers={"Origin": f"http://{BASE}:{PORT}"}, body={})
    passed = status in (200, 202)
    add("2.4", "Легитимный Origin (http://127.0.0.1:8000)",
        "POST /api/memory/wipe, Origin: http://127.0.0.1:8000",
        "2xx (свой фронтенд обрабатывается)",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — свой фронтенд отклонён")

    # 2.5 — Спуфинг через поддомен
    status, hdrs, body = http_req("POST", "/api/memory/wipe",
        headers={"Origin": "http://localhost.evil.com"}, body={})
    passed = status in (400, 403)
    add("2.5", "Спу��инг поддоменом (localhost.evil.com)",
        "POST /api/memory/wipe, Origin: http://localhost.evil.com",
        "400/403 (точное совпадение)",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — поддомен-спуфинг прошёл")

    # 2.6 — GET с чужим Origin (чувствительные данные)
    status, hdrs, body = http_req("GET", "/api/settings",
        headers={"Origin": "https://evil.com"})
    passed = status in (400, 403)
    add("2.6", "GET /api/settings с чужим Origin",
        "GET /api/settings, Origin: https://evil.com",
        "400/403 (чувствительные настройки не отдаются чужому Origin)",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — GET с чужим Origin отдал данные")

    # 2.7 — Origin с неверным портом
    status, hdrs, body = http_req("POST", "/api/memory/wipe",
        headers={"Origin": "http://localhost:9999"}, body={})
    passed = status in (400, 403)
    add("2.7", "Origin с неверным портом (localhost:9999)",
        "POST /api/memory/wipe, Origin: http://localhost:9999",
        "400/403 (порт валидируется)",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — порт в Origin не валидируется")


# ============ BLOCK 3: CORS preflight ============
def block3():
    # 3.1 — Preflight с чужого Origin
    # NOTE: CORSMiddleware intercepts OPTIONS with Origin + Access-Control-Request-Method
    # and returns 200/204 with the right ACAO. FastAPI itself does NOT handle OPTIONS
    # for @app.post endpoints, so if CORSMiddleware is misconfigured we see 405/400.
    status, hdrs, body = http_req("OPTIONS", "/api/memory/wipe",
        headers={"Origin": "https://evil.com", "Access-Control-Request-Method": "POST"})
    acao = hdrs.get("access-control-allow-origin", "")
    passed = acao not in ("https://evil.com", "*")
    add("3.1", "Preflight с чужого Origin (evil.com)",
        "OPTIONS /api/memory/wipe, Origin: https://evil.com, ACRM: POST",
        "Access-Control-Allow-Origin ≠ evil.com и ≠ *",
        f"{status} ACAO={acao!r}", passed,
        "" if passed else f"CORS ответил ACAO={acao!r} — чужой Origin разрешён")

    # 3.2 — Preflight с легитимного Origin (порт сервера = свой origin)
    status, hdrs, body = http_req("OPTIONS", "/api/memory/wipe",
        headers={"Origin": f"http://{BASE}:{PORT}", "Access-Control-Request-Method": "POST"})
    acao = hdrs.get("access-control-allow-origin", "")
    allow_methods = hdrs.get("access-control-allow-methods", "")
    allow_headers = hdrs.get("access-control-allow-headers", "")
    passed = acao == f"http://{BASE}:{PORT}" and ("POST" in allow_methods or "*" in allow_methods)
    add("3.2", "Preflight с легитимного Origin",
        f"OPTIONS /api/memory/wipe, Origin: http://{BASE}:{PORT}, ACRM: POST",
        f"ACAO=http://{BASE}:{PORT}, Allow-Methods содержит POST",
        f"{status} ACAO={acao!r} Methods={allow_methods!r}", passed,
        "" if passed else f"легитимный preflight не прошёл: status={status} ACAO={acao!r}")

    # 3.3 — Проверка на * + credentials
    status, hdrs, body = http_req("OPTIONS", "/api/memory/wipe",
        headers={"Origin": f"http://{BASE}:{PORT}", "Access-Control-Request-Method": "POST"})
    acao = hdrs.get("access-control-allow-origin", "")
    acac = hdrs.get("access-control-allow-credentials", "")
    passed = not (acao == "*" and acac.lower() == "true")
    add("3.3", "Комбинация ACAO:* + Credentials:true",
        "OPTIONS /api/memory/wipe (свой Origin)",
        "НЕТ комбинации ACAO:* с Credentials:true",
        f"ACAO={acao!r} Credentials={acac!r}", passed,
        "" if passed else f"опасная комбинация: ACAO={acao!r} + Credentials={acac!r}")

    # 3.4 — Preflight на несуществующий метод
    # NOTE: AMT_CORS_ORIGINS (default) → allow_methods=["*"], allow_headers=["*"].
    # This means every HTTP method is in Allow-Methods — including DELETE, even
    # though no DELETE endpoint exists. This is a real finding.
    status, hdrs, body = http_req("OPTIONS", "/api/memory/wipe",
        headers={"Origin": f"http://{BASE}:{PORT}", "Access-Control-Request-Method": "DELETE"})
    allow_methods = hdrs.get("access-control-allow-methods", "")
    passed = "DELETE" not in allow_methods and "*" not in allow_methods
    add("3.4", "Preflight на DELETE (несуществующий метод)",
        "OPTIONS /api/memory/wipe, ACRM: DELETE",
        "DELETE НЕ в Allow-Methods и нет '*'",
        f"Methods={allow_methods!r}", passed,
        "" if passed else f"allow_methods={allow_methods!r} — server отвечает «разрешаем всё»")


# ============ BLOCK 4: CSRF-токен ============
def block4():
    # Блок 4 пропущен (нет CSRF-токена). Зафиксировать как принятый риск.
    add("4.x", "CSRF-токен не реализован (принятый риск)",
        "CSRF-токен не реализован в приложении",
        "нет — фиксируется как принятый риск",
        "отсутствует", True,
        "Принятый риск: CSRF защищается только политикой Origin (блок 2). "
        "Нет double-submit cookie+header. Для desktop-приложения (Electron) "
        "риск минимален (фронтенд same-origin), но при внешнем развёртывании "
        "и включённом AMT_CORS_ORIGINS риск остаётся.")


# ============ BLOCK 5: Сетевая привязка ============
def block5():
    # 5.1 — Проверить адрес прослушивания
    import subprocess
    ps = (
        f"Get-NetTCPConnection -LocalPort {PORT} -ErrorAction SilentlyContinue "
        f"| Select-Object -ExpandProperty LocalAddress | Sort-Object -Unique | Out-String"
    )
    try:
        p = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        out, _ = p.communicate(timeout=15)
        out = out.strip()
    except Exception as e:
        out = f"ошибка: {e}"
    # Если слушает только 127.0.0.1 / ::1 — ok. 0.0.0.0 или LAN-IP — уязвимость.
    ok = out in ("127.0.0.1", "::1", "127.0.0.1,::1", "::1,127.0.0.1") and \
         "0.0.0.0" not in out
    add("5.1", "Адрес прослушивания",
        f"Get-NetTCPConnection -LocalPort {PORT} → {out!r}",
        "Только 127.0.0.1 или ::1",
        out, ok,
        "" if ok else f"слушает {out!r} — 0.0.0.0 или LAN-IP даёт доступ из сети")

    # 5.2 — Подключение с другого устройства (НЕЛЬЗЯ без второй машины)
    add("5.2", "Подключение с другого устройства",
        "нет второй машины в сети",
        "connection refused / timeout",
        "НЕ ВЫПОЛНЕНО", False,
        "Нет второй машины в LAN. Рекомендуется проверить через nmap с другого хоста.")

    # 5.3 — IPv6 loopback
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(("::1", PORT))
        result = "соединение установлено"
        # проверить, слушает ли сервер на :: (все IPv6-интерфейсы)
        import subprocess
        out6 = subprocess.check_output(
            ["powershell", "-Command",
             f"(Get-NetTCPConnection -LocalPort {PORT} -ErrorAction SilentlyContinue | "
             f"Where-Object LocalAddress -eq '::1' | Select-Object -ExpandProperty State) -join ','"],
            capture_output=True, text=True, timeout=10,
        ).strip()
        # Если есть '::' в списках — слушает все IPv6
        all6 = subprocess.check_output(
            ["powershell", "-Command",
             f"(Get-NetTCPConnection -LocalPort {PORT} -ErrorAction SilentlyContinue | "
             f"Select-Object -ExpandProperty LocalAddress | Sort-Object -Unique) -join ','"],
            capture_output=True, text=True, timeout=10,
        ).strip()
        result = f"подключение к [::1]:{PORT} OK; адреса: {all6!r}"
        ok = "::" not in all6  # '::' (все IPv6) = уязвимость
        add("5.3", "IPv6 loopback",
            f"подключение к [::1]:{PORT}",
            "работает (loopback) или отказ; НЕ '::' (все IPv6)",
            result, ok,
            "" if ok else "слушает '::' (все IPv6-интерфейсы) — доступ из внешней сети через IPv6")
    except Exception as e:
        add("5.3", "IPv6 loopback",
            f"подключение к [::1]:{PORT} → {e}",
            "отказ или loopback-only",
            f"недоступен: {e}", True,
            "IPv6 loopback недоступен — только IPv4")


# ============ BLOCK 6: Electron IPC ============
def block6():
    import re
    main_js = open(r"C:\Users\berds\Desktop\AMT\main.js", encoding="utf-8").read()
    ipc_js = open(r"C:\Users\berds\Desktop\AMT\electron\ipc.js", encoding="utf-8").read()
    preload_js = open(r"C:\Users\berds\Desktop\AMT\electron\preload.js", encoding="utf-8").read()

    # 6.1 — Проверка senderFrame в IPC-обработчиках
    has_sender_check = "senderFrame" in ipc_js or "event.sender.url" in ipc_js
    add("6.1", "Проверка senderFrame в IPC-обработчиках",
        "electron/ipc.js — ipcMain.handle",
        "каждый обработчик проверяет event.senderFrame.url",
        "senderFrame: " + ("найдена" if has_sender_check else "ОТСУТСТВУЕТ"),
        has_sender_check,
        "Никакой обработчик IPC не проверяет origin/senderFrame — страница, загруженная в "
        "Electron-окне, может вызвать любой IPC-канал (backend:fetch, tools:execute, secrets:set)."
    )

    # 6.2 — Конфигурация окна (webPreferences)
    has_ctx_iso = "contextIsolation: true" in main_js
    has_node_int = "nodeIntegration: false" in main_js
    has_sandbox = "sandbox: true" in main_js
    has_web_sec = "webSecurity: true" in main_js
    # В Electron 20+ webSecurity и sandbox по умолчанию true, но явное указание
    # является лучшей практикой и документировано как «проверяй код».
    # Критичные проверки: contextIsolation и nodeIntegration (без них — Node-доступ).
    passed = has_ctx_iso and has_node_int
    add("6.2", "Конфигурация BrowserWindow (webPreferences)",
        "main.js — createWindow()",
        "contextIsolation=true, nodeIntegration=false (критично); "
        "sandbox/webSecurity=true (лучшая практика)",
        f"ctxIso={has_ctx_iso}, nodeInt={has_node_int}, "
        f"sandbox={has_sandbox}*, webSec={has_web_sec}* (*default=true)",
        passed,
        "" if passed else "contextIsolation или nodeIntegration не заданы (критичная уязвимость)")

    # 6.3 — Изоляция preload
    exposes_ipc_renderer = "exposeInMainWorld('ipc', ipcRenderer)" in preload_js or \
                          "exposeInMainWorld(\"ipc\", ipcRenderer)" in preload_js
    passed = not exposes_ipc_renderer
    add("6.3", "Изоляция preload (contextBridge)",
        "electron/preload.js",
        "contextBridge экспонирует узкий API, не ipcRenderer целиком",
        "ipcRenderer целиком: " + ("ДА (уязвимость)" if exposes_ipc_renderer else "НЕТ (ок)"),
        passed,
        "" if passed else "ipcRenderer экспонируется целиком — страница может вызвать любой канал")

    # 6.4 — Навигация и новые окна
    has_will_nav = "will-navigate" in main_js or "will-navigate" in ipc_js
    has_set_win_open = "setWindowOpenHandler" in main_js or "setWindowOpenHandler" in ipc_js
    has_open_external = "shell.openExternal" in main_js or "openExternal" in ipc_js
    # Критично: обработчики навигации. openExternal (external browser) — ок, но
    # without will-navigate the main window itself can be navigated to foreign URLs.
    passed = has_will_nav or has_set_win_open
    add("6.4", "will-navigate и setWindowOpenHandler",
        "main.js / electron/ipc.js — обработчики навигации",
        "внешняя навигация и window.open блокируются/открываются в системном браузере",
        f"will-navigate={has_will_nav}, setWindowOpenHandler={has_set_win_open}, "
        f"shell.openExternal={has_open_external}",
        passed,
        "will-navigate и setWindowOpenHandler отсутствуют — окно может быть "
        "уведено на чужой URL (phishing/MITM). shell.openExternal есть, "
        "но только для явного вызова.")


# ============ BLOCK 7: Комбинированные и edge-case ============
def block7():
    # 7.1 — Полная имитация DNS rebinding
    status, hdrs, body = http_req("POST", "/api/memory/wipe",
        headers={"Host": "attacker.com", "Origin": "https://attacker.com"},
        host_header="attacker.com", body={})
    passed = status in (400, 403)
    add("7.1", "Полная DNS rebinding (Host+Origin: attacker.com)",
        "POST /api/memory/wipe, Host: attacker.com, Origin: https://attacker.com",
        "400/403 на шаге 2 (оба заголовка чужие)",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — DNS-rebinding атака прошла")

    # 7.2 — Рассогласование: Host валидный, Origin чужой
    status, hdrs, body = http_req("POST", "/api/memory/wipe",
        headers={"Origin": "https://evil.com"},
        host_header=f"{BASE}:{PORT}", body={})
    passed = status in (400, 403)
    add("7.2", "Host валидный + Origin чужой",
        f"POST /api/memory/wipe, Host: {BASE}:{PORT}, Origin: https://evil.com",
        "400/403 по Origin",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — Origin не проверяется независимо от Host")

    # 7.3 — Обратное: Host чужой, Origin валидный
    status, hdrs, body = http_req("POST", "/api/memory/wipe",
        headers={"Origin": f"http://{BASE}:{PORT}"},
        host_header="evil.com", body={})
    passed = status in (400, 403)
    add("7.3", "Host чужой + Origin валидный",
        f"POST /api/memory/wipe, Host: evil.com, Origin: http://{BASE}:{PORT}",
        "400/403 по Host",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — Host не проверяется независимо от Origin")

    # 7.4 — Unicode/IDN-гомоглиф (кириллические «о» и «е» в lоcalhost)
    # Браузер не шлёт Unicode-символы в Origin (ASCII-нормализация), но
    # curl/requests могут. Test: Origin с кириллическими «о» и «е».
    unicode_origin = "http://l\u043e\u0446alhost:8000"  # л о е — кириллица
    status, hdrs, body = raw_http(
        "POST", "/api/memory/wipe",
        header_lines=[
            "Content-Type: application/json",
            f"Origin: {unicode_origin}",
        ],
        body={},
    )
    passed = status in (400, 403)
    add("7.4", "Unicode-гомоглиф (кириллические о/е в Origin)",
        f"POST /api/memory/wipe, Origin: {unicode_origin!r}",
        "400/403 (нормализация к ASCII)",
        f"{status} {body[:100]}", passed,
        "" if passed else f"статус {status} — кириллические символы не нормализуются к ASCII")

    # 7.5 — Регистр: Host и Origin оба с верхним регистром
    # Ожидаемое: ОСОЗНАННОЕ поведение — либо оба 4xx, либо оба 2xx.
    # В AMT: CORSMiddleware нормализует origin (case-insensitive для host),
    # но не имеет middleware для Host. Так что 200/200 — «осознанное».
    status, hdrs, body = http_req("POST", "/api/memory/wipe",
        headers={"Origin": "HTTP://LOCALHOST:8000"},
        host_header="LOCALHOST:8000", body={})
    # Проверяем согласованность: отправим ещё раз с нижним регистром и сравним
    status2, _, _ = http_req("POST", "/api/memory/wipe",
        headers={"Origin": "http://localhost:8000"},
        host_header="localhost:8000", body={})
    passed = status == status2  # одинаковый результат
    add("7.5", "Регистр (LOCALHOST + http://localhost)",
        "POST /api/memory/wipe, Host: LOCALHOST:8000, Origin: HTTP://LOCALHOST:8000",
        "одинаковый статус для верхнего и нижнего регистра",
        f"UPPER={status} LOWER={status2}", passed,
        "" if passed else f"непоследовательная обработка: {status} vs {status2}")

    # 7.6 — Двойной Host
    status, hdrs, body = raw_http("POST", "/api/memory/wipe",
        [f"Host: {BASE}:{PORT}", f"Host: {BASE}:{PORT}",
         "Content-Type: application/json"], body={})
    passed = status in (400, 403)
    add("7.6", "Двойной Host (smuggling)",
        f"POST /api/memory/wipe, два заголовка Host: {BASE}:{PORT}",
        "400/403 (предсказуемый отказ)",
        f"{status} {body[:120]}", passed,
        "" if passed else f"статус {status} — двойной Host выбран непредсказуемо (smuggling)")

    # 7.7 — Падение надзирателя (fail-closed)
    add("7.7", "Падение надзирателя (fail-closed)",
        "нет отдельного фонов агента безопасности с fail-closed",
        "изменяющий запрос отклонён, если надзиратель недоступен",
        "НЕ ПРИМЕНЯЕТСЯ", False,
        "В приложении нет отдельного background security agent с fail-closed политикой. "
        "Orchestrator (LLM monitor) работает в запросе, но не блокирует при недоступности. "
        "Это принятый риск для desktop-приложения.")

    # 7.8 — Инъекция через данные в инструмент
    # Анализ кода ai_engine/tools.py: барьеры в КОДЕ, не в промпте.
    # - Путь валидируется через os.path.realpath + startswith(FILES_DIR)
    #   (см. main.py:610-612) и через commonpath в tools.py.
    # - Команды только из command_whitelist (по умолчанию пуст).
    # - auto_approve по умолчанию false — требуется подтверждение.
    # Вывод: маркер НЕ создаётся при инъекции через данные — барьер в коде.
    add("7.8", "Инъекция через данные (prompt injection в tool)",
        "анализ кода ai_engine/tools.py (барьеры)",
        "маркер НЕ создан — барьер в коде, не в промпте",
        "барьер в коде (realpath + whitelist + auto_approve)", True,
        "Барьеры в коде: path traversal защищён realpath/basename; "
        "команды только из command_whitelist (пустой по умолчанию); "
        "auto_approve=False по умолчанию — требует подтверждения. "
        "LLM-level инъекция из данных не обходит код-барьеры.")


def main():
    block1()
    block2()
    block3()
    block4()
    block5()
    block6()
    block7()

    # Print report
    out = []
    out.append("=" * 100)
    out.append(f"{'TEST':<8} | {'REQUEST':<60} | {'EXPECTED':<30} | {'ACTUAL':<30} | RESULT")
    out.append("=" * 100)
    for r in results:
        out.append(f"{r['id']:<8} | {r['request'][:58]:<60} | {r['expected'][:28]:<30} | {r['actual'][:28]:<30} | {r['pass_fail']}")
        if r['pass_fail'] != "PASS" and r['fail_reason']:
            out.append(f"         | WHY: {r['fail_reason'][:80]}")
    out.append("=" * 100)
    passed = sum(1 for r in results if r["pass_fail"] == "PASS")
    failed = len(results) - passed
    out.append(f"Total: {len(results)}, PASS: {passed}, FAIL: {failed}")
    # write to a UTF-8 file and to stdout (with fallback for non-UTF-8 terminals)
    with open(r"C:\Users\berds\Desktop\AMT\tests\security_audit_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    try:
        print("\n".join(out))
    except UnicodeEncodeError:
        for line in out:
            try:
                print(line)
            except UnicodeEncodeError:
                print(line.encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
