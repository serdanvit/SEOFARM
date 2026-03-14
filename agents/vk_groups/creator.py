"""
agents/vk_groups/creator.py — Агент 1: Создание VK групп
Полный pipeline: сайт → ниша → ключи → группа → SEO → прогрев
"""
import os, sys, time, random, glob, json, re, logging
from datetime import datetime, timedelta, date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.db import fetchone, fetchall, execute
from core.database import db_log, get_setting
from core.vk_api import (create_group, edit_group, upload_avatar, upload_cover,
                          upload_photo_for_post, upload_video_for_post,
                          publish_post, pin_post, api_call, human_delay)
from core.token_manager import decrypt_token
from core.config import UPLOADS_DIR, MAX_GROUPS_PER_DAY, MAX_ACTIONS_PER_DAY
from core.ai_content import (generate_keywords, generate_group_name,
                              generate_group_description, generate_pinned_post,
                              analyze_niche, check_ollama_status)
from core.keyword_base import expand_keywords, detect_niche, get_niche_data
from core.yandex_ping import submit_url
from agents.vk_groups.warmup import schedule_warmup

logger = logging.getLogger("vk_creator")


# ── Вспомогательные функции ─────────────────────────────────

def _rand_file(folder, exts=("jpg", "jpeg", "png")):
    files = []
    for e in exts:
        files += glob.glob(os.path.join(folder, f"*.{e}"))
    return random.choice(files) if files else None


def _rand_media(folder):
    return _rand_file(folder, ("jpg", "jpeg", "png", "mp4", "mov"))


def _get_account():
    """Возвращает (account_id, token) с учётом дневных лимитов"""
    today = str(date.today())
    accounts = fetchall(
        "SELECT id,token_encrypted,daily_groups,daily_actions,last_reset_date "
        "FROM vk_accounts WHERE status='active'"
    )
    for acc in accounts:
        if acc["last_reset_date"] != today:
            execute(
                "UPDATE vk_accounts SET daily_groups=0,daily_actions=0,"
                "last_reset_date=? WHERE id=?",
                (today, acc["id"])
            )
            acc = dict(acc)
            acc["daily_groups"] = 0
            acc["daily_actions"] = 0

        if (acc["daily_groups"] < MAX_GROUPS_PER_DAY
                and acc["daily_actions"] < MAX_ACTIONS_PER_DAY):
            return acc["id"], decrypt_token(acc["token_encrypted"])
    return None, None


def _inc(aid, groups=0, actions=1):
    execute(
        "UPDATE vk_accounts SET daily_groups=daily_groups+?,"
        "daily_actions=daily_actions+?,last_used=datetime('now') WHERE id=?",
        (groups, actions, aid)
    )


def _transliterate(text: str) -> str:
    """Транслит русского текста в латиницу для URL группы"""
    table = {
        "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo",
        "ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m",
        "н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u",
        "ф":"f","х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"shch",
        "ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
        " ":"_","-":"_",".":"","(":"",")":"",",":"","«":"","»":"","—":"_",
    }
    result = ""
    for char in text.lower():
        result += table.get(char, char)
    # Убираем не-ASCII и длинные подчёркивания
    result = re.sub(r"[^a-z0-9_]", "", result)
    result = re.sub(r"_+", "_", result).strip("_")
    return result[:50]


def _set_group_url(token: str, group_id: int, keyword: str) -> bool:
    """Устанавливает короткий адрес группы (SEO-фактор)"""
    short = _transliterate(keyword)
    if not short:
        return False

    # Добавляем случайный суффикс чтобы избежать конфликтов
    suffix = str(random.randint(100, 999))
    screen_name = f"{short}_{suffix}"

    r = api_call("groups.editAddress", {
        "group_id":    group_id,
        "screen_name": screen_name,
    }, token)

    if "error" not in r:
        db_log("INFO", "vk_creator",
               f"URL группы: vk.com/{screen_name}")
        return True
    else:
        # groups.editAddress может не работать — пробуем utils.resolveScreenName
        # через groups.edit тоже не всегда доступно
        db_log("WARNING", "vk_creator",
               f"URL не установлен: {r.get('error','?')} — оставляем club{group_id}")
        return False


# ── Основной pipeline ────────────────────────────────────────

def create_group_pipeline(keyword_id, keyword: str,
                          site_data: dict = None) -> dict:
    """
    Создаёт одну VK группу под ключевое слово.
    site_data: уже спарсенные данные сайта (если есть).
    """
    db_log("INFO", "vk_creator", f"Старт: «{keyword}»")

    # Настройки из системы
    brand    = get_setting("brand_name", "")
    region   = get_setting("region", "")
    site_url = get_setting("site_url", "")
    nucleus  = get_setting("nucleus_url", "")

    if not brand or not site_url:
        return {"success": False,
                "error": "Заполни Настройки: Бренд и Сайт обязательны"}

    aid, token = _get_account()
    if not aid:
        return {"success": False,
                "error": "Нет доступных аккаунтов (лимит на сегодня или нет токенов)"}

    # Данные с сайта
    services = []
    utp      = ""
    if site_data:
        services = site_data.get("services", [])
        utp      = site_data.get("utp", "")
        if not brand and site_data.get("brand"):
            brand = site_data["brand"]
        if not region and site_data.get("region"):
            region = site_data["region"]

    # ── Шаг 1: Название ──────────────────────────────────────
    name = generate_group_name(keyword, brand, region)
    db_log("INFO", "vk_creator", f"Название: «{name}»")

    # ── Шаг 2: Описание ──────────────────────────────────────
    desc = generate_group_description(
        keyword, brand, region, site_url, services, utp
    )

    # ── Шаг 3: Создание группы ───────────────────────────────
    human_delay(0.5)
    r = create_group(token, name, desc)
    _inc(aid, groups=1)

    if not r["success"]:
        db_log("ERROR", "vk_creator", f"Ошибка создания: {r['error']}")
        return r

    vk_gid = r["group_id"]
    db_log("INFO", "vk_creator", f"Создана: vk.com/club{vk_gid}")

    # Сохраняем в БД
    gdb_id = execute(
        "INSERT INTO vk_groups(vk_group_id,vk_group_url,account_id,keyword_id,"
        "name,description,status,nucleus_url) VALUES(?,?,?,?,?,?,'creating',?)",
        (str(vk_gid), f"https://vk.com/club{vk_gid}",
         aid, keyword_id, name, desc, nucleus)
    )
    if keyword_id:
        execute("UPDATE vk_keywords SET used=1,group_id=? WHERE id=?",
                (gdb_id, keyword_id))

    # ── Шаг 4: URL группы (SEO-фактор) ───────────────────────
    human_delay(0.4)
    url_ok = _set_group_url(token, vk_gid, keyword)
    _inc(aid)

    # ── Шаг 5: Аватар ────────────────────────────────────────
    av_file = _rand_file(os.path.join(UPLOADS_DIR, "avatars"))
    if av_file:
        human_delay(0.3)
        r2 = upload_avatar(token, vk_gid, av_file)
        _inc(aid)
        db_log("INFO" if r2["success"] else "WARNING", "vk_creator",
               f"Аватар: {'OK' if r2['success'] else r2.get('error','?')}")
    else:
        db_log("WARNING", "vk_creator",
               "Нет аватара — добавь фото в uploads/avatars/")

    # ── Шаг 6: Обложка ───────────────────────────────────────
    cv_file = _rand_file(os.path.join(UPLOADS_DIR, "covers"))
    if cv_file:
        human_delay(0.3)
        r2 = upload_cover(token, vk_gid, cv_file)
        _inc(aid)
        db_log("INFO" if r2["success"] else "WARNING", "vk_creator",
               f"Обложка: {'OK' if r2['success'] else r2.get('error','?')}")
    else:
        db_log("WARNING", "vk_creator",
               "Нет обложки — добавь фото в uploads/covers/")

    # ── Шаг 7: Сайт в профиле ────────────────────────────────
    human_delay(0.3)
    edit_group(token, vk_gid, description=desc, website=site_url)
    _inc(aid)

    # ── Шаг 8: Закреплённый пост ─────────────────────────────
    human_delay(0.4)
    post_text = generate_pinned_post(
        keyword, brand, region, site_url, services, utp
    )

    media_file = _rand_media(os.path.join(UPLOADS_DIR, "media"))
    attachment = None
    if media_file:
        ext = os.path.splitext(media_file)[1].lower()
        mr  = (upload_video_for_post(token, vk_gid, media_file)
               if ext in (".mp4", ".mov")
               else upload_photo_for_post(token, vk_gid, media_file))
        _inc(aid)
        if mr["success"]:
            attachment = mr.get("attachment")

    pr = publish_post(token, vk_gid, post_text, attachment)
    _inc(aid)

    if pr["success"]:
        pid = pr["post_id"]
        human_delay(0.2)
        pin_post(token, vk_gid, pid)
        _inc(aid)
        execute("UPDATE vk_groups SET post_id=?,posts_count=1 WHERE id=?",
                (str(pid), gdb_id))
        db_log("INFO", "vk_creator", f"Закреп #{pid} опубликован")
    else:
        db_log("WARNING", "vk_creator",
               f"Пост не создан: {pr.get('error','?')}")

    # ── Шаг 9: Подача в Яндекс ───────────────────────────────
    ym_token = get_setting("yandex_webmaster_token", "")
    group_url = f"https://vk.com/club{vk_gid}"
    submit_url(group_url, ym_token)

    # ── Шаг 10: Планируем прогрев 7 дней ─────────────────────
    schedule_warmup(
        group_db_id=gdb_id,
        vk_group_id=vk_gid,
        account_id=aid,
        keyword=keyword,
        brand=brand,
        region=region,
        site_url=site_url,
        services=services,
    )

    # Финал
    execute("UPDATE vk_groups SET status='done' WHERE id=?", (gdb_id,))
    db_log("SUCCESS", "vk_creator",
           f"✅ Готово: vk.com/club{vk_gid} «{name}»")

    return {
        "success":      True,
        "group_db_id":  gdb_id,
        "vk_group_id":  vk_gid,
        "group_url":    group_url,
        "name":         name,
        "keyword":      keyword,
    }


# ── Запуск всей кампании ─────────────────────────────────────

def run_campaign(site_url: str = None, count: int = 30) -> dict:
    """
    Главная функция — запускает создание N групп по сайту клиента.
    1. Парсит сайт
    2. Определяет нишу через AI
    3. Генерирует ключи
    4. Планирует создание групп (1-2 в день)
    """
    from core.site_parser import parse_site

    if not site_url:
        site_url = get_setting("site_url", "")
    if not site_url:
        return {"success": False, "error": "Сайт не задан в настройках"}

    region = get_setting("region", "")
    brand  = get_setting("brand_name", "")

    db_log("INFO", "vk_creator", f"Кампания: {site_url}, {count} групп")

    # ── Парсинг сайта ─────────────────────────────────────────
    db_log("INFO", "vk_creator", "Парсинг сайта...")
    site = parse_site(site_url)

    if site.get("error"):
        db_log("WARNING", "vk_creator",
               f"Парсинг: {site['error']} — продолжаем без данных сайта")

    # ── Анализ ниши через AI ──────────────────────────────────
    site_data = {}
    if site.get("text"):
        db_log("INFO", "vk_creator", "AI анализирует нишу...")
        site_data = analyze_niche(site["text"])
        if not brand and site_data.get("brand"):
            brand = site_data["brand"]
        if not region and site_data.get("region"):
            region = site_data["region"]

    niche    = site_data.get("niche", "")
    services = site_data.get("services", [])
    utp      = site_data.get("utp", "")

    if not niche and site.get("text"):
        niche = detect_niche(site["text"])

    db_log("INFO", "vk_creator",
           f"Ниша: {niche}, бренд: {brand}, регион: {region}")

    # ── Генерация ключей ──────────────────────────────────────
    db_log("INFO", "vk_creator", f"Генерирую {count} ключей...")

    ollama = check_ollama_status()
    if ollama["running"]:
        keywords = generate_keywords(niche or brand, region,
                                     services, brand, count)
    else:
        keywords = expand_keywords(niche or brand, region, services, count)

    if not keywords:
        return {"success": False,
                "error": "Не удалось сгенерировать ключевые слова"}

    db_log("INFO", "vk_creator",
           f"Сгенерировано {len(keywords)} ключей")

    # ── Сохраняем ключи в БД ─────────────────────────────────
    keyword_ids = []
    for kw in keywords:
        existing = fetchone(
            "SELECT id FROM vk_keywords WHERE keyword=?", (kw,)
        )
        if existing:
            keyword_ids.append((existing["id"], kw))
        else:
            kid = execute(
                "INSERT INTO vk_keywords(keyword,region,used) VALUES(?,?,0)",
                (kw, region)
            )
            keyword_ids.append((kid, kw))

    # ── Планируем создание групп по 1-2 в день ───────────────
    now    = datetime.now()
    day    = 0
    count_today = 0
    MAX_PER_DAY = 2
    scheduled = 0

    for kid, kw in keyword_ids:
        if count_today >= MAX_PER_DAY:
            day += 1
            count_today = 0

        hour   = random.randint(10, 20)
        minute = random.randint(0, 59)
        sched  = (now + timedelta(days=day)).replace(
            hour=hour, minute=minute, second=0
        )

        payload = {
            "keyword_id": kid,
            "keyword":    kw,
            "site_data":  site_data,
        }
        execute(
            "INSERT INTO tasks(agent,type,payload,scheduled_time,status) "
            "VALUES('vk_groups','create',?,?,'pending')",
            (json.dumps(payload, ensure_ascii=False),
             sched.strftime("%Y-%m-%d %H:%M:%S"))
        )

        count_today += 1
        scheduled   += 1

    db_log("SUCCESS", "vk_creator",
           f"Кампания запланирована: {scheduled} групп за {day+1} дней")

    return {
        "success":    True,
        "keywords":   len(keyword_ids),
        "scheduled":  scheduled,
        "days":       day + 1,
        "niche":      niche,
        "brand":      brand,
        "region":     region,
        "site_data":  site_data,
    }
