@echo off
chcp 65001 >nul
title SEO FARM — Сборка .exe

echo.
echo  =============================================
echo   SEO FARM — Сборка в .exe файл
echo   Это займёт 2-5 минут
echo  =============================================
echo.

:: Проверяем Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ОШИБКА: Python не найден!
    pause & exit /b
)

:: Активируем venv если есть
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo  Создаём venv...
    python -m venv venv
    call venv\Scripts\activate.bat
)

echo  [1/4] Устанавливаем зависимости...
pip install flask flask-cors requests cryptography werkzeug pywebview pyinstaller --quiet
echo  Готово.
echo.

echo  [2/4] Собираем приложение...
echo  (не закрывай окно, это займёт пару минут)
echo.

pyinstaller ^
  --name "SEO FARM" ^
  --onefile ^
  --windowed ^
  --icon "static\logo.png" ^
  --add-data "static;static" ^
  --add-data "core;core" ^
  --add-data "agents;agents" ^
  --hidden-import flask ^
  --hidden-import flask_cors ^
  --hidden-import webview ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import cryptography ^
  --hidden-import requests ^
  --hidden-import werkzeug ^
  --hidden-import sqlite3 ^
  --collect-all webview ^
  --noconfirm ^
  desktop.py

if errorlevel 1 (
    echo.
    echo  ОШИБКА при сборке! Смотри сообщения выше.
    pause & exit /b
)

echo.
echo  [3/4] Копируем дополнительные файлы...
if not exist "dist\SEO FARM\data" mkdir "dist\SEO FARM\data"
if not exist "dist\SEO FARM\logs" mkdir "dist\SEO FARM\logs"
if not exist "dist\SEO FARM\uploads" mkdir "dist\SEO FARM\uploads"

echo  [4/4] Готово!
echo.
echo  =============================================
echo   Файл создан: dist\SEO FARM.exe
echo.
echo   Можешь скопировать его куда угодно
echo   и запускать без установки Python!
echo  =============================================
echo.
pause
