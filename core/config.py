"""
core/config.py — Конфигурация SEO FARM
Для смены SQLite → PostgreSQL замени DB_URL на строку подключения.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR    = os.path.join(BASE_DIR, "data")
LOGS_DIR    = os.path.join(BASE_DIR, "logs")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
LOG_FILE    = os.path.join(LOGS_DIR, "seofarm.log")
SECRET_KEY_FILE = os.path.join(DATA_DIR, ".secret_key")

# ── БАЗА ДАННЫХ ───────────────────────────────────────────────
# SQLite (локально, без настройки):
DB_URL = f"sqlite:///{os.path.join(DATA_DIR, 'seofarm.db')}"

# PostgreSQL (раскомментируй и подставь свои данные):
# DB_URL = "postgresql://user:password@localhost:5432/seofarm"

# ── FLASK ─────────────────────────────────────────────────────
FLASK_HOST  = "0.0.0.0"
FLASK_PORT  = 5000

# ── VK API ────────────────────────────────────────────────────
VK_API_URL     = "https://api.vk.com/method/"
VK_API_VERSION = "5.131"

# Лимиты в день на один аккаунт (не превышай — заблокируют)
MAX_GROUPS_PER_DAY  = 2    # не более 2 групп в день с аккаунта
MAX_ACTIONS_PER_DAY = 15   # лайки, посты, репосты

# Задержки между действиями (секунды) — имитация живого поведения
DELAY_BETWEEN_ACTIONS = 35
DELAY_JITTER          = 15  # ±15 сек случайный разброс

# Репосты из ядра
REPOST_DAYS      = 3   # планировать репосты на N дней
REPOSTS_PER_DAY  = 2   # репостов в день

# ── МОНИТОРИНГ (Агент 2) ──────────────────────────────────────
MONITOR_INTERVAL_MINUTES = 30
MONITOR_MAX_RESULTS      = 100
MONITOR_COMMENT_AGE_HOURS = 48
