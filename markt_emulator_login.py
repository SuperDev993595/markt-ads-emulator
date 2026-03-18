"""
markt.de auto-login via Android emulator (LDPlayer or BlueStacks).
Uses Appium to control Chrome inside the emulator — same flow as browser/Playwright,
but runs in the emulator's Chrome.

Requirements:
  - Emulator running (LDPlayer or BlueStacks) with ADB enabled
  - Appium server running (e.g. appium)
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
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config


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
        return True
    except FileNotFoundError:
        log("system", "adb not found. Install Android SDK platform-tools or set config.ADB_PATH.", "error")
        return False
    except Exception as e:
        log("system", f"adb check error: {e}", "error")
        return False


def create_driver(udid: Optional[str] = None):
    """Create Appium WebDriver for Chrome on Android emulator."""
    caps = {
        "platformName": "Android",
        "automationName": "UiAutomator2",
        "browserName": "Chrome",
        "deviceName": "Android",
        # Optional: force a specific emulator if multiple devices
        # "udid": "emulator-5554",
    }
    if udid:
        caps["udid"] = udid
    options = UiAutomator2Options().load_capabilities(caps)
    driver = webdriver.Remote(config.APPIUM_SERVER_URL, options=options)
    driver.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
    driver.implicitly_wait(config.IMPLICIT_WAIT)
    return driver


def _click_accept_all_cookies(driver, email: str) -> None:
    """Click cookie consent (e.g. 'Alle akzeptieren') if present."""
    selectors = [
        (By.CSS_SELECTOR, "button[data-action='accept']"),
        (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'alle akzeptieren')]"),
        (By.XPATH, "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'alle akzeptieren')]"),
        (By.CSS_SELECTOR, "[data-testid='accept-cookies'], .cookie-accept, #accept-cookies, .accept-cookies"),
    ]
    for by, selector in selectors:
        try:
            el = WebDriverWait(driver, 5).until(EC.presence_of_element_located((by, selector)))
            if el.is_displayed():
                el.click()
                log(email, "Clicked cookie consent.", "debug")
                return
        except Exception:
            continue
    log(email, "No cookie consent button found (may already be accepted).", "debug")


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
    _click_accept_all_cookies(driver, email)
    time.sleep(2)

    try:
        email_el = driver.find_element(By.CSS_SELECTOR, "#clsy-login-username")
        pw_el = driver.find_element(By.CSS_SELECTOR, "#clsy-login-password")
        remember_me = driver.find_element(By.CSS_SELECTOR, "#clsy-login-rememberme")
        if remember_me:
            remember_me.click()
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

    save_cookies(driver, email)
    return True, False


def run_login(account: dict, connect_adb: bool = True, udid: str | None = None) -> tuple[bool, bool]:
    """
    Full flow: ensure ADB connected, create driver, login, quit.
    Returns (success, blocked).
    """
    if connect_adb and not ensure_adb_connected():
        return False, True

    driver = None
    try:
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


if __name__ == "__main__":
    # Example: run with one account from command line or env
    import os as _os
    _email = _os.environ.get("MARKT_EMAIL", "").strip()  # noqa: PLC0415
    _password = _os.environ.get("MARKT_PASSWORD", "").strip()
    if not _email or not _password:
        print("Usage: set MARKT_EMAIL and MARKT_PASSWORD, or pass email password as args.", file=sys.stderr)
        if len(sys.argv) >= 3:
            _email, _password = sys.argv[1], sys.argv[2]
        else:
            sys.exit(1)
    account = {"email": _email, "password": _password}
    success, blocked = run_login(account)
    sys.exit(0 if success else (2 if blocked else 1))
