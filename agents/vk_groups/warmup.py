"""
agents/vk_groups/warmup.py — 7-дневный прогрев VK группы
После создания группа получает посты и обсуждения по расписанию.
Живая группа = выше в поиске VK и Яндекса.
"""
import os, sys, time, random, json, logging
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.db import fetchone, fetchall, execute
from core.database import db_log, get_setting
from core.vk_api import api_call, publish_post
from core.token_manager import decrypt_token
from core.ai_content import generate_warmup_post, generate_discussion

logger = logging.getLogger("vk_warmup")

# Расписание прогрева — какие действия на каком день
WARMUP_PLAN = {
    2: ["post"],          # День 2: информационный пост
    3: ["repost"],        # День 3: репост из ядра
    4: ["post",           # День 4: пост + первые обсуждения
        "discussion:0",
        "discussion:1"],
    5: ["post",           # День 5: вовлекающий пост + обсуждения
        "discussion:2",
        "discussion:3"],
    6: ["repost",         # День 6: репост + обсуждение
        "discussion:4"],
    7: ["post"],          # День 7: пост с отзывом/кейсом
}


def _get_token(account_id):
    row = fetchone(
        "SELECT token_encrypted FROM vk_accounts WHERE id=? AND status='active'",
        (account_id,)
    )
    if row:
        return decrypt_token(row["token_encrypted"])
    # Берём любой активный
    tokens = fetchall(
        "SELECT token_encrypted FROM vk_accounts WHERE status='active' LIMIT 1"
    )
    return decrypt_token(tokens[0]["token_encrypted"]) if tokens else None


def _create_discussion(token: str, group_id: int,
                       title: str, text: str) -> bool:
    """Создаёт тему обсуждения в группе"""
    r = api_call("board.addTopic", {
        "group_id": group_id,
        "title":    title[:100],
        "text":     text[:4096],
    }, token)
    ok = "error" not in r
    if ok:
        db_log("INFO", "vk_warmup",
               f"Обсуждение «{title[:40]}» в группе {group_id}")
    else:
        db_log("WARNING", "vk_warmup",
               f"Ошибка обсуждения: {r.get('error','?')}")
    return ok


def _get_repost_post(token: str, nucleus_url: str):
    """Получает случайный пост из ядра для репоста"""
    if not nucleus_url:
        return None
    from core.vk_api import parse_group_url, get_nucleus_posts
    info = parse_group_url(nucleus_url, token)
    if not info.get("success"):
        return None
    posts = get_nucleus_posts(token, info["owner_id"], count=10)
    if not posts.get("success") or not posts.get("posts"):
        return None
    return random.choice(posts["posts"])


def _do_repost(token: str, group_id: int, nucleus_url: str) -> bool:
    """Делает репост из ядра в группу"""
    post = _get_repost_post(token, nucleus_url)
    if not post:
        return False

    from core.vk_api import parse_group_url
    info    = parse_group_url(nucleus_url, token)
    obj     = f"wall{info['owner_id']}_{post['id']}"
    result  = api_call("wall.repost",
                       {"object": obj, "group_id": group_id}, token)
    ok = "error" not in result
    if ok:
        db_log("INFO", "vk_warmup", f"Репост в группу {group_id}")
    return ok


def schedule_warmup(group_db_id: int, vk_group_id: int,
                    account_id: int, keyword: str,
                    brand: str, region: str, site_url: str,
                    services: list = None):
    """
    Планирует задачи прогрева на 7 дней для новой группы.
    Вызывается сразу после создания группы.
    """
    now = datetime.now()

    for day, actions in WARMUP_PLAN.items():
        # Рандомное время в рабочие часы (10:00 - 20:00)
        hour   = random.randint(10, 20)
        minute = random.randint(0, 59)
        sched  = (now + timedelta(days=day)).replace(
            hour=hour, minute=minute, second=0
        )

        for action in actions:
            payload = {
                "group_db_id": group_db_id,
                "vk_group_id": vk_group_id,
                "action":      action,
                "keyword":     keyword,
                "brand":       brand,
                "region":      region,
                "site_url":    site_url,
                "services":    services or [],
                "day":         day,
            }
            execute(
                "INSERT INTO tasks(agent,type,account_id,ref_id,payload,scheduled_time,status) "
                "VALUES('vk_warmup','warmup',?,?,?,?,'pending')",
                (account_id, group_db_id,
                 json.dumps(payload, ensure_ascii=False),
                 sched.strftime("%Y-%m-%d %H:%M:%S"))
            )

    db_log("INFO", "vk_warmup",
           f"Запланирован прогрев группы {vk_group_id} на 7 дней")


def run_warmup_task(task: dict) -> dict:
    """
    Выполняет одну задачу прогрева.
    Вызывается из планировщика.
    """
    payload    = json.loads(task.get("payload") or "{}")
    account_id = task.get("account_id")
    action     = payload.get("action", "")
    vk_group_id = int(payload.get("vk_group_id", 0))
    keyword    = payload.get("keyword", "")
    brand      = payload.get("brand", "")
    region     = payload.get("region", "")
    site_url   = payload.get("site_url", "")
    services   = payload.get("services", [])
    day        = payload.get("day", 1)

    if not vk_group_id:
        return {"success": False, "error": "vk_group_id не задан"}

    token = _get_token(account_id)
    if not token:
        return {"success": False, "error": "Нет активного токена"}

    nucleus_url = get_setting("nucleus_url", "")

    # Публикация поста
    if action == "post":
        text = generate_warmup_post(
            keyword, brand, region, site_url, day, services
        )
        r = publish_post(token, vk_group_id, text)
        if r.get("success"):
            execute(
                "UPDATE vk_groups SET posts_count=posts_count+1 WHERE vk_group_id=?",
                (str(vk_group_id),)
            )
            db_log("SUCCESS", "vk_warmup",
                   f"День {day}: пост опубликован в группе {vk_group_id}")
            return {"success": True, "action": "post", "day": day}
        else:
            db_log("ERROR", "vk_warmup",
                   f"День {day}: ошибка поста — {r.get('error','?')}")
            return {"success": False, "error": r.get("error")}

    # Репост из ядра
    elif action == "repost":
        ok = _do_repost(token, vk_group_id, nucleus_url)
        if ok:
            execute(
                "UPDATE vk_groups SET reposts_done=reposts_done+1 WHERE vk_group_id=?",
                (str(vk_group_id),)
            )
        return {"success": ok, "action": "repost", "day": day}

    # Создание обсуждения
    elif action.startswith("discussion:"):
        idx  = int(action.split(":")[1])
        disc = generate_discussion(keyword, idx, brand, region)
        ok   = _create_discussion(
            token, vk_group_id, disc["title"], disc["text"]
        )
        if ok:
            execute(
                "UPDATE vk_groups SET discussions_count=COALESCE(discussions_count,0)+1 "
                "WHERE vk_group_id=?",
                (str(vk_group_id),)
            )
        return {"success": ok, "action": "discussion", "day": day}

    return {"success": False, "error": f"Неизвестное действие: {action}"}
