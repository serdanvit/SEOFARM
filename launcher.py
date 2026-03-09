"""
launcher.py — Запускает Flask + ngrok вместе
Показывает публичный URL и QR-код для телефона
"""
import threading, time, os, sys

def run_flask():
    """Запускаем Flask в отдельном потоке"""
    os.system(f'"{sys.executable}" app.py')

# Стартуем Flask
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# Ждём пока Flask поднимется
print("  Запускаем Flask...", end="", flush=True)
time.sleep(3)
print(" OK")

# Открываем ngrok туннель
try:
    from pyngrok import ngrok, conf

    # Запускаем туннель
    tunnel = ngrok.connect(5000, "http")
    public_url = tunnel.public_url

    # Если http — делаем https
    if public_url.startswith("http://"):
        public_url = public_url.replace("http://", "https://", 1)

    print()
    print("  ┌─────────────────────────────────────────────────────┐")
    print("  │                                                     │")
    print("  │   Открой на телефоне:                               │")
    print(f"  │   {public_url:<51} │")
    print("  │                                                     │")
    print("  └─────────────────────────────────────────────────────┘")
    print()

    # QR-код прямо в терминале
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(public_url)
        qr.make(fit=True)
        print("  Сканируй QR камерой телефона:")
        print()
        qr.print_ascii(invert=True)
        print()
    except ImportError:
        pass

    print("  Нажми Ctrl+C для остановки платформы")
    print()

    # Держим живым пока Flask работает
    flask_thread.join()

except KeyboardInterrupt:
    print("\n  Остановка...")
    ngrok.kill()
    sys.exit(0)

except Exception as e:
    print(f"\n  Ngrok ошибка: {e}")
    print("  Платформа доступна только локально: http://localhost:5000")
    flask_thread.join()
