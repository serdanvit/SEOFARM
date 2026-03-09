"""
core/database.py — Единая база данных для всех агентов
Одна БД, разные таблицы для каждого агента.
"""
import sqlite3, os, json, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import DB_PATH

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # безопаснее при многопоточности
    return conn

def db_log(level, agent, message, extra=None):
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO logs (level, agent, message, extra) VALUES (?,?,?,?)",
            (level, agent, message, json.dumps(extra or {}, ensure_ascii=False))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB LOG ERROR] {e}")

def init_all_tables():
    """Создаёт все таблицы для всех агентов"""
    conn = get_conn()
    c = conn.cursor()

    # ── ОБЩИЕ ──────────────────────────────────────────────

    # Логи всей платформы
    c.execute("""CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT DEFAULT 'INFO',
        agent TEXT DEFAULT 'core',
        message TEXT,
        extra TEXT DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # Настройки платформы (ключ-значение)
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── АГЕНТ 1: VK ГРУППЫ ─────────────────────────────────

    # Аккаунты VK (общие для всех агентов!)
    c.execute("""CREATE TABLE IF NOT EXISTS vk_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_encrypted TEXT NOT NULL,
        token_hint TEXT,
        user_id TEXT,
        user_name TEXT,
        status TEXT DEFAULT 'active',
        daily_actions INTEGER DEFAULT 0,
        daily_groups INTEGER DEFAULT 0,
        last_reset_date TEXT,
        last_used TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # Созданные группы
    c.execute("""CREATE TABLE IF NOT EXISTS vk_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vk_group_id TEXT,
        vk_group_url TEXT,
        account_id INTEGER,
        keyword_id INTEGER,
        name TEXT,
        description TEXT,
        status TEXT DEFAULT 'pending',
        reposts_done INTEGER DEFAULT 0,
        post_id TEXT,
        nucleus_url TEXT,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # Ключевые слова для групп
    c.execute("""CREATE TABLE IF NOT EXISTS vk_keywords (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT NOT NULL UNIQUE,
        region TEXT DEFAULT '',
        used INTEGER DEFAULT 0,
        group_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # Очередь задач (для всех агентов)
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent TEXT NOT NULL,
        type TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        account_id INTEGER,
        ref_id INTEGER,
        payload TEXT DEFAULT '{}',
        scheduled_time TEXT,
        attempts INTEGER DEFAULT 0,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── АГЕНТ 2: МОНИТОРИНГ КОММЕНТАРИЕВ ───────────────────

    # Поисковые задания (что искать)
    c.execute("""CREATE TABLE IF NOT EXISTS monitor_queries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT NOT NULL,
        source TEXT DEFAULT 'vk',
        region TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        last_run TEXT,
        found_total INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # Найденные комментарии/посты
    c.execute("""CREATE TABLE IF NOT EXISTS monitor_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query_id INTEGER,
        source TEXT DEFAULT 'vk',
        author_id TEXT,
        author_name TEXT,
        author_url TEXT,
        text TEXT,
        post_url TEXT,
        group_name TEXT,
        found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'new',
        sent_to_telegram INTEGER DEFAULT 0,
        manager_note TEXT,
        query_text TEXT
    )""")

    # ── АГЕНТ 3: СТАТЬИ ────────────────────────────────────

    # Статьи для публикации
    c.execute("""CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        content TEXT,
        tags TEXT DEFAULT '',
        status TEXT DEFAULT 'draft',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # Публикации статей по платформам
    c.execute("""CREATE TABLE IF NOT EXISTS article_publications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER,
        platform TEXT,
        url TEXT,
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        published_at TIMESTAMP
    )""")

    conn.commit()
    conn.close()
    print("✅ Все таблицы созданы")

# ── ХЕЛПЕРЫ ────────────────────────────────────────────────

def get_setting(key, default=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings(key,value,updated_at) VALUES(?,?,datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, str(value))
    )
    conn.commit()
    conn.close()

def get_all_settings():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings")
    rows = {r["key"]: r["value"] for r in c.fetchall()}
    conn.close()
    return rows

def get_logs(limit=200, agent=None):
    conn = get_conn()
    c = conn.cursor()
    if agent:
        c.execute("SELECT * FROM logs WHERE agent=? ORDER BY created_at DESC LIMIT ?", (agent, limit))
    else:
        c.execute("SELECT * FROM logs ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_platform_stats():
    conn = get_conn()
    c = conn.cursor()
    def cnt(table, where="1=1"):
        c.execute(f"SELECT COUNT(*) as n FROM {table} WHERE {where}")
        r = c.fetchone(); return r["n"] if r else 0
    stats = {
        "vk_groups_total":   cnt("vk_groups"),
        "vk_groups_done":    cnt("vk_groups", "status='done'"),
        "vk_groups_error":   cnt("vk_groups", "status='error'"),
        "vk_accounts":       cnt("vk_accounts", "status='active'"),
        "vk_keywords_free":  cnt("vk_keywords", "used=0"),
        "monitor_queries":   cnt("monitor_queries", "status='active'"),
        "monitor_leads_new": cnt("monitor_leads", "status='new'"),
        "monitor_leads_total": cnt("monitor_leads"),
        "articles_draft":    cnt("articles", "status='draft'"),
        "articles_published":cnt("article_publications", "status='done'"),
        "tasks_pending":     cnt("tasks", "status='pending'"),
    }
    conn.close()
    return stats
