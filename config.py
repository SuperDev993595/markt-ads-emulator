"""
Configuration for markt.de emulator login.
Adjust these for your LDPlayer or BlueStacks instance.
"""

# Appium server (start with: appium)
APPIUM_SERVER_URL = "http://127.0.0.1:4723"

# ADB connection to emulator (used to ensure device is connected before Appium)
# LDPlayer: usually 5554 (first instance), 5556, 5564, etc.
# BlueStacks 5: usually 5555 (first instance), 5557, 5559, etc.
EMULATOR_ADB_HOST = "127.0.0.1"
EMULATOR_ADB_PORT = 5555

# Path to adb.exe if "adb" is not in your PATH. Uncomment and fix for your install:
# LDPlayer: adb is inside the LDPlayer folder, e.g.:
#   ADB_PATH = r"C:\LDPlayer9\adb.exe"
#   ADB_PATH = r"D:\LDPlayer\LDPlayer9\adb.exe"
# (Open LDPlayer install folder in Explorer and look for adb.exe.)
# BlueStacks: you can use system adb after installing platform-tools, or leave None.
ADB_PATH = r"D:\LDPlayer\LDPlayer9\adb.exe"

# Where to save cookies (directory). Files will be named like {email}.cookies.json
COOKIES_DIR = "cookies"

# Timeouts (seconds)
PAGE_LOAD_TIMEOUT = 60
IMPLICIT_WAIT = 10
