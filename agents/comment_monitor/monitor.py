"""
agents/comment_monitor/monitor.py — Агент 2: Мониторинг комментариев VK
Ищет людей которые задают вопросы по нашей теме → лид в базу → Telegram менеджеру.
Исправлено: новый db API, retry, надёжная отправка Telegram.
"""
import os, sys, time, random, re, json, logging
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.db import fetchall, fetchone, execute
from core.database import db_log, get_setting
from core.vk_api import api_call, search_comments, get_post_comments
from core.token_manager import get_active_tokens
from core.config import MONITOR_COMMENT_AGE_HOURS

logger = logging.getLogger("comment_monitor")

# Стоп-слова: реклама и спам — пропускаем
SPAM_PATTERNS = [
    r"подпишись", r"переходи по ссылке", r"заработок", r"млм",
    r"https?://", r"t\.me/", r"@[a-zA-Z0-9_]{5,}",
    r"скидка \d+%", r"промокод", r"партнёр",
]

# Слова намерения: человек что-то ИЩЕТ — наш потенциальный клиент
INTENT_KEYWORDS = [
    "ищу", "ищем", "посоветуйте", "посоветуй", "порекомендуйте",
    "подскажите", "подскажи", "помогите", "кто знает", "где найти",
    "где можно", "кто сталкивался", "кто пользовался", "есть ли",
    "какие варианты", "стоит ли", "как выбрать", "что выбрать",
    "хочу найти", "нужна помощь", "нужен совет", "нужно найти",
    "интересует", "рассматриваю", "думаем о", "планируем",
    "отзывы", "реальные отзывы", "кто ходил", "кто учился",
    "сравните", "хороший ли", "стоит идти", "рекомендуете",
]


def _is_spam(text: str) -> bool:
    tl = text.lower()
    return any(re.search(p, tl) for p in SPAM_PATTERNS)


def _has_intent(text: str, extra_kw=None) -> bool:
    tl = text.lower()
    if any(kw in tl for kw in INTENT_KEYWORDS):
        return True
    if extra_kw and any(k.lower() in tl for k in extra_kw):
        return True
    if "?" in text and len(text) > 25:
        return True
    return False


def _is_fresh(timestamp_unix) -> bool:
    if not timestamp_unix:
        return True
    age = datetime.now() - datetime.fromtimestamp(int(timestamp_unix))
    return age.total_seconds() < MONITOR_COMMENT_AGE_HOURS * 3600


def _already_saved(post_url: str, author_id) -> bool:
    row = fetchone(
        "SELECT id FROM monitor_leads WHERE post_url=? AND author_id=?",
        (post_url, str(author_id))
    )
    return row is not None


def _save_lead(query_id, query_text, author_id, author_name,
               author_url, text, post_url, group_name="") -> int:
    lead_id = execute(
        """INSERT INTO monitor_leads
           (query_id, query_text, source, author_id, author_name,
            author_url, text, post_url, group_name, status, sent_to_telegram)
           VALUES (?,?,'vk',?,?,?,?,?,?,'new',0)""",
        (query_id, query_text, str(author_id), author_name,
         author_url, text[:2000], post_url, group_name)
    )
    execute("UPDATE monitor_queries SET found_total=found_total+1 WHERE id=?", (query_id,))
    return lead_id


# ── TELEGRAM ─────────────────────────────────────────────────

def send_telegram(text: str) -> bool:
    bot_token  = get_setting("telegram_bot_token", "")
    chat_ids_r = get_setting("telegram_chat_ids", "")
    if not bot_token or not chat_ids_r:
        return False

    import requests as req
    chat_ids = [x.strip() for x in chat_ids_r.split(",") if x.strip()]
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    ok = False

    for cid in chat_ids:
        for attempt in range(3):
            try:
                r = req.post(url, json={
                    "chat_id": cid, "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }, timeout=10)
                data = r.json()
                if data.get("ok"):
                    ok = True
                    break
                elif data.get("error_code") == 429:
                    time.sleep(data.get("parameters", {}).get("retry_after", 5))
                else:
                    logger.warning(f"[TG] {cid}: {data.get('description')}")
                    break
            except Exception as e:
                logger.error(f"[TG] {cid} attempt {attempt}: {e}")
                time.sleep(2)
    return ok


def _format_lead(lead: dict, query_text: str) -> str:
    text = (lead.get("text") or "")[:400]
    return (
        f"🎯 <b>НОВЫЙ ЛИД</b>\n\n"
        f"🔍 <b>Запрос:</b> {query_text}\n"
        f"👤 <b>Автор:</b> {lead.get('author_name','?')}\n"
        f"📍 <b>Группа:</b> {lead.get('group_name','?')}\n\n"
        f"💬 <b>Написал:</b>\n<i>{text}</i>\n\n"
        f"🔗 {lead.get('post_url','')}\n\n"
        f"⚡️ Ответь быстро — человек горячий!"
    )


def _notify(lead_id: int, query_text: str):
    lead = fetchone("SELECT * FROM monitor_leads WHERE id=?", (lead_id,))
    if not lead:
        return
    msg = _format_lead(dict(lead), query_text)
    ok  = send_telegram(msg)
    execute("UPDATE monitor_leads SET sent_to_telegram=? WHERE id=?", (1 if ok else 0, lead_id))
    if ok:
        db_log("SUCCESS", "comment_monitor", f"Лид #{lead_id} → Telegram")


# ── СКАНИРОВАНИЕ ─────────────────────────────────────────────

def scan_query(query_id: int, query_text: str, token: str) -> int:
    found    = 0
    extra_kw = query_text.lower().split()
    db_log("INFO", "comment_monitor", f"Сканирую: «{query_text}»")

    result = search_comments(token, query_text, count=100)
    if "error" in result:
        db_log("ERROR", "comment_monitor", f"Ошибка поиска «{query_text}»: {result['error']}")
        return 0

    resp     = result.get("response", {})
    items    = resp.get("items", [])
    profiles = {str(p["id"]): p for p in resp.get("profiles", [])}
    groups   = {str(g["id"]): g for g in resp.get("groups", [])}

    for item in items:
        owner_id = item.get("owner_id", item.get("from_id", 0))
        post_id  = item.get("id", 0)
        text     = (item.get("text") or "").strip()
        date_ts  = item.get("date", 0)

        if len(text) < 20 or not _is_fresh(date_ts) or _is_spam(text):
            continue

        post_url   = f"https://vk.com/wall{owner_id}_{post_id}"
        group_name = ""
        if owner_id < 0:
            g = groups.get(str(abs(owner_id)), {})
            group_name = g.get("name", "")

        # Сам пост — если содержит интент
        from_id = item.get("from_id", owner_id)
        if _has_intent(text, extra_kw) and not _already_saved(post_url, from_id):
            prof = profiles.get(str(from_id), {})
            name = f"{prof.get('first_name','')} {prof.get('last_name','')}".strip() or f"ID{from_id}"
            url  = f"https://vk.com/id{from_id}" if from_id > 0 else ""
            lid  = _save_lead(query_id, query_text, from_id, name, url, text, post_url, group_name)
            _notify(lid, query_text)
            found += 1

        # Комментарии к посту
        time.sleep(random.uniform(0.8, 2.0))
        c_result = get_post_comments(token, owner_id, post_id, count=50)
        if "response" in c_result:
            for cp in c_result["response"].get("profiles", []):
                profiles[str(cp["id"])] = cp
            for comment in c_result["response"].get("items", []):
                c_id   = comment.get("id", 0)
                c_from = comment.get("from_id", 0)
                c_text = (comment.get("text") or "").strip()
                c_date = comment.get("date", 0)
                c_url  = f"{post_url}?reply={c_id}"

                if (len(c_text) < 15 or not _is_fresh(c_date)
                        or _is_spam(c_text) or not _has_intent(c_text, extra_kw)
                        or _already_saved(c_url, c_from)):
                    continue

                prof = profiles.get(str(c_from), {})
                name = f"{prof.get('first_name','')} {prof.get('last_name','')}".strip() or f"ID{c_from}"
                url  = f"https://vk.com/id{c_from}" if c_from > 0 else ""
                lid  = _save_lead(query_id, query_text, c_from, name, url, c_text, c_url, group_name)
                _notify(lid, query_text)
                found += 1

    db_log("INFO" if found == 0 else "SUCCESS", "comment_monitor",
           f"«{query_text}»: {found} новых лидов")
    return found


def run_full_scan() -> dict:
    tokens = get_active_tokens()
    if not tokens:
        db_log("WARNING", "comment_monitor", "Нет аккаунтов")
        return {"error": "Нет аккаунтов", "leads": 0}

    account_id, token = random.choice(tokens)
    queries = fetchall("SELECT * FROM monitor_queries WHERE status='active' ORDER BY id")

    if not queries:
        db_log("INFO", "comment_monitor", "Нет активных поисковых запросов")
        return {"leads": 0, "queries": 0}

    total = 0
    for q in queries:
        leads = scan_query(q["id"], q["query"], token)
        total += leads
        execute("UPDATE monitor_queries SET last_run=datetime('now') WHERE id=?", (q["id"],))
        delay = random.randint(20, 45)
        db_log("INFO", "comment_monitor", f"Пауза {delay}с...")
        time.sleep(delay)

    db_log("SUCCESS", "comment_monitor",
           f"Сканирование завершено: {total} лидов по {len(queries)} запросам")
    return {"leads": total, "queries": len(queries)}
