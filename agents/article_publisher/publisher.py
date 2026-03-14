"""
agents/article_publisher/publisher.py — Агент 3: Публикация статей
Исправлено: Telegraph токен сохраняется в БД, VK публикует через wall.post,
новый db API.
"""
import os, sys, time, random, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.db import fetchone, execute
from core.database import db_log, get_setting, set_setting

logger = logging.getLogger("article_publisher")

PLATFORMS = {
    "telegra_ph":  "Telegra.ph",
    "vk_wall":     "VK (пост на стене)",
    "vk_articles": "VK Статьи",
}


def publish_to_platforms(article_id: int, platforms: list) -> dict:
    article = fetchone("SELECT * FROM articles WHERE id=?", (article_id,))
    if not article:
        db_log("ERROR", "article_publisher", f"Статья #{article_id} не найдена")
        return {"success": False, "error": "Статья не найдена"}

    article = dict(article)
    db_log("INFO", "article_publisher",
           f"Публикуем «{article['title']}» на {len(platforms)} платформах")

    results = {}
    for platform in platforms:
        time.sleep(random.randint(3, 10))
        try:
            result = _publish_one(article, platform)
        except Exception as e:
            result = {"success": False, "error": str(e)}

        status = "done" if result.get("success") else "failed"
        execute(
            """INSERT INTO article_publications
               (article_id, platform, url, status, error_message, published_at)
               VALUES (?,?,?,?,?,datetime('now'))""",
            (article_id, platform, result.get("url",""), status, result.get("error",""))
        )
        results[platform] = result

        if result.get("success"):
            db_log("SUCCESS", "article_publisher",
                   f"{platform}: {result.get('url','OK')}")
        else:
            db_log("ERROR", "article_publisher",
                   f"{platform}: {result.get('error','?')}")

    execute("UPDATE articles SET status='published' WHERE id=?", (article_id,))
    return {"success": True, "results": results}


def _publish_one(article: dict, platform: str) -> dict:
    if platform == "telegra_ph":
        return _publish_telegraph(article)
    elif platform == "vk_wall":
        return _publish_vk_wall(article)
    elif platform == "vk_articles":
        return _publish_vk_article(article)
    else:
        return {"success": False, "error": f"Платформа {platform} — в разработке"}


def _publish_telegraph(article: dict) -> dict:
    """
    Публикует на Telegra.ph.
    Токен аккаунта сохраняется в настройках — не создаём новый каждый раз.
    """
    import requests

    # Берём сохранённый токен или создаём новый
    access_token = get_setting("telegraph_token", "")

    if not access_token:
        try:
            r = requests.post("https://api.telegra.ph/createAccount", json={
                "short_name": "SEOFarm",
                "author_name": get_setting("brand_name", "SEO Farm")
            }, timeout=15).json()

            if not r.get("ok"):
                return {"success": False, "error": "Не удалось создать аккаунт Telegraph"}

            access_token = r["result"]["access_token"]
            set_setting("telegraph_token", access_token)
            logger.info("[publisher] Создан Telegraph аккаунт")
        except Exception as e:
            return {"success": False, "error": f"Telegraph: {e}"}

    # Формируем контент
    content = []
    for para in article["content"].split("\n\n"):
        para = para.strip()
        if para:
            content.append({"tag": "p", "children": [para]})

    try:
        r = requests.post("https://api.telegra.ph/createPage", json={
            "access_token": access_token,
            "title": article["title"][:256],
            "content": content,
            "return_content": False
        }, timeout=15).json()

        if r.get("ok"):
            return {"success": True, "url": r["result"]["url"]}

        # Токен устарел — сбрасываем и пробуем один раз заново
        if "ACCESS_TOKEN_INVALID" in str(r.get("error", "")):
            set_setting("telegraph_token", "")
            return _publish_telegraph(article)

        return {"success": False, "error": str(r.get("error", "?"))}

    except Exception as e:
        return {"success": False, "error": str(e)}


def _publish_vk_wall(article: dict) -> dict:
    """
    Публикует как обычный пост на стены всех наших групп.
    Использует реально существующий VK API метод wall.post.
    """
    from core.token_manager import get_active_tokens, decrypt_token
    from core.vk_api import api_call, publish_post
    from core.db import fetchall

    tokens = get_active_tokens()
    if not tokens:
        return {"success": False, "error": "Нет токенов VK"}

    groups = fetchall(
        "SELECT vk_group_id, account_id FROM vk_groups WHERE status='done' AND vk_group_id IS NOT NULL"
    )
    if not groups:
        return {"success": False, "error": "Нет готовых групп VK"}

    # Текст поста: заголовок + первые 2000 символов контента
    message = f"{article['title']}\n\n{article['content'][:2000]}"

    published_urls = []
    for group in groups:
        gid = group["vk_group_id"]

        # Берём токен владельца группы
        acc_id, fallback_token = random.choice(tokens)
        token = fallback_token
        if group["account_id"]:
            row = fetchone(
                "SELECT token_encrypted FROM vk_accounts WHERE id=? AND status='active'",
                (group["account_id"],)
            )
            if row:
                token = decrypt_token(row["token_encrypted"])

        result = publish_post(token, int(gid), message)
        if result.get("success"):
            url = f"https://vk.com/wall-{gid}_{result['post_id']}"
            published_urls.append(url)
            db_log("SUCCESS", "article_publisher", f"Пост в группе {gid}")

        time.sleep(random.randint(10, 25))

    if published_urls:
        return {"success": True, "url": published_urls[0],
                "all_urls": published_urls}
    return {"success": False, "error": "Ни одна группа не получила пост"}


def _publish_vk_article(article: dict) -> dict:
    """
    VK Статьи через Donut/Статьи API.
    Требует отдельного токена с правом 'articles'.
    Пока что публикуем как пост с длинным текстом.
    """
    return _publish_vk_wall(article)


# ── CRUD статей ───────────────────────────────────────────────

def create_article(title: str, content: str, tags: str = "") -> int:
    return execute(
        "INSERT INTO articles(title, content, tags, status) VALUES(?,?,?,'draft')",
        (title, content, tags)
    )


def get_articles(status: str = None) -> list:
    from core.db import fetchall
    if status:
        return fetchall("SELECT * FROM articles WHERE status=? ORDER BY created_at DESC", (status,))
    return fetchall("SELECT * FROM articles ORDER BY created_at DESC")


def delete_article(article_id: int):
    execute("DELETE FROM articles WHERE id=?", (article_id,))
    execute("DELETE FROM article_publications WHERE article_id=?", (article_id,))
