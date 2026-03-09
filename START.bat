@echo off
chcp 65001 >nul
title SEO FARM

echo.
echo  =============================================
echo   SEO FARM — Мультиагентная платформа
echo  =============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  ОШИБКА: Python не найден!
    echo  Скачай с https://python.org
    echo  При установке отметь "Add Python to PATH"
    pause
    exit /b
)

echo  Python найден.
echo.

if not exist "venv\Scripts\python.exe" (
    echo  Создаём виртуальное окружение...
    python -m venv venv
    echo  Готово.
    echo.
)

call venv\Scripts\activate.bat

echo  Проверяем зависимости...
pip install flask flask-cors requests cryptography werkzeug --quiet
echo  Готово.
echo.

echo  =============================================
echo   Открой браузер: http://localhost:5000
echo   Остановить: Ctrl+C
echo  =============================================
echo.

python app.py

echo.
echo  Платформа остановлена.
pause
