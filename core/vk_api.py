"""
core/vk_api.py — Полная обёртка VK API
Взята из VKGA (боевая версия) + функции мониторинга для Агента 2
"""
import requests, time, random, logging, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import VK_API_URL, VK_API_VERSION, DELAY_BETWEEN_ACTIONS, DELAY_JITTER

logger = logging.getLogger("vk_api")


def api_call(method: str, params: dict, token: str, retries: int = 2) -> dict:
    params["access_token"] = token
    params["v"] = VK_API_VERSION
    for attempt in range(retries + 1):
        try:
            r = requests.post(f"{VK_API_URL}{method}", data=params, timeout=30)
            result = r.json()
            if "error" in result:
                code = result["error"].get("error_code", 0)
                msg  = result["error"].get("error_msg", "?")
                if code == 5:  return {"error": f"Токен недействителен: {msg}", "error_code": 5}
                if code == 6:  time.sleep(10); continue
                if code == 9:  time.sleep(30); continue
                if code == 14: return {"error": "Капча — требуется ручная проверка", "error_code": 14}
                if code == 15: return {"error": f"Доступ запрещён: {msg}", "error_code": 15}
                if code == 29: return {"error": f"Лимит запросов: {msg}", "error_code": 29}
                logger.error(f"[VK] {code}: {msg}")
                return {"error": f"VK {code}: {msg}", "error_code": code}
            return result
        except requests.exceptions.ConnectionError:
            return {"error": "Нет соединения с VK"}
        except requests.exceptions.Timeout:
            return {"error": "Таймаут — VK не ответил за 30 сек"}
        except Exception as e:
            if attempt < retries: time.sleep(5); continue
            return {"error": str(e)}
    return {"error": "Все попытки исчерпаны"}


def random_delay():
    d = max(10, DELAY_BETWEEN_ACTIONS + random.randint(-DELAY_JITTER, DELAY_JITTER))
    logger.info(f"[VK] Пауза {d} сек...")
    time.sleep(d)


# ── ТОКЕН ────────────────────────────────────────────────────

def check_token(token: str):
    r = api_call("users.get", {"fields": "photo_50"}, token)
    if "error" in r:
        if r.get("error_code") == 5:
            return False, {"error": "Токен недействителен. Получи новый: python get_token.py"}
        return False, {"error": r["error"]}
    if not r.get("response"):
        return False, {"error": "Пустой ответ от VK"}
    u = r["response"][0]
    name = f"{u.get('first_name','')} {u.get('last_name','')}".strip()
    g = api_call("groups.get", {"count": 1}, token)
    if "error" in g:
        return False, {"error": f"Токен работает ({name}), но нет права 'groups'. Получи новый токен."}
    return True, {"id": u["id"], "name": name, "photo": u.get("photo_50", "")}


def get_any_token():
    from core.database import get_conn
    from core.token_manager import decrypt_token
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, token_encrypted FROM vk_accounts WHERE status='active' LIMIT 1")
    row = c.fetchone()
    conn.close()
    if not row: return None, None
    return decrypt_token(row["token_encrypted"]), row["id"]


# ── СОЗДАНИЕ ГРУППЫ ──────────────────────────────────────────

def create_group(token: str, title: str, description: str = "") -> dict:
    r = api_call("groups.create", {"title": title[:80], "type": "group", "description": description[:4096]}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    if "response" in r:
        gid = r["response"].get("id")
        logger.info(f"[VK] Создана группа {gid}: {title}")
        return {"success": True, "group_id": gid, "data": r["response"]}
    return {"success": False, "error": "Неожиданный ответ VK"}


def edit_group(token: str, group_id: int, title: str = None, description: str = None, website: str = None) -> dict:
    params = {"group_id": group_id}
    if title:       params["title"] = title[:80]
    if description: params["description"] = description[:4096]
    if website:     params["website"] = website
    r = api_call("groups.edit", params, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    return {"success": True}


# ── МЕДИА ────────────────────────────────────────────────────

def upload_avatar(token: str, group_id: int, image_path: str) -> dict:
    r = api_call("photos.getOwnerPhotoUploadServer", {"owner_id": f"-{group_id}"}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    url = r.get("response", {}).get("upload_url")
    if not url: return {"success": False, "error": "Нет URL для аватара"}
    try:
        with open(image_path, "rb") as f:
            ud = requests.post(url, files={"photo": f}, timeout=60).json()
    except Exception as e:
        return {"success": False, "error": str(e)}
    s = api_call("photos.saveOwnerPhoto", {"photo": ud.get("photo"), "server": ud.get("server"), "hash": ud.get("hash")}, token)
    if "error" in s: return {"success": False, "error": s["error"]}
    return {"success": True}


def upload_cover(token: str, group_id: int, image_path: str) -> dict:
    r = api_call("photos.getOwnerCoverPhotoUploadServer", {"group_id": group_id, "crop_x": 0, "crop_y": 0, "crop_x2": 1920, "crop_y2": 768}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    url = r.get("response", {}).get("upload_url")
    if not url: return {"success": False, "error": "Нет URL для обложки"}
    try:
        with open(image_path, "rb") as f:
            ud = requests.post(url, files={"photo": f}, timeout=60).json()
    except Exception as e:
        return {"success": False, "error": str(e)}
    s = api_call("photos.saveOwnerCoverPhoto", {"group_id": group_id, "hash": ud.get("hash"), "photo": ud.get("photo")}, token)
    if "error" in s: return {"success": False, "error": s["error"]}
    return {"success": True}


def upload_photo_for_post(token: str, group_id: int, image_path: str) -> dict:
    r = api_call("photos.getWallUploadServer", {"group_id": group_id}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    url = r.get("response", {}).get("upload_url")
    try:
        with open(image_path, "rb") as f:
            ud = requests.post(url, files={"photo": f}, timeout=60).json()
    except Exception as e:
        return {"success": False, "error": str(e)}
    s = api_call("photos.saveWallPhoto", {"group_id": group_id, "photo": ud.get("photo"), "server": ud.get("server"), "hash": ud.get("hash")}, token)
    if "error" in s: return {"success": False, "error": s["error"]}
    photos = s.get("response", [])
    if photos:
        p = photos[0]
        return {"success": True, "attachment": f"photo{p['owner_id']}_{p['id']}"}
    return {"success": False, "error": "Фото не сохранилось"}


def upload_video_for_post(token: str, group_id: int, video_path: str, title: str = "Видео") -> dict:
    r = api_call("video.save", {"name": title, "group_id": group_id, "wallpost": 0}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    resp = r.get("response", {})
    try:
        with open(video_path, "rb") as f:
            requests.post(resp.get("upload_url"), files={"video_file": f}, timeout=300)
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": True, "attachment": f"video{resp.get('owner_id')}_{resp.get('video_id')}"}


# ── ПОСТЫ ────────────────────────────────────────────────────

def publish_post(token: str, group_id: int, message: str, attachments: str = None) -> dict:
    params = {"owner_id": f"-{group_id}", "from_group": 1, "message": message}
    if attachments: params["attachments"] = attachments
    r = api_call("wall.post", params, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    post_id = r.get("response", {}).get("post_id")
    logger.info(f"[VK] Пост в -{group_id}, id={post_id}")
    return {"success": True, "post_id": post_id}


def pin_post(token: str, group_id: int, post_id: int) -> dict:
    r = api_call("wall.pin", {"owner_id": f"-{group_id}", "post_id": post_id}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    return {"success": True}


def get_nucleus_posts(token: str, nucleus_owner_id: str, count: int = 10) -> dict:
    r = api_call("wall.get", {"owner_id": nucleus_owner_id, "count": count, "filter": "owner"}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    posts = r.get("response", {}).get("items", [])
    posts = [p for p in posts if not p.get("is_pinned") and not p.get("marked_as_ads")]
    return {"success": True, "posts": posts[:count]}


def repost_post(token: str, group_id: int, owner_id: str, post_id: int, message: str = "") -> dict:
    obj = f"wall{owner_id}_{post_id}"
    r = api_call("wall.repost", {"object": obj, "group_id": group_id, "message": message}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    return {"success": True, "new_post_id": r.get("response", {}).get("post_id")}


def parse_group_url(url_or_id: str, token: str) -> dict:
    clean = url_or_id.strip().replace("https://","").replace("http://","").replace("vk.com/","").strip("/")
    if clean.startswith("club") or clean.startswith("-"):
        screen_name = f"club{clean.replace('club','').replace('-','')}"
    else:
        screen_name = clean
    r = api_call("groups.getById", {"group_id": screen_name}, token)
    if "error" in r: return {"success": False, "error": r["error"]}
    groups = r.get("response", [])
    if not groups: return {"success": False, "error": "Группа не найдена"}
    g = groups[0]
    return {"success": True, "group_id": g["id"], "owner_id": f"-{g['id']}", "name": g.get("name",""), "screen_name": g.get("screen_name","")}


# ── МОНИТОРИНГ (Агент 2) ─────────────────────────────────────

def search_comments(token: str, query: str, count: int = 100, start_from=None) -> dict:
    params = {"q": query, "count": min(count, 200), "extended": 1}
    if start_from: params["start_from"] = start_from
    return api_call("newsfeed.search", params, token)


def get_post_comments(token: str, owner_id, post_id: int, count: int = 100) -> dict:
    return api_call("wall.getComments", {
        "owner_id": owner_id, "post_id": post_id,
        "count": min(count, 100), "extended": 1, "thread_items_count": 10
    }, token)


def get_group_info(token: str, group_id) -> dict:
    r = api_call("groups.getById", {"group_id": str(group_id).lstrip("-")}, token)
    if "error" in r: return None
    groups = r.get("response", [])
    return groups[0] if groups else None
