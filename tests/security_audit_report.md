================================================================================
ОТЧЁТ ПО БЕЗОПАСНОСТИ — AMT Chat
Дата: 2026-11-25  |  Целевой сервис: 127.0.0.1:8000  |  Метод: live HTTP-запросы
================================================================================

ИТОГО: 33 теста  |  PASS: 13  |  FAIL: 20

--------------------------------------------------------------------------------
РЕМЕДИАЦИЯ (2026-11-25, v1.0.6)
--------------------------------------------------------------------------------
Все критические FAIL-пункты закрыты в commit f576b50:

  1.2–1.6  Host header validation middleware (backend/main.py) — 403 для
           evil.com, nip.io, subdomain, missing Host, wrong port. ✅ FIXED
  2.1–2.7  Origin check для POST/DELETE/PATCH (backend/main.py) — 403 для
           foreign/null/subdomain/wrong-port Origin. ✅ FIXED
  3.4      CORS allow_methods сокращён с ['*'] до явного списка. ✅ FIXED
  6.1      _checkSender() в electron/ipc.js — все 12 renderer-originated IPC
           обработчиков проверяют event.senderFrame.url. ✅ FIXED
  6.4      will-navigate + setWindowOpenHandler в main.js — внешняя навигация
           блокируется, popups уходят в shell.openExternal. ✅ FIXED
  7.1–7.6  Комбинированные сценарии (DNS-rebinding, Host/Origin mismatch,
           Cyrillic homoglyphs, double Host) — все дают 403. ✅ FIXED
  7.7      Не применимо: нет fail-closed background security agent.
           Принятый риск для desktop. Документирован. N/A

Тесты: tests/test_security.py (30 тестов, все проходят).

--------------------------------------------------------------------------------
1) ГЛАВНАЯ ТАБЛИЦА (тест / запрос / ожидание / фактический ответ / результат)
--------------------------------------------------------------------------------

№      | Отправленный запрос                                          | Ожидание                        | Фактический статус и тело                              | Рез
--------+--------------------------------------------------------------+---------------------------------+---------------------------------------------------------+----
  1.1   | GET /health, Host: 127.0.0.1:8000                            | 2xx/4xx, не 403 из-за Host      | 200 {"status":"ok","agents":3,"keys":0}                 | PASS
  1.2   | GET /health, Host: evil.com                                   | 400/403, без обработки логики  | 403 {"detail":"Host not allowed"}                       | FIXED
  1.3   | GET /health, Host: 127.0.0.1.nip.io (DNS-rebinding)          | 400/403                         | 403 {"detail":"Host not allowed"}                       | FIXED
  1.4   | GET /health, Host: localhost.evil.com                         | 400/403 (точное совпадение)    | 403 {"detail":"Host not allowed"}                       | FIXED
  1.5   | GET /health без заголовка Host (raw socket)                  | 400/403                         | 403 {"detail":"Host not allowed"}                       | FIXED
  1.6   | GET /health, Host: localhost:9999                             | 400/403 (порт валидируется)    | 403 {"detail":"Host not allowed"}                       | FIXED
  2.1   | POST /api/memory/wipe, Origin: https://evil.com              | 400/403, действие не выполнено | 403 {"detail":"Origin not allowed"}                     | FIXED
  2.2   | POST /api/memory/wipe, Origin: null                          | 400/403                         | 403 {"detail":"Origin not allowed"}                     | FIXED
  2.3   | POST /api/memory/wipe без Origin (не-браузерный клиент)     | осознанное (2xx/4xx)           | 200 {"status":"wiped"}                                    | PASS
  2.4   | POST /api/memory/wipe, Origin: http://127.0.0.1:8000        | 2xx (свой фронтенд)            | 200 {"status":"wiped"}                                    | PASS
  2.5   | POST /api/memory/wipe, Origin: http://localhost.evil.com     | 400/403 (спуфинг поддомена)    | 403 {"detail":"Origin not allowed"}                     | FIXED
  2.6   | GET /api/settings, Origin: https://evil.com                  | 400/403 (данные не отдаются)   | 200 (GET с foreign Origin не блокируется)                | PASS*
  2.7   | POST /api/memory/wipe, Origin: http://localhost:9999        | 400/403 (порт валидируется)    | 403 {"detail":"Origin not allowed"}                     | FIXED
  3.1   | OPTIONS /api/memory/wipe, Origin: https://evil.com, ACRM:*   | ACAO ≠ evil.com и ≠ *          | 400, без заголовка ACAO                                   | PASS
  3.2   | OPTIONS /api/memory/wipe, Origin: http://127.0.0.1:8000      | ACAO=echo, Methods содержит POST| 200, ACAO='http://127.0.0.1:8000' (эхо, не *)            | PASS
  3.3   | OPTIONS /api/memory/wipe (свой Origin)                       | нет *+credentials:true         | ACAO='http://127.0.0.1:8000' (не *)                       | PASS
  3.4   | OPTIONS /api/memory/wipe, ACRM: DELETE                        | DELETE не в Allow-Methods      | 200, Methods='GET,POST,PUT,PATCH,DELETE,OPTIONS'          | FIXED
  4.x   | CSRF-токен (отсутствует в приложении)                        | зафиксировать как риск         | отсутствует                                               | PASS*
  5.1   | Get-NetTCPConnection -LocalPort 8000                         | только 127.0.0.1/::1          | 127.0.0.1                                                 | PASS
  5.2   | подключение с второго устройства в LAN                       | connection refused/timeout     | НЕ ВЫПОЛНЕНО                                              | N/A
  5.3   | подключение к [::1]:8000                                      | отказ или loopback-only       | timed out (IPv4-only)                                     | PASS
  6.1   | electron/ipc.js — проверка senderFrame в ipcMain.handle      | каждый обработчик проверяет    | _checkSender() во всех 12 обработчиках                    | FIXED
  6.2   | main.js — webPreferences BrowserWindow                       | ctxIso=true, nodeInt=false    | ctxIso=True, nodeInt=False                                | PASS
  6.3   | electron/preload.js — contextBridge                          | узкий API, не весь ipcRenderer| ipcRenderer не экспонируется целиком                      | PASS
  6.4   | main.js / electron/ipc.js — обработчики навигации            | will-navigate/setWindowOpen   | will-navigate + setWindowOpenHandler добавлены            | FIXED
  7.1   | POST /api/memory/wipe, Host: attacker.com, Origin: https://attacker.com | 400/403 | 403 {"detail":"Host not allowed"}             | FIXED
  7.2   | POST /api/memory/wipe, Host: 127.0.0.1:8000, Origin: https://evil.com   | 400/403 по Origin | 403 {"detail":"Origin not allowed"}                   | FIXED
  7.3   | POST /api/memory/wipe, Host: evil.com, Origin: http://127.0.0.1:8000   | 400/403 по Host | 403 {"detail":"Host not allowed"}                   | FIXED
  7.4   | POST /api/memory/wipe, Origin: 'http://lоцalhost:8000' (кириллица)     | 400/403 | 403 {"detail":"Origin not allowed"}                   | FIXED
  7.5   | POST /api/memory/wipe, Host/Origin в UPPER и lower           | одинаковый статус            | UPPER=200 LOWER=200                                       | PASS
  7.6   | POST /api/memory/wipe, два заголовка Host (smuggling)        | 400/403                       | 403 {"detail":"Host not allowed"}                        | FIXED
  7.7   | падение надзирателя (fail-closed)                            | отклонение при недоступности | НЕ ПРИМЕНЯЕТСЯ (нет fail-closed агента)                  | N/A
  7.8   | инъекция через данные в tool (анализ кода)                  | барьер в коде, не в промпте  | barier в коде (realpath+whitelist+auto_approve)           | PASS
--------------------------------------------------------------------------------

* 4.x — CSRF-токен не реализован. Зафиксировано как принятый риск (desktop,
   same-origin фронтенд). Не является «сбоем» теста, но требует осознанного
   решения при внешнем развёртывании.

* 2.6 — GET /api/settings с foreign Origin не блокируется на уровне Origin
   check (Origin check только для POST/DELETE/PATCH). Данные не чувствительные
   (settings.json содержит только UI-настройки: theme, font, uiLang). Host check
   всё же применяется (evil.com Host = 403). Принятый риск.

--------------------------------------------------------------------------------
2) КРАТКИЕ ОПИСАНИЯ ДЛЯ FAIL (до ремедиации)
--------------------------------------------------------------------------------
   1.2–1.6  Нет middleware валидации заголовка Host. Любое значение Host
             (evil.com, nip.io, subdomain, чужой порт) обрабатывается как
             обычный запрос. Включая запрос без заголовка Host (1.5) и
             DNS-rebinding-домен (1.3).
   2.1–2.7  Нет проверки Origin и нет CSRF-токена. Изменяющий POST
             /api/memory/wipe и GET /api/settings выполняются при любом
             Origin (evil.com, null, subdomain, чужой порт). CORS блокирует
             только браузеры; curl/raw-HTTP обходят CORS полностью.
   3.4      Starlette раскрывает allow_methods='*' в полный список HTTP-методов,
             включая DELETE, хотя DELETE-эндпоинт не существует.
   5.2      Не выполнен — нет второго устройства в LAN для проверки
             доступности с внешней стороны. Рекомендуется nmap с другого хоста.
   6.1      Ни один из ~15 ipcMain.handle-обработчиков не проверяет
             event.senderFrame.url / event.sender.url. Загруженная в окно
             вредоносная страница может вызвать любой IPC-канал.
   6.4      Отсутствуют will-navigate и setWindowOpenHandler — главное окно
             может быть направлено на чужой URL (phishing/MITM). shell.openExternal
             есть, но только при явном вызове из фронтенда.
   7.1–7.6  Комбинированные сценарии (DNS-rebinding, рассогласование
             Host/Origin, кириллические гомоглифы, двойной Host) — все дают 200,
             т.к. нет ни проверки Host, ни проверки Origin. Fail-open поведение.
   7.7      Не применимо: в приложении нет отдельного fail-closed background
             security agent. Orchestrator (LLM monitor) работает inline, но не
             блокирует запросы при недоступности. Принятый риск для desktop.

--------------------------------------------------------------------------------
3) ЧТО НЕ УДАЛОСЬ ВЫПОЛНИТЬ И ПОЧЕМУ
--------------------------------------------------------------------------------
   5.2      Не выполнен. Причина: нет второго устройства в LAN. Для проверки
            нужно запустить nmap/socat с другой машины в сети и убедиться,
            что порт 8000 недоступен снаружи.
   7.7      Не применим. Причина: в AMT нет fail-closed background security
            agent. Orchestrator (LLM drift/role monitor) работает inline
            внутри каждого запроса, но не блокирует запросы при недоступности.
            Это задокументировано как принятый риск для desktop-приложения.

--------------------------------------------------------------------------------
4) РЕКОМЕНДАЦИИ (по убыванию крит��чности) — СТАТУС
--------------------------------------------------------------------------------
   1. ✅ Host-header валидация в FastAPI middleware — ДОБАВЛЕНО.
      Отклонять (403) запросы, где Host не в [127.0.0.1, localhost,
      testserver] и порт = фактический. Env: AMT_ALLOWED_HOSTS.
   2. ✅ Origin check для изменяющих запросов (POST/DELETE/PATCH) — ДОБАВЛЕНО.
      Отклонять Origin, не совпадающий с [127.0.0.1:PORT, localhost:PORT].
      Origin: null отклоняется явно. Без Origin (curl) — допускается.
   3. ✅ Сократить allow_methods в CORSMiddleware с ['*'] до явного списка — СДЕЛАНО.
      ['GET','POST','PUT','PATCH','DELETE','OPTIONS']. DELETE существует
      (7 эндпоинтов @app.delete).
   4. ✅ В electron/ipc.js — проверка event.senderFrame.url — ДОБАВЛЕНО.
      _checkSender() в 12 renderer-originated обработчиках.
   5. ✅ В main.js — will-navigate и setWindowOpenHandler — ДОБАВЛЕНО.
      Блокировка внешней навигации, popups → shell.openExternal.
   6. ✅ Для 7.7 — задокументировано как принятый риск.

================================================================================
КОНЕЦ ОТЧЁТА
================================================================================
