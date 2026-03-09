"""
desktop.py — Запуск SEO FARM как нативного десктопного приложения
Использует PyWebView для отображения интерфейса в нативном окне.
"""
import threading
import time
import sys
import os
import logging

# Отключаем лишние логи в окне приложения
logging.getLogger('werkzeug').setLevel(logging.ERROR)

def find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

PORT = find_free_port()

# ── Запускаем Flask в фоновом потоке ──────────────────────
def run_flask():
    # Подменяем порт в конфиге
    os.environ['SEOFARM_PORT'] = str(PORT)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from core.database import init_all_tables
    import core.scheduler as scheduler
    from app import app

    init_all_tables()
    scheduler.start()

    app.run(
        host='127.0.0.1',
        port=PORT,
        debug=False,
        use_reloader=False,
        threaded=True
    )

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# Ждём пока Flask поднимется
print("Запускаем SEO FARM...")
time.sleep(2)

# ── Открываем нативное окно ───────────────────────────────
try:
    import webview

    # Иконка приложения
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'logo.png')

    window = webview.create_window(
        title='SEO FARM',
        url=f'http://127.0.0.1:{PORT}',
        width=1280,
        height=820,
        min_size=(900, 600),
        resizable=True,
        text_select=True,
        # Скрываем адресную строку — выглядит как нативное приложение
    )

    # Запускаем webview (блокирует до закрытия окна)
    webview.start(
        gui='edgechromium',   # Windows: Edge WebView2 (встроен в Win10/11)
        debug=False,
    )

except ImportError:
    # Если pywebview не установлен — открываем в браузере
    print(f"\nPyWebView не найден, открываем в браузере...")
    import webbrowser
    webbrowser.open(f'http://127.0.0.1:{PORT}')
    print(f"SEO FARM запущен: http://127.0.0.1:{PORT}")
    print("Закрой это окно чтобы остановить платформу.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

except Exception as e:
    # Fallback на браузер при любой ошибке webview
    print(f"\nОкно не открылось ({e}), используем браузер...")
    import webbrowser
    webbrowser.open(f'http://127.0.0.1:{PORT}')
    print(f"SEO FARM запущен: http://127.0.0.1:{PORT}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
