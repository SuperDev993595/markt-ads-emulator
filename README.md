# markt.de auto-login via emulator (LDPlayer / BlueStacks)

This project automates **markt.de** login using **Chrome inside an Android emulator**, controlled by **Appium**. The flow mirrors your Playwright browser script (cookie consent, email/password, remember me, block checks, cookie save) but runs in the emulator.

## How it works

1. **Appium** connects to your emulator (over ADB) and starts **Chrome**.
2. The script opens markt.de in that Chrome, accepts cookies, fills login form, submits.
3. It checks for blocked/invalid messages and restricted profile, then saves cookies to `cookies/{email}.cookies.json`.

Same selectors as your Playwright version (`#clsy-login-username`, `#clsy-login-password`, `ul.clsy-c-navigation a.clsy-c-navigation__link--logout`, etc.).

## Requirements

- **Python 3.8+**
- **Android emulator**: LDPlayer or BlueStacks, with **ADB** enabled.
- **Appium 2** with **UiAutomator2** driver (and Node.js).
- **Chrome** installed inside the emulator (usually preinstalled).

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Appium (if not already)

```bash
npm install -g appium
appium driver install uiautomator2
```

### 3. Emulator and ADB

- **LDPlayer**: Settings → turn on “ADB debugging”. Default port is often **5554** (first instance).
- **BlueStacks 5**: Settings → Advanced → enable “Android Debug Bridge”. Default port is **5555**.

Connect ADB (from this folder):

```bash
# Uses config.EMULATOR_ADB_PORT (default 5554 — AVD / LDPlayer first instance)
python connect_emulator.py

# Or set the port explicitly (BlueStacks is often 5555)
python connect_emulator.py 5554
python connect_emulator.py 5555
```

Or manually (if your device does not auto-register as `emulator-*`):

```bash
adb connect 127.0.0.1:5554
adb devices
```

Use the serial shown by `adb devices` as **`APPIUM_UDID`** (default **`emulator-5554`**).

### 4. Config

Edit **`config.py`**:

- **`EMULATOR_ADB_PORT` / `APPIUM_UDID`**: default **`5554`** and **`emulator-5554`** (typical AVD / first LDPlayer). For BlueStacks use port **5555** and the serial `adb devices` prints (often `127.0.0.1:5555`).
- **`APPIUM_SERVER_URL`**: Default `http://127.0.0.1:4723`.
- **`ADB_PATH`**: Set if `adb` is not in PATH (e.g. LDPlayer’s bundled `adb.exe`).
- **`COOKIES_DIR`**: Where to save cookies (default `cookies`).

## Running

### 1. Start Appium

In a separate terminal:

```bash
appium
```

Leave it running (default: `http://0.0.0.0:4723`).

### 2. Run login

**Environment variables:**

```bash
set MARKT_EMAIL=your@email.com
set MARKT_PASSWORD=yourpassword
set MARKT_PROXY_URL=http://user:pass@proxy.example.com:44443
python markt_ads_post.py
```

(`MARKT_PROXY_URL` is optional — same full upstream URL as `proxies.txt`. When set, `post_ads` runs `set_proxy.begin_proxy_session` before Appium and `set_proxy.end_proxy_session` after (local forwarder + ADB global `http_proxy`, not Chrome `--proxy-server`.))

**Command-line args:**

```bash
python markt_ads_post.py your@email.com yourpassword
python markt_ads_post.py your@email.com yourpassword "http://user:pass@proxy.example.com:44443"
```

**From your own code:**

```python
from markt_ads_post import post_ads

account = {
    "email": "your@email.com",
    "password": "yourpassword",
    "proxy_url": "http://user:pass@proxy.example.com:44443",  # optional
}
success, blocked = post_ads(account)
# success: True if logged in and cookies saved
# blocked: True if account is blocked/banned
```

Optional: skip ADB check or target a specific device:

```python
success, blocked = post_ads(account, connect_adb=False, udid="emulator-5554")
```

## Cookie format

Cookies are saved as JSON in `cookies/{email}.cookies.json` (email with `@`/`.` replaced for filename). Structure is the same as Selenium/Appium `get_cookies()` (e.g. `name`, `value`, `domain`, `path`, `expiry`, `secure`, `httpOnly`). You can load them in another Selenium/Appium session with `add_cookie()` for each dict, or adapt to your Playwright cookie format if needed.

## Troubleshooting

- **“No emulator connected”**  
  Start the emulator, enable ADB, then run `python connect_emulator.py [port]` and ensure `adb devices` lists the device.

- **Chrome / Chromedriver version mismatch**  
  Update Chrome inside the emulator (Play Store) so it matches the Chromedriver version Appium uses. If needed, install a specific driver: `appium driver run uiautomator2 --chromedriver-autodownload`.

- **Appium can’t find device**  
  If you have multiple devices, set `udid` in code (e.g. `post_ads(account, udid="emulator-5554")`) or in Appium capabilities.

- **Cookie consent not clicked**  
  If markt.de changes the consent UI, add or adjust selectors in `click_accept_all_cookies_selenium()` in `markt_cookie_consent.py`.
