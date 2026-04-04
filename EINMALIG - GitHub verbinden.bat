@echo off
cd /d "%~dp0"

echo.
echo  =========================================
echo   EINMALIGES SETUP - Nur einmal ausfuehren
echo  =========================================
echo.

echo  Schritt 1: Remote hinzufuegen...
git remote add origin https://github.com/hjhansjanzen-eng/Familienplaner.git

echo  Schritt 2: Branch umbenennen (master -> main)...
git branch -M main

echo  Schritt 3: Alles zum GitHub hochladen...
git add .
git commit -m "Erster Upload - Familienplaner"
git push -u origin main

echo.
echo  =========================================
echo   Setup abgeschlossen!
echo   Ab jetzt: "Deploy zu Netlify.bat" nutzen.
echo.
echo   DIESE DATEI KANN DANACH GELOESCHT WERDEN.
echo  =========================================
echo.
pause
