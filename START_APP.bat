@echo off
chcp 65001 >nul
title SEO FARM

echo.
echo  =============================================
echo   SEO FARM — Десктопное приложение
echo  =============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  ОШИБКА: Python не найден!
    echo  Скачай с https://python.org
    pause & exit /b
)

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo  Создаём окружение...
    python -m venv venv
    call venv\Scripts\activate.bat
)

echo  Устанавливаем зависимости...
pip install flask flask-cors requests cryptography werkzeug pywebview --quiet
echo.
echo  Запускаем приложение...
echo.

python desktop.py

echo.
pause
