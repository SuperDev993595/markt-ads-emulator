# Run once in PowerShell (as your user):  .\setup-android-env.ps1
# Then close ALL terminals and reopen before starting Appium.

# Keep in sync with config.ANDROID_SDK_PATH and start-appium.cmd
$SdkRoot = "C:\Users\root\AppData\Local\Android\Sdk"
$PlatformTools = Join-Path $SdkRoot "platform-tools"

[Environment]::SetEnvironmentVariable("ANDROID_HOME", $SdkRoot, "User")
[Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", $SdkRoot, "User")

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notmatch [regex]::Escape("platform-tools")) {
    $newPath = if ($userPath) { "$userPath;$PlatformTools" } else { $PlatformTools }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
}

Write-Host "Set ANDROID_HOME and ANDROID_SDK_ROOT to: $SdkRoot"
Write-Host "Added platform-tools to User PATH (if not already present)."
Write-Host "Close this window, open a NEW PowerShell, then run Appium and your script."
