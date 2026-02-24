@echo off
cd /d "%~dp0"

:: Proxy unsichtbar im Hintergrund starten
start "" /B pythonw schulmanager_proxy.py 2>nul || start "" /B python schulmanager_proxy.py

:: Kurz warten bis Proxy bereit ist
timeout /t 1 /nobreak >nul

:: Wochenplaner im Browser öffnen
start "" "%~dp0index.html"
