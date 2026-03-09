@echo off
chcp 65001 >nul
title ДИАГНОСТИКА SEO FARM
color 0E

echo.
echo ========================================
echo  ДИАГНОСТИКА SEO FARM
echo ========================================
echo.

echo [1] Проверяем Python...
python --version
if errorlevel 1 (
    echo ОШИБКА: Python не найден!
    echo Скачай с https://python.org
    echo При установке отметь "Add Python to PATH"!
) else (
    echo OK: Python найден
)
echo.

echo [2] Проверяем pip...
pip --version
if errorlevel 1 (echo ОШИБКА: pip не работает) else (echo OK: pip работает)
echo.

echo [3] Проверяем папку SEOFARM...
if exist "requirements.txt" (echo OK: requirements.txt есть) else (echo ОШИБКА: requirements.txt не найден - ты в правильной папке?)
if exist "app.py" (echo OK: app.py есть) else (echo ОШИБКА: app.py не найден)
echo.

echo [4] Проверяем зависимости...
pip install flask flask-cors requests cryptography werkzeug
echo.

echo [5] Пробуем запустить app.py...
echo (Если Flask запустится - открой http://localhost:5000)
echo (Для остановки нажми Ctrl+C)
echo.
python app.py

echo.
echo ========================================
echo Готово. Нажми любую клавишу для выхода.
echo ========================================
pause >nul
