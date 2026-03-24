"""
Configuration for markt.de emulator login.
Adjust these for your LDPlayer or BlueStacks instance.
"""

import os

# Appium server — on Windows, start Appium with start-appium.cmd so ANDROID_HOME
# is set for the Appium process (User env vars alone are often not picked up).
APPIUM_SERVER_URL = "http://127.0.0.1:4723"

# Your Android SDK root (same as ANDROID_HOME). Used for docs / setup-android-env.ps1.
ANDROID_SDK_PATH = r"C:\Users\root\AppData\Local\Android\Sdk"

# On the Appium host (Windows): folder where matching chromedrivers are downloaded for Chrome-in-emulator.
CHROMEDRIVER_EXECUTABLE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "chromedriver-cache"
)

# ADB connection to emulator (used by connect_emulator.py and "adb connect" hints)
# Android Studio AVD: often appears as emulator-5554 / TCP 5554 on localhost.
# LDPlayer: usually 127.0.0.1:5554 (first instance), 5556, 5564, etc.
# BlueStacks 5: usually 5555 (first instance), 5557, 5559, etc.
EMULATOR_ADB_HOST = "127.0.0.1"
EMULATOR_ADB_PORT = 5554

# If `adb devices` lists more than one device, Chromedriver must target the one running Chrome.
# Must match `adb devices` serial (e.g. "emulator-5554" for AVD, "127.0.0.1:5554" for LDPlayer TCP).
APPIUM_UDID = "emulator-5554"

# Chrome package inside the emulator (must match installed browser).
# Check: adb -s <serial> shell pm list packages | findstr chrome
CHROME_ANDROID_PACKAGE = "com.android.chrome"

# Use the same Chrome profile as when you open Chrome manually (tap icon). When True: Chrome is
# started via ADB before the script, then Chromedriver connects to it — so your one-time
# "Use without an account" setup is reused and the welcome screen stays away. Set False to
# let Appium start Chrome (different profile; welcome screen often appears each run).
CHROME_USE_RUNNING_APP: bool = True

# Extra Chrome flags for Android when not using running app. If "chrome not reachable", set [].
CHROME_EXTRA_ARGS: list[str] = [
    "--disable-fre",
    "--no-first-run",
    "--disable-default-browser-check",
]

# Optional: full path to chromedriver.exe on THIS Windows PC, matching emulator Chrome major version.
# Download "chromedriver" for your Chrome version from: https://googlechromelabs.github.io/chrome-for-testing/
# Unzip chromedriver-win64/chromedriver.exe and set path below. When set, autodownload is turned off.
CHROMEDRIVER_EXECUTABLE: str | None = None
# Example:
# CHROMEDRIVER_EXECUTABLE = r"D:\tools\chromedriver-win64\chromedriver.exe"

# Path to adb.exe if "adb" is not in your PATH. Uncomment and fix for your install:
# LDPlayer: adb is inside the LDPlayer folder, e.g.:
#   ADB_PATH = r"C:\LDPlayer9\adb.exe"
#   ADB_PATH = r"D:\LDPlayer\LDPlayer9\adb.exe"
# (Open LDPlayer install folder in Explorer and look for adb.exe.)
# BlueStacks: you can use system adb after installing platform-tools, or leave None.
ADB_PATH = r"D:\LDPlayer\LDPlayer9\adb.exe"

# Where to save cookies (directory). Files will be named like {email}.cookies.json
COOKIES_DIR = "cookies"

# If True, do not close Chrome when the script finishes (so you can inspect the page). Default False = close when done.
KEEP_BROWSER_OPEN: bool = False

# Timeouts (seconds)
PAGE_LOAD_TIMEOUT = 60
IMPLICIT_WAIT = 10
