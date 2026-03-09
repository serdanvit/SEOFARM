"""
agents/article_publisher/publisher.py — Агент 3: Публикация статей
"""
import os, sys, time, random, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.database import get_conn, db_log

logger = logging.getLogger("article_publisher")

PLATFORMS = {
    "telegra_ph": "Telegra.ph",
    "vk_articles": "VK Статьи",
    "dzen": "Яндекс Дзен",
    "vc_ru": "VC.ru",
}

def publish_to_platforms(article_id: int, platforms: list):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM articles WHERE id=?", (article_id,))
    article = c.fetchone()
    conn.close()
    if not article:
        db_log("ERROR","article_publisher", f"Статья #{article_id} не найдена")
        return

    article = dict(article)
    db_log("INFO","article_publisher",
           f"Публикуем «{article['title']}» на {len(platforms)} платформах")

    for platform in platforms:
        time.sleep(random.randint(5, 15))
        try:
            result = _publish_one(article, platform)
            status = "done" if result.get("success") else "failed"
            url    = result.get("url", "")
            error  = result.get("error", "")
        except Exception as e:
            status = "failed"; url = ""; error = str(e)

        conn = get_conn()
        conn.execute("""INSERT INTO article_publications
            (article_id, platform, url, status, error_message, published_at)
            VALUES (?,?,?,?,?,datetime('now'))""",
            (article_id, platform, url, status, error))
        conn.commit(); conn.close()

        if status == "done":
            db_log("SUCCESS","article_publisher", f"Опубликовано на {platform}: {url}")
        else:
            db_log("ERROR","article_publisher", f"Ошибка {platform}: {error}")

    # Обновляем статус статьи
    conn = get_conn()
    conn.execute("UPDATE articles SET status='published' WHERE id=?", (article_id,))
    conn.commit(); conn.close()

def _publish_one(article: dict, platform: str) -> dict:
    if platform == "telegra_ph":
        return _publish_telegraph(article)
    elif platform == "vk_articles":
        return _publish_vk_article(article)
    else:
        return {"success": False, "error": f"Платформа {platform} — скоро будет доступна"}

def _publish_telegraph(article: dict) -> dict:
    """Публикует на Telegra.ph — бесплатно, без регистрации"""
    import requests
    try:
        # Создаём аккаунт (одноразово)
        account = requests.post("https://api.telegra.ph/createAccount", json={
            "short_name": "SEOFarm",
            "author_name": "SEO Farm"
        }, timeout=15).json()

        if not account.get("ok"):
            return {"success": False, "error": "Не удалось создать аккаунт Telegraph"}

        token = account["result"]["access_token"]

        # Публикуем страницу
        content = [{"tag": "p", "children": [p]}
                   for p in article["content"].split("\n\n") if p.strip()]

        page = requests.post("https://api.telegra.ph/createPage", json={
            "access_token": token,
            "title": article["title"],
            "content": content,
            "return_content": False
        }, timeout=15).json()

        if page.get("ok"):
            return {"success": True, "url": page["result"]["url"]}
        return {"success": False, "error": str(page.get("error","?"))}

    except Exception as e:
        return {"success": False, "error": str(e)}

def _publish_vk_article(article: dict) -> dict:
    """Публикует как статью VK"""
    from core.token_manager import get_active_tokens
    from core.vk_api import api_call

    tokens = get_active_tokens()
    if not tokens:
        return {"success": False, "error": "Нет токенов VK"}

    acc_id, token = random.choice(tokens)

    # Пробуем создать статью через VK Статьи API
    r = api_call("articles.create", {
        "title": article["title"],
        "content": article["content"]
    }, token)

    if "error" not in r:
        url = r.get("response", {}).get("url", "")
        return {"success": True, "url": url}
    return {"success": False, "error": r.get("error","?")}
