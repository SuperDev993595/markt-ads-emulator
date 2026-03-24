"""
markt.de ads posting flow via Android emulator (LDPlayer or BlueStacks) — login and post setup.
Uses Appium to control Chrome inside the emulator — same flow as browser/Playwright,
but runs in the emulator's Chrome.

Requirements:
  - Emulator running (LDPlayer or BlueStacks) with ADB enabled
  - Appium server running — on Windows use start-appium.cmd (sets ANDROID_HOME for Appium)
  - Chrome installed in the emulator
  - config.py adjusted for your emulator port
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import config
from markt_cookie_consent import click_accept_all_cookies_selenium, dismiss_cmp_if_blocking

MARKT_MEINE_ANZEIGEN_URL = "https://www.markt.de/benutzer/meineanzeigen.htm"
MARKT_INSERIEREN_URL = "https://www.markt.de/benutzer/inserieren.htm"

# Account dict keys: "email", "password", optional "proxy_url" (full upstream URL for
# set_proxy.begin_proxy_session — device uses ADB global http_proxy, not Chrome flags).

# Shown on Meine Anzeigen when the profile cannot publish (all parts should appear in page HTML).
MEINE_ANZEIGEN_CANNOT_POST_SNIPPETS: tuple[str, ...] = (
    "Dein Profil ist derzeit eingeschränkt",
    "Du kannst keine Anzeigen veröffentlichen",
    "Alle aktiven Anzeigen wurden pausiert",
)


def log(email: str, message: str, level: str = "info") -> None:
    """Simple logger; replace with your own if needed."""
    level = level.upper()
    print(f"[{level}] {email}: {message}", flush=True)


def ensure_adb_connected() -> bool:
    """Ensure ADB is connected to the emulator. Returns True if device is listed."""
    adb = config.ADB_PATH or "adb"
    try:
        out = subprocess.run(
            [adb, "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            log("system", f"adb devices failed: {out.stderr}", "error")
            return False
        lines = [l.strip() for l in out.stdout.strip().splitlines() if l.strip()]
        # First line is "List of devices attached"
        devices = [l for l in lines[1:] if l and not l.startswith("*") and "device" in l]
        if not devices:
            log("system", "No emulator connected. Run: adb connect " + config.EMULATOR_ADB_HOST + ":" + str(config.EMULATOR_ADB_PORT), "error")
            return False
        log("system", f"ADB devices: {devices}", "debug")
        if len(devices) > 1:
            udid = getattr(config, "APPIUM_UDID", None)
            log(
                "system",
                "Multiple ADB devices — Chromedriver often fails with 'chrome not reachable' "
                f"if APPIUM_UDID is wrong. Current APPIUM_UDID={udid!r}. "
                "Disconnect extras or set APPIUM_UDID to the device where Chrome runs.",
                "warning",
            )
        return True
    except FileNotFoundError:
        log("system", "adb not found. Install Android SDK platform-tools or set config.ADB_PATH.", "error")
        return False
    except Exception as e:
        log("system", f"adb check error: {e}", "error")
        return False


def launch_chrome_via_adb(udid: str) -> bool:
    """Start Chrome on the device via ADB (same as tapping the icon). Uses default profile so one-time setup is reused."""
    adb = config.ADB_PATH or "adb"
    pkg = getattr(config, "CHROME_ANDROID_PACKAGE", "com.android.chrome")
    activity = "com.google.android.apps.chrome.Main"
    try:
        r = subprocess.run(
            [adb, "-s", udid, "shell", "am", "start", "-n", f"{pkg}/{activity}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode != 0:
            log("system", f"ADB launch Chrome failed: {r.stderr or r.stdout}", "warning")
            return False
        log("system", "Launched Chrome via ADB (default profile).", "debug")
        return True
    except Exception as e:
        log("system", f"ADB launch Chrome error: {e}", "warning")
        return False


def create_driver(udid: Optional[str] = None, use_running_chrome: Optional[bool] = None):
    """Create Appium WebDriver for Chrome on Android emulator."""
    cache = Path(config.CHROMEDRIVER_EXECUTABLE_DIR).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    effective_udid = udid or getattr(config, "APPIUM_UDID", None) or None
    pkg = getattr(config, "CHROME_ANDROID_PACKAGE", "com.android.chrome")
    use_running = use_running_chrome if use_running_chrome is not None else getattr(config, "CHROME_USE_RUNNING_APP", False)

    extra_args = list(getattr(config, "CHROME_EXTRA_ARGS", None) or [])

    chrome_opts: dict = {"androidPackage": pkg}
    if use_running:
        chrome_opts["androidUseRunningApp"] = True
    if extra_args and not use_running:
        chrome_opts["args"] = extra_args

    pinned = getattr(config, "CHROMEDRIVER_EXECUTABLE", None)
    use_autodownload = True
    if pinned:
        p = Path(pinned)
        if p.is_file():
            use_autodownload = False
        else:
            log("system", f"CHROMEDRIVER_EXECUTABLE not found ({p}), using autodownload.", "warning")

    caps = {
        "platformName": "Android",
        "automationName": "UiAutomator2",
        "browserName": "Chrome",
        "deviceName": "Android",
        # Prevent Appium from running "pm clear com.android.chrome" so Chrome profile (and "first run done") is kept.
        "appium:noReset": True,
        "appium:chromedriverAutodownload": use_autodownload,
        "appium:chromedriverExecutableDir": str(cache),
        "appium:chromedriverDisableBuildCheck": True,
        "appium:chromedriverLaunchTimeout": 120000,
        "goog:chromeOptions": chrome_opts,
    }
    if not use_autodownload and pinned:
        caps["appium:chromedriverExecutable"] = str(Path(pinned).resolve())
    if effective_udid:
        caps["udid"] = effective_udid
        caps["appium:udid"] = effective_udid
    options = UiAutomator2Options().load_capabilities(caps)
    last_err: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            driver = webdriver.Remote(config.APPIUM_SERVER_URL, options=options)
            driver.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
            driver.implicitly_wait(config.IMPLICIT_WAIT)
            return driver
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "chrome not reachable" in msg and attempt < 3:
                log("system", f"Chrome not reachable (attempt {attempt}/3), retrying…", "warning")
                time.sleep(4)
                continue
            raise
    assert last_err is not None
    raise last_err


def save_cookies(driver, email: str) -> None:
    """Save current browser cookies to COOKIES_DIR/{email}.cookies.json."""
    try:
        cookies = driver.get_cookies()
    except Exception as e:
        log(email, f"Failed to get cookies: {e}", "error")
        return
    path = Path(config.COOKIES_DIR)
    path.mkdir(parents=True, exist_ok=True)
    # Sanitize filename (e.g. replace @ and .)
    safe_name = email.replace("@", "_at_").replace(".", "_")
    filepath = path / f"{safe_name}.cookies.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2, ensure_ascii=False)
    log(email, f"Saved cookies to {filepath}", "info")


def navigate_to_meine_anzeigen(driver, email: str) -> tuple[bool, bool]:
    """
    Open the logged-in «Meine Anzeigen» page where users post and manage ads.
    Call only after login is confirmed (session cookies apply).

    Returns (navigation_ok, profile_restricted_cannot_post).
    - (True, False): page loaded and no “cannot publish” restriction message.
    - (False, True): restriction text present — account cannot post ads.
    - (False, False): load/page read error.
    """
    try:
        driver.get(MARKT_MEINE_ANZEIGEN_URL)
        time.sleep(2)
    except Exception as e:
        log(email, f"Failed to open Meine Anzeigen: {e}", "error")
        return False, False

    try:
        html = driver.page_source
    except Exception as e:
        log(email, f"Meine Anzeigen: could not read page: {e}", "error")
        return False, False

    if all(snippet in html for snippet in MEINE_ANZEIGEN_CANNOT_POST_SNIPPETS):
        log(
            email,
            "Meine Anzeigen: profile restricted — cannot publish ads; active listings paused.",
            "warning",
        )
        return False, True

    log(email, f"Opened Meine Anzeigen: {MARKT_MEINE_ANZEIGEN_URL}", "info")
    return True, False


def navigate_to_inserieren(driver, email: str) -> bool:
    """Open the logged-in ad creation page (Inserieren). Call after Meine Anzeigen shows no posting block."""
    try:
        driver.get(MARKT_INSERIEREN_URL)
        time.sleep(2)
        log(email, f"Opened Inserieren: {MARKT_INSERIEREN_URL}", "info")
        return True
    except Exception as e:
        log(email, f"Failed to open Inserieren: {e}", "error")
        return False


def markt_login_and_save(driver, account: dict) -> tuple[bool, bool]:
    """
    Navigate to Markt, accept cookie if needed, login with email/password, save cookies.
    Returns (success, blocked).
    """
    email = account.get("email", "")
    password = account.get("password") or ""
    login_url = "https://www.markt.de/nichtangemeldet.htm"

    log(email, f"email: {email} password: {'*' * len(password)}", "info")

    try:
        driver.get(login_url)
    except Exception as e:
        log(email, f"Page load error: {e}", "error")
        return False, True

    time.sleep(2)
    # click_accept_all_cookies_selenium(driver, email, log)
    dismiss_cmp_if_blocking(driver, email, log)
    time.sleep(2)

    try:
        email_el = driver.find_element(By.CSS_SELECTOR, "#clsy-login-username")
        pw_el = driver.find_element(By.CSS_SELECTOR, "#clsy-login-password")
        remember_me = driver.find_element(By.CSS_SELECTOR, "#clsy-login-rememberme")
        if remember_me:
            try:
                remember_me.click()
            except Exception:
                driver.execute_script("arguments[0].click();", remember_me)
            time.sleep(1)
        if email_el:
            email_el.clear()
            email_el.send_keys(email)
            time.sleep(0.5)
        if pw_el:
            pw_el.clear()
            pw_el.send_keys(password)
            time.sleep(0.5)
            pw_el.send_keys(Keys.ENTER)
    except Exception as e:
        log(email, f"Login form error: {e}", "error")
        return False, True

    time.sleep(5)

    # Check for blocked / invalid
    try:
        html = driver.page_source
        if "Dein Konto wurde gesperrt" in html:
            log(email, "Account blocked: 'Dein Konto wurde gesperrt' message found.", "warning")
            return False, True
        if "Ungültige Eingabe" in html:
            log(email, "Invalid entry (Ungültige Eingabe). Not updating user state.", "warning")
            return False, False
    except Exception as e:
        log(email, f"Post-login message check error: {e}", "debug")

    time.sleep(10)

    # Logged-in: logout link in nav
    try:
        nav_logout = driver.find_elements(By.CSS_SELECTOR, "ul.clsy-c-navigation a.clsy-c-navigation__link--logout")
        logged_in = len(nav_logout) > 0
    except Exception:
        logged_in = False

    log(email, "logged_in: " + str(logged_in), "info")
    if not logged_in:
        log(email, "Login failed (logout not found). Not updating user state.", "warning")
        return False, False

    log(email, "Markt login successful.", "info")

    # Restricted profile check
    try:
        time.sleep(2)
        html = driver.page_source
        pattern = r"clsy-c-message--warning[^>]*>.*?Dein Profil ist derzeit eingeschränkt"
        if re.search(pattern, html, re.IGNORECASE | re.DOTALL):
            log(email, "Account blocked: profile restricted (warning message found).", "warning")
            return False, True
        log(email, "Block check: No restriction message found, account appears to be active.", "debug")
    except Exception as e:
        log(email, f"Block check error: {e}", "error")

    nav_ok, meine_restricted = navigate_to_meine_anzeigen(driver, email)
    if meine_restricted:
        return False, True

    inserieren_ok = navigate_to_inserieren(driver, email) if nav_ok else False

    save_cookies(driver, email)
    if not nav_ok:
        return False, False
    if not inserieren_ok:
        return False, False
    return True, False


def post_ads(account: dict, connect_adb: bool = True, udid: str | None = None) -> tuple[bool, bool]:
    """
    Full flow: optional ``set_proxy`` session from ``account[\"proxy_url\"]``, ensure ADB connected,
    create driver, login, quit, then tear down the proxy session.

    ``account`` keys: ``email``, ``password``, optional ``proxy_url`` (upstream URL for
    ``set_proxy.begin_proxy_session``, e.g. ``http://user:pass@host:44443``).

    Returns (success, blocked).
    """
    if connect_adb and not ensure_adb_connected():
        return False, True

    proxy_url = (account.get("proxy_url") or "").strip() or None
    driver = None
    try:
        if proxy_url:
            import set_proxy

            set_proxy.begin_proxy_session(proxy_url)
        effective_udid = udid or getattr(config, "APPIUM_UDID", None)
        prelaunch = bool(getattr(config, "CHROME_USE_RUNNING_APP", False) and effective_udid)
        if prelaunch:
            launch_chrome_via_adb(effective_udid)
            time.sleep(3)
        driver = create_driver(udid=udid)
        return markt_login_and_save(driver, account)
    except Exception as e:
        log(account.get("email", "?"), f"Driver or login error: {e}", "error")
        import traceback
        traceback.print_exc()
        return False, True
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        if proxy_url:
            import set_proxy

            set_proxy.end_proxy_session()


if __name__ == "__main__":
    # Example: run with one account from command line or env
    import os as _os
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent / ".env")
    except ImportError:
        pass
    _email = _os.environ.get("MARKT_EMAIL", "").strip()  # noqa: PLC0415
    _password = _os.environ.get("MARKT_PASSWORD", "").strip()
    _proxy = _os.environ.get("MARKT_PROXY_URL", "").strip()
    if not _email or not _password:
        print(
            "Usage: set MARKT_EMAIL and MARKT_PASSWORD (optional MARKT_PROXY_URL), "
            "or: python markt_ads_post.py email password [proxy_url]",
            file=sys.stderr,
        )
        if len(sys.argv) >= 3:
            _email, _password = sys.argv[1], sys.argv[2]
            if len(sys.argv) >= 4:
                _proxy = sys.argv[3].strip()
        else:
            sys.exit(1)
    account = {"email": _email, "password": _password}
    if _proxy:
        account["proxy_url"] = _proxy
    success, blocked = post_ads(account)
    sys.exit(0 if success else (2 if blocked else 1))
