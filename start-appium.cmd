@echo off
REM Appium only sees ANDROID_HOME in THIS process. Start Appium with this file
REM (keep the window open), then run: python markt_emulator_login.py
REM Edit the path below if your SDK is elsewhere (must match Android Studio SDK path).

set "ANDROID_HOME=C:\Users\root\AppData\Local\Android\Sdk"
set "ANDROID_SDK_ROOT=%ANDROID_HOME%"

if not exist "%ANDROID_HOME%\platform-tools\adb.exe" (
  echo ERROR: SDK not found at: %ANDROID_HOME%
  echo Install Android Studio SDK or fix ANDROID_HOME in this .cmd file.
  pause
  exit /b 1
)

echo Starting Appium with ANDROID_HOME=%ANDROID_HOME%
echo Chromedriver auto-download enabled (matches emulator Chrome version).
echo.
REM UiAutomator2 + Chrome needs a host chromedriver matching Android Chrome;
REM Appium 3 requires "driver:feature" format (uiautomator2 = Android UiAutomator2 driver).
call "%APPDATA%\npm\appium.cmd" --allow-insecure uiautomator2:chromedriver_autodownload
pause
