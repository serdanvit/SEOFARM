"""
agents/vk_groups/activity.py — Лайки и комментарии по всем группам
"""
import os, sys, time, random, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.database import get_conn, db_log
from core.vk_api import api_call
from core.token_manager import get_active_tokens

COMMENTS = [
    "Полезная информация, спасибо!","Интересно, буду следить",
    "Хорошая подборка 👍","Спасибо за информацию",
    "Нашёл то что искал","Очень полезно!",
    "Давно искал такое","Отличный контент",
    "Подписался, буду читать","Как записаться?",
    "Есть ли скидки?","Подскажите подробнее",
    "Рекомендую всем 🔥","Топ!","Класс!","👍👍",
    "Профессионально","Сохранил себе","Поделился с друзьями",
]

def run_activity_all(max_likes=3, max_comments=1):
    tokens = get_active_tokens()
    if not tokens:
        db_log("WARNING", "vk_activity", "Нет аккаунтов")
        return {"likes": 0, "comments": 0}

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, vk_group_id FROM vk_groups WHERE status='done' AND vk_group_id IS NOT NULL")
    groups = [dict(r) for r in c.fetchall()]
    conn.close()

    total_likes = 0; total_comments = 0

    for group in groups:
        gid = group["vk_group_id"]
        owner_id = f"-{gid}"

        # Берём посты группы
        r = api_call("wall.get", {"owner_id": owner_id, "count": 5, "filter": "owner"},
                     tokens[0][1])
        posts = r.get("response", {}).get("items", []) if "error" not in r else []

        for post in posts:
            post_id = post.get("id")
            if not post_id: continue

            shuffled = random.sample(tokens, min(len(tokens), max_likes + max_comments))

            # Лайки
            for acc_id, tok in shuffled[:max_likes]:
                time.sleep(random.randint(5, 20))
                r = api_call("likes.add", {"type":"post","owner_id":owner_id,"item_id":post_id}, tok)
                if "error" not in r:
                    total_likes += 1
                    db_log("SUCCESS","vk_activity",f"Лайк на пост {post_id} в группе {gid}")

            # Комменты
            for acc_id, tok in shuffled[max_likes:max_likes+max_comments]:
                time.sleep(random.randint(15, 40))
                text = random.choice(COMMENTS)
                r = api_call("wall.createComment",
                             {"owner_id":owner_id,"post_id":post_id,"message":text,"from_group":0}, tok)
                if "error" not in r:
                    total_comments += 1
                    db_log("SUCCESS","vk_activity",f"Коммент «{text[:25]}» на пост {post_id}")

            time.sleep(random.randint(20, 60))
        time.sleep(random.randint(60, 180))

    db_log("SUCCESS","vk_activity",f"Активность: {total_likes} лайков, {total_comments} коммент.")
    return {"likes": total_likes, "comments": total_comments}
