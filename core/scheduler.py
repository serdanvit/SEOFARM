"""
core/scheduler.py — Планировщик всей платформы
Управляет расписанием всех агентов.
"""
import threading, time, random, logging
from datetime import date, datetime

logger = logging.getLogger("scheduler")

_running = False
_paused  = False
_thread  = None
_last = {
    "vk_reposts":    None,
    "vk_activity":   None,
    "monitor_scan":  None,
}

def start():
    global _running, _thread, _paused
    if _running: return {"status": "already_running"}
    _running = True; _paused = False
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()
    from core.database import db_log
    db_log("INFO", "scheduler", "Платформа запущена ✅")
    return {"status": "started"}

def stop():
    global _running
    _running = False
    from core.database import db_log
    db_log("INFO", "scheduler", "Платформа остановлена")
    return {"status": "stopped"}

def pause():
    global _paused
    _paused = True
    return {"status": "paused"}

def resume():
    global _paused
    _paused = False
    return {"status": "resumed"}

def status():
    return {
        "running": _running,
        "paused":  _paused,
        "status":  "paused" if _paused else ("running" if _running else "stopped"),
        "last_monitor_scan":  str(_last["monitor_scan"])  if _last["monitor_scan"]  else "никогда",
        "last_vk_reposts":    str(_last["vk_reposts"])    if _last["vk_reposts"]    else "никогда",
        "last_vk_activity":   str(_last["vk_activity"])   if _last["vk_activity"]   else "никогда",
    }

def run_monitor_now():
    """Ручной запуск мониторинга комментариев"""
    def go():
        try:
            from agents.comment_monitor.monitor import run_full_scan
            run_full_scan()
        except Exception as e:
            from core.database import db_log
            db_log("ERROR", "scheduler", f"Мониторинг: {e}")
    threading.Thread(target=go, daemon=True).start()
    return {"status": "started"}

def run_vk_reposts_now():
    """Ручной запуск репостов"""
    def go():
        try:
            from agents.vk_groups.repost import repost_to_all_groups
            repost_to_all_groups()
        except Exception as e:
            from core.database import db_log
            db_log("ERROR", "scheduler", f"Репосты: {e}")
    threading.Thread(target=go, daemon=True).start()
    return {"status": "started"}

def run_vk_activity_now(likes=3, comments=1):
    """Ручной запуск активности"""
    def go():
        try:
            from agents.vk_groups.activity import run_activity_all
            run_activity_all(likes, comments)
        except Exception as e:
            from core.database import db_log
            db_log("ERROR", "scheduler", f"Активность: {e}")
    threading.Thread(target=go, daemon=True).start()
    return {"status": "started"}

def _loop():
    global _running, _paused
    tick = 0
    while _running:
        if _paused:
            time.sleep(10); continue
        tick += 1
        try:
            # Каждые 30 тиков (~30 минут) — мониторинг комментариев
            if tick % 30 == 0:
                _auto_monitor()
            # Каждые 1440 тиков (~24 часа) — репосты из ядра
            if tick % 1440 == 0:
                _auto_vk_reposts()
            # Каждые 4320 тиков (~3 дня) — активность
            if tick % 4320 == 0:
                _auto_vk_activity()
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
        time.sleep(60)  # тик = 1 минута

def _auto_monitor():
    global _last
    from core.database import db_log
    db_log("INFO", "scheduler", "Авто-мониторинг комментариев...")
    _last["monitor_scan"] = datetime.now()
    def go():
        try:
            from agents.comment_monitor.monitor import run_full_scan
            run_full_scan()
        except Exception as e:
            from core.database import db_log
            db_log("ERROR", "scheduler", f"Авто-мониторинг: {e}")
    threading.Thread(target=go, daemon=True).start()

def _auto_vk_reposts():
    global _last
    _last["vk_reposts"] = datetime.now()
    def go():
        try:
            from agents.vk_groups.repost import repost_to_all_groups
            repost_to_all_groups()
        except Exception as e:
            from core.database import db_log
            db_log("ERROR", "scheduler", f"Авто-репосты: {e}")
    threading.Thread(target=go, daemon=True).start()

def _auto_vk_activity():
    global _last
    _last["vk_activity"] = datetime.now()
    def go():
        try:
            from agents.vk_groups.activity import run_activity_all
            run_activity_all(3, 1)
        except Exception as e:
            from core.database import db_log
            db_log("ERROR", "scheduler", f"Авто-активность: {e}")
    threading.Thread(target=go, daemon=True).start()
