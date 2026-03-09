"""
core/config.py — Глобальная конфигурация всей платформы SEO FARM
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "seofarm.db")
SECRET_KEY_FILE = os.path.join(DATA_DIR, ".secret_key")
LOG_FILE = os.path.join(LOGS_DIR, "seofarm.log")

# Flask
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
FLASK_DEBUG = False

# VK API
VK_API_URL = "https://api.vk.com/method/"
VK_API_VERSION = "5.131"

# Лимиты VK групп (Агент 1)
MAX_GROUPS_PER_DAY = 2
MAX_ACTIONS_PER_DAY = 15
DELAY_BETWEEN_ACTIONS = 30
DELAY_JITTER = 20
REPOST_DAYS = 3
REPOSTS_PER_DAY = 2

# Мониторинг комментариев (Агент 2)
MONITOR_INTERVAL_MINUTES = 30   # как часто сканировать
MONITOR_MAX_RESULTS = 100       # максимум результатов за поиск
MONITOR_COMMENT_AGE_HOURS = 48  # не старше N часов

# Telegram (для уведомлений менеджерам)
TELEGRAM_BOT_TOKEN = ""         # заполняется в настройках
TELEGRAM_CHAT_IDS = []          # список chat_id менеджеров

# Статусы задач
TASK_PENDING  = "pending"
TASK_RUNNING  = "running"
TASK_DONE     = "done"
TASK_FAILED   = "failed"

# Агенты
AGENT_VK_GROUPS       = "vk_groups"
AGENT_COMMENT_MONITOR = "comment_monitor"
AGENT_ARTICLE_PUB     = "article_publisher"
AGENT_YANDEX_MAPS     = "yandex_maps"
AGENT_2GIS            = "gis"
