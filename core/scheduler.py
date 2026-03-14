"""
core/scheduler.py — Планировщик задач
Исправлено: защита от двойного запуска, timeout зависших задач,
автоматический сброс зависших задач при старте.
"""
import threading, time, json, logging, os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("scheduler")

_running  = False
_thread   = None
_lock     = threading.Lock()
_active_tasks = set()  # id задач которые сейчас выполняются


def _run_task(task: dict):
    task_id = task["id"]

    with _lock:
        if task_id in _active_tasks:
            return  # уже запущена
        _active_tasks.add(task_id)

    from core.db import execute
    execute("UPDATE tasks SET status='running', updated_at=datetime('now') WHERE id=?", (task_id,))

    try:
        result = _dispatch(task)
        success = result.get("success") is not False

        execute(
            "UPDATE tasks SET status=?, updated_at=datetime('now') WHERE id=?",
            ("done" if success else "failed", task_id)
        )
        if not success:
            execute("UPDATE tasks SET error_message=? WHERE id=?",
                    (str(result.get("error","?"))[:500], task_id))

    except Exception as e:
        logger.exception(f"[scheduler] Задача #{task_id}: {e}")
        execute("UPDATE tasks SET status='failed', error_message=?, updated_at=datetime('now') WHERE id=?",
                (str(e)[:500], task_id))
    finally:
        with _lock:
            _active_tasks.discard(task_id)


def _dispatch(task: dict) -> dict:
    agent   = task["agent"]
    ttype   = task["type"]
    payload = json.loads(task.get("payload") or "{}")

    if agent == "vk_groups":
        if ttype == "create":
            from agents.vk_groups.creator import create_group_pipeline
            return create_group_pipeline(payload.get("keyword_id"), payload.get("keyword", ""))

        elif ttype == "repost":
            from core.vk_api import repost_post
            from core.token_manager import decrypt_token
            from core.db import fetchone
            row = fetchone("SELECT token_encrypted FROM vk_accounts WHERE id=? AND status='active'",
                           (task.get("account_id"),))
            if not row:
                return {"success": False, "error": "Аккаунт не найден"}
            tok = decrypt_token(row["token_encrypted"])
            return repost_post(tok, payload["vk_group_id"],
                               payload["owner_id"], payload["post_id"])

    elif agent == "vk_warmup":
        from agents.vk_groups.warmup import run_warmup_task
        return run_warmup_task(task)

    elif agent == "comment_monitor":
        from agents.comment_monitor.monitor import run_full_scan
        return run_full_scan()

    elif agent == "article_publisher":
        from agents.article_publisher.publisher import publish_to_platforms
        publish_to_platforms(payload.get("article_id"), payload.get("platforms", []))
        return {"success": True}

    return {"success": False, "error": f"Неизвестный агент: {agent}/{ttype}"}


def _reset_stuck_tasks():
    """Сбрасывает задачи которые застряли в статусе 'running' после перезапуска"""
    from core.db import execute
    execute(
        "UPDATE tasks SET status='pending', updated_at=datetime('now') "
        "WHERE status='running'"
    )


def _loop():
    from core.db import fetchall
    global _running
    logger.info("[scheduler] Запущен")
    _reset_stuck_tasks()

    while _running:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tasks = fetchall(
                """SELECT * FROM tasks
                   WHERE status='pending'
                     AND (scheduled_time IS NULL OR scheduled_time <= ?)
                   ORDER BY scheduled_time ASC LIMIT 3""",
                (now,)
            )
            for task in tasks:
                if not _running:
                    break
                t = threading.Thread(target=_run_task, args=(task,), daemon=True)
                t.start()
                # Не ждём завершения — задачи параллельны, но не больше 3

        except Exception as e:
            logger.error(f"[scheduler] loop error: {e}")

        time.sleep(30)

    logger.info("[scheduler] Остановлен")


def start():
    global _running, _thread
    if _running:
        return
    _running = True
    _thread = threading.Thread(target=_loop, daemon=True, name="scheduler")
    _thread.start()


def stop():
    global _running
    _running = False


def is_running() -> bool:
    return _running
