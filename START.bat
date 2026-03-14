@echo off
chcp 65001 >nul
title SEO FARM

echo.
echo  ════════════════════════════════════════════
echo    SEO FARM — Мультиагентная платформа
echo  ════════════════════════════════════════════
echo.

:: ── Проверяем Python ─────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  ОШИБКА: Python не установлен!
    echo.
    echo  Скачай Python 3.12 с:
    echo  https://www.python.org/downloads/release/python-3129/
    echo.
    echo  При установке ОБЯЗАТЕЛЬНО отметь:
    echo  [x] Add Python to PATH
    echo.
    pause & exit /b
)

:: ── Предупреждение о Python 3.14 ────────────────────────────
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  Python %PYVER% обнаружен.

echo %PYVER% | findstr /b "3.14" >nul
if not errorlevel 1 (
    echo.
    echo  [!] Python 3.14 — пакет flask-cors может не поддерживаться.
    echo      Если появится ошибка — установи Python 3.12:
    echo      https://www.python.org/downloads/release/python-3129/
    echo.
)

:: ── Виртуальное окружение ────────────────────────────────────
if not exist "venv\Scripts\python.exe" (
    echo  Создаём виртуальное окружение...
    python -m venv venv
    if errorlevel 1 (
        echo  Ошибка venv! Запускаем без него...
        goto :no_venv
    )
)
call venv\Scripts\activate.bat

:install_deps
echo  Устанавливаем зависимости...
pip install --upgrade pip -q
pip install -r requirements.txt -q
if errorlevel 1 (
    echo  Ошибка установки пакетов. Проверь интернет.
    pause & exit /b
)
goto :run

:no_venv
pip install -r requirements.txt -q

:run
echo.
echo  ════════════════════════════════════════════
echo   Открой браузер: http://localhost:5000
echo   Остановить:     Ctrl+C
echo  ════════════════════════════════════════════
echo.

python app.py
echo.
echo  Платформа остановлена.
pause
