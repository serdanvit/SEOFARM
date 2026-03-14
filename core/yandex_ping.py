"""
core/yandex_ping.py — Ускоренная индексация через Яндекс.Вебмастер
Отправляет URL новой группы на индексацию — сокращает срок с 2-4 недель до 3-7 дней.
"""
import requests, logging, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("yandex_ping")

PING_URL = "https://webmaster.yandex.ru/ping"
QUOTA_URL = "https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/recrawl/quota"
RECRAWL_URL = "https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/recrawl/queue"


def ping_url(url: str) -> bool:
    """
    Бесплатный ping — уведомляет Яндекс о новой странице.
    Работает без токена, но менее надёжен.
    """
    try:
        r = requests.get(PING_URL, params={"sitemap": url}, timeout=10)
        ok = r.status_code == 200
        logger.info(f"[yandex_ping] ping {'OK' if ok else 'FAIL'}: {url}")
        return ok
    except Exception as e:
        logger.error(f"[yandex_ping] ping error: {e}")
        return False


def submit_url(group_url: str, webmaster_token: str = "",
               user_id: str = "", host_id: str = "") -> dict:
    """
    Отправляет URL VK группы на переобход через API Яндекс.Вебмастер.
    Если токен не задан — использует бесплатный ping.

    group_url: полный URL группы (https://vk.com/clubXXXX)
    webmaster_token: OAuth токен Яндекс.Вебмастера
    """
    # Сначала бесплатный ping — всегда
    ping_ok = ping_url(group_url)

    # Если нет токена — только ping
    if not webmaster_token:
        return {
            "success":  ping_ok,
            "method":   "ping",
            "url":      group_url,
        }

    # Полный API Вебмастера
    try:
        headers = {"Authorization": f"OAuth {webmaster_token}"}

        # Добавляем URL в очередь переобхода
        api_url = RECRAWL_URL.format(user_id=user_id, host_id=host_id)
        r = requests.post(api_url, headers=headers,
                         json={"url": group_url}, timeout=15)

        if r.status_code in (200, 201):
            logger.info(f"[yandex_ping] API OK: {group_url}")
            return {"success": True, "method": "api", "url": group_url}
        else:
            logger.warning(f"[yandex_ping] API {r.status_code}: {r.text[:200]}")
            # Fallback на ping
            return {"success": ping_ok, "method": "ping", "url": group_url}

    except Exception as e:
        logger.error(f"[yandex_ping] API error: {e}")
        return {"success": ping_ok, "method": "ping", "url": group_url}


def submit_batch(urls: list, webmaster_token: str = "",
                 user_id: str = "", host_id: str = "") -> dict:
    """Отправляет несколько URL пакетом"""
    results = {"ok": 0, "fail": 0, "urls": []}
    for url in urls:
        r = submit_url(url, webmaster_token, user_id, host_id)
        if r["success"]:
            results["ok"] += 1
        else:
            results["fail"] += 1
        results["urls"].append(r)
    return results
