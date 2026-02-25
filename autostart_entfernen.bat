@echo off
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

del "%STARTUP%\Wochenplaner Proxy.vbs" >nul 2>&1
echo Autostart wurde entfernt. Der Proxy startet nicht mehr automatisch.
pause
