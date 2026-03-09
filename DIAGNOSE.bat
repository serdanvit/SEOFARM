@echo off
chcp 65001 >nul
title ДИАГНОСТИКА SEO FARM
color 0E

echo ============================================
echo  ДИАГНОСТИКА SEO FARM
echo  Это окно НЕ закроется автоматически
echo ============================================
echo.

echo [1] Проверяем Python...
python --version
if errorlevel 1 (
    echo.
    echo  ПРОБЛЕМА: Python не найден!
    echo  Решение: скачай https://python.org
    echo  При установке: отметь "Add Python to PATH"
    echo.
    goto :end
)
echo  OK
echo.

echo [2] Проверяем pip...
pip --version
if errorlevel 1 (
    echo  ПРОБЛЕМА: pip не работает
    goto :end
)
echo  OK
echo.

echo [3] Проверяем файлы в текущей папке...
if exist "app.py" (echo  OK: app.py) else (echo  НЕТ: app.py - запусти из папки SEOFARM!)
if exist "core\config.py" (echo  OK: core\config.py) else (echo  НЕТ: core\config.py)
if exist "core\database.py" (echo  OK: core\database.py) else (echo  НЕТ: core\database.py)
if exist "core\vk_api.py" (echo  OK: core\vk_api.py) else (echo  НЕТ: core\vk_api.py)
if exist "core\token_manager.py" (echo  OK: core\token_manager.py) else (echo  НЕТ: core\token_manager.py)
if exist "agents\vk_groups\creator.py" (echo  OK: agents\vk_groups\creator.py) else (echo  НЕТ: agents\vk_groups\creator.py)
if exist "static\index.html" (echo  OK: static\index.html) else (echo  НЕТ: static\index.html)
echo.

echo [4] Устанавливаем зависимости...
pip install flask flask-cors requests cryptography werkzeug
echo.

echo [5] Запускаем app.py (смотри ошибки ниже)...
echo ============================================
python app.py
echo ============================================

:end
echo.
echo Готово. Нажми любую клавишу для выхода.
pause >nul
