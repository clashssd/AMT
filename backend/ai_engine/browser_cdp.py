"""CDP-реконноосансраузеров Chromium через Chrome DevTools Protocol.

Вместо httpx page_recon (который не видит JS-отрендеренную страницу)
эти функции подключаются к запущенному Chromium-браузеру через
--remote-debugging-port и извлекают элементы через CDP/Playwright.

Поддерживает ЛЮБОЙ Chromium-браузер: Chrome, Edge, Brave, Yandex, Chromium, Opera.
Не хардкодим конкретный браузер — детектим по списку CHROMIUM_BROWSERS.

Требования:
  - Браузер запущен с флагом --remote-debugging-port=9222
  - Установлен playwright (pip install playwright)

Использование:
    from ai_engine.browser_cdp import launch_chromium_cdp, cdp_recon, cdp_click, cdp_fill
    result = launch_chromium_cdp("edge", "https://example.com")
    elements = cdp_recon()
"""

import json
import logging
import os
import platform
import subprocess
import time
from typing import Optional

logger = logging.getLogger("amt-browser-cdp")

# ---------- Detektsiya Chromium-based browsers ----------
# List of known Chromium-based browsers and their executable names.
# This is a DETECTION list, not a restriction — any Chromium browser works.
CHROMIUM_BROWSERS: list[dict] = [
    {"name": "edge", "exe": "msedge.exe", "reg_key": r"SOFTWARE\Microsoft\EdgeUpdate\Install"},
    {"name": "chrome", "exe": "chrome.exe", "reg_key": r"SOFTWARE\Google\Update\Install\Google\\Chrome"},
    {"name": "brave", "exe": "brave.exe", "reg_key": r"SOFTWARE\BraveSoftware\Brave-Browser"},
    {"name": "yandex", "exe": "YandexBrowser.exe", "reg_key": r"SOFTWARE\Yandex\YandexBrowser"},
    {"name": "chromium", "exe": "chromium.exe", "reg_key": ""},
    {"name": "opera", "exe": "opera.exe", "reg_key": r"SOFTWARE\Opera Software\Opera Stable"},
    {"name": "vivaldi", "exe": "Vivaldi.exe", "reg_key": r"SOFTWARE\Vivaldi"},
    {"name": "arc", "exe": "arc.exe", "reg_key": r"SOFTWARE\Arc\Arc"},
    {"name": "kometa", "exe": "Kometa.exe", "reg_key": ""},
]

CDP_PORT = 9222
CDP_ENDPOINT = f"http://127.0.0.1:{CDP_PORT}"


def _is_chromium(name: str) -> bool:
    """Checks if a browser name is Chromium-based."""
    name_lower = (name or "").lower().replace(".exe", "").strip()
    return any(c["name"] == name_lower for c in CHROMIUM_BROWSERS) or \
           any(name_lower in c["name"] for c in CHROMIUM_BROWSERS)


def _find_chromium_exe(name: str) -> Optional[str]:
    """Find the executable path for a Chromium-based browser.

    Searches:
      1. Registry Uninstall keys (DisplayName matching name)
      2. Common install directories
      3. PATH
    """
    import shutil
    import os as _os

    name_lower = (name or "").lower().replace(".exe", "").strip()
    if not name_lower:
        return None

    # Try PATH first (fastest)
    found = shutil.which(name_lower) or shutil.which(name_lower + ".exe")
    if found:
        return found

    # Common install dirs (Chromium browsers often in LOCALAPPDATA or ProgramFiles)
    env_pf = _os.environ.get("ProgramFiles", r"C:\Program Files")
    env_pf86 = _os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    env_local = _os.environ.get("LOCALAPPDATA", "")

    # Known Chromium exe names to try
    chromium_exes = ["chrome.exe", "msedge.exe", "brave.exe", "YandexBrowser.exe",
                     "chromium.exe", "opera.exe", "Vivaldi.exe", "arc.exe"]
    for exe in chromium_exes:
        for base in [env_pf, env_pf86, env_local]:
            if not base:
                continue
            candidate = _os.path.join(base, exe)
            if _os.path.isfile(candidate):
                return candidate
            # Subdirectory pattern: <base>\<vendor>\<exe>
            import glob
            for pattern in [
                _os.path.join(base, f"*{name_lower}*", exe),
                _os.path.join(base, f"*{name_lower}*", f"*{name_lower}*.exe"),
            ]:
                matches = glob.glob(pattern)
                if matches:
                    return matches[0]

    # Fallback: registry Uninstall
    try:
        import winreg
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
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
                                display_name, _ = winreg.QueryValueEx(sub, "DisplayName")
                                if name_lower in display_name.lower():
                                    icon_path, _ = winreg.QueryValueEx(sub, "DisplayIcon")
                                    exe_path = icon_path.split(",")[0].replace('"', "").strip()
                                    if exe_path and _os.path.isfile(exe_path):
                                        return exe_path
                        except Exception:
                            continue
            except Exception:
                continue
    except ImportError:
        pass

    return None


def _get_user_data_dir(browser_name: str) -> str:
    """Get (or create) the user-data-dir for a CDP-managed browser instance.

    Uses %LOCALAPPDATA%/AMT/profile_<name> to isolate browser profiles
    per browser type, so multiple CDP sessions can coexist.
    """
    env_local = os.environ.get("LOCALAPPDATA", "")
    profile_dir = os.path.join(env_local, "AMT", f"profile_{browser_name.lower()}")
    os.makedirs(profile_dir, exist_ok=True)
    return profile_dir


def _is_cdp_alive(browser_name: str = "") -> bool:
    """Check if a CDP endpoint is reachable on the given browser's port.

    If browser_name is empty, checks the default CDP_PORT.
    """
    import httpx
    try:
        r = httpx.get(f"{CDP_ENDPOINT}/json/version", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _wait_for_cdp(timeout: float = 10.0) -> bool:
    """Wait for CDP endpoint to become available. Polls every 0.5s."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_cdp_alive():
            return True
        time.sleep(0.5)
    return False


def launch_chromium_cdp(
    browser_name: str = "",
    url: str = "",
    port: int = CDP_PORT,
) -> dict:
    """Launch a Chromium-based browser with CDP debugging enabled.

    Args:
        browser_name: Name of the browser (edge, chrome, brave, yandex, etc).
                      If empty, uses the default system browser.
        url: URL to open (empty = new tab / homepage).
        port: CDP debugging port (default 9222).

    Returns:
        {"ok": bool, "browser": str, "pid": int, "cdp_endpoint": str, ...}
    """
    if platform.system() != "Windows":
        return {"ok": False, "error": "CDP launch is Windows-only"}

    # If browser_name is empty or "default", use the system default
    if not browser_name or browser_name.lower() in ("default", "системный", "system"):
        browser_name = _detect_default_chromium() or "edge"

    exe = _find_chromium_exe(browser_name)
    if not exe:
        return {
            "ok": False,
            "error": f"Chromium browser '{browser_name}' not found on this system",
            "code": "browser_not_found",
        }

    profile_dir = _get_user_data_dir(browser_name)
    cmd = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if url:
        cmd.append(url)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        return {"ok": False, "error": str(e), "code": "launch_failed"}

    logger.info("Launched %s (pid=%d, CDP port=%d)", browser_name, proc.pid, port)

    # Wait for CDP to become available
    cdp_ok = _wait_for_cdp(timeout=10.0)
    result = {
        "ok": cdp_ok,
        "browser": browser_name,
        "pid": proc.pid,
        "cdp_endpoint": CDP_ENDPOINT,
        "port": port,
    }
    if not cdp_ok:
        result["note"] = "Browser launched but CDP endpoint not reachable (check firewall/port)"
    return result


def _detect_default_chromium() -> str:
    """Detect the default Chromium-based browser on this system."""
    try:
        import winreg
        import re as _re

        # Check UrlAssociations for https
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
        ) as key:
            prog_id, _ = winreg.QueryValueEx(key, "ProgId")
            # Map ProgId to browser name
            prog_map = {
                "MSEdgeHTM": "edge",
                "ChromeHTML": "chrome",
                "BraveHTML": "brave",
            }
            if prog_id in prog_map:
                return prog_map[prog_id]
            # Try to extract from ProgId
            m = _re.match(r"^([A-Za-z]+)", prog_id)
            if m:
                candidate = m.group(1).lower()
                for c in CHROMIUM_BROWSERS:
                    if c["name"] == candidate:
                        return candidate
    except Exception:
        pass
    return "edge"  # sensible default


def _get_cdp_session() -> Optional[dict]:
    """Get a Playwright CDP session to the running browser.

    Returns {"browser": Browser, "context": BrowserContext} or None.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("playwright not installed (pip install playwright)")
        return None

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_ENDPOINT)
        return {"playwright": pw, "browser": browser}
    except Exception as e:
        logger.warning("CDP connect failed: %s", e)
        pw.stop()
        return None


def _close_cdp_session(session: Optional[dict]) -> None:
    """Close a CDP session."""
    if not session:
        return
    try:
        session.get("browser").close()
    except Exception:
        pass
    try:
        session.get("playwright").stop()
    except Exception:
        pass


def cdp_recon(url: str = "") -> dict:
    """Recon a page via CDP: get title, URL, and interactive elements.

    If url is provided, navigates to it first. Otherwise, uses the
    current active tab.

    Returns:
        {"ok": bool, "url": str, "title": str, "elements": [{...}], ...}
    """
    session = _get_cdp_session()
    if not session:
        return {"ok": False, "error": "CDP connection unavailable (is browser running with --remote-debugging-port?)", "code": "cdp_unavailable"}

    try:
        browser = session["browser"]
        contexts = browser.contexts
        if not contexts:
            return {"ok": False, "error": "No browser context found", "code": "no_context"}

        context = contexts[0]
        if url:
            page = context.new_page()
            page.goto(url, timeout=15000)
            page.wait_for_load_state("networkidle", timeout=10000)
        else:
            if not context.pages:
                return {"ok": False, "error": "No open pages in browser", "code": "no_pages"}
            page = context.pages[0]

        title = page.title()
        current_url = page.url

        # Extract interactive elements
        elements = []
        # Buttons
        buttons = page.query_selector_all("button, [role=button], input[type=submit]")
        for btn in buttons[:30]:
            text = (btn.inner_text() or "").strip()[:100]
            btn_id = btn.get_attribute("id") or ""
            btn_class = (btn.get_attribute("class") or "").strip()
            if text or btn_id:
                elements.append({
                    "type": "button",
                    "text": text,
                    "id": btn_id,
                    "class": btn_class[:100],
                    "selector": _build_selector(btn, page),
                })

        # Inputs
        inputs = page.query_selector_all("input:not([type=hidden]), textarea")
        for inp in inputs[:30]:
            tag = inp.evaluate("el => el.tagName").lower()
            inp_type = (inp.get_attribute("type") or "text").lower()
            inp_id = inp.get_attribute("id") or ""
            inp_name = inp.get_attribute("name") or ""
            inp_placeholder = inp.get_attribute("placeholder") or ""
            elements.append({
                "type": "input" if tag == "input" else "textarea",
                "input_type": inp_type,
                "id": inp_id,
                "name": inp_name,
                "placeholder": inp_placeholder,
                "selector": _build_selector(inp, page),
            })

        # Links
        links = page.query_selector_all("a[href]")
        link_list = []
        for link in links[:30]:
            href = link.get_attribute("href") or ""
            text = (link.inner_text() or "").strip()[:100]
            if href and not href.startswith("javascript:"):
                link_list.append({"href": href, "text": text})

        # Images
        images = page.query_selector_all("img[src]")
        for img in images[:20]:
            src = img.get_attribute("src") or ""
            alt = (img.get_attribute("alt") or "").strip()[:200]
            if src:
                elements.append({
                    "type": "image",
                    "src": src[:300],
                    "alt": alt,
                    "selector": _build_selector(img, page),
                })

        # Videos
        videos = page.query_selector_all("video")
        for vid in videos[:10]:
            vid_src = vid.get_attribute("src") or ""
            elements.append({
                "type": "video",
                "src": vid_src[:300],
                "controls": vid.get_attribute("controls") is not None,
                "selector": _build_selector(vid, page),
            })

        if url:
            page.close()

        logger.info("CDP recon: %s (%d elements, %d links)", current_url, len(elements), len(link_list))

        return {
            "ok": True,
            "url": current_url,
            "title": title,
            "elements": elements,
            "links": link_list,
            "method": "cdp",
        }
    except Exception as e:
        logger.warning("CDP recon error: %s", e)
        return {"ok": False, "error": str(e), "code": "cdp_error"}
    finally:
        _close_cdp_session(session)


def _build_selector(el, page) -> str:
    """Build a CSS selector for a Playwright element handle."""
    try:
        # Use the element's own id if available
        el_id = el.get_attribute("id")
        if el_id:
            return f"#{el_id}"
        # Use name attribute
        el_name = el.get_attribute("name")
        if el_name:
            tag = el.evaluate("el => el.tagName").lower()
            return f'{tag}[name="{el_name}"]'
        # Use placeholder
        el_ph = el.get_attribute("placeholder")
        if el_ph:
            tag = el.evaluate("el => el.tagName").lower()
            return f'{tag}[placeholder="{el_ph}"]'
        # Fallback: nth-of-type
        tag = el.evaluate("el => el.tagName").lower()
        index = el.evaluate(
            "el => Array.from(el.parentElement.children).filter(c => c.tagName === el.tagName).indexOf(el)"
        )
        return f"{tag}:nth-child({index + 1})"
    except Exception:
        return ""


def cdp_click(selector: str) -> dict:
    """Click an element by CSS selector via CDP.

    Args:
        selector: CSS selector (e.g. "#search-input", "button.primary", "input[name=q]").

    Returns:
        {"ok": bool, ...}
    """
    session = _get_cdp_session()
    if not session:
        return {"ok": False, "error": "CDP connection unavailable", "code": "cdp_unavailable"}

    try:
        context = session["browser"].contexts[0]
        if not context.pages:
            return {"ok": False, "error": "No open pages", "code": "no_pages"}
        page = context.pages[0]
        el = page.query_selector(selector)
        if not el:
            return {"ok": False, "error": f"Element not found: {selector}", "code": "element_not_found"}
        el.click(timeout=5000)
        logger.info("CDP click: %s", selector)
        return {"ok": True, "selector": selector}
    except Exception as e:
        return {"ok": False, "error": str(e), "code": "cdp_error"}
    finally:
        _close_cdp_session(session)


def cdp_fill(selector: str, text: str) -> dict:
    """Fill an input field by CSS selector via CDP.

    Args:
        selector: CSS selector of the input/textarea.
        text: Text to fill.

    Returns:
        {"ok": bool, ...}
    """
    session = _get_cdp_session()
    if not session:
        return {"ok": False, "error": "CDP connection unavailable", "code": "cdp_unavailable"}

    try:
        context = session["browser"].contexts[0]
        if not context.pages:
            return {"ok": False, "error": "No open pages", "code": "no_pages"}
        page = context.pages[0]
        el = page.query_selector(selector)
        if not el:
            return {"ok": False, "error": f"Element not found: {selector}", "code": "element_not_found"}
        el.fill(text, timeout=5000)
        logger.info("CDP fill: %s = '%s'", selector, text[:50])
        return {"ok": True, "selector": selector, "text": text[:100]}
    except Exception as e:
        return {"ok": False, "error": str(e), "code": "cdp_error"}
    finally:
        _close_cdp_session(session)


def cdp_press(key: str) -> dict:
    """Press a keyboard key via CDP.

    Args:
        key: Key name (e.g. "Enter", "Tab", "Escape", "a", "1").

    Returns:
        {"ok": bool, ...}
    """
    session = _get_cdp_session()
    if not session:
        return {"ok": False, "error": "CDP connection unavailable", "code": "cdp_unavailable"}

    try:
        context = session["browser"].contexts[0]
        if not context.pages:
            return {"ok": False, "error": "No open pages", "code": "no_pages"}
        page = context.pages[0]
        page.keyboard.press(key)
        logger.info("CDP press: %s", key)
        return {"ok": True, "key": key}
    except Exception as e:
        return {"ok": False, "error": str(e), "code": "cdp_error"}
    finally:
        _close_cdp_session(session)


def cdp_navigate(url: str) -> dict:
    """Navigate the active CDP tab to a URL.

    Args:
        url: http/https URL to navigate to.

    Returns:
        {"ok": bool, "url": str, "title": str}
    """
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "Only http/https URLs", "code": "scheme"}

    session = _get_cdp_session()
    if not session:
        return {"ok": False, "error": "CDP connection unavailable", "code": "cdp_unavailable"}

    try:
        context = session["browser"].contexts[0]
        if not context.pages:
            page = context.new_page()
        else:
            page = context.pages[0]
        page.goto(url, timeout=15000)
        title = page.title()
        logger.info("CDP navigate: %s", url)
        return {"ok": True, "url": page.url, "title": title}
    except Exception as e:
        return {"ok": False, "error": str(e), "code": "cdp_error"}
    finally:
        _close_cdp_session(session)


def cdp_screenshot() -> Optional[str]:
    """Take a screenshot of the active CDP tab. Returns file path or None."""
    session = _get_cdp_session()
    if not session:
        return None
    try:
        context = session["browser"].contexts[0]
        if not context.pages:
            return None
        page = context.pages[0]
        import tempfile
        path = os.path.join(tempfile.gettempdir(), f"amt_cdp_screenshot_{int(time.time())}.png")
        page.screenshot(path=path)
        logger.info("CDP screenshot: %s", path)
        return path
    except Exception:
        return None
    finally:
        _close_cdp_session(session)
