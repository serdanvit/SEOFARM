"""
agents/vk_groups/activity.py — Лайки и комментарии по всем группам
Исправлено: ротация токенов, не лайкаем с токена создателя, проверка дублей.
"""
import os, sys, time, random, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.db import fetchall, execute
from core.database import db_log
from core.vk_api import api_call
from core.token_manager import get_active_tokens

logger = logging.getLogger("vk_activity")

# Комментарии — нейтральные, как от обычных подписчиков
COMMENTS = [
    "Полезная информация, спасибо!",
    "Интересно, буду следить за группой",
    "Хорошая подборка 👍",
    "Спасибо за информацию",
    "Очень полезно, сохранил себе",
    "Нашёл то что искал",
    "Отличный контент, рекомендую",
    "Подписался, буду читать",
    "Как можно записаться?",
    "Есть ли акции или скидки?",
    "Подскажите подробнее про условия",
    "Профессионально, спасибо!",
    "Сохранил, поделился с друзьями",
    "Именно то что нужно было найти",
    "Давно искал такое, спасибо",
]


def _already_liked(owner_id, post_id, account_id):
    """Проверяем что с этого аккаунта уже ставили лайк"""
    rows = fetchall(
        "SELECT id FROM tasks WHERE type='like' AND agent='vk_activity' AND account_id=? AND payload LIKE ?",
        (account_id, f'%"post_id": {post_id}%')
    )
    return len(rows) > 0


def run_activity_all(max_likes=3, max_comments=1):
    tokens = get_active_tokens()
    if not tokens:
        db_log("WARNING", "vk_activity", "Нет аккаунтов")
        return {"likes": 0, "comments": 0}

    if len(tokens) < 2:
        db_log("WARNING", "vk_activity",
               "Меньше 2 аккаунтов — активность не имитируется (нужны разные люди)")
        return {"likes": 0, "comments": 0}

    groups = fetchall(
        "SELECT id, vk_group_id, account_id FROM vk_groups WHERE status='done' AND vk_group_id IS NOT NULL"
    )

    total_likes = 0
    total_comments = 0

    for group in groups:
        gid      = group["vk_group_id"]
        owner_id = f"-{gid}"
        creator_account_id = group["account_id"]

        # Берём случайный токен (не создателя группы) для получения постов
        reader_acc_id, reader_token = random.choice(tokens)

        r = api_call("wall.get", {"owner_id": owner_id, "count": 5, "filter": "owner"}, reader_token)
        posts = r.get("response", {}).get("items", []) if "error" not in r else []

        for post in posts:
            post_id = post.get("id")
            if not post_id:
                continue

            # Аккаунты кроме создателя группы — они не должны лайкать своё
            other_tokens = [(aid, tok) for aid, tok in tokens if aid != creator_account_id]
            if not other_tokens:
                continue

            shuffled = random.sample(other_tokens, min(len(other_tokens), max_likes + max_comments))

            # Лайки
            import json
            for acc_id, tok in shuffled[:max_likes]:
                if _already_liked(owner_id, post_id, acc_id):
                    continue
                time.sleep(random.randint(8, 25))
                r2 = api_call("likes.add", {"type": "post", "owner_id": owner_id, "item_id": post_id}, tok)
                if "error" not in r2:
                    execute(
                        "INSERT INTO tasks(agent,type,status,account_id,payload) VALUES('vk_activity','like','done',?,?)",
                        (acc_id, json.dumps({"group_id": gid, "post_id": post_id}))
                    )
                    total_likes += 1
                    db_log("SUCCESS", "vk_activity", f"Лайк: пост {post_id} в группе {gid}")

            # Комментарии (только если несколько аккаунтов)
            for acc_id, tok in shuffled[max_likes:max_likes + max_comments]:
                time.sleep(random.randint(20, 50))
                text = random.choice(COMMENTS)
                r2 = api_call("wall.createComment",
                              {"owner_id": owner_id, "post_id": post_id,
                               "message": text, "from_group": 0}, tok)
                if "error" not in r2:
                    total_comments += 1
                    db_log("SUCCESS", "vk_activity", f"Коммент в группе {gid}: «{text[:30]}»")
                elif "error_code" in r2 and r2.get("error_code") in [15, 214]:
                    db_log("WARNING", "vk_activity", f"Комменты закрыты в группе {gid}")
                    break

            time.sleep(random.randint(30, 80))

        time.sleep(random.randint(90, 200))

    db_log("SUCCESS", "vk_activity", f"Активность: {total_likes} лайков, {total_comments} комментов")
    return {"likes": total_likes, "comments": total_comments}
