"""
agents/comment_monitor/monitor.py — Агент 2: Мониторинг комментариев
Ищет реальные комментарии людей в VK по ключевым запросам.
Находит → анализирует → отправляет менеджеру в Telegram.
"""
import os, sys, time, random, re, json, logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.database import get_conn, db_log, get_setting
from core.vk_api import api_call, search_comments, get_post_comments, get_group_info
from core.token_manager import get_active_tokens
from core.config import MONITOR_COMMENT_AGE_HOURS

logger = logging.getLogger("comment_monitor")

# ============================================================
# ФИЛЬТРАЦИЯ — отличаем живых людей от ботов/групп
# ============================================================

# Слова которые выдают рекламный/спамный комментарий — пропускаем
SPAM_PATTERNS = [
    r"подпишись", r"переходи по ссылке", r"заработок", r"млм",
    r"http[s]?://", r"t\.me/", r"@[a-zA-Z0-9_]{5,}",
    r"скидка \d+%", r"акция", r"промокод",
]

# Слова которые говорят что человек ИЩЕТ что-то — нужные нам
INTENT_KEYWORDS = [
    "ищу", "ищем", "посоветуйте", "посоветуй", "порекомендуйте",
    "подскажите", "подскажи", "помогите", "кто знает", "где найти",
    "где можно", "кто сталкивался", "кто пользовался", "есть ли",
    "какие варианты", "стоит ли", "как выбрать", "что выбрать",
    "помогите выбрать", "хочу найти", "нужна помощь", "нужен совет",
    "нужно найти", "нужна рекомендация", "нужны варианты",
    "интересует", "рассматриваю", "думаем о", "планируем",
    "сравните", "стоит идти", "хороший ли", "плохой ли",
    "отзывы", "реальные отзывы", "кто ходил", "кто учился",
]

def _is_spam(text):
    """Возвращает True если это реклама/спам"""
    text_lower = text.lower()
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def _has_intent(text, extra_keywords=None):
    """
    Возвращает True если человек явно что-то ищет/спрашивает.
    extra_keywords — доп. слова из конкретного запроса.
    """
    text_lower = text.lower()
    # Проверяем базовые слова намерения
    for kw in INTENT_KEYWORDS:
        if kw in text_lower:
            return True
    # Проверяем дополнительные ключи
    if extra_keywords:
        for kw in extra_keywords:
            if kw.lower() in text_lower:
                return True
    # Вопросительные предложения тоже считаем
    if "?" in text and len(text) > 30:
        return True
    return False

def _is_too_old(timestamp_unix):
    """Возвращает True если комментарий слишком старый"""
    if not timestamp_unix:
        return False
    dt = datetime.fromtimestamp(int(timestamp_unix))
    age = datetime.now() - dt
    return age.total_seconds() > MONITOR_COMMENT_AGE_HOURS * 3600

def _already_saved(post_url, author_id):
    """Проверяет что мы уже сохранили этот лид"""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM monitor_leads WHERE post_url=? AND author_id=?",
        (post_url, str(author_id))
    )
    exists = c.fetchone() is not None
    conn.close()
    return exists

# ============================================================
# СОХРАНЕНИЕ ЛИДА
# ============================================================

def _save_lead(query_id, query_text, source, author_id, author_name,
               author_url, text, post_url, group_name=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO monitor_leads
        (query_id, query_text, source, author_id, author_name, author_url,
         text, post_url, group_name, status, sent_to_telegram)
        VALUES (?,?,?,?,?,?,?,?,?,'new',0)""",
        (query_id, query_text, source, str(author_id), author_name,
         author_url, text, post_url, group_name))
    lead_id = c.lastrowid
    c.execute("UPDATE monitor_queries SET found_total=found_total+1 WHERE id=?",
              (query_id,))
    conn.commit()
    conn.close()
    return lead_id

# ============================================================
# TELEGRAM УВЕДОМЛЕНИЯ
# ============================================================

def send_telegram(text):
    """Отправляет сообщение всем менеджерам в Telegram"""
    bot_token = get_setting("telegram_bot_token", "")
    chat_ids_raw = get_setting("telegram_chat_ids", "")

    if not bot_token or not chat_ids_raw:
        logger.warning("Telegram не настроен — пропускаем отправку")
        return False

    chat_ids = [x.strip() for x in chat_ids_raw.split(",") if x.strip()]
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    success = False

    for chat_id in chat_ids:
        try:
            import requests
            r = requests.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }, timeout=10)
            if r.ok:
                success = True
        except Exception as e:
            logger.error(f"Ошибка Telegram [{chat_id}]: {e}")

    return success

def _format_lead_message(lead: dict, query_text: str) -> str:
    """Форматирует красивое сообщение для менеджера"""
    author = lead.get("author_name", "Неизвестный")
    text   = lead.get("text", "")[:400]
    url    = lead.get("post_url", "")
    group  = lead.get("group_name", "")
    ts     = lead.get("found_at", "")[:16]

    msg = (
        f"🎯 <b>НОВЫЙ ЛИД — горячий запрос!</b>\n\n"
        f"🔍 <b>Запрос:</b> {query_text}\n"
        f"👤 <b>Автор:</b> {author}\n"
        f"📍 <b>Группа:</b> {group}\n"
        f"🕐 <b>Время:</b> {ts}\n\n"
        f"💬 <b>Что написал:</b>\n<i>{text}</i>\n\n"
        f"🔗 <b>Ссылка:</b> {url}\n\n"
        f"➡️ <b>Ответь быстро — человек ещё горячий!</b>"
    )
    return msg

# ============================================================
# ОСНОВНОЙ ПОИСК
# ============================================================

def scan_query(query_id: int, query_text: str, token: str) -> int:
    """
    Сканирует VK по одному поисковому запросу.
    Возвращает количество найденных новых лидов.
    """
    found = 0
    extra_kw = query_text.lower().split()

    db_log("INFO", "comment_monitor", f"Сканирую: «{query_text}»")

    # === ПОИСК 1: newsfeed.search — посты и комментарии из всего VK ===
    result = search_comments(token, query_text, count=100)

    if "error" in result:
        db_log("ERROR", "comment_monitor",
               f"Ошибка поиска «{query_text}»: {result['error']}")
        return 0

    items   = result.get("response", {}).get("items", [])
    profiles = {str(p["id"]): p
                for p in result.get("response", {}).get("profiles", [])}
    groups   = {str(g["id"]): g
                for g in result.get("response", {}).get("groups", [])}

    for item in items:
        owner_id = item.get("owner_id", item.get("from_id", 0))
        post_id  = item.get("id", 0)
        text     = item.get("text", "").strip()
        date_ts  = item.get("date", 0)

        if not text or len(text) < 20:
            continue
        if _is_too_old(date_ts):
            continue
        if _is_spam(text):
            continue

        # Ищем комментарии к этому посту — там реальные люди
        comments_result = get_post_comments(token, owner_id, post_id, count=50)
        time.sleep(random.uniform(0.5, 1.5))  # пауза между запросами

        comments = []
        if "response" in comments_result:
            comments = comments_result["response"].get("items", [])
            # Профили из комментариев
            for p in comments_result["response"].get("profiles", []):
                profiles[str(p["id"])] = p

        # Обрабатываем сам пост
        post_author_id = item.get("from_id", owner_id)
        post_url = _build_post_url(owner_id, post_id)
        group_name = ""
        if owner_id < 0:
            g = groups.get(str(abs(owner_id)), {})
            group_name = g.get("name", "")

        # Если сам пост содержит запрос с интентом
        if _has_intent(text, extra_kw) and not _already_saved(post_url, post_author_id):
            profile = profiles.get(str(post_author_id), {})
            author_name = _get_name(profile, post_author_id)
            author_url  = f"https://vk.com/id{post_author_id}" if post_author_id > 0 else ""

            lead_id = _save_lead(
                query_id, query_text, "vk",
                post_author_id, author_name, author_url,
                text, post_url, group_name
            )
            _notify_manager(lead_id, query_text)
            found += 1

        # Обрабатываем комментарии под постом
        for comment in comments:
            c_author_id = comment.get("from_id", 0)
            c_text      = comment.get("text", "").strip()
            c_date      = comment.get("date", 0)
            c_id        = comment.get("id", 0)

            if not c_text or len(c_text) < 15:
                continue
            if _is_too_old(c_date):
                continue
            if _is_spam(c_text):
                continue
            if not _has_intent(c_text, extra_kw):
                continue

            comment_url = f"{post_url}?reply={c_id}"
            if _already_saved(comment_url, c_author_id):
                continue

            profile     = profiles.get(str(c_author_id), {})
            author_name = _get_name(profile, c_author_id)
            author_url  = f"https://vk.com/id{c_author_id}" if c_author_id > 0 else ""

            lead_id = _save_lead(
                query_id, query_text, "vk",
                c_author_id, author_name, author_url,
                c_text, comment_url, group_name
            )
            _notify_manager(lead_id, query_text)
            found += 1

    db_log("INFO" if found == 0 else "SUCCESS", "comment_monitor",
           f"Запрос «{query_text}»: найдено {found} новых лидов")
    return found


def _build_post_url(owner_id, post_id):
    if owner_id < 0:
        return f"https://vk.com/wall{owner_id}_{post_id}"
    return f"https://vk.com/wall{owner_id}_{post_id}"


def _get_name(profile, uid):
    if profile:
        return f"{profile.get('first_name','')} {profile.get('last_name','')}".strip()
    return f"ID{uid}"


def _notify_manager(lead_id, query_text):
    """Отправляет уведомление в Telegram и помечает лид как отправленный"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM monitor_leads WHERE id=?", (lead_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return

    lead = dict(row)
    msg  = _format_lead_message(lead, query_text)
    ok   = send_telegram(msg)

    conn = get_conn()
    conn.execute(
        "UPDATE monitor_leads SET sent_to_telegram=? WHERE id=?",
        (1 if ok else 0, lead_id)
    )
    conn.commit()
    conn.close()

    if ok:
        db_log("SUCCESS", "comment_monitor",
               f"Лид #{lead_id} отправлен в Telegram: {lead.get('author_name')}")


# ============================================================
# ЗАПУСК ПОЛНОГО СКАНИРОВАНИЯ
# ============================================================

def run_full_scan() -> dict:
    """
    Сканирует все активные поисковые запросы.
    Вызывается планировщиком или вручную из панели.
    """
    tokens = get_active_tokens()
    if not tokens:
        db_log("WARNING", "comment_monitor", "Нет активных аккаунтов для сканирования")
        return {"error": "Нет аккаунтов", "leads": 0}

    # Берём случайный токен
    account_id, token = random.choice(tokens)

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM monitor_queries WHERE status='active' ORDER BY id")
    queries = [dict(r) for r in c.fetchall()]
    conn.close()

    if not queries:
        db_log("INFO", "comment_monitor", "Нет активных поисковых запросов")
        return {"leads": 0, "queries": 0}

    total_leads = 0
    for q in queries:
        leads = scan_query(q["id"], q["query"], token)
        total_leads += leads

        # Обновляем время последнего запуска
        conn = get_conn()
        conn.execute(
            "UPDATE monitor_queries SET last_run=datetime('now') WHERE id=?",
            (q["id"],)
        )
        conn.commit()
        conn.close()

        # Пауза между запросами — не спамим VK
        delay = random.randint(15, 40)
        db_log("INFO", "comment_monitor", f"Пауза {delay}s...")
        time.sleep(delay)

    db_log("SUCCESS", "comment_monitor",
           f"Полное сканирование завершено: {total_leads} лидов по {len(queries)} запросам")
    return {"leads": total_leads, "queries": len(queries)}
