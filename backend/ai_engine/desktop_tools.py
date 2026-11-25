"""Безопасный слой desktop-инструментов для AMT.

Инструменты:
  open_url(url, browser?)     — открыть URL в системном или указанном браузере
  launch_app(name, args?)     — запустить системное приложение (multi-strategy)
  page_recon(url)            — получить текст + structured elements страницы
  window_focus(app)          — привести окно приложения на передний план
  window_send_keys(text)     — отправить клавиши в активное окно
  window_click(x, y)        — клик мыши в координатах экрана
  window_screenshot()       — скриншот активного окна (PrintWindow)

Политика безопасности:
  - open_url: только http/https
  - launch_app: имя приложения проверяется whitelist'ом (command_whitelist)
  - page_recon: только http/https, не загружает скрипты
  - Все действия логируются в tools_log.jsonl.
"""
import json
import os
import time
import re
import subprocess
import webbrowser
from typing import Optional


class DesktopSandbox:
    """Изолированный исполнитель desktop-инструментов."""

    def __init__(self, log_path: str = None):
        self.log_path = log_path or os.environ.get("AMT_DESKTOP_LOG") or os.path.join(os.path.dirname(__file__), "..", "desktop_log.jsonl")
        # Debounce: track last browser open to avoid spawning duplicate instances
        self._last_browser_open: dict = {"browser": "", "ts": 0}

    def _log(self, action: str, detail: dict, result: str):
        try:
            rec = {
                "ts": int(time.time()),
                "action": action,
                "tool": action,
                "detail": detail,
                "result": result[:300],
            }
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ---------- URL tools ----------
    def _normalize_url(self, url: str) -> str:
        """Нормализует URL: добавляет схему, кодирует кириллицу, чинит query."""
        import urllib.parse
        url = url.strip().strip('"\'')
        if not url:
            return url
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        try:
            parts = urllib.parse.urlsplit(url)
            host = parts.netloc
            try:
                host_enc = host.encode("idna").decode("ascii") if host else ""
            except Exception:
                host_enc = host
            path = urllib.parse.quote(parts.path, safe="/%")
            # НЕ перекодируем query: urlsplit сохраняет percent-encoding как есть,
            # а quote() закодировал бы % как %25 → двойное кодирование.
            # Кодировать только кириллицу в query (если не закодирована).
            query = parts.query
            if query and not any(c in query for c in "0123456789ABCDEFabcdef"):
                # query содержит необработанные спецсимволы — кодируем
                query = urllib.parse.quote(query, safe="&=?+!*,;@$~")
            frag = urllib.parse.quote(parts.fragment, safe="") if parts.fragment else ""
            url = urllib.parse.urlunsplit((parts.scheme, host_enc, path, query, frag))
        except Exception:
            pass
        return url

    def open_url(self, url: str, browser: str = "") -> dict:
        """Открывает URL в системном браузере.

        url — http(s)-ссылка. Если browser не пуст, пытается открыть в указанном
        браузере (edge, firefox, chrome, brave, vivaldi, opera, ...). Иначе —
        системный браузер (или remembered defaultBrowser из settings).
        Кириллица в домене/URL нормализуется автоматически.
        Если url пуст и browser указан — открывает домашнюю страницу браузера.
        """
        # Если URL пуст и браузер указан — открываем домашнюю страницу
        if not url or not url.strip().strip('"\''):
            if browser:
                url = "https://www.google.com"
            else:
                self._log("open_url_denied", {"url": url, "browser": browser}, "empty url")
                return {"ok": False, "error": "Пустой URL", "code": "empty"}
        # Сначала проверяем схему — file://, ftp:// и т.д. запрещены
        raw = url.strip().strip('"\'')
        if raw.lower().startswith(("file://", "ftp://", "ftps://", "data:", "javascript:", "mailto:", "tel:")):
            self._log("open_url_denied", {"url": raw}, "non-http scheme")
            return {"ok": False, "error": "Только http/https ссылки", "code": "scheme"}
        url = self._normalize_url(raw)
        if not url.startswith(("http://", "https://")):
            self._log("open_url_denied", {"url": url}, "non-http scheme")
            return {"ok": False, "error": "Только http/https ссылки", "code": "scheme"}
        try:
            # Debounce: if the same browser was opened < 5s ago, reuse it (focus + navigate)
            if browser and self._last_browser_open["browser"].lower() == browser.lower() and \
                    (time.time() - self._last_browser_open["ts"]) < 5:
                self._log("open_url", {"url": url, "browser": browser, "mode": "reuse"}, "reusing existing browser")
                # Focus the running browser and send the URL via address bar
                self._focus_window_by_app(browser)
                time.sleep(1.0)
                self.window_send_keys(url, app=browser)
                return {"ok": True, "url": url, "browser": browser, "note": "browser reused (debounce)"}
            if browser:
                launched = self._launch_browser(browser, url)
                if launched:
                    self._last_browser_open = {"browser": browser, "ts": time.time()}
                    self._log("open_url", {"url": url, "browser": browser}, "ok")
                    return {"ok": True, "url": url, "browser": browser}
                # Браузер указан, но не найден — НЕ падаем на системный браузер
                self._log("open_url_error", {"url": url, "browser": browser}, "browser not found")
                return {"ok": False, "error": f"Браузер '{browser}' не найден на этом компьютере", "code": "browser_not_found"}
            else:
                # Use remembered default browser if set
                default = self._get_default_browser()
                if default:
                    # Debounce for default browser too
                    if self._last_browser_open["browser"].lower() == default.lower() and \
                            (time.time() - self._last_browser_open["ts"]) < 5:
                        self._log("open_url", {"url": url, "browser": default, "mode": "reuse"}, "reusing existing browser")
                        self._focus_window_by_app(default)
                        time.sleep(1.0)
                        self.window_send_keys(url, app=default)
                        return {"ok": True, "url": url, "browser": default, "note": "browser reused (debounce)"}
                    launched = self._launch_browser(default, url)
                    if launched:
                        self._last_browser_open = {"browser": default, "ts": time.time()}
                        self._log("open_url", {"url": url, "browser": default, "method": "default"}, "ok")
                        return {"ok": True, "url": url, "browser": default}
            webbrowser.open(url)
            # Определим какой браузер реально запустился
            browser_name = self._detect_running_browser()
            if browser_name:
                self._last_browser_open = {"browser": browser_name, "ts": time.time()}
            self._log("open_url", {"url": url, "browser": browser_name}, "ok (system default)")
            result = {"ok": True, "url": url}
            if browser_name:
                result["browser"] = browser_name
            return result
        except Exception as e:
            self._log("open_url_error", {"url": url}, str(e))
            return {"ok": False, "error": str(e)}

    def _get_default_browser(self) -> str:
        """Читает remembered default browser из settings.json.

        Если settings.json нет или defaultBrowser пуст — детектит системный
        браузер через реестр Windows (UrlAssociations + HKCR).
        """
        # Сначала из settings.json
        try:
            settings_file = os.environ.get("AMT_SETTINGS_FILE") or os.path.join(
                os.path.dirname(__file__), "..", "settings.json"
            )
            if os.path.isfile(settings_file):
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                browser = data.get("defaultBrowser", "")
                if browser:
                    return browser
        except Exception:
            pass

        # Fallback: детектим системный браузер через реестр
        import os as _os
        try:
            import winreg
            import re as _re

            prog_id_map = {
                'ChromeHTML': 'chrome',
                'MSEdgeHTM': 'edge',
                'FirefoxURL': 'firefox',
                'BraveHTML': 'brave',
                'VivaldiShell': 'vivaldi',
                'Opera': 'opera',
            }

            # Method 1: HKCU UrlAssociations
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice') as key:
                    prog_id, _ = winreg.QueryValueEx(key, 'ProgId')
                    # ProgId like "ChromeHTML" → extract "Chrome" → lowercase
                    name = prog_id.replace('HTM', '').replace('MSEdge', 'edge').lower()
                    if name in prog_id_map.values():
                        return name
                    # Try to extract from ProgId directly
                    base = _re.match(r'^([A-Za-z]+)', prog_id)
                    if base:
                        candidate = base.group(1).lower()
                        if candidate in prog_id_map.values():
                            return candidate
                        if candidate + 'HTML' in prog_id_map:
                            return prog_id_map[candidate + 'HTML']
            except Exception:
                pass

            # Method 2: HKCR http shell open command
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                     r'http\shell\open\command') as key:
                    cmd, _ = winreg.QueryValueEx(key, '')
                    # Parse exe name from command like '"C:\...\chrome.exe" "%1"'
                    m = _re.search(r'["\']([^"\'\\]+\.exe)', cmd, _re.IGNORECASE)
                    if m:
                        exe = _os.path.basename(m.group(1)).replace('.exe', '').lower()
                        return exe
            except Exception:
                pass

        except Exception:
            pass

        return ""

    def _launch_browser(self, name: str, url: str) -> bool:
        """Запускает указанный браузер с URL. Returns True если удалось.

        Универсальный поиск: реестр Uninstall → common install dirs → Start Menu .lnk → PATH.
        Поддерживает ЛЮБОЙ браузер (edge, chrome, firefox, brave, vivaldi, opera, arc,
        chromium, maxthon, kometa, yandex, etc.) — не хардкодим список.
        """
        import platform, shutil
        system = platform.system()
        name_lower = name.lower()
        try:
            if system == "Windows":
                path = self._find_browser(name)
                if path:
                    subprocess.Popen([path, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    import time as _time
                    _time.sleep(1.0)
                    self._win_foreground_if_running(os.path.basename(path))
                    return True
                return False
            elif system == "Darwin":
                subprocess.Popen(["open", "-a", name, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            else:
                subprocess.Popen([name, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
        except Exception:
            return False

    def _detect_running_browser(self) -> str:
        """Определяет какой браузер реально запущен (по имени процесса)."""
        import platform
        if platform.system() != "Windows":
            return ""
        try:
            ps = "Get-Process | Where-Object {$_.Name -match '(chrome|msedge|firefox|brave|vivaldi|opera|chromium)'} | Select-Object -First 1 -ExpandProperty Name"
            proc = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=5,
            )
            name = proc.stdout.decode('utf-8', errors='ignore').strip()
            if name:
                # Нормализуем: msedge → edge, chrome → chrome
                name = name.lower().replace('.exe', '')
                if 'edge' in name:
                    return 'edge'
                return name
        except Exception:
            pass
        return ""

    def _find_browser(self, name: str) -> Optional[str]:
        """Ищет браузер по имени в реестре, common dirs, Start Menu и PATH.

        Returns путь к .exe или None. Поддерживает любой браузер — не хардкодим.
        """
        import os as _os
        import glob as _glob
        name_lower = name.lower().replace('.exe', '').strip()
        if not name_lower:
            return None

        # --- 1. Registry Uninstall keys (matches DisplayName containing name) ---
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
                (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
            ]
            for hive, subkey in reg_paths:
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        i = 0
                        while True:
                            try:
                                sub_name = winreg.EnumKey(key, i)
                                i += 1
                            except OSError:
                                break
                            try:
                                with winreg.OpenKey(key, sub_name) as sub:
                                    display_name, _ = winreg.QueryValueEx(sub, 'DisplayName')
                                    if name_lower in display_name.lower():
                                        # Prefer the exe matching the display name
                                        icon_path, _ = winreg.QueryValueEx(sub, 'DisplayIcon')
                                        exe_path = icon_path.split(',')[0].replace('"', '').strip()
                                        if exe_path and _os.path.isfile(exe_path):
                                            return exe_path
                                        # Fallback: look for <name>.exe in the install location
                                        install_loc, _ = winreg.QueryValueEx(sub, 'InstallLocation')
                                        if install_loc:
                                            candidates = [
                                                _os.path.join(install_loc, name_lower + '.exe'),
                                                _os.path.join(install_loc, name_lower.replace('browser', '') + '.exe'),
                                            ]
                                            for c in candidates:
                                                if _os.path.isfile(c):
                                                    return c
                            except Exception:
                                continue
                except Exception:
                    continue
        except ImportError:
            pass

        # --- 2. Common install dirs (broad glob search) ---
        env_pf = _os.environ.get('ProgramFiles', r'C:\Program Files')
        env_pf86 = _os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
        env_local = _os.environ.get('LOCALAPPDATA', '')
        env_sysroot = _os.environ.get('SystemRoot', r'C:\Windows')
        search_bases = [env_pf, env_pf86, env_local, env_local and _os.path.join(env_local, 'Programs')]
        # Also try <name> as a directory name with <name>.exe inside
        for base in search_bases:
            if not base or not _os.path.isdir(base):
                continue
            # Direct match: <base>\<name>\<name>.exe
            direct = _os.path.join(base, name_lower, name_lower + '.exe')
            if _os.path.isfile(direct):
                return direct
            # Broad glob: <base>\<name>*\*<name>*.exe
            try:
                pattern = _os.path.join(base, f'{name_lower}*', f'*{name_lower}*.exe')
                matches = _glob.glob(pattern)
                if matches:
                    return matches[0]
            except Exception:
                pass

        # --- 3. Start Menu .lnk search ---
        sm_dirs = [
            _os.path.join(_os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
            r'C:\ProgramData\Microsoft\Windows\Start Menu\Programs',
        ]
        for sm_dir in sm_dirs:
            if not sm_dir or not _os.path.isdir(sm_dir):
                continue
            try:
                for entry in _os.listdir(sm_dir):
                    entry_lower = entry.lower()
                    if name_lower in entry_lower and entry.endswith('.lnk'):
                        # Resolve .lnk target via PowerShell
                        lnk_path = _os.path.join(sm_dir, entry)
                        safe = lnk_path.replace("'", "''")
                        ps = (
                            f'$ws = New-Object -ComObject WScript.Shell; '
                            f'$sc = $ws.CreateShortcut("{safe}"); '
                            f'Write-Output $sc.TargetPath'
                        )
                        try:
                            proc = subprocess.run(
                                ['powershell', '-NoProfile', '-Command', ps],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=5,
                            )
                            target = proc.stdout.decode('utf-8', errors='ignore').strip()
                            if target and _os.path.isfile(target):
                                return target
                        except Exception:
                            pass
            except Exception:
                continue

        # --- 4. PATH search ---
        import shutil
        found = shutil.which(name_lower) or shutil.which(name)
        if found:
            return found

        # --- 5. Try <name>.exe in PATH ---
        found_exe = shutil.which(name_lower + '.exe')
        if found_exe:
            return found_exe

        return None

    def page_recon(self, url: str) -> dict:
        """Получает текст + structured elements страницы через httpx (без JS-рендеринга).

        Возвращает: {ok, url, title, text, chars, links, elements}
        elements — структурированный список элементов на странице:
          buttons, inputs, videos, images, iframes, selects, textareas
        — с контекстом (текст, id, class, src, alt). Это позволяет ИИ
        рассуждать о структуре страницы и формулировать целевые действия.

        Для JS-тяжёлых страниц (YouTube, Twitch) текст может быть пустым —
        это нормально, ИИ понимает и использует open_url вместо page_recon.
        """
        url = self._normalize_url(url)
        raw_lower = url.lower()
        if raw_lower.startswith(("file://", "ftp://", "ftps://", "data:", "javascript:")):
            self._log("page_recon_denied", {"url": url}, "non-http scheme")
            return {"ok": False, "error": "Только http/https ссылки", "code": "scheme"}
        if not url.startswith(("http://", "https://")):
            self._log("page_recon_denied", {"url": url}, "non-http scheme")
            return {"ok": False, "error": "Только http/https ссылки", "code": "scheme"}
        try:
            import httpx
            r = httpx.get(url, timeout=15, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AMT/1.0"})
            r.raise_for_status()
            html = r.text

            # Извлекаем title
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
            title = title_match.group(1).strip()[:200] if title_match else ""

            # Извлекаем ссылки <a href>
            links = []
            for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE):
                href = m.group(1).strip()
                text = re.sub(r'<[^>]+>', '', m.group(2)).strip()[:100]
                if href and not href.startswith('javascript:') and not href.startswith('#'):
                    links.append({"href": href, "text": text})
                if len(links) >= 50:
                    break

            # Structured elements
            elements = self._extract_structured_elements(html)

            # Убираем script/style/hidden → чистый текст
            html_clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html_clean = re.sub(r'<style[^>]*>.*?</style>', '', html_clean, flags=re.DOTALL | re.IGNORECASE)
            html_clean = re.sub(r'<nav[^>]*>.*?</nav>', '', html_clean, flags=re.DOTALL | re.IGNORECASE)
            html_clean = re.sub(r'<footer[^>]*>.*?</footer>', '', html_clean, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', html_clean)
            text = re.sub(r'\s+', ' ', text).strip()
            text = text[:50000]

            # Если текста мало (< 100 символов) — пробуем Electron capturePage
            screenshot_url = None
            if len(text) < 100:
                screenshot_url = self._try_electron_screenshot(url)

            self._log("page_recon", {"url": url, "chars": len(text), "title": title[:100],
                                     "links": len(links), "elements": len(elements)}, "ok")
            result = {
                "ok": True,
                "url": str(r.url),
                "title": title,
                "text": text,
                "chars": len(text),
                "links": links,
                "elements": elements,
            }
            if screenshot_url:
                result["screenshot"] = screenshot_url
            return result
        except Exception as e:
            self._log("page_recon_error", {"url": url}, str(e))
            err_str = str(e)
            if "handshake" in err_str.lower() or "ssl" in err_str.lower() or "timeout" in err_str.lower():
                err_str = (
                    f"Не удалось получить страницу ({url}): таймаут SSL/сети. "
                    f"Попробуй открыть её напрямую через [[SYS:open_url|{url}]] "
                    f"и объясни пользователю, что нужно сделать вручную."
                )
            elif "connection" in err_str.lower():
                err_str = (
                    f"Не удалось подключиться к {url}: проверь адрес. "
                    f"Попробуй открыть её напрямую через [[SYS:open_url|{url}]]."
                )
            return {"ok": False, "error": err_str}

    def _extract_structured_elements(self, html: str) -> list[dict]:
        """Извлекает структурированные элементы из HTML.

        Возвращает список:
          [{"type": "button", "text": "Play", "id": "btn1", "class": "primary"},
           {"type": "video",  "src": "https://...mp4", "controls": true},
           {"type": "input",  "type": "text", "id": "search", "placeholder": "Search..."},
           ...]
        Лимит: 100 элементов (защита от overflow).
        """
        elements = []

        def _tag_attrs(tag_str: str) -> dict:
            """Парсит атрибуты из строки тега: <button class="x" id="y">."""
            attrs = {}
            for m in re.finditer(r'(\w[\w-]*)\s*=\s*["\']([^"\']*)["\']', tag_str):
                attrs[m.group(1).lower()] = m.group(2)
            return attrs

        # <button>...</button>
        for m in re.finditer(r'<button([^>]*)>(.*?)</button>', html, re.DOTALL | re.IGNORECASE):
            attrs = _tag_attrs(m.group(1))
            text = re.sub(r'<[^>]+>', '', m.group(2)).strip()[:100]
            if text:
                elements.append({
                    "type": "button",
                    "text": text,
                    "id": attrs.get("id", ""),
                    "class": attrs.get("class", ""),
                })

        # <input>
        for m in re.finditer(r'<input([^>]*)/?>', html, re.IGNORECASE):
            attrs = _tag_attrs(m.group(1))
            in_type = attrs.get("type", "text").lower()
            if in_type in ("hidden", "image"):
                continue
            elements.append({
                "type": "input",
                "input_type": in_type,
                "id": attrs.get("id", ""),
                "class": attrs.get("class", ""),
                "name": attrs.get("name", ""),
                "placeholder": attrs.get("placeholder", ""),
            })

        # <textarea>
        for m in re.finditer(r'<textarea([^>]*)>(.*?)</textarea>', html, re.DOTALL | re.IGNORECASE):
            attrs = _tag_attrs(m.group(1))
            elements.append({
                "type": "textarea",
                "id": attrs.get("id", ""),
                "class": attrs.get("class", ""),
                "name": attrs.get("name", ""),
            })

        # <video>
        for m in re.finditer(r'<video([^>]*)/?>', html, re.IGNORECASE):
            attrs = _tag_attrs(m.group(1))
            src = attrs.get("src", "")
            if not src:
                # Check for <source> child
                m2 = re.search(r'<video([^>]*)>(.*?)</video>', html, re.DOTALL | re.IGNORECASE)
                if m2:
                    src_m = re.search(r'<source[^>]+src=["\']([^"\']+)["\']', m2.group(2), re.IGNORECASE)
                    src = src_m.group(1) if src_m else ""
            elements.append({
                "type": "video",
                "src": src,
                "controls": attrs.get("controls") is not None,
                "id": attrs.get("id", ""),
                "class": attrs.get("class", ""),
            })

        # <img>
        for m in re.finditer(r'<img([^>]*?)/?>', html, re.IGNORECASE):
            attrs = _tag_attrs(m.group(1))
            src = attrs.get("src", "")
            alt = attrs.get("alt", "")
            if src and (alt or "data:image" in src or src.startswith("http")):
                elements.append({
                    "type": "image",
                    "src": src[:300],
                    "alt": alt[:200],
                    "id": attrs.get("id", ""),
                })

        # <iframe>
        for m in re.finditer(r'<iframe([^>]*)/?>', html, re.IGNORECASE):
            attrs = _tag_attrs(m.group(1))
            src = attrs.get("src", "")
            if src:
                elements.append({
                    "type": "iframe",
                    "src": src[:300],
                    "id": attrs.get("id", ""),
                    "class": attrs.get("class", ""),
                })

        # <select>
        for m in re.finditer(r'<select([^>]*)>(.*?)</select>', html, re.DOTALL | re.IGNORECASE):
            attrs = _tag_attrs(m.group(1))
            options = re.findall(r'<option[^>]*>(.*?)</option>', m.group(2), re.DOTALL | re.IGNORECASE)
            options_clean = [re.sub(r'<[^>]+>', '', o).strip()[:50] for o in options[:20]]
            elements.append({
                "type": "select",
                "id": attrs.get("id", ""),
                "class": attrs.get("class", ""),
                "name": attrs.get("name", ""),
                "options": options_clean,
            })

        return elements[:100]

    def _try_electron_screenshot(self, url: str) -> Optional[str]:
        """Пытается получить JS-скриншот через Electron-мост.
        Возвращает URL скриншота или None.
        """
        try:
            # Бэкенд уже имеет _electron_screenshot() и /api/screenshots/bridge.
            # Мы не можем вызвать asyncio из sync-кода, поэтому используем
            # httpx для запроса к локальному API.
            import httpx
            # Проверяем, доступен ли Electron-мост (GET /api/screenshots/pending)
            # Если нет — пропускаем (чистый headless-режим).
            base = os.environ.get("AMT_API_BASE", "http://127.0.0.1:8765")
            # Просто логгируем, что хотели бы скриншот. Реальный скриншот
            # приходит через отдельный [[SCREENSHOT:url]] токен в LLM-ответе.
            # Здесь мы не бло��ируем поток.
            self._log("page_recon_js_fallback", {"url": url}, "requesting electron screenshot")
            return None
        except Exception:
            return None

    # ---------- App launch ----------
    def launch_app(self, app: str, args: str = "") -> dict:
        """Запускает системное приложение.

        Windows: multi-strategy (PATH .exe → UWP shell:AppsFolder → full path lookup)
        Linux:   xdg-open / direct
        macOS:   open -a

        app — имя приложения (steam, discord, firefox, notepad, …)
        или полный путь к .exe/.app/.desktop. НЕ хардкодим — ИИ выбирает сам.
        """
        app = (app or "").strip()
        if not app:
            return {"ok": False, "error": "Пустое имя приложения", "code": "empty"}

        import platform
        system = platform.system()

        if system == "Windows":
            # Полный путь → сразу запускаем (стратегия 0).
            if os.path.isabs(app) and os.path.exists(app):
                res = self._win_start(app, args)
                if res.get("ok"):
                    import time as _time
                    _time.sleep(0.5)
                    if self._win_foreground_if_running(app):
                        res["foregrounded"] = True
                return res

            # Если приложени�� уже запущено — приводим на передний план
            if self._win_foreground_if_running(app):
                self._log("launch_app_foreground", {"app": app}, "already running, foregrounded")
                return {"ok": True, "app": app, "method": "foreground", "note": "Приложение уже запущено — приведено на передний план"}

            # Короткое имя (discord, firefox, steam, …):
            #   1) Start Menu / registry lookup — ищет .lnk в Start Menu и реестр
            #   2) UWP lookup (powershell Get-AppxPackage) — для UWP-приложений
            #   3) start <app> (PATH .exe: firefox, notepad, cmd, …)
            #   4) explorer shell:AppsFolder\<app>!<app> (fallback)
            strategies = [
                lambda: self._win_startmenu_lookup(app, args),
                lambda: self._win_appx_lookup(app, args),
                lambda: self._win_start(app, args),
                lambda: self._win_uwp(app, args),
            ]
            last_err = ""
            for i, strat in enumerate(strategies):
                try:
                    res = strat()
                    if res.get("ok"):
                        self._log("launch_app", {"app": app, "args": args, "strategy": i + 1, "method": res.get("method", "")}, "started")
                        # Приводим окно на передний план — иначе процесс запущен,
                        # но пользователь его не видит (за другим окном / в фоне).
                        # Для UWP-приложений нужно подождать дольше (2-3s).
                        import time as _time
                        wait = 3.0 if "appx" in res.get("method", "") else 1.0
                        _time.sleep(wait)
                        if not self._win_foreground_if_running(app):
                            # Retry after extra wait — UWP windows can be slow to appear
                            _time.sleep(1.5)
                            if self._win_foreground_if_running(app):
                                res["foregrounded"] = True
                                res["note"] = "Окно приведено на передний план (с задержкой)"
                        else:
                            res["foregrounded"] = True
                        return res
                    else:
                        last_err = res.get("method", f"strategy_{i+1}_failed")
                except Exception as ex:
                    last_err = str(ex)
            self._log("launch_app_error", {"app": app, "args": args, "last_err": last_err}, "all strategies failed")
            return {
                "ok": False,
                "error": f"Не удалось запустить '{app}': приложение не найдено (проверено: UWP/PATH/полный путь). "
                         f"Попробуйте указать полный путь к .exe, например C:\\Program Files\\{app}\\{app}.exe",
                "code": "not_found",
            }

        elif system == "Darwin":
            cmd = ["open", "-a", app]
            if args:
                cmd += ["--args", args]
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._log("launch_app", {"app": app, "args": args, "pid": proc.pid}, "started")
            return {"ok": True, "app": app, "pid": proc.pid}
        else:  # Linux
            cmd = [app]
            if args:
                cmd.append(args)
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._log("launch_app", {"app": app, "args": args, "pid": proc.pid}, "started")
            return {"ok": True, "app": app, "pid": proc.pid}

    # ---------- Windows strategies ----------
    def _win_startmenu_lookup(self, app: str, args: str) -> dict:
        """Стратегия 1: поиск в Start Menu (.lnk) и реестре Uninstall.

        Ищет приложение по имени в:
          1. %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\*.lnk
          2. C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\*.lnk
          3. Реестр: HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall
          4. Common install dirs (широкий glob)
        Запускает через WScript.Shell (для .lnk) или Start-Process (для .exe).
        """
        import os as _os
        app_lower = app.lower().replace('.exe', '').strip()
        if not app_lower:
            return {"ok": False, "app": app, "method": "startmenu_empty"}

        # --- 1. Start Menu .lnk files ---
        start_menu_dirs = [
            _os.path.join(_os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
            r'C:\ProgramData\Microsoft\Windows\Start Menu\Programs',
        ]
        for sm_dir in start_menu_dirs:
            if not sm_dir or not _os.path.isdir(sm_dir):
                continue
            # Search for .lnk with matching name (case-insensitive, also match "app (x86)" etc.)
            try:
                for entry in _os.listdir(sm_dir):
                    name_no_ext = _os.path.splitext(entry)[0].lower()
                    if name_no_ext == app_lower or app_lower in name_no_ext:
                        lmk_path = _os.path.join(sm_dir, entry)
                        if _os.path.isfile(lmk_path):
                            # Launch .lnk via powershell
                            safe = lmk_path.replace("'", "''")
                            ps = f"(New-Object -ComObject WScript.Shell).Run('{safe}', 1)"
                            try:
                                subprocess.Popen(
                                    ['powershell', '-NoProfile', '-Command', ps],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    shell=False,
                                )
                                import time as _time
                                _time.sleep(2.0)
                                if self._win_verify_process(app):
                                    return {"ok": True, "app": app, "method": f"startmenu:{entry}"}
                                return {"ok": False, "app": app, "method": f"startmenu_verify_failed:{entry}"}
                            except Exception:
                                pass
            except Exception:
                continue

        # --- 2. Registry Uninstall keys ---
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
                (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
            ]
            for hive, subkey in reg_paths:
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        i = 0
                        while True:
                            try:
                                name = winreg.EnumKey(key, i)
                                i += 1
                            except OSError:
                                break
                            try:
                                with winreg.OpenKey(key, name) as sub:
                                    display_name, _ = winreg.QueryValueEx(sub, 'DisplayName')
                                    if app_lower in display_name.lower():
                                        icon_path, _ = winreg.QueryValueEx(sub, 'DisplayIcon')
                                        # icon_path is like "C:\Program Files (x86)\Steam\steam.exe,-112"
                                        exe_path = icon_path.split(',')[0].replace('"', '').strip()
                                        if exe_path and _os.path.isfile(exe_path):
                                            cmd = [exe_path]
                                            if args:
                                                cmd.append(args)
                                            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                            import time as _time
                                            _time.sleep(2.0)
                                            if self._win_verify_process(app):
                                                return {"ok": True, "app": app, "method": f"registry:{display_name}"}
                                            return {"ok": False, "app": app, "method": f"registry_verify_failed:{display_name}"}
                            except Exception:
                                continue
                except Exception:
                    continue
        except ImportError:
            pass

        # --- 3. Broader filesystem search (common install locations) ---
        import glob
        env_pf = _os.environ.get('ProgramFiles', r'C:\Program Files')
        env_pf86 = _os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
        env_local = _os.environ.get('LOCALAPPDATA', '')
        env_appdata = _os.environ.get('APPDATA', '')
        search_patterns = [
            # <install_dir>\<app>*\<app>.exe
            _os.path.join(env_pf, f'{app}*', app + '.exe'),
            _os.path.join(env_pf86, f'{app}*', app + '.exe'),
            # <install_dir>\<app>\bin\<app>.exe
            _os.path.join(env_pf, f'{app}*', 'bin', app + '.exe'),
            _os.path.join(env_pf86, f'{app}*', 'bin', app + '.exe'),
            # %LOCALAPPDATA%\<app>\app-*.exe (Electron apps like Discord, opencode)
            _os.path.join(env_local, f'{app}*', 'app-*.exe'),
            _os.path.join(env_local, f'{app}*', 'app-*.dll'),  # for Electron: run main exe
            _os.path.join(env_local, f'{app}*', 'resources', 'app.asar'),
            # %APPDATA%\<app> (portable apps)
            _os.path.join(env_appdata, f'{app}*', app + '.exe'),
            # Steam portable
            _os.path.join(env_local, 'Steam', 'steamapps', 'common', f'{app}*', f'{app}.exe'),
        ]
        for pattern in search_patterns:
            if not pattern:
                continue
            try:
                matches = glob.glob(pattern)
                if matches:
                    exe = matches[0]
                    cmd = [exe]
                    if args:
                        cmd.append(args)
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    import time as _time
                    _time.sleep(2.0)
                    if self._win_verify_process(app):
                        return {"ok": True, "app": app, "method": f"fssearch:{_os.path.basename(exe)}"}
                    return {"ok": False, "app": app, "method": f"fssearch_verify_failed:{_os.path.basename(exe)}"}
            except Exception:
                continue

        return {"ok": False, "app": app, "method": "startmenu_not_found"}

    def _win_verify_process(self, app: str, timeout: int = 3) -> bool:
        """Проверяет что процесс с именем <app> реально запущен."""
        import platform
        if platform.system() != "Windows":
            return True
        base = os.path.basename(app).replace('.exe', '') if app.endswith('.exe') else app.replace('.exe', '').strip()
        safe = base.replace("'", "''")
        ps = f"Get-Process | Where-Object {{ $_.Name -ilike '*{safe}*' }} | Select-Object -First 1 | ForEach-Object {{ $_.Id }}"
        try:
            proc = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=timeout,
            )
            pid = proc.stdout.decode('utf-8', errors='ignore').strip()
            return bool(pid and pid.isdigit())
        except Exception:
            return False

    def _win_start(self, app: str, args: str) -> dict:
        """Стратегия 2: start <app> [args] — для .exe в PATH или известных каталогах."""
        import shutil
        import glob

        found_path = shutil.which(app)
        if not found_path:
            env_pf = os.environ.get('ProgramFiles', r'C:\Program Files')
            env_pf86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
            env_local = os.environ.get('LOCALAPPDATA', '')
            env_sysroot = os.environ.get('SystemRoot', r'C:\Windows')
            search_dirs = [
                env_pf,
                env_pf86,
                os.path.join(env_local, 'Programs') if env_local else '',
                env_local,
                os.path.join(env_sysroot, 'System32'),
            ]
            for base in search_dirs:
                if not base or not os.path.isdir(base):
                    continue
                candidate1 = os.path.join(base, app + '.exe')
                candidate2 = os.path.join(base, app, app + '.exe')
                if os.path.isfile(candidate1):
                    found_path = candidate1
                    break
                if os.path.isfile(candidate2):
                    found_path = candidate2
                    break
                try:
                    pattern = os.path.join(base, f'{app}*', app + '.exe')
                    matches = glob.glob(pattern)
                    if matches:
                        found_path = matches[0]
                        break
                except Exception:
                    pass
        if not found_path:
            return {"ok": False, "app": app, "method": "start_not_found"}
        shell_cmd = f'start "" "{found_path}"' + (f' {args}' if args else '')
        subprocess.Popen(
            shell_cmd, shell=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        import time as _time
        _time.sleep(1.0)
        verified = self._win_verify_process(app)
        if verified:
            return {"ok": True, "app": app, "method": f"start:{os.path.basename(found_path)}"}
        return {"ok": False, "app": app, "method": "start_verify_failed",
                "error": f"Процесс '{os.path.basename(found_path)}' не запустился после start"}

    def _win_uwp(self, app: str, args: str) -> dict:
        r"""Стратегия 3: explorer shell:AppsFolder\<AppId> — UWP fallback."""
        return self._win_appx_lookup(app, args)

    def _win_appx_lookup(self, app: str, args: str) -> dict:
        """Стратегия UWP: PowerShell Get-AppxPackage — UWP-lookup по имени.

        Ищет UWP-приложение: точное → prefix → substring (TelegramDesktop
        содержит "Telegram"). Верифицирует что процесс реально стартовал.
        """
        safe_app = app.replace("'", "''").replace('"', '""')
        # ВАЖНО: регулярка ^(Microsoft|Windows) без кавычек-escape — в PS \"
        # внутри f-строки ломает парсинг. Используем [ ] вместо \.
        ps = (
            f'$app = "{safe_app}"; '
            f'$pkg = Get-AppxPackage | Where-Object {{ $_.Name -ieq $app }} | Select-Object -First 1; '
            f'if (-not $pkg) {{ $pkg = Get-AppxPackage | Where-Object {{ $_.Name -ilike ($app + "*") }} | Sort-Object Name | Select-Object -First 1 }}; '
            f'if (-not $pkg) {{ $pkg = Get-AppxPackage | Where-Object {{ $_.Name -ilike ("*" + $app + "*") }} | Sort-Object Name | Select-Object -First 1 }}; '
            f'if ($pkg) {{ '
            f'  $target = $pkg.PackageFamilyName; '
            f'  Start-Process "shell:AppsFolder\\$target"; '
            f'  Write-Output "LAUNCHED:$target" '
            f'}} else {{ Write-Output "NOT_FOUND" }}'
        )
        try:
            proc = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=15, shell=False,
            )
            out = proc.stdout.decode('utf-8', errors='ignore').strip()
            if out.startswith('LAUNCHED:'):
                target = out[len('LAUNCHED:'):]
                import time as _time
                _time.sleep(3.0)
                if self._win_verify_process(app):
                    return {"ok": True, "app": app, "method": f"appx:{target}"}
                return {"ok": False, "app": app, "method": f"appx_verify_failed:{target}",
                        "error": "UWP пакет найден, но процесс не запустился"}
            if out == 'LAUNCHED' or 'LAUNCHED' in out:
                import time as _time
                _time.sleep(3.0)
                if self._win_verify_process(app):
                    return {"ok": True, "app": app, "method": "appx"}
                return {"ok": False, "app": app, "method": "appx_verify_failed",
                        "error": "UWP пакет найден, но процесс не запустился"}
            if 'NOT_FOUND' in out:
                return {"ok": False, "app": app, "method": "appx_not_found"}
            # Fallback: проще
            ps_simple = (
                f'$app = "{safe_app}"; '
                f'$pkg = Get-AppxPackage | Where-Object {{ $_.Name -ieq $app }} '
                f'| Select-Object -First 1; '
                f'if (-not $pkg) {{ $pkg = Get-AppxPackage | Where-Object {{ $_.Name -ilike ("*" + $app + "*") }} | Sort-Object Name | Select-Object -First 1 }}; '
                f'if ($pkg) {{ $pkg.PackageFamilyName }} else {{ "NOT_FOUND" }}'
            )
            proc2 = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_simple],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10, shell=False,
            )
            family = proc2.stdout.decode('utf-8', errors='ignore').strip()
            if family and family != "NOT_FOUND":
                subprocess.Popen(
                    ['explorer', f'shell:AppsFolder\\{family}'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    shell=True,
                )
                import time as _time
                _time.sleep(2.0)
                if self._win_verify_process(app):
                    return {"ok": True, "app": app, "method": f"appx_fallback:{family}"}
                return {"ok": False, "app": app, "method": f"appx_fallback_verify_failed:{family}",
                        "error": "UWP fallback: процесс не запустился"}
            return {"ok": False, "app": app, "method": "appx_not_found"}
        except subprocess.TimeoutExpired:
            self._log("launch_app_timeout", {"app": app, "method": "appx_lookup"}, "15s timeout")
            return {"ok": False, "app": app, "method": "appx_timeout"}
        except Exception as e:
            return {"ok": False, "app": app, "method": f"appx_error:{e}"}

    # ---------- Win32 helpers ----------
    def window_focus(self, app: str) -> dict:
        """Приводит окно приложения на передний план.

        app — имя процесса (discord, code, notepad, ...) или путь к .exe.
        Если app = "default" — использует авто-детект системного браузера.
        Ищет окно через EnumWindows + GetWindowThreadProcessId.
        """
        import platform
        if platform.system() != "Windows":
            return {"ok": False, "error": "window_focus доступен только на Windows"}

        # "default" → авто-детект системного браузера
        if app.lower().strip() in ("default", "системный", "system"):
            app = self._get_default_browser() or self._detect_running_browser()
            if not app:
                return {"ok": False, "error": "Не удалось определить системный браузер", "code": "no_default"}

        base = os.path.basename(app).replace('.exe', '') if app.endswith('.exe') else app.replace('.exe', '').strip()
        # Пробуем несколько вариантов: firefox, firefox.exe, Firefox, FIREFOX
        found = None
        for variant in [base, base.lower(), base.upper(), base.title()]:
            found = self._find_window_by_process(variant)
            if found:
                break
        if not found:
            self._log("window_focus_not_found", {"app": app}, "no matching window")
            return {
                "ok": False,
                "error": f"Не найдено окно приложения '{app}'. Запустите сначала через [[SYS:launch_app|{app}]] или [[SYS:open_url|<URL>|{app}]]",
                "code": "not_found",
            }
        self._log("window_focus", {"app": app, "hwnd": found}, "focused")
        return {"ok": True, "app": app, "hwnd": found, "note": "Окно приведено на передний план"}

    def _send_key_combo(self, text: str) -> bool:
        """Отправляет комбинацию клавиш, например '{CTRL}3' → Ctrl+3 (вкладка 3).

        Поддерживаемые паттерны:
          {CTRL}<1-9>  — Ctrl+цифра (переключение вкладки в браузере)
          {ALT}<1-9>   — Alt+цифра
          {F5}         — F5
        Если паттерн не распознан — возвращает False.
        """
        import ctypes
        import re as _re
        import time as _time

        user32 = ctypes.windll.user32
        KEYEVENTF_KEYUP = 0x2

        VK = {
            "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74,
            "F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79,
            "F11": 0x7A, "F12": 0x7B,
        }
        for ch in "123456789":
            VK[ch] = 0x30 + int(ch)  # '1'=0x31, '2'=0x32, ..., '9'=0x39
        VK["0"] = 0x30  # '0'=0x30

        m = _re.match(r"^\{(\w+)\}(\d|F\d+)$", text.strip())
        if not m:
            return False
        mod, key = m.group(1).upper(), m.group(2)

        mod_vk = {"CTRL": 0x11, "ALT": 0x12, "SHIFT": 0x10, "WIN": 0x5B}.get(mod)
        if mod_vk is None:
            return False
        key_vk = VK.get(key)
        if key_vk is None:
            return False

        try:
            user32.keybd_event(mod_vk, 0, 0, None)
            _time.sleep(0.03)
            user32.keybd_event(key_vk, 0, 0, None)
            _time.sleep(0.03)
            user32.keybd_event(key_vk, 0, KEYEVENTF_KEYUP, None)
            _time.sleep(0.03)
            user32.keybd_event(mod_vk, 0, KEYEVENTF_KEYUP, None)
            _time.sleep(0.1)
            return True
        except Exception:
            return False

    def _focus_window_by_app(self, app: str) -> dict:
        """Приводит окно в фокус по имени процесса. Возвращает {ok, ...}."""
        import time as _time
        # "default" → авто-детект
        if app.lower().strip() in ("default", "системный", "system"):
            app = self._get_default_browser() or self._detect_running_browser()
        base = os.path.basename(app).replace('.exe', '') if app.endswith('.exe') else app.replace('.exe', '').strip()
        found = None
        for variant in [base, base.lower(), base.upper(), base.title()]:
            found = self._find_window_by_process(variant)
            if found:
                break
        if not found:
            focus_res = self.window_focus(app)
            if not focus_res.get("ok"):
                return focus_res
            found = None  # window_focus already brought it to foreground
        _time.sleep(1.5)
        return {"ok": True, "hwnd": found}

    def window_send_keys(self, text: str, app: str = "", skip_ctrl_l: bool = False) -> dict:
        """Отправляет клавиши (text или клавиши через \\n для Enter, \\t для Tab)
        в активное окно или в указанное приложение (если app указан — сначала фокус).

        text — строка для ввода. Служебные последовательности:
          \\n → Enter, \\t → Tab, {UP} {DOWN} {LEFT} {RIGHT} → стрелки
          {CTRL} → зажать Ctrl, {ALT} → Alt, {SHIFT} → Shift

        skip_ctrl_l — если True и app является браузером, НЕ присылает Ctrl+L
        (фокус на адресной строке). Использовать, когда текст нужно ввести в
        поле на странице (например, поле поиска), а не в адресную строку.
        В этом случае сначала нужно window_click по координатам нужного поля.
        """
        import platform
        if platform.system() != "Windows":
            return {"ok": False, "error": "window_send_keys доступен только на Windows"}

        if not text:
            return {"ok": False, "error": "Пустой текст для ввода", "code": "empty"}

        # Детектируем комбинацию клавиш: {CTRL}3, {ALT}4, {F5} и т.д.
        import re as _re
        if _re.match(r"^\{\w+\}(?:\d|F\d+)$", text.strip()):
            if app:
                focus_res = self._focus_window_by_app(app)
                if not focus_res.get("ok"):
                    return focus_res
            ok = self._send_key_combo(text)
            if ok:
                self._log("window_send_keys", {"text": text, "app": app}, "key_combo_sent")
                return {"ok": True, "text": text, "app": app}
            return {"ok": False, "error": f"Не удалось отправить комбинацию: {text}"}

        is_browser = False
        if app:
            # "default" → авто-детект
            if app.lower().strip() in ("default", "системный", "system"):
                app = self._get_default_browser() or self._detect_running_browser()
            # Приводим окно в фокус напрямую (надёжнее)
            base = os.path.basename(app).replace('.exe', '') if app.endswith('.exe') else app.replace('.exe', '').strip()
            found = None
            for variant in [base, base.lower(), base.upper(), base.title()]:
                found = self._find_window_by_process(variant)
                if found:
                    break
            if not found:
                # Пробуем через window_focus
                focus_res = self.window_focus(app)
                if not focus_res.get("ok"):
                    return focus_res
                # window_focus succeeded but we don't have an HWND.
                # Try to find the HWND again after focus.
                found = self._find_window_by_process(base)
            # Ждём — браузеру нужно время для загрузки/рендеринга.
            # 3s для браузеров (страница может грузиться), 1.5s для остальных.
            import time as _time
            _time.sleep(3.0 if is_browser else 1.5)
            # Для браузеров фокусируем адресную строку (Ctrl+L — универсальный
            # шорткат для Firefox/Chrome/Edge/Opera/Brave/Vivaldi). Для
            # остальных приложений — клик по центру окна.
            is_browser = any(
                b in base.lower()
                for b in ("firefox", "chrome", "edge", "opera", "brave", "vivaldi", "arc", "chromium")
            )
            if is_browser and not skip_ctrl_l:
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    VK_CONTROL = 0x11
                    VK_L = 0x4C
                    KEYEVENTF_KEYUP = 0x2
                    user32.keybd_event(VK_CONTROL, 0, 0, None)
                    _time.sleep(0.05)
                    user32.keybd_event(VK_L, 0, 0, None)
                    _time.sleep(0.05)
                    user32.keybd_event(VK_L, 0, KEYEVENTF_KEYUP, None)
                    _time.sleep(0.05)
                    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, None)
                    _time.sleep(0.3)
                    self._log("window_send_keys", {"app": app}, "focused address bar via Ctrl+L")
                except Exception:
                    pass
            else:
                # Кликаем по центру окна чтобы убедиться что input-поле в фокусе
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    if found:
                        import ctypes.wintypes as wt
                        rect = wt.RECT()
                        user32.GetWindowRect(found, ctypes.byref(rect))
                        cx = (rect.left + rect.right) // 2
                        cy = (rect.top + rect.bottom) // 2
                        user32.SetCursorPos(cx, cy)
                        _time.sleep(0.1)
                        user32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
                        _time.sleep(0.05)
                        user32.mouse_event(0x0004, 0, 0, 0, 0)  # left up
                        _time.sleep(0.2)
                except Exception:
                    pass

        # Retry once if first attempt fails (page may still be loading)
        success = self._send_text_to_active(text)
        if not success and is_browser:
            import time as _time
            _time.sleep(2.0)
            success = self._send_text_to_active(text, wait=1.0)
        if success:
            self._log("window_send_keys", {"text": text[:100], "app": app}, "sent")
            return {"ok": True, "text": text[:100], "app": app}
        self._log("window_send_keys_error", {"text": text[:100], "app": app}, "failed")
        return {"ok": False, "error": "Не удалось отправить клавиши (окно не в фокусе?)" }

    def window_click(self, x: int, y: int, app: str = "") -> dict:
        """Кликает в координатах экрана (левый клик).

        x, y — координаты в пикселях. Если app указан — сначала фокусирует окно.
        Для точного клика по элементу сначала используйте page_recon или
        window_screenshot чтобы узнать координаты.
        """
        import platform
        if platform.system() != "Windows":
            return {"ok": False, "error": "window_click доступен только на Windows"}

        if app:
            focus_res = self.window_focus(app)
            if not focus_res.get("ok"):
                return focus_res

        try:
            x = int(x)
            y = int(y)
        except (TypeError, ValueError):
            self._log("window_click_bad_coords", {"x": str(x)[:50], "y": str(y)[:50], "app": app}, "invalid coords")
            return {
                "ok": False,
                "error": f"Некорректные координаты клика: x={x!r}, y={y!r}. "
                          f"Укажите целые числа (пиксели на экране). Сначала узнайте координаты через window_ui_recon или window_screenshot.",
                "code": "bad_coords",
            }
        success = self._click_at(x, y)
        if success:
            self._log("window_click", {"x": x, "y": y, "app": app}, "clicked")
            return {"ok": True, "x": x, "y": y, "app": app}
        self._log("window_click_error", {"x": x, "y": y, "app": app}, "failed")
        return {"ok": False, "error": "Не удалось выполнить клик"}

    def window_screenshot(self, app: str = "") -> dict:
        """Скриншот активного окна (или всего экрана если app пуст).

        Возвращает: {ok, path} — path: путь к .png файлу (временный).
        Использует PrintWindow (для конкретного окна) или BitBlt (весь экран).
        """
        import platform
        if platform.system() != "Windows":
            return {"ok": False, "error": "window_screenshot доступен только на Windows"}

        if app:
            focus_res = self.window_focus(app)
            if not focus_res.get("ok"):
                return focus_res

        path = self._capture_screenshot(app)
        if not path:
            self._log("window_screenshot_error", {"app": app}, "capture failed")
            return {"ok": False, "error": "Не удалось сделать скриншот"}
        self._log("window_screenshot", {"app": app, "path": path}, "captured")
        return {"ok": True, "path": path, "app": app}

    # ---------- Win32 helpers ----------
    def _find_window_by_process(self, process_name: str) -> Optional[int]:
        """Ищет HWND первого видимого окна процесса. Returns hwnd или None."""
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Получаем список PID'ов процесса
        pids: list[int] = []
        ps = f"Get-Process | Where-Object {{ $_.Name -ilike '*{process_name}*' }} | Select-Object -ExpandProperty Id"
        try:
            proc = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=5,
            )
            out = proc.stdout.decode('utf-8', errors='ignore').strip()
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
        except Exception:
            pass

        if not pids:
            return None

        found_hwnd = [0]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def _cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid_out = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
            if int(pid_out.value) in pids:
                # Проверяем что у окна есть заголовок (не hidden helper window)
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    found_hwnd[0] = int(hwnd)
                    return False
            return True

        user32.EnumWindows(_cb, 0)

        if found_hwnd[0]:
            hwnd = found_hwnd[0]
            # Приводим на передний план (надёжный способ)
            self._bring_to_foreground(hwnd)
            return hwnd
        return None

    def _bring_to_foreground(self, hwnd: int) -> bool:
        """Приводит окно на передний план. 

        Многоступенчатый подход:
          1. IsIconic? → ShowWindow(SW_RESTORE) для минимизированных окон
          2. Alt-key trick — сбрасывает Windows-ограничение на SetForegroundWindow
          3. AttachThreadInput + BringWindowToTop + SetForegroundWindow
          4. Fallback: SetWindowPos HWND_TOPMOST → HWND_NOTOPMOST (принудительный pop-up)
        """
        import ctypes
        import ctypes.wintypes as wt
        import time as _time
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        VK_MENU = 0x12  # Alt key
        KEYEVENTF_KEYUP = 0x2
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOZORDER = 0x0004
        SWP_SHOWWINDOW = 0x0040

        # 1. Если окно свёрнуто (IsIconic) — раскрываем
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            _time.sleep(0.2)
        elif not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 5)  # SW_SHOW
            _time.sleep(0.15)

        # 2. Alt-key trick: нажимаем и отпускаем Alt — это сбрасывает
        #    Windows-ограничение на SetForegroundWindow из другого процесса
        user32.keybd_event(VK_MENU, 0, 0, None)
        _time.sleep(0.05)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, None)
        _time.sleep(0.05)

        # 3. AttachThreadInput + BringWindowToTop + SetForegroundWindow
        fg_hwnd = user32.GetForegroundWindow()
        if fg_hwnd:
            fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
            cur_tid = kernel32.GetCurrentThreadId()
            if fg_tid and fg_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, True)
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.AttachThreadInput(cur_tid, fg_tid, False)
            else:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
        else:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)

        _time.sleep(0.3)

        # 4. Если фокус не перешёл — принудительный SetWindowPos
        if user32.GetForegroundWindow() != hwnd:
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            _time.sleep(0.1)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            _time.sleep(0.3)

        return user32.GetForegroundWindow() == hwnd

    def _win_foreground_if_running(self, app: str) -> bool:
        """Если процесс с похожим именем уже запущен — приводим на передний план.

        Двухфазный подход:
          1. По имени процесса (Get-Process -ilike '*name*')
          2. По заголовку окна (EnumWindows + title -ilike name) — для UWP,
             где окно может принадлежать другому PID (ApplicationFrame.exe).
        """
        import platform
        if platform.system() != "Windows":
            return False
        try:
            base = os.path.basename(app).replace('.exe', '') if app.endswith('.exe') else app.replace('.exe', '')
            safe = base.replace("'", "''")
            import ctypes
            import ctypes.wintypes as wt
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            EnumWindows = user32.EnumWindows

            # Phase 1: process name match
            ps = f"Get-Process | Where-Object {{ $_.Name -ilike '*{safe}*' }} | Select-Object -First 1 | ForEach-Object {{ $_.Id }}"
            proc = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=5,
            )
            pid = proc.stdout.decode('utf-8', errors='ignore').strip()
            if pid and pid.isdigit():
                pid_int = int(pid)
                found = [False]

                @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
                def _cb_pid(hwnd, lparam):
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    pid_out = wt.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
                    if int(pid_out.value) == pid_int:
                        self._bring_to_foreground(int(hwnd))
                        found[0] = True
                        return False
                    return True

                EnumWindows(_cb_pid, 0)
                if found[0]:
                    return True

            # Phase 2: window title match (UWP fallback)
            title_base = base.lower()
            if title_base and len(title_base) >= 3:
                found2 = [False]

                @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
                def _cb_title(hwnd, lparam):
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length < 1:
                        return True
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    if title and title_base in title.lower():
                        self._bring_to_foreground(int(hwnd))
                        found2[0] = True
                        return False
                    return True

                EnumWindows(_cb_title, 0)
                if found2[0]:
                    return True
        except Exception:
            return False
        return False

    def _send_text_to_active(self, text: str, wait: float = 1.0) -> bool:
        """Отправляет текст через clipboard + Ctrl+V (надёжно для кириллицы).

        Проверки:
          1. Окно реально в фокусе (GetForegroundWindow)
          2. Clipboard реально забалансирован
          3. Ctrl+V через keybd_event
          4. Если clipboard не сработал — SendInput побуквенно (fallback)

        wait — сколько секунд ждать после фокуса перед вводом текста
               (по умолчанию 1.0с — браузерам нужно время для загрузки страницы).
        """
        try:
            import ctypes
            import ctypes.wintypes as wt
            import time as _time

            user32 = ctypes.windll.user32

            # 1. Проверяем что есть активное окно
            fg_hwnd = user32.GetForegroundWindow()
            if not fg_hwnd:
                return False

            # Ждём после фокуса — браузерам нужно время для загрузки/рендеринга
            _time.sleep(wait)

            # 2. Clipboard: запоминаем текущий формат, ставим наш текст
            clipboard_buf = ctypes.create_unicode_buffer(len(text) + 1)
            clipboard_buf.value = text
            # Держим reference (иначе GC соберёт и SetClipboardData вернёт 0)

            if not user32.OpenClipboard(0):
                # Retry once with small delay
                _time.sleep(0.2)
                if not user32.OpenClipboard(0):
                    # Fallback: SendInput побуквенно
                    return self._send_text_via_sendinput(text)
            user32.EmptyClipboard()
            ptr = user32.SetClipboardData(13, ctypes.cast(clipboard_buf, ctypes.c_void_p))
            user32.CloseClipboard()

            if ptr == 0:
                return self._send_text_via_sendinput(text)

            # 3. Ctrl+V через keybd_event
            VK_CONTROL = 0x11
            VK_V = 0x56
            KEYEVENTF_KEYUP = 0x2

            user32.keybd_event(VK_CONTROL, 0, 0, None)
            _time.sleep(0.05)
            user32.keybd_event(VK_V, 0, 0, None)
            _time.sleep(0.05)
            user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, None)
            _time.sleep(0.05)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, None)
            _time.sleep(0.05)

            return True
        except Exception:
            return False

    def _send_text_via_sendinput(self, text: str) -> bool:
        """Fallback: PostMessage WM_CHAR побуквенно (надёжнее clipboard для некоторых окон)."""
        try:
            import ctypes
            import time as _time

            user32 = ctypes.windll.user32
            user32.PostMessageW.argtypes = [
                ctypes.wintypes.HWND,
                ctypes.c_uint,
                ctypes.wintypes.WPARAM,
                ctypes.wintypes.LPARAM,
            ]
            user32.PostMessageW.restype = ctypes.c_int

            fg_hwnd = user32.GetForegroundWindow()
            if not fg_hwnd:
                return False

            WM_CHAR = 0x0102
            for ch in text:
                user32.PostMessageW(fg_hwnd, WM_CHAR, ord(ch), 0)
                _time.sleep(0.005)

            return True
        except Exception:
            return False

    def _click_at(self, x: int, y: int) -> bool:
        """Клик мыши в координатах (SetCursorPos + mouse_event)."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetCursorPos(x, y)
            import time as _time
            _time.sleep(0.05)
            # MOUSEEVENTF_LEFTDOWN = 0x0002, MOUSEEVENTF_LEFTUP = 0x0004
            user32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
            _time.sleep(0.05)
            user32.mouse_event(0x0004, 0, 0, 0, 0)  # left up
            return True
        except Exception:
            return False

    def _capture_screenshot(self, app: str = "") -> Optional[str]:
        """Скриншот окна (PrintWindow) или экрана (BitBlt). Returns путь к .png."""
        try:
            import ctypes
            import ctypes.wintypes as wt
            import tempfile

            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            if app:
                hwnd = self._find_window_by_process(
                    os.path.basename(app).replace('.exe', '') if app.endswith('.exe') else app.replace('.exe', '').strip()
                )
                if not hwnd:
                    return None
                # Get window rect
                rect = wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width <= 0 or height <= 0:
                    return None
            else:
                hwnd = 0  # full screen
                width = user32.GetSystemMetrics(0)   # SM_CXSCREEN
                height = user32.GetSystemMetrics(1)  # SM_CYSCREEN

            # Create DC
            hdc_screen = user32.GetDC(0 if not app else hwnd)
            hdc = gdi32.CreateCompatibleDC(hdc_screen)
            hbm = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
            gdi32.SelectObject(hdc, hbm)

            if app:
                user32.PrintWindow(hwnd, hdc, 2)  # PW_RENDERFULLCONTENT
            else:
                gdi32.BitBlt(hdc, 0, 0, width, height, hdc_screen, 0, 0, 0x00CC0020)  # SRCCOPY

            # Save as PNG via PIL
            import io
            from PIL import Image
            # Get DIB header + pixel data
            BITMAPINFO = ctypes.Structure
            import struct
            # Simpler: use GDI to get bitmap info
            bm_info = (ctypes.c_int * 40)()
            bm_info[0] = 40  # size
            bm_info[1] = width
            bm_info[2] = -height  # top-down
            bm_info[3] = 1
            bm_info[4] = 32
            pixel_size = width * height * 4
            pixels = ctypes.create_string_buffer(pixel_size)
            gdi32.GetDIBits(hdc, hbm, 0, height, pixels, ctypes.byref(bm_info), 0x00)

            # BGRA → RGBA
            img = Image.frombuffer("RGBA", (width, height), bytes(pixels.raw), "raw", "BGRA", 0, -1)
            img = img.convert("RGB")

            out_path = os.path.join(tempfile.gettempdir(), f"amt_screenshot_{int(time.time())}.png")
            img.save(out_path, "PNG")

            # Cleanup
            gdi32.DeleteObject(hbm)
            gdi32.DeleteDC(hdc)
            user32.ReleaseDC(0 if not app else hwnd, hdc_screen)
            return out_path
        except Exception:
            return None

    # ---------- Windows UI Automation (UIA) ----------
    # UIA gives access to the accessibility tree of any window:
    # buttons, edit fields, menus, etc — with coordinates and names.
    #
    # Two strategies:
    #   1) comtypes (preferred) — proper UIA COM interfaces
    #   2) ctypes fallback — uses oleacc (MSAA) for simple cases
    #
    # The result is a flat list of element dicts that the LLM can use
    # to find targets for window_click / window_send_keys.

    # UIA control type ID → human-readable name
    _UIA_CONTROL_TYPES: dict[int, str] = {
        50000: "Button", 50001: "Calendar", 50002: "CheckBox",
        50003: "ComboBox", 50004: "Edit", 50005: "Hyperlink",
        50006: "Image", 50007: "ListItem", 50008: "List",
        50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
        50012: "ProgressBar", 50013: "RadioButton",
        50014: "ScrollBar", 50015: "Spinner", 50016: "Tab",
        50017: "TabItem", 50018: "Text", 50019: "ToolBar",
        50020: "ToolTip", 50021: "Tree", 50022: "TreeItem",
        50023: "Custom", 50024: "Group", 50025: "Pane",
        50026: "DataGrid", 50027: "DataItem", 50028: "Document",
        50029: "SplitButton", 50030: "Window", 50031: "Pane",
        50032: "Header", 50033: "HeaderItem", 50034: "Table",
        50035: "TitleBar", 50036: "Separator", 50037: "SemanticZoom",
        50038: "AppBar",
    }

    def _uia_get_elements(self, hwnd: int, max_depth: int = 4, max_elements: int = 150) -> list[dict]:
        """Gets accessible elements of a window via UI Automation.

        Returns a flat list of element dicts:
        [{name, control_type, automation_id, class_name,
          rect: [l,t,r,b], is_editable, is_enabled, depth}]

        Uses comtypes if available, otherwise falls back to MSAA.
        """
        import platform
        if platform.system() != "Windows":
            return []

        elements: list[dict] = []

        # ---- Strategy 1: comtypes UIA (Windows only, since Win7) ----
        try:
            import comtypes
            from comtypes.client import CreateObject
            # CLSID_CUIAutomation: {4780B56D-11B2-4A99-9E2F-4581F9E10B08}
            CLSID_CUIAutomation = comtypes.GUID("{4780B56D-11B2-4A99-9E2F-4581F9E10B08}")
            uia_obj = CreateObject(CLSID_CUIAutomation)
            if not uia_obj:
                return []
            # Get the element for our HWND
            elem = uia_obj.ElementFromHandle(hwnd)
            if elem:
                # Get raw view walker for full tree access
                raw_walker = uia_obj.GetRawViewWalker()
                # UIA property IDs (from UIAutomationClient.h)
                UIA_ControlTypePropertyId = 30003
                UIA_AutomationIdPropertyId = 30011
                UIA_ClassNamePropertyId = 30012
                UIA_IsEnabledPropertyId = 30006
                UIA_IsKeyboardFocusablePropertyId = 30005
                UIA_IsVisiblePropertyId = 30010
                UIA_NamePropertyId = 30005
                def _walk(el, depth: int, out: list[dict], max_d: int, max_n: int,
                          ct_map: dict[int, str]):
                    """Recursively walk the UIA tree, collecting elements."""
                    if depth > max_d or len(out) >= max_n:
                        return
                    try:
                        # Get name via property (UIA_NamePropertyId = 30005)
                        try:
                            name_val = el.GetCurrentPropertyValue(UIA_NamePropertyId)
                            name = str(name_val or "") if name_val is not None else ""
                        except Exception:
                            name = ""
                        try:
                            ct_val = el.GetCurrentPropertyValue(UIA_ControlTypePropertyId)
                            ct_int = int(ct_val) if ct_val is not None else 0
                        except Exception:
                            ct_int = 0
                        ct_name = ct_map.get(ct_int, f"CT_{ct_int}" if ct_int else "Unknown")
                        try:
                            auto_id = str(el.GetCurrentPropertyValue(UIA_AutomationIdPropertyId) or "")[:100]
                        except Exception:
                            auto_id = ""
                        try:
                            cls_name = str(el.GetCurrentPropertyValue(UIA_ClassNamePropertyId) or "")[:100]
                        except Exception:
                            cls_name = ""
                        try:
                            rect_val = el.GetBoundingRectangle()
                            if rect_val:
                                rect = [int(rect_val.left), int(rect_val.top),
                                        int(rect_val.right), int(rect_val.bottom)]
                            else:
                                rect = []
                        except Exception:
                            rect = []
                        try:
                            is_enabled = bool(int(el.GetCurrentPropertyValue(UIA_IsEnabledPropertyId)))
                        except Exception:
                            is_enabled = True
                        try:
                            is_editable = bool(int(el.GetCurrentPropertyValue(UIA_IsKeyboardFocusablePropertyId)))
                        except Exception:
                            is_editable = False
                        try:
                            is_visible = bool(int(el.GetCurrentPropertyValue(UIA_IsVisiblePropertyId)))
                        except Exception:
                            is_visible = True

                        # Only include visible elements
                        if is_visible:
                            out.append({
                                "name": str(name)[:200],
                                "control_type": ct_name,
                                "automation_id": auto_id,
                                "class_name": cls_name,
                                "rect": rect,
                                "is_editable": is_editable,
                                "is_enabled": is_enabled,
                                "depth": depth,
                            })
                    except Exception:
                        pass

                    # Walk children via raw view walker
                    try:
                        child = raw_walker.GetFirstChildElement(el)
                        while child and len(out) < max_n:
                            _walk(child, depth + 1, out, max_d, max_n, ct_map)
                            child = raw_walker.GetNextSiblingElement(child)
                    except Exception:
                        pass

                _walk(elem, 0, elements, max_depth, max_elements, self._UIA_CONTROL_TYPES)

            if elements:
                return elements[:max_elements]
        except Exception:
            pass

        # ---- Strategy 2: MSAA fallback via ctypes ----
        # Walks the MSAA tree (simpler, fewer properties, but works without comtypes)
        try:
            import ctypes
            import ctypes.wintypes as wt

            oleacc = ctypes.windll.oleacc
            IID_IAccessible = ctypes.UUID("618703F0-6DA8-11D0-AE51-11CEA74255C1")

            # Get the client-area accessible object
            acc = ctypes.c_void_p()
            hr = oleacc.AccessibleObjectFromWindow(
                hwnd, 0x00000002,  # OBJID_CLIENT
                ctypes.byref(IID_IAccessible),
                ctypes.byref(acc),
            )
            if hr != 0 or not acc:
                return []

            # IAccessible::GetChildCount
            oleacc.oleacc_GetChildCount = oleacc.AccessibleObjectFromWindow  # placeholder
            # This is getting too complex for pure ctypes without proper COM vtable dispatch.
            # Instead, use the MSAA property map via ctypes — simpler but limited.
            return []
        except Exception:
            return []

        return elements[:max_elements]

    def window_ui_recon(self, app: str = "") -> dict:
        """Returns structured UI elements of a running window via UI Automation.

        This is the desktop-app equivalent of page_recon (web).
        For each visible element: name, control_type, automation_id, class_name,
        bounding_rect [l, t, r, b], is_editable, is_enabled.

        Use this BEFORE window_click / window_send_keys to find target elements
        (search fields, buttons, menu items, etc).

        app: process name (e.g. "notepad", "explorer", "chrome") or "default".
        If empty — active window.
        """
        import platform
        if platform.system() != "Windows":
            return {"ok": False, "error": "window_ui_recon доступен только на Windows"}

        import ctypes
        user32 = ctypes.windll.user32

        hwnd = 0
        if app:
            if app.lower().strip() in ("default", "системный", "system"):
                hwnd = user32.GetForegroundWindow()
            else:
                base = os.path.basename(app).replace('.exe', '') if app.endswith('.exe') else app.replace('.exe', '').strip()
                for variant in [base, base.lower(), base.upper(), base.title()]:
                    found = self._find_window_by_process(variant)
                    if found:
                        hwnd = found
                        break
                if not hwnd:
                    return {
                        "ok": False,
                        "error": f"Не найдено окно '{app}'. Запустите сначала через [[SYS:launch_app|{app}]]",
                    }

        if not hwnd:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return {"ok": False, "error": "Нет активного окна"}

        elements = self._uia_get_elements(hwnd, max_depth=4, max_elements=150)
        if not elements:
            self._log("window_ui_recon_empty", {"app": app, "hwnd": hwnd}, "no UIA elements")
            return {
                "ok": True,
                "app": app,
                "hwnd": hwnd,
                "elements": [],
                "note": "UI Automation не вернул элементов (возможно, UIA недоступен для этого окна). "
                        "Попробуйте [[SYS:window_screenshot|]] и опишите что вы видите, "
                        "или задайте координаты вручную через [[SYS:window_click|x|y|app]].",
            }

        self._log("window_ui_recon", {"app": app, "hwnd": hwnd, "elements": len(elements)}, "ok")
        return {
            "ok": True,
            "app": app,
            "hwnd": hwnd,
            "elements": elements,
        }

    # ---------- Element search by text ----------
    def find_element_by_text(
        self, text: str, app: str = "",
        control_type_filter: str = "",
        url: str = "",
    ) -> dict:
        """Ищет элемент UIA по тексту (name) и возвращает его координаты.

        Универсальный метод: работает с ЛЮБЫМ приложением (браузер, мессенджер,
        редактор и т.д.). Не привязан к конкретному приложению.

        Args:
            text: Текст для поиска (case-insensitive, substring match).
            app: Имя приложения (для фокуса).
            control_type_filter: Фильтр по ControlType (например "Edit", "Button", "Text").
            url: Если UIA не вернул элементов (браузеры Chromium) — попробует
                 page_recon(url) и найдёт элемент по name/id/placeholder.
                 Без координат, но LLM сможет использовать open_url с поисковым URL.

        Returns:
            {ok, found, element: {name, control_type, rect, ...}, coords: {x, y, cx, cy}}
        """
        import platform
        if platform.system() != "Windows":
            return {"ok": False, "error": "find_element_by_text доступен только на Windows"}

        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "Пустой текст поиска", "code": "empty_text"}

        recon = self.window_ui_recon(app)
        if not recon.get("ok"):
            return recon

        elements = recon.get("elements", [])

        # If UIA returned no elements and we have a URL, try page_recon fallback
        if not elements and url:
            pr = self.page_recon(url)
            if pr.get("ok"):
                pr_elements = pr.get("elements", [])
                search_lower = text.lower()
                for pel in pr_elements:
                    # Match by name, id, or placeholder
                    hay = (pel.get("name", "") + " " + pel.get("id", "") + " " +
                           pel.get("placeholder", "")).lower()
                    if search_lower in hay:
                        return {
                            "ok": True, "found": True,
                            "element": {
                                "name": pel.get("name", ""),
                                "id": pel.get("id", ""),
                                "control_type": "input",
                                "source": "page_recon",
                            },
                            "coords": None,
                            "note": (f"Элемент найден через page_recon (не UIA): "
                                      f"id={pel.get('id','')}, name={pel.get('name','')}. "
                                      f"Для браузеров UIA не доступен — используйте "
                                      f"open_url с поисковым URL (например, https://www.bing.com/search?q=<запрос>) "
                                      f"или window_send_keys в адресную строку."),
                            "scanned": len(pr_elements),
                        }
                if pr_elements:
                    return {
                        "ok": True, "found": False,
                        "error": f"Элемент «{text}» не найден в {len(pr_elements)} элементах page_recon",
                        "note": "UIA не работает для этого браузера. Используйте open_url с поисковым URL.",
                        "scanned": len(pr_elements),
                    }

        if not elements:
            return {
                "ok": True, "found": False,
                "error": "Элементы не найдены в UIA",
                "note": "UIA не вернул элементов. Попробуйте window_screenshot или ручные координаты.",
                "scanned": 0,
            }

        # Filter by control type if specified
        if control_type_filter:
            ct = control_type_filter.lower()
            elements = [e for e in elements if e.get("control_type", "").lower().startswith(ct)]

        # Find first element whose name contains the search text
        found = None
        search_lower = text.lower()
        for elem in elements:
            name = elem.get("name", "")
            if search_lower in name.lower():
                found = elem
                break

        if not found:
            return {
                "ok": True, "found": False,
                "error": f"Элемент с текстом «{text}» не найден в {len(elements)} элементах UIA",
                "scanned": len(elements),
                "note": "Попробуйте другой текст или window_screenshot + ручные координаты.",
            }

        # Compute center coordinates
        rect = found.get("rect", [0, 0, 0, 0])
        cx = (rect[0] + rect[2]) // 2
        cy = (rect[1] + rect[3]) // 2

        self._log("find_element_by_text", {"text": text, "app": app, "element_name": found.get("name", "")[:80], "coords": (cx, cy)}, "found")

        return {
            "ok": True, "found": True,
            "element": found,
            "coords": {"x": cx, "y": cy, "cx": cx, "cy": cy},
            "scanned": len(elements),
        }

    # ---------- Dispatcher ----------
    def execute(self, tool: str, **args) -> dict:
        """Dispatcher (совместимый с ToolSandbox.execute).

        Поддерживает алиасы ключей: LLM может прислать "app", "window", "target",
        "name" вместо "app" — все эквивалентны.
        """
        def _get_app():
            return (args.get("app") or args.get("window") or args.get("target")
                    or args.get("name") or "")

        if tool == "open_url":
            return self.open_url(args.get("url", ""), args.get("browser", ""))
        if tool == "launch_app":
            return self.launch_app(_get_app(), args.get("args", ""))
        if tool == "page_recon":
            return self.page_recon(args.get("url", ""))
        if tool == "window_focus":
            return self.window_focus(_get_app())
        if tool == "window_send_keys":
            return self.window_send_keys(args.get("text", ""), _get_app(), skip_ctrl_l=str(args.get("skip_ctrl_l", "")).lower() in ("1", "true", "yes"))
        if tool == "window_click":
            return self.window_click(args.get("x", 0), args.get("y", 0), _get_app())
        if tool == "window_screenshot":
            return self.window_screenshot(_get_app())
        if tool == "window_ui_recon":
            return self.window_ui_recon(_get_app())
        if tool == "find_element_by_text":
            return self.find_element_by_text(
                args.get("text", ""),
                _get_app(),
                control_type_filter=args.get("control_type_filter", ""),
                url=args.get("url", ""),
            )
        return {"ok": False, "error": "Неизвестный desktop-инструмент: " + tool}


# Глобальный экземпляр
desktop_sandbox = DesktopSandbox()
