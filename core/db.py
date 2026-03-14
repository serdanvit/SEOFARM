"""
core/db.py — Универсальный адаптер базы данных
Поддерживает SQLite и PostgreSQL — переключение через DB_URL в config.py

Использование:
    from core.db import get_conn, query, execute, fetchone, fetchall

get_conn()  — соединение (для транзакций вручную)
query(sql, params)    — execute + commit
fetchone(sql, params) — один ряд как dict
fetchall(sql, params) — список dict
"""
import os, sys, logging, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import DB_URL, DATA_DIR

logger = logging.getLogger("db")

# Определяем тип БД
_IS_PG = DB_URL.startswith("postgresql") or DB_URL.startswith("postgres")

# SQLite: один пул на поток
_local = threading.local()


def get_conn():
    """Возвращает соединение с БД"""
    if _IS_PG:
        return _pg_conn()
    else:
        return _sqlite_conn()


def _sqlite_conn():
    import sqlite3
    db_path = DB_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        # WAL — быстрее и безопаснее при многопоточности
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-32000")   # 32MB кэш
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA temp_store=MEMORY")
        _local.conn = conn

    return _local.conn


def _pg_conn():
    """PostgreSQL соединение (создаётся каждый раз — используй пул в проде)"""
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DB_URL)
        conn.autocommit = False
        return conn
    except ImportError:
        raise RuntimeError(
            "psycopg2 не установлен. Выполни: pip install psycopg2-binary"
        )


class _Row(dict):
    """dict с доступом через точку: row.id вместо row['id']"""
    def __getattr__(self, key):
        try: return self[key]
        except KeyError: raise AttributeError(key)


def _to_dict(row, cursor=None):
    if row is None: return None
    if _IS_PG and cursor:
        cols = [d[0] for d in cursor.description]
        return _Row(zip(cols, row))
    return _Row(row)


def fetchone(sql: str, params: tuple = ()) -> dict | None:
    """Один ряд как dict или None"""
    sql = _adapt(sql)
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(sql, params)
        row = c.fetchone()
        return _to_dict(row, c if _IS_PG else None)
    except Exception as e:
        logger.error(f"[DB] fetchone error: {e}\nSQL: {sql}")
        raise


def fetchall(sql: str, params: tuple = ()) -> list:
    """Список dict"""
    sql = _adapt(sql)
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(sql, params)
        rows = c.fetchall()
        if _IS_PG:
            return [_to_dict(r, c) for r in rows]
        return [_Row(r) for r in rows]
    except Exception as e:
        logger.error(f"[DB] fetchall error: {e}\nSQL: {sql}")
        raise


def execute(sql: str, params: tuple = ()) -> int:
    """Выполнить INSERT/UPDATE/DELETE, вернуть lastrowid"""
    sql = _adapt(sql)
    conn = get_conn()
    try:
        c = conn.cursor()
        if _IS_PG:
            # PostgreSQL: добавляем RETURNING id для INSERT
            if sql.strip().upper().startswith("INSERT") and "RETURNING" not in sql.upper():
                sql = sql.rstrip(";") + " RETURNING id"
            c.execute(sql, params)
            conn.commit()
            row = c.fetchone()
            return row[0] if row else 0
        else:
            c.execute(sql, params)
            conn.commit()
            return c.lastrowid
    except Exception as e:
        if _IS_PG:
            try: conn.rollback()
            except: pass
        logger.error(f"[DB] execute error: {e}\nSQL: {sql}")
        raise


def executemany(sql: str, params_list: list):
    """Массовая вставка"""
    sql = _adapt(sql)
    conn = get_conn()
    try:
        c = conn.cursor()
        c.executemany(sql, params_list)
        conn.commit()
    except Exception as e:
        if _IS_PG:
            try: conn.rollback()
            except: pass
        logger.error(f"[DB] executemany error: {e}")
        raise


def _adapt(sql: str) -> str:
    """Конвертирует SQLite ? в PostgreSQL %s"""
    if _IS_PG:
        return sql.replace("?", "%s").replace("datetime('now')", "NOW()").replace("date('now')", "CURRENT_DATE")
    return sql


def init_schema():
    """Создаёт все таблицы если не существуют"""
    conn = get_conn()
    c = conn.cursor()

    # SQLite AUTO_INCREMENT vs PostgreSQL SERIAL
    if _IS_PG:
        pk = "SERIAL PRIMARY KEY"
        ts = "TIMESTAMP DEFAULT NOW()"
        dt = "TIMESTAMP"
    else:
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT"
        ts = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        dt = "TIMESTAMP"

    tables = [
        f"""CREATE TABLE IF NOT EXISTS logs (
            id {pk},
            level TEXT DEFAULT 'INFO',
            agent TEXT DEFAULT 'core',
            message TEXT,
            extra TEXT DEFAULT '{{}}',
            created_at {ts}
        )""",

        f"""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at {ts}
        )""",

        f"""CREATE TABLE IF NOT EXISTS vk_accounts (
            id {pk},
            token_encrypted TEXT NOT NULL,
            token_hint TEXT,
            user_id TEXT,
            user_name TEXT,
            status TEXT DEFAULT 'active',
            daily_actions INTEGER DEFAULT 0,
            daily_groups INTEGER DEFAULT 0,
            last_reset_date TEXT,
            last_used {dt},
            notes TEXT,
            created_at {ts}
        )""",

        f"""CREATE TABLE IF NOT EXISTS vk_groups (
            id {pk},
            vk_group_id TEXT,
            vk_group_url TEXT,
            account_id INTEGER,
            keyword_id INTEGER,
            name TEXT,
            description TEXT,
            status TEXT DEFAULT 'pending',
            posts_count INTEGER DEFAULT 0,
            reposts_done INTEGER DEFAULT 0,
            discussions_count INTEGER DEFAULT 0,
            post_id TEXT,
            nucleus_url TEXT,
            error_message TEXT,
            created_at {ts}
        )""",

        f"""CREATE TABLE IF NOT EXISTS vk_keywords (
            id {pk},
            keyword TEXT NOT NULL UNIQUE,
            region TEXT DEFAULT '',
            used INTEGER DEFAULT 0,
            group_id INTEGER,
            created_at {ts}
        )""",

        f"""CREATE TABLE IF NOT EXISTS tasks (
            id {pk},
            agent TEXT NOT NULL,
            type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            account_id INTEGER,
            ref_id INTEGER,
            payload TEXT DEFAULT '{{}}',
            scheduled_time TEXT,
            attempts INTEGER DEFAULT 0,
            error_message TEXT,
            created_at {ts},
            updated_at {ts}
        )""",

        f"""CREATE TABLE IF NOT EXISTS monitor_queries (
            id {pk},
            query TEXT NOT NULL,
            source TEXT DEFAULT 'vk',
            region TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            last_run {dt},
            found_total INTEGER DEFAULT 0,
            created_at {ts}
        )""",

        f"""CREATE TABLE IF NOT EXISTS monitor_leads (
            id {pk},
            query_id INTEGER,
            source TEXT DEFAULT 'vk',
            author_id TEXT,
            author_name TEXT,
            author_url TEXT,
            text TEXT,
            post_url TEXT,
            group_name TEXT,
            found_at {ts},
            status TEXT DEFAULT 'new',
            sent_to_telegram INTEGER DEFAULT 0,
            manager_note TEXT,
            query_text TEXT
        )""",

        f"""CREATE TABLE IF NOT EXISTS articles (
            id {pk},
            title TEXT,
            content TEXT,
            tags TEXT DEFAULT '',
            status TEXT DEFAULT 'draft',
            created_at {ts}
        )""",

        f"""CREATE TABLE IF NOT EXISTS article_publications (
            id {pk},
            article_id INTEGER,
            platform TEXT,
            url TEXT,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            published_at {dt}
        )""",
    ]

    # Индексы для скорости
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_logs_agent ON logs(agent)",
        "CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_leads_status ON monitor_leads(status)",
        "CREATE INDEX IF NOT EXISTS idx_leads_found ON monitor_leads(found_at)",
        "CREATE INDEX IF NOT EXISTS idx_groups_status ON vk_groups(status)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_sched ON tasks(scheduled_time)",
    ]

    for sql in tables:
        sql_adapted = _adapt(sql)
        try:
            c.execute(sql_adapted)
        except Exception as e:
            logger.error(f"[DB] Schema error: {e}")

    for sql in indexes:
        try:
            c.execute(_adapt(sql))
        except Exception:
            pass  # индексы — не критично

    if not _IS_PG:
        conn.commit()
    else:
        conn.commit()

    _run_schema_fixes(conn)

    logger.info(f"[DB] Схема инициализирована ({'PostgreSQL' if _IS_PG else 'SQLite'})")
    print(f"✅ БД готова ({'PostgreSQL' if _IS_PG else 'SQLite WAL'})")


def _run_schema_fixes(conn):
    """Лёгкие миграции для старых баз (без отдельного migration-фреймворка)."""
    # Эти поля используются в runtime, но могли отсутствовать в БД, созданной старой версией.
    _ensure_column(conn, "vk_groups", "posts_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "vk_groups", "discussions_count", "INTEGER DEFAULT 0")
    conn.commit()


def _ensure_column(conn, table: str, column: str, col_type: str):
    c = conn.cursor()

    if _IS_PG:
        c.execute(
            """SELECT 1
               FROM information_schema.columns
               WHERE table_name=%s AND column_name=%s""",
            (table, column),
        )
        exists = c.fetchone() is not None
    else:
        c.execute(f"PRAGMA table_info({table})")
        exists = any(row[1] == column for row in c.fetchall())

    if not exists:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        logger.info(f"[DB] Миграция: добавлен столбец {table}.{column}")
