"""
core/vk_api.py — VK API с защитой от блокировок
Работает на Python 3.8+ включая 3.14 alpha. Нет бинарных зависимостей.
"""
import requests, time, random, logging, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import VK_API_URL, VK_API_VERSION, DELAY_BETWEEN_ACTIONS, DELAY_JITTER

logger = logging.getLogger("vk_api")

# Реальные User-Agent — VK видит браузер, не скрипт
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/118.0.0.0 Safari/537.36 Edg/118.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]

# Ошибки: временные (retry) / лимиты (долгое ожидание) / критические (стоп)
RETRY_CODES = {6, 9, 10, 603}
LIMIT_CODES  = {29, 30}
FATAL_CODES  = {5, 15, 17, 100, 101, 113, 125}


def api_call(method: str, params: dict, token: str, retries: int = 3) -> dict:
    """Вызов VK API с ретраями, рандомным User-Agent и обработкой всех ошибок"""
    params = dict(params)
    params["access_token"] = token
    params["v"] = VK_API_VERSION

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Connection": "keep-alive",
    }

    for attempt in range(retries + 1):
        try:
            resp = requests.post(f"{VK_API_URL}{method}", data=params,
                                 headers=headers, timeout=30)
            result = resp.json()

            if "error" in result:
                code = result["error"].get("error_code", 0)
                msg  = result["error"].get("error_msg", "?")

                if code in FATAL_CODES:
                    logger.error(f"[VK] Фатальная ошибка {code}: {msg}")
                    return {"error": f"VK {code}: {msg}", "error_code": code}
                if code == 14:
                    return {"error": "Капча (14) — сделай паузу 1-2 часа", "error_code": 14}
                if code in LIMIT_CODES:
                    time.sleep(60 + attempt * 30); continue
                if code in RETRY_CODES:
                    time.sleep(10 + attempt * 10); continue

                logger.error(f"[VK] {code}: {msg}")
                return {"error": f"VK {code}: {msg}", "error_code": code}

            return result

        except requests.exceptions.ConnectionError:
            if attempt < retries: time.sleep(5); continue
            return {"error": "Нет соединения с VK"}
        except requests.exceptions.Timeout:
            if attempt < retries: time.sleep(10); continue
            return {"error": "Таймаут VK"}
        except Exception as e:
            if attempt < retries: time.sleep(5); continue
            return {"error": str(e)}

    return {"error": "Все попытки исчерпаны"}


def human_delay(multiplier: float = 1.0):
    """Имитация живого пользователя — случайная пауза"""
    wait = max(8, (DELAY_BETWEEN_ACTIONS + random.randint(-DELAY_JITTER, DELAY_JITTER)) * multiplier)
    if random.random() < 0.08:  # иногда длинная пауза
        wait += random.randint(30, 90)
    time.sleep(wait)


# ── ТОКЕН ────────────────────────────────────────────────────

def check_token(token: str) -> tuple:
    r = api_call("users.get", {"fields": "photo_50"}, token)
    if "error" in r:
        if r.get("error_code") == 5:
            return False, {"error": "Токен недействителен — получи новый через get_token.py"}
        return False, {"error": r["error"]}
    if not r.get("response"):
        return False, {"error": "Пустой ответ VK"}
    u    = r["response"][0]
    name = f"{u.get('first_name','')} {u.get('last_name','')}".strip()
    info = {"id": u["id"], "name": name, "photo": u.get("photo_50", ""), "warnings": []}
    # Проверяем права но НЕ блокируем добавление
    g = api_call("groups.get", {"count": 1}, token)
    if "error" in g:
        info["warnings"].append("Нет права groups — создание групп может не работать")
    return True, info


def get_any_token():
    from core.db import fetchone
    from core.token_manager import decrypt_token
    row = fetchone("SELECT id, token_encrypted FROM vk_accounts WHERE status='active' LIMIT 1")
    if not row: return None, None
    return decrypt_token(row["token_encrypted"]), row["id"]


# ── ГРУППЫ ───────────────────────────────────────────────────

def create_group(token, title, description=""):
    r = api_call("groups.create", {"title": title[:80], "type": "group",
                                    "description": description[:4096]}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    gid = r.get("response", {}).get("id")
    logger.info(f"[VK] Создана группа {gid}: {title}")
    return {"success": True, "group_id": gid}


def edit_group(token, group_id, title=None, description=None, website=None):
    params = {"group_id": group_id}
    if title:       params["title"]       = title[:80]
    if description: params["description"] = description[:4096]
    if website:     params["website"]     = website
    r = api_call("groups.edit", params, token)
    return {"success": "error" not in r, "error": r.get("error", "")}


def parse_group_url(url_or_id, token):
    clean = url_or_id.strip()
    for p in ["https://vk.com/", "http://vk.com/", "vk.com/"]:
        clean = clean.replace(p, "")
    clean = clean.strip("/")
    screen = f"club{clean.replace('club','').lstrip('-')}" if (clean.startswith("club") or clean.lstrip("-").isdigit()) else clean
    r = api_call("groups.getById", {"group_id": screen}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    groups = r.get("response", [])
    if not groups: return {"success": False, "error": "Группа не найдена"}
    g = groups[0]
    return {"success": True, "group_id": g["id"], "owner_id": f"-{g['id']}",
            "name": g.get("name", ""), "screen_name": g.get("screen_name", "")}


# ── ЗАГРУЗКА МЕДИА ───────────────────────────────────────────

def _upload(url, file_path, field="photo"):
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    with open(file_path, "rb") as f:
        return requests.post(url, files={field: f}, headers=headers, timeout=120).json()


def upload_avatar(token, group_id, image_path):
    r = api_call("photos.getOwnerPhotoUploadServer", {"owner_id": f"-{group_id}"}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    url = r.get("response", {}).get("upload_url")
    if not url: return {"success": False, "error": "Нет upload_url"}
    try:
        ud = _upload(url, image_path)
    except Exception as e:
        return {"success": False, "error": str(e)}
    s = api_call("photos.saveOwnerPhoto", {"photo": ud.get("photo"),
                  "server": ud.get("server"), "hash": ud.get("hash")}, token)
    return {"success": "error" not in s, "error": s.get("error", "")}


def upload_cover(token, group_id, image_path):
    r = api_call("photos.getOwnerCoverPhotoUploadServer",
                 {"group_id": group_id, "crop_x": 0, "crop_y": 0,
                  "crop_x2": 1920, "crop_y2": 768}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    url = r.get("response", {}).get("upload_url")
    if not url: return {"success": False, "error": "Нет upload_url"}
    try:
        ud = _upload(url, image_path)
    except Exception as e:
        return {"success": False, "error": str(e)}
    s = api_call("photos.saveOwnerCoverPhoto",
                 {"group_id": group_id, "hash": ud.get("hash"), "photo": ud.get("photo")}, token)
    return {"success": "error" not in s, "error": s.get("error", "")}


def upload_photo_for_post(token, group_id, image_path):
    r = api_call("photos.getWallUploadServer", {"group_id": group_id}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    url = r.get("response", {}).get("upload_url")
    try:
        ud = _upload(url, image_path)
    except Exception as e:
        return {"success": False, "error": str(e)}
    s = api_call("photos.saveWallPhoto",
                 {"group_id": group_id, "photo": ud.get("photo"),
                  "server": ud.get("server"), "hash": ud.get("hash")}, token)
    if "error" in s: return {"success": False, "error": s["error"]}
    photos = s.get("response", [])
    if photos:
        p = photos[0]
        return {"success": True, "attachment": f"photo{p['owner_id']}_{p['id']}"}
    return {"success": False, "error": "Фото не сохранилось"}


def upload_video_for_post(token, group_id, video_path, title="Видео"):
    r = api_call("video.save", {"name": title, "group_id": group_id, "wallpost": 0}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    resp = r.get("response", {})
    try:
        _upload(resp.get("upload_url", ""), video_path, field="video_file")
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": True, "attachment": f"video{resp.get('owner_id')}_{resp.get('video_id')}"}


# ── ПОСТЫ ────────────────────────────────────────────────────

def publish_post(token, group_id, message, attachments=None):
    params = {"owner_id": f"-{group_id}", "from_group": 1, "message": message}
    if attachments: params["attachments"] = attachments
    r = api_call("wall.post", params, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    return {"success": True, "post_id": r.get("response", {}).get("post_id")}


def pin_post(token, group_id, post_id):
    r = api_call("wall.pin", {"owner_id": f"-{group_id}", "post_id": post_id}, token)
    return {"success": "error" not in r, "error": r.get("error", "")}


def get_nucleus_posts(token, nucleus_owner_id, count=10):
    r = api_call("wall.get", {"owner_id": nucleus_owner_id, "count": count, "filter": "owner"}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    posts = [p for p in r.get("response", {}).get("items", [])
             if not p.get("is_pinned") and not p.get("marked_as_ads")]
    return {"success": True, "posts": posts[:count]}


def repost_post(token, group_id, owner_id, post_id, message=""):
    r = api_call("wall.repost",
                 {"object": f"wall{owner_id}_{post_id}", "group_id": group_id, "message": message},
                 token)
    if "error" in r: return {"success": False, "error": r["error"]}
    return {"success": True, "new_post_id": r.get("response", {}).get("post_id")}


# ── МОНИТОРИНГ ───────────────────────────────────────────────

def search_comments(token, query, count=100, start_from=None):
    params = {"q": query, "count": min(count, 200), "extended": 1}
    if start_from: params["start_from"] = start_from
    return api_call("newsfeed.search", params, token)


def get_post_comments(token, owner_id, post_id, count=100):
    return api_call("wall.getComments",
                    {"owner_id": owner_id, "post_id": post_id,
                     "count": min(count, 100), "extended": 1}, token)


def get_group_info(token, group_id):
    r = api_call("groups.getById", {"group_id": str(group_id).lstrip("-")}, token)
    if "error" in r: return None
    groups = r.get("response", [])
    return groups[0] if groups else None
