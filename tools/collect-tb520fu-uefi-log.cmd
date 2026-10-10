@echo off
setlocal
set "OUT=%~dp0uefi-pstore"
adb devices
adb shell id
if errorlevel 1 exit /b 1
if not exist "%OUT%" mkdir "%OUT%"
adb pull /sys/fs/pstore "%OUT%"
adb shell dmesg > "%OUT%\recovery-dmesg.txt"
echo Saved recovery logs under "%OUT%".
endlocal
