@echo off
cd /d "%~dp0"

echo.
echo  =========================================
echo   Familienplaner -- Deploy zu Netlify
echo  =========================================
echo.

git add .

set /p MSG="Commit-Nachricht (Enter = 'Update'): "
if "%MSG%"=="" set MSG=Update

git commit -m "%MSG%"

echo.
echo  Pushe zu GitHub...
git push origin main

echo.
echo  =========================================
echo   Fertig! Netlify baut automatisch.
echo   Ca. 30 Sekunden bis live.
echo  =========================================
echo.
pause
