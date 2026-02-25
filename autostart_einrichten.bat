@echo off
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

echo Richte Autostart ein...
copy /Y "%~dp0start_proxy_silently.vbs" "%STARTUP%\Wochenplaner Proxy.vbs" >nul

echo Proxy wird ab jetzt automatisch mit Windows gestartet.
echo.
echo Starte Proxy jetzt...
wscript "%~dp0start_proxy_silently.vbs"
echo.
echo Fertig! Der Proxy laeuft jetzt im Hintergrund.
pause
