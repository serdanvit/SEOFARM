"""
agents/vk_groups/repost.py — Репосты из ядра во все группы
"""
import os, sys, time, random, json, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.database import get_conn, db_log, get_setting
from core.vk_api import api_call, get_nucleus_posts
from core.token_manager import get_active_tokens, decrypt_token

logger = logging.getLogger("vk_repost")

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
    if clean.startswith("club"):
        gid = clean.replace("club","")
        owner_id = f"-{gid}"
    else:
        r = api_call("groups.getById", {"group_id": clean}, token)
        if "error" in r:
            db_log("ERROR", "vk_repost", f"Не удалось найти ядро: {r['error']}")
            return {"reposts": 0}
        owner_id = f"-{r['response'][0]['id']}"

    # Получаем посты из ядра
    r = api_call("wall.get", {"owner_id": owner_id, "count": 20, "filter": "owner"}, token)
    if "error" in r:
        db_log("ERROR", "vk_repost", f"Ошибка получения постов ядра: {r['error']}")
        return {"reposts": 0}

    nucleus_posts = r.get("response", {}).get("items", [])
    nucleus_posts = [p for p in nucleus_posts if not p.get("is_pinned")]

    # Получаем все готовые группы
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, vk_group_id, account_id FROM vk_groups WHERE status='done' AND vk_group_id IS NOT NULL")
    groups = [dict(r) for r in c.fetchall()]
    conn.close()

    total = 0
    for group in groups:
        gid = group["vk_group_id"]
        g_account_id = group["account_id"]

        # Ищем какие посты уже репостили
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT payload FROM tasks WHERE ref_id=? AND type='repost' AND status='done'", (group["id"],))
        done_payloads = [json.loads(r["payload"]) for r in c.fetchall()]
        conn.close()
        done_post_ids = {p.get("post_id") for p in done_payloads}

        new_posts = [p for p in nucleus_posts if p["id"] not in done_post_ids][:posts_per_run]

        for post in new_posts:
            # Берём токен создателя группы или любой
            g_token = token
            if g_account_id:
                conn = get_conn()
                c = conn.cursor()
                c.execute("SELECT token_encrypted, status FROM vk_accounts WHERE id=?", (g_account_id,))
                row = c.fetchone()
                conn.close()
                if row and row["status"] == "active":
                    g_token = decrypt_token(row["token_encrypted"])

            obj = f"wall{owner_id}_{post['id']}"
            result = api_call("wall.repost", {"object": obj, "group_id": int(gid)}, g_token)

            if "error" not in result:
                total += 1
                conn = get_conn()
                conn.execute("""INSERT INTO tasks (agent,type,status,account_id,ref_id,payload)
                    VALUES ('vk_groups','repost','done',?,?,?)""",
                    (g_account_id, group["id"],
                     json.dumps({"post_id": post["id"], "owner_id": owner_id})))
                conn.execute("UPDATE vk_groups SET reposts_done=reposts_done+1 WHERE id=?", (group["id"],))
                conn.commit()
                conn.close()
                db_log("SUCCESS", "vk_repost", f"Репост {post['id']} → группа {gid}")
            else:
                db_log("ERROR", "vk_repost", f"Ошибка репоста: {result['error']}")

            time.sleep(random.randint(15, 45))

        time.sleep(random.randint(30, 90))

    db_log("SUCCESS", "vk_repost", f"Репосты завершены: {total} репостов в {len(groups)} групп")
    return {"reposts": total}
