"""
agents/vk_groups/repost.py — Репосты из ядра во все группы
Исправлено: новый db API, дедупликация, ротация токенов.
"""
import os, sys, time, random, json, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.db import fetchall, fetchone, execute
from core.database import db_log, get_setting
from core.vk_api import api_call
from core.token_manager import get_active_tokens, decrypt_token

logger = logging.getLogger("vk_repost")


def _get_group_token(g_account_id, fallback_token):
    if g_account_id:
        row = fetchone(
            "SELECT token_encrypted FROM vk_accounts WHERE id=? AND status='active'",
            (g_account_id,)
        )
        if row:
            return decrypt_token(row["token_encrypted"])
    return fallback_token


def _already_reposted(group_db_id, post_id):
    rows = fetchall(
        "SELECT payload FROM tasks WHERE ref_id=? AND type='repost' AND status='done'",
        (group_db_id,)
    )
    for r in rows:
        try:
            p = json.loads(r["payload"] or "{}")
            if str(p.get("post_id")) == str(post_id):
                return True
        except Exception:
            pass
    return False


def repost_to_all_groups(posts_per_run=2):
    nucleus_url = get_setting("nucleus_url", "")
    if not nucleus_url:
        db_log("WARNING", "vk_repost", "Ядро не задано в настройках")
        return {"reposts": 0}

    tokens = get_active_tokens()
    if not tokens:
        db_log("WARNING", "vk_repost", "Нет активных токенов")
        return {"reposts": 0}

    account_id, token = random.choice(tokens)

    # Парсим ссылку на ядро
    clean = nucleus_url.replace("https://","").replace("http://","").replace("vk.com/","").strip("/")
    if clean.startswith("club") or clean.lstrip("-").isdigit():
        owner_id = f"-{clean.replace('club','').lstrip('-')}"
    else:
        r = api_call("groups.getById", {"group_id": clean}, token)
        if "error" in r:
            db_log("ERROR", "vk_repost", f"Ядро не найдено: {r['error']}")
            return {"reposts": 0}
        owner_id = f"-{r['response'][0]['id']}"

    # Получаем посты ядра
    r = api_call("wall.get", {"owner_id": owner_id, "count": 20, "filter": "owner"}, token)
    if "error" in r:
        db_log("ERROR", "vk_repost", f"Ошибка постов ядра: {r['error']}")
        return {"reposts": 0}

    nucleus_posts = [p for p in r.get("response", {}).get("items", [])
                     if not p.get("is_pinned")]
    if not nucleus_posts:
        db_log("WARNING", "vk_repost", "В ядре нет постов")
        return {"reposts": 0}

    groups = fetchall(
        "SELECT id, vk_group_id, account_id FROM vk_groups WHERE status='done' AND vk_group_id IS NOT NULL"
    )

    total = 0
    for group in groups:
        gid     = group["vk_group_id"]
        g_token = _get_group_token(group["account_id"], token)

        new_posts = [p for p in nucleus_posts
                     if not _already_reposted(group["id"], p["id"])][:posts_per_run]
        if not new_posts:
            continue

        for post in new_posts:
            result = api_call("wall.repost",
                              {"object": f"wall{owner_id}_{post['id']}", "group_id": int(gid)},
                              g_token)
            if "error" not in result:
                execute(
                    "INSERT INTO tasks(agent,type,status,account_id,ref_id,payload) VALUES('vk_groups','repost','done',?,?,?)",
                    (group["account_id"], group["id"],
                     json.dumps({"post_id": post["id"], "owner_id": owner_id}))
                )
                execute("UPDATE vk_groups SET reposts_done=reposts_done+1 WHERE id=?", (group["id"],))
                db_log("SUCCESS", "vk_repost", f"Репост {post['id']} → группа {gid}")
                total += 1
            else:
                db_log("ERROR", "vk_repost", f"Ошибка {gid}: {result['error']}")

            time.sleep(random.randint(20, 50))

        time.sleep(random.randint(40, 100))

    db_log("SUCCESS", "vk_repost", f"Итог: {total} репостов в {len(groups)} групп")
    return {"reposts": total}
