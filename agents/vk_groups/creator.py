"""
agents/vk_groups/creator.py — Создание VK групп (Агент 1)
Полная реализация из VKGA, адаптированная под SEO FARM.
"""
import os, sys, time, random, glob, logging
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.database import get_conn, db_log, get_setting
from core.vk_api import (create_group, edit_group, upload_avatar, upload_cover,
                          upload_photo_for_post, upload_video_for_post,
                          publish_post, pin_post, get_nucleus_posts,
                          parse_group_url, random_delay)
from core.token_manager import get_active_tokens, decrypt_token
from core.config import UPLOADS_DIR, MAX_GROUPS_PER_DAY, MAX_ACTIONS_PER_DAY, REPOST_DAYS, REPOSTS_PER_DAY
from agents.vk_groups.content_gen import generate_name, generate_description, generate_pinned_post_text

logger = logging.getLogger("vk_creator")


def _get_random_file(folder: str):
    files = (glob.glob(os.path.join(folder, "*.jpg")) +
             glob.glob(os.path.join(folder, "*.jpeg")) +
             glob.glob(os.path.join(folder, "*.png")))
    return random.choice(files) if files else None


def _get_random_media(folder: str):
    files = (glob.glob(os.path.join(folder, "*.jpg")) +
             glob.glob(os.path.join(folder, "*.jpeg")) +
             glob.glob(os.path.join(folder, "*.png")) +
             glob.glob(os.path.join(folder, "*.mp4")) +
             glob.glob(os.path.join(folder, "*.mov")))
    return random.choice(files) if files else None


def _get_available_account():
    """Возвращает (account_id, token) с учётом дневных лимитов"""
    from datetime import date
    today = str(date.today())
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT id, token_encrypted, daily_groups, daily_actions, last_reset_date
                 FROM vk_accounts WHERE status='active'""")
    accounts = [dict(r) for r in c.fetchall()]
    conn.close()

    for acc in accounts:
        # Сбрасываем счётчик если новый день
        if acc["last_reset_date"] != today:
            conn = get_conn()
            conn.execute("UPDATE vk_accounts SET daily_groups=0, daily_actions=0, last_reset_date=? WHERE id=?",
                         (today, acc["id"]))
            conn.commit(); conn.close()
            acc["daily_groups"] = 0
            acc["daily_actions"] = 0

        if acc["daily_groups"] < MAX_GROUPS_PER_DAY and acc["daily_actions"] < MAX_ACTIONS_PER_DAY:
            token = decrypt_token(acc["token_encrypted"])
            return acc["id"], token

    return None, None


def _increment_actions(account_id, groups_delta=0, actions_delta=1):
    conn = get_conn()
    conn.execute("""UPDATE vk_accounts
                    SET daily_groups = daily_groups + ?,
                        daily_actions = daily_actions + ?,
                        last_used = datetime('now')
                    WHERE id = ?""",
                 (groups_delta, actions_delta, account_id))
    conn.commit(); conn.close()


def create_group_pipeline(keyword_id: int, keyword: str) -> dict:
    """
    Полный pipeline создания группы (из VKGA):
    1. Получаем аккаунт → 2. Генерируем контент → 3. Создаём группу
    4. Аватар → 5. Обложка → 6. Редактируем описание
    7. Закреп с медиа → 8. Планируем репосты
    """
    db_log("INFO", "vk_creator", f"Запуск pipeline для ключа: '{keyword}'")

    # Настройки
    brand       = get_setting("brand_name", "")
    region      = get_setting("region", "")
    site_url    = get_setting("site_url", "")
    base_desc   = get_setting("base_description", "")
    nucleus_url = get_setting("nucleus_url", "")
    pinned_base = get_setting("pinned_post_text", "")

    if not brand and not region:
        db_log("ERROR", "vk_creator", "Настройки не заданы! Заполни раздел Настройки в панели.")
        return {"success": False, "error": "Сначала заполни Настройки: бренд и регион"}

    # Аккаунт
    account_id, token = _get_available_account()
    if not account_id:
        db_log("WARNING", "vk_creator", "Нет доступных аккаунтов (лимит или нет токенов)")
        return {"success": False, "error": "Нет доступных аккаунтов"}

    db_log("INFO", "vk_creator", f"Используем аккаунт ID={account_id} для '{keyword}'")

    # Генерируем контент
    group_name = generate_name(keyword, brand, region)
    group_desc = generate_description(keyword, base_desc, brand, region, site_url)
    db_log("INFO", "vk_creator", f"Название: '{group_name}'")

    # Создаём группу
    result = create_group(token, group_name, group_desc)
    _increment_actions(account_id, groups_delta=1)
    if not result["success"]:
        db_log("ERROR", "vk_creator", f"Ошибка создания: {result['error']}")
        return {"success": False, "error": result["error"]}

    vk_group_id = result["group_id"]
    db_log("INFO", "vk_creator", f"Группа создана: vk.com/club{vk_group_id}")

    # Сохраняем в БД
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO vk_groups
                 (vk_group_id, vk_group_url, account_id, keyword_id, name, description, status, nucleus_url)
                 VALUES (?,?,?,?,?,?,'creating',?)""",
              (str(vk_group_id), f"https://vk.com/club{vk_group_id}",
               account_id, keyword_id, group_name, group_desc, nucleus_url))
    group_db_id = c.lastrowid
    if keyword_id:
        c.execute("UPDATE vk_keywords SET used=1, group_id=? WHERE id=?", (group_db_id, keyword_id))
    conn.commit(); conn.close()

    # Аватар
    avatar = _get_random_file(os.path.join(UPLOADS_DIR, "avatars"))
    if avatar:
        time.sleep(5)
        r = upload_avatar(token, vk_group_id, avatar)
        _increment_actions(account_id)
        db_log("INFO" if r["success"] else "WARNING", "vk_creator",
               f"Аватар: {'OK' if r['success'] else r['error']}")
    else:
        db_log("WARNING", "vk_creator", "Нет аватара в uploads/avatars/")

    # Обложка
    cover = _get_random_file(os.path.join(UPLOADS_DIR, "covers"))
    if cover:
        time.sleep(5)
        r = upload_cover(token, vk_group_id, cover)
        _increment_actions(account_id)
        db_log("INFO" if r["success"] else "WARNING", "vk_creator",
               f"Обложка: {'OK' if r['success'] else r['error']}")
    else:
        db_log("WARNING", "vk_creator", "Нет обложки в uploads/covers/")

    # Редактируем группу (добавляем сайт)
    time.sleep(5)
    edit_group(token, vk_group_id, description=group_desc, website=site_url)
    _increment_actions(account_id)

    # Закреплённый пост с медиа
    time.sleep(8)
    pinned_text = generate_pinned_post_text(keyword, pinned_base, brand, site_url, region)
    media = _get_random_media(os.path.join(UPLOADS_DIR, "media"))
    attachment = None

    if media:
        ext = os.path.splitext(media)[1].lower()
        if ext in [".mp4", ".mov"]:
            mr = upload_video_for_post(token, vk_group_id, media)
        else:
            mr = upload_photo_for_post(token, vk_group_id, media)
        _increment_actions(account_id)
        if mr["success"]:
            attachment = mr.get("attachment")
            db_log("INFO", "vk_creator", f"Медиа загружено: {attachment}")
        else:
            db_log("WARNING", "vk_creator", f"Медиа не загружено: {mr['error']}")

    time.sleep(5)
    post_result = publish_post(token, vk_group_id, pinned_text, attachment)
    _increment_actions(account_id)

    if post_result["success"]:
        post_id = post_result["post_id"]
        time.sleep(3)
        pin_post(token, vk_group_id, post_id)
        _increment_actions(account_id)
        conn = get_conn()
        conn.execute("UPDATE vk_groups SET post_id=? WHERE id=?", (str(post_id), group_db_id))
        conn.commit(); conn.close()
        db_log("INFO", "vk_creator", f"Закреплённый пост опубликован (id={post_id})")
    else:
        db_log("WARNING", "vk_creator", f"Пост не опубликован: {post_result['error']}")

    # Планируем репосты из ядра
    if nucleus_url:
        _schedule_reposts(account_id, group_db_id, vk_group_id, nucleus_url, token)

    # Финал
    conn = get_conn()
    conn.execute("UPDATE vk_groups SET status='done' WHERE id=?", (group_db_id,))
    conn.commit(); conn.close()

    db_log("INFO", "vk_creator",
           f"Pipeline завершён! Группа vk.com/club{vk_group_id} '{group_name}'")

    return {
        "success": True,
        "group_db_id": group_db_id,
        "vk_group_id": vk_group_id,
        "group_url": f"https://vk.com/club{vk_group_id}",
        "name": group_name
    }


def _schedule_reposts(account_id, group_db_id, vk_group_id, nucleus_url, token):
    nucleus_info = parse_group_url(nucleus_url, token)
    if not nucleus_info["success"]:
        db_log("WARNING", "vk_creator", f"URL ядра не разобрать: {nucleus_info['error']}")
        return

    owner_id = nucleus_info["owner_id"]
    posts_r = get_nucleus_posts(token, owner_id, count=10)
    if not posts_r["success"]:
        db_log("WARNING", "vk_creator", f"Посты ядра: {posts_r['error']}")
        return

    posts = posts_r["posts"]
    db_log("INFO", "vk_creator", f"Получено {len(posts)} постов из ядра, планируем репосты")

    post_idx = 0
    conn = get_conn()
    for day in range(REPOST_DAYS):
        for rep in range(REPOSTS_PER_DAY):
            if post_idx >= len(posts): break
            post = posts[post_idx]; post_idx += 1
            hours = max(1, day * 24 + rep * (24 // max(REPOSTS_PER_DAY, 1)) + random.randint(-2, 2))
            sched = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
            import json
            conn.execute("""INSERT INTO tasks (agent, type, account_id, ref_id, payload, scheduled_time)
                            VALUES ('vk_groups','repost',?,?,?,?)""",
                         (account_id, group_db_id,
                          json.dumps({"vk_group_id": vk_group_id, "owner_id": owner_id,
                                      "post_id": post["id"], "nucleus_url": nucleus_url}),
                          sched))
    conn.commit(); conn.close()
    db_log("INFO", "vk_creator", f"Репосты запланированы для группы {vk_group_id}")
