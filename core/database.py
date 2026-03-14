"""
core/database.py — Функции работы с данными
Использует core/db.py как адаптер (SQLite или PostgreSQL).
"""
import json, os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import fetchone, fetchall, execute, init_schema

logger = logging.getLogger("database")


def init_all_tables():
    init_schema()


def get_conn():
    from core.db import get_conn as _gc
    return _gc()


def db_log(level: str, agent: str, message: str, extra: dict = None):
    try:
        execute(
            "INSERT INTO logs (level, agent, message, extra) VALUES (?,?,?,?)",
            (level, agent, message, json.dumps(extra or {}, ensure_ascii=False))
        )
    except Exception as e:
        print(f"[DB LOG ERROR] {e}")


def get_setting(key: str, default: str = "") -> str:
    row = fetchone("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str):
    from core.config import DB_URL
    if DB_URL.startswith("postgresql") or DB_URL.startswith("postgres"):
        execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
            (key, str(value))
        )
    else:
        execute(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, str(value))
        )


def get_all_settings() -> dict:
    rows = fetchall("SELECT key, value FROM settings")
    return {r["key"]: r["value"] for r in rows}


def get_logs(limit: int = 200, agent: str = None) -> list:
    if agent:
        return fetchall(
            "SELECT * FROM logs WHERE agent=? ORDER BY created_at DESC LIMIT ?",
            (agent, limit)
        )
    return fetchall("SELECT * FROM logs ORDER BY created_at DESC LIMIT ?", (limit,))


def get_platform_stats() -> dict:
    def cnt(table, where="1=1", params=()):
        row = fetchone(f"SELECT COUNT(*) as n FROM {table} WHERE {where}", params)
        return row["n"] if row else 0

    return {
        "vk_groups_total":    cnt("vk_groups"),
        "vk_groups_done":     cnt("vk_groups", "status='done'"),
        "vk_groups_error":    cnt("vk_groups", "status='error'"),
        "vk_accounts":        cnt("vk_accounts", "status='active'"),
        "vk_keywords_free":   cnt("vk_keywords", "used=0"),
        "monitor_queries":    cnt("monitor_queries", "status='active'"),
        "monitor_leads_new":  cnt("monitor_leads", "status='new'"),
        "monitor_leads_total":cnt("monitor_leads"),
        "articles_draft":     cnt("articles", "status='draft'"),
        "articles_published": cnt("article_publications", "status='done'"),
        "tasks_pending":      cnt("tasks", "status='pending'"),
    }
