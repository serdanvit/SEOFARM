# Что именно менять (коротко и по делу)

Если вы не разработчик, **в коде `app.py` вручную менять ничего не нужно**.

## 1) Что менять обязательно

Меняйте через интерфейс **Настройки** (`/api/settings`) только эти ключи:

- `site_url` — ваш сайт.
- `brand_name` — название бренда.
- `region` — регион/город.
- `public_base_url` — адрес, по которому реально открывается система
  (пример: `http://127.0.0.1:5000` или `https://my-domain.ru`).

## 2) Что менять при необходимости

- `vk_client_id` — только если используете **своё** VK-приложение.
  Если не знаете — оставьте по умолчанию.
- `use_wordstat` — `true` или `false`.
  - `false` (по умолчанию): работает без Wordstat.
  - `true`: включит уточнение ключей через Wordstat.
- `yandex_wordstat_token` и `yandex_wordstat_username` — нужны только если включили `use_wordstat=true`.

## 3) Что обычно НЕ менять

- `app.py`
- `core/db.py`
- SQL-запросы

Эти файлы уже содержат нужные фиксы (миграции, OAuth-redirect, проверки).

## 4) Как понять, что всё применилось

Откройте:

- `/api/system/checks` — покажет, что ключевые фиксы активны;
- `/api/meta/routes` — покажет реальные маршруты сервера.

Если в `/api/system/checks` видите:
- `vk_groups_has_posts_count: true`
- `vk_groups_has_discussions_count: true`

значит миграции на месте.

## 5) Быстрый сценарий (5 шагов)

1. Запустить сервер: `python app.py`
2. В Настройках заполнить: `site_url`, `brand_name`, `region`, `public_base_url`
3. Нажать «Войти через VK»
4. Проверить `/api/system/checks`
5. Запустить кампанию
app.py
app.py
+87
-6

"""
app.py — SEO FARM Flask сервер
Все эндпоинты которые вызывает фронтенд.
"""
import os, sys, json, logging, threading, webbrowser
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.config import FLASK_HOST, FLASK_PORT, LOG_FILE, LOGS_DIR, DATA_DIR, UPLOADS_DIR, DB_URL
from core.db import init_schema, fetchone, fetchall, execute, get_conn
from core.database import db_log, get_setting, set_setting, get_all_settings, get_platform_stats, get_logs

# ── Логи ──────────────────────────────────────────────────────
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
for sub in ("avatars", "covers", "media"):
    os.makedirs(os.path.join(UPLOADS_DIR, sub), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("app")

# ── Flask ──────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# ── Старт ─────────────────────────────────────────────────────
init_schema()

if DB_URL.startswith("postgres"):
    try:
        import psycopg2  # noqa: F401
    except Exception:
        logger.error("Выбран PostgreSQL, но psycopg2 не установлен. Установи requirements-postgres.txt")

from core import scheduler
scheduler.start()
logger.info("SEO FARM запущен")


# ─────────────────────────────────────────────────────────────
# FRONTEND
# ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ─────────────────────────────────────────────────────────────
# СТАТИСТИКА
# ─────────────────────────────────────────────────────────────
@app.route("/api/stats")
def api_stats():
    return jsonify(get_platform_stats())


# ─────────────────────────────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────────────────────────────
@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    return jsonify(get_all_settings())

@app.route("/api/settings", methods=["POST"])
def api_settings_save():
    data = request.json or {}
    for k, v in data.items():
        set_setting(str(k), str(v))
    db_log("INFO", "app", "Настройки сохранены")
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────
# АККАУНТЫ VK
# ─────────────────────────────────────────────────────────────
@app.route("/api/accounts")
def api_accounts():
    from core.token_manager import get_all_accounts
    return jsonify(get_all_accounts())

@app.route("/api/accounts/add", methods=["POST"])
def api_accounts_add():
    data  = request.json or {}
    token = data.get("token", "").strip()
    if not token:
        return jsonify({"success": False, "error": "Токен пустой"})
    from core.token_manager import add_vk_account
    return jsonify(add_vk_account(token, notes=data.get("notes", "")))

@app.route("/api/accounts/<int:aid>", methods=["DELETE"])
def api_accounts_delete(aid):
    execute("DELETE FROM vk_accounts WHERE id=?", (aid,))
    return jsonify({"success": True})

@app.route("/api/accounts/<int:aid>/toggle", methods=["POST"])
def api_accounts_toggle(aid):
    row = fetchone("SELECT status FROM vk_accounts WHERE id=?", (aid,))
    if not row:
        return jsonify({"success": False, "error": "Не найден"})
    new = "inactive" if row["status"] == "active" else "active"
    execute("UPDATE vk_accounts SET status=? WHERE id=?", (new, aid))
    return jsonify({"success": True, "status": new})

@app.route("/api/accounts/check", methods=["POST"])
def api_accounts_check():
    from core.vk_api import check_token
    from core.token_manager import decrypt_token
    accounts = fetchall("SELECT id, token_encrypted FROM vk_accounts WHERE status='active'")
    results  = []
    for acc in accounts:
        tok   = decrypt_token(acc["token_encrypted"])
        valid, info = check_token(tok)
        execute("UPDATE vk_accounts SET status=? WHERE id=?",
                ("active" if valid else "error", acc["id"]))
        results.append({"id": acc["id"], "valid": valid, "info": info})
    return jsonify({"results": results})


# ─────────────────────────────────────────────────────────────
# VK КЛЮЧЕВЫЕ СЛОВА
# ─────────────────────────────────────────────────────────────
@app.route("/api/vk/keywords")
def api_vk_keywords():
    rows = fetchall("SELECT * FROM vk_keywords ORDER BY id DESC")
    return jsonify([dict(r) for r in rows])

@app.route("/api/vk/keywords/add", methods=["POST"])
def api_vk_keywords_add():
    data = request.json or {}
    text = data.get("keywords", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Пустой список"})
    keywords = [k.strip() for k in text.replace("\n", ",").split(",") if k.strip()]
    region   = data.get("region", "")
    added = 0
    for kw in keywords:
        try:
            execute("INSERT INTO vk_keywords(keyword,region) VALUES(?,?)", (kw, region))
            added += 1
        except Exception:
            pass
    return jsonify({"success": True, "added": added})

@app.route("/api/vk/keywords/import", methods=["POST"])
def api_vk_keywords_import():
    """Импорт ключей из загруженного текстового файла или CSV"""
    if "file" in request.files:
        f    = request.files["file"]
        text = f.read().decode("utf-8", errors="ignore")
    else:
        text = (request.json or {}).get("text", "")

    region   = (request.json or request.form or {}).get("region", "")
    keywords = [k.strip() for k in text.replace("\n", ",").replace(";", ",").split(",")
                if k.strip() and len(k.strip()) > 2]
    added = 0
    for kw in keywords:
        try:
            execute("INSERT INTO vk_keywords(keyword,region) VALUES(?,?)", (kw, region))
            added += 1
        except Exception:
            pass
    return jsonify({"success": True, "added": added, "total": len(keywords)})

@app.route("/api/vk/keywords/<int:kid>", methods=["DELETE"])
def api_vk_keywords_delete(kid):
    execute("DELETE FROM vk_keywords WHERE id=?", (kid,))
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────
# VK ГРУППЫ — создание
# ─────────────────────────────────────────────────────────────
@app.route("/api/vk/groups")
def api_vk_groups():
    rows = fetchall("SELECT * FROM vk_groups ORDER BY created_at DESC LIMIT 200")
    return jsonify([dict(r) for r in rows])

@app.route("/api/vk/groups/start", methods=["POST"])
@app.route("/api/vk/create-now",   methods=["POST"])
def api_vk_create_now():
    """Запуск пакетного создания групп по свободным ключам"""
    data     = request.json or {}
    count    = int(data.get("count", 1))
    kw_ids   = data.get("keyword_ids", [])

    if kw_ids:
        keywords = []
        for kid in kw_ids[:count]:
            row = fetchone("SELECT id,keyword FROM vk_keywords WHERE id=? AND used=0", (kid,))
            if row:
                keywords.append(row)
    else:
        keywords = fetchall(
            "SELECT id,keyword FROM vk_keywords WHERE used=0 LIMIT ?", (count,)
        )

    if not keywords:
        return jsonify({"success": False, "error": "Нет свободных ключевых слов"})

    def run():
        from agents.vk_groups.creator import create_group_pipeline
        for kw in keywords:
            create_group_pipeline(kw["id"], kw["keyword"])

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "started": len(keywords),
                    "keywords": [k["keyword"] for k in keywords]})

@app.route("/api/vk/groups/create-one", methods=["POST"])
def api_vk_create_one():
    """Создать одну группу по конкретному ключу"""
    data = request.json or {}
    keyword    = data.get("keyword", "").strip()
    keyword_id = data.get("keyword_id")

    if not keyword:
        return jsonify({"success": False, "error": "Ключевое слово пустое"})

    def run():
        from agents.vk_groups.creator import create_group_pipeline
        create_group_pipeline(keyword_id, keyword)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "keyword": keyword})


# ─────────────────────────────────────────────────────────────
# VK ГРУППЫ — репосты и активность
# ─────────────────────────────────────────────────────────────
@app.route("/api/vk/reposts-now", methods=["POST"])
def api_vk_reposts_now():
    def run():
        from agents.vk_groups.repost import repost_to_all_groups
        repost_to_all_groups()
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True})

@app.route("/api/vk/activity-now", methods=["POST"])
def api_vk_activity_now():
    def run():
        from agents.vk_groups.activity import run_activity_all
        run_activity_all()
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────
# VK МЕДИА — загрузка файлов (аватары, обложки, медиа)
# ─────────────────────────────────────────────────────────────
ALLOWED_EXTS = {
    "avatars": {".jpg", ".jpeg", ".png"},
    "covers":  {".jpg", ".jpeg", ".png"},
    "media":   {".jpg", ".jpeg", ".png", ".mp4", ".mov"},
}

@app.route("/api/vk/upload/<sub>", methods=["POST"])
def api_vk_upload(sub):
    if sub not in ALLOWED_EXTS:
        return jsonify({"success": False, "error": "Неверная категория"})

    files   = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return jsonify({"success": False, "error": "Файлы не выбраны"})

    folder  = os.path.join(UPLOADS_DIR, sub)
    os.makedirs(folder, exist_ok=True)
    saved   = []
    errors  = []

    for f in files:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTS[sub]:
            errors.append(f"{f.filename}: неверный формат")
            continue
        # Безопасное имя файла
        safe = f"{int(datetime.now().timestamp())}_{os.path.basename(f.filename)}"
        safe = "".join(c for c in safe if c.isalnum() or c in "._-")
        path = os.path.join(folder, safe)
        f.save(path)
        saved.append(safe)

    return jsonify({
        "success": len(saved) > 0,
        "saved": saved,
        "errors": errors,
        "count": len(saved),
    })

@app.route("/api/vk/upload/list/<sub>")
def api_vk_upload_list(sub):
    if sub not in ALLOWED_EXTS:
        return jsonify({"files": []})
    folder = os.path.join(UPLOADS_DIR, sub)
    os.makedirs(folder, exist_ok=True)
    files  = []
    for fname in sorted(os.listdir(folder)):
        ext = os.path.splitext(fname)[1].lower()
        if ext in ALLOWED_EXTS.get(sub, set()):
            files.append(fname)
    return jsonify({"files": files, "count": len(files)})

@app.route("/api/vk/upload/delete/<sub>/<filename>", methods=["DELETE"])
def api_vk_upload_delete(sub, filename):
    if sub not in ALLOWED_EXTS:
        return jsonify({"success": False})
    # Защита от path traversal
    safe = os.path.basename(filename)
    path = os.path.join(UPLOADS_DIR, sub, safe)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────
# МОНИТОРИНГ (Агент 2)
# ─────────────────────────────────────────────────────────────
@app.route("/api/monitor/queries")
def api_monitor_queries():
    rows = fetchall("SELECT * FROM monitor_queries ORDER BY id DESC")
    return jsonify([dict(r) for r in rows])

@app.route("/api/monitor/queries/add", methods=["POST"])
def api_monitor_queries_add():
    data  = request.json or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"success": False, "error": "Запрос пустой"})
    qid = execute("INSERT INTO monitor_queries(query,source,region) VALUES(?,?,?)",
                  (query, data.get("source", "vk"), data.get("region", "")))
    return jsonify({"success": True, "id": qid})

@app.route("/api/monitor/queries/import", methods=["POST"])
def api_monitor_queries_import():
    if "file" in request.files:
        text = request.files["file"].read().decode("utf-8", errors="ignore")
    else:
        text = (request.json or {}).get("text", "")

    queries = [q.strip() for q in text.replace("\n", ",").split(",")
               if q.strip() and len(q.strip()) > 2]
    added = 0
    for q in queries:
        try:
            execute("INSERT INTO monitor_queries(query,source) VALUES(?,'vk')", (q,))
            added += 1
        except Exception:
            pass
    return jsonify({"success": True, "added": added})

@app.route("/api/monitor/queries/<int:qid>", methods=["DELETE"])
def api_monitor_queries_delete(qid):
    execute("DELETE FROM monitor_queries WHERE id=?", (qid,))
    return jsonify({"success": True})

@app.route("/api/monitor/leads")
def api_monitor_leads():
    status = request.args.get("status", "")
    limit  = int(request.args.get("limit", 100))
    if status:
        rows = fetchall(
            "SELECT * FROM monitor_leads WHERE status=? ORDER BY found_at DESC LIMIT ?",
            (status, limit)
        )
    else:
        rows = fetchall("SELECT * FROM monitor_leads ORDER BY found_at DESC LIMIT ?", (limit,))
    return jsonify([dict(r) for r in rows])

@app.route("/api/monitor/leads/<int:lid>/status", methods=["POST"])
def api_monitor_lead_status(lid):
    new_status = (request.json or {}).get("status", "")
    if new_status:
        execute("UPDATE monitor_leads SET status=? WHERE id=?", (new_status, lid))
    return jsonify({"success": True})

@app.route("/api/monitor/leads/<int:lid>", methods=["DELETE"])
def api_monitor_lead_delete(lid):
    execute("DELETE FROM monitor_leads WHERE id=?", (lid,))
    return jsonify({"success": True})

@app.route("/api/monitor/scan-now", methods=["POST"])
def api_monitor_scan_now():
    def run():
        from agents.comment_monitor.monitor import run_full_scan
        run_full_scan()
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────
# СТАТЬИ (Агент 3)
# ─────────────────────────────────────────────────────────────
@app.route("/api/articles")
def api_articles():
    from agents.article_publisher.publisher import get_articles
    rows = get_articles()
    return jsonify({"articles": [dict(r) for r in rows]})

@app.route("/api/articles/add", methods=["POST"])
def api_articles_add():
    data  = request.json or {}
    title = data.get("title", "").strip()
    body  = data.get("content", data.get("body", "")).strip()
    if not title or not body:
        return jsonify({"success": False, "error": "Заголовок и текст обязательны"})
    from agents.article_publisher.publisher import create_article
    aid = create_article(title, body, data.get("tags", ""))
    return jsonify({"success": True, "id": aid})

@app.route("/api/articles/<int:aid>")
def api_articles_get(aid):
    row = fetchone("SELECT * FROM articles WHERE id=?", (aid,))
    if not row:
        return jsonify({"success": False, "error": "Не найдена"})
    pubs = fetchall("SELECT * FROM article_publications WHERE article_id=?", (aid,))
    return jsonify({"article": dict(row), "publications": [dict(p) for p in pubs]})

@app.route("/api/articles/<int:aid>", methods=["DELETE"])
def api_articles_delete(aid):
    from agents.article_publisher.publisher import delete_article
    delete_article(aid)
    return jsonify({"success": True})

@app.route("/api/articles/<int:aid>/publish", methods=["POST"])
def api_articles_publish(aid):
    data      = request.json or {}
    platforms = data.get("platforms", ["telegra_ph"])
    if not platforms:
        return jsonify({"success": False, "error": "Не выбрана ни одна платформа"})

    def run():
        from agents.article_publisher.publisher import publish_to_platforms
        publish_to_platforms(aid, platforms)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "platforms": platforms})
# ─────────────────────────────────────────────────────────────
# ЗАДАЧИ
# ─────────────────────────────────────────────────────────────
@app.route("/api/tasks")
def api_tasks():
    status = request.args.get("status", "")
    limit  = int(request.args.get("limit", 50))
    if status:
        rows = fetchall(
            "SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?",
            (status, limit)
        )
    else:
        rows = fetchall("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))
    return jsonify([dict(r) for r in rows])

@app.route("/api/tasks/<int:tid>/retry", methods=["POST"])
def api_tasks_retry(tid):
    execute("UPDATE tasks SET status='pending', attempts=0, error_message='' WHERE id=?", (tid,))
    return jsonify({"success": True})

@app.route("/api/tasks/<int:tid>", methods=["DELETE"])
def api_tasks_delete(tid):
    execute("DELETE FROM tasks WHERE id=?", (tid,))
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────
# ЛОГИ
# ─────────────────────────────────────────────────────────────
@app.route("/api/logs")
def api_logs():
    agent = request.args.get("agent", "")
    limit = int(request.args.get("limit", 200))
    rows  = get_logs(limit=limit, agent=agent or None)
    return jsonify([dict(r) for r in rows])

@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    execute("DELETE FROM logs WHERE created_at < datetime('now', '-7 days')")
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────
# ПЛАНИРОВЩИК
# ─────────────────────────────────────────────────────────────
@app.route("/api/scheduler/status")
def api_scheduler_status():
    return jsonify({"running": scheduler.is_running()})

# Поддерживаем оба варианта: toggle и отдельные start/stop/pause/resume
@app.route("/api/scheduler/stop",    methods=["POST"])
@app.route("/api/scheduler/pause",   methods=["POST"])
def api_scheduler_stop():
    scheduler.stop()
    return jsonify({"running": False})


# ─────────────────────────────────────────────────────────────
# СТАРТ
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    url = f"http://localhost:{FLASK_PORT}"
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"\n  SEO FARM: {url}\n")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, threaded=True)

# ─────────────────────────────────────────────────────────────
# OAUTH VK — встроенная авторизация прямо в браузере
# ─────────────────────────────────────────────────────────────
VK_CLIENT_ID = "2685278"
VK_SCOPE     = "groups,wall,photos,video,offline"

def _public_base_url() -> str:
    """Пытаемся корректно определить внешний URL приложения."""
    configured = get_setting("public_base_url", "").strip()
    if configured:
        return configured.rstrip("/")
    return request.host_url.rstrip("/")

@app.route("/vk/auth")
def vk_auth():
    redirect_uri = f"{_public_base_url()}/vk/callback"
    client_id = get_setting("vk_client_id", VK_CLIENT_ID).strip() or VK_CLIENT_ID
    url = (f"https://oauth.vk.com/authorize?client_id={client_id}"
           f"&display=page&redirect_uri={redirect_uri}"
           f"&scope={VK_SCOPE}&response_type=token&v=5.131")
    from flask import redirect as _redirect
    return _redirect(url)

@app.route("/vk/callback")
def vk_callback():
    return """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>VK Авторизация</title>
<style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;
height:100vh;margin:0;background:#f0f2f5}.box{background:#fff;padding:40px;border-radius:16px;
text-align:center;box-shadow:0 4px 24px rgba(0,0,0,.1);max-width:380px}
button{padding:12px 28px;background:#2196F3;color:#fff;border:none;border-radius:8px;
cursor:pointer;font-size:1rem;margin-top:12px}</style></head>
<body><div class="box" id="box"><div style="font-size:2rem">⏳</div>
<h2>Получаем токен...</h2></div>
<script>
const p=new URLSearchParams(window.location.hash.substring(1));
const token=p.get('access_token');
const err=p.get('error')||p.get('error_description');
const box=document.getElementById('box');
if(err){
  box.innerHTML='<div style="font-size:2rem">❌</div><h2>VK не выдал токен</h2>'+
    '<p style="color:#666">'+err+'</p>'+
    '<p style="font-size:.9rem;color:#666">Проверь public_base_url и vk_client_id в настройках.</p>'+
    '<button onclick="window.close()">Закрыть</button>';
} else if(token){
  fetch('/api/accounts/add',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token,notes:'OAuth '+new Date().toLocaleDateString()})})
  .then(r=>r.json()).then(d=>{
    if(d.success){
      box.innerHTML='<div style="font-size:2rem">✅</div><h2>Аккаунт добавлен!</h2>'+
        '<p style="color:#666">'+(d.user_info&&d.user_info.name?d.user_info.name:'VK аккаунт')+'</p>'+
        '<button onclick="window.close()">Закрыть и вернуться</button>';
    } else {
      box.innerHTML='<div style="font-size:2rem">❌</div><h2>Ошибка</h2><p>'+(d.error||'?')+'</p>'+
        '<button onclick="window.close()">Закрыть</button>';
    }
  });
} else {
  box.innerHTML='<div style="font-size:2rem">❌</div><h2>Токен не получен</h2>'+
    '<p>Попробуй ещё раз</p><button onclick="window.close()">Закрыть</button>';
}
</script></body></html>"""

# ─────────────────────────────────────────────────────────────
# OAUTH ЯНДЕКС
# ─────────────────────────────────────────────────────────────
@app.route("/yandex/auth")
def yandex_auth():
    cid = get_setting("yandex_client_id", "")
    if not cid:
        return "<h2 style='font-family:sans-serif;padding:40px'>Укажи Yandex Client ID в Настройках → Интеграции</h2>", 400
    from flask import redirect as _r
    return _r(f"https://oauth.yandex.ru/authorize?response_type=token&client_id={cid}"
              f"&redirect_uri={_public_base_url()}/yandex/callback")

@app.route("/yandex/callback")
def yandex_callback():
    return """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Яндекс</title>
<style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;
height:100vh;margin:0;background:#f5f5f5}
.box{background:#fff;padding:40px;border-radius:16px;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,.1)}
button{padding:12px 28px;background:#fc0;border:none;border-radius:8px;cursor:pointer;font-size:1rem;margin-top:12px}
</style></head>
<body><div class="box" id="box"><div style="font-size:2rem">⏳</div><p>Сохраняем токен...</p></div>
<script>
const t=new URLSearchParams(window.location.hash.substring(1)).get('access_token');
const box=document.getElementById('box');
if(t){
  fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({yandex_wordstat_token:t})})
  .then(()=>{
    box.innerHTML='<div style="font-size:2rem">✅</div><h2>Яндекс подключён!</h2>'+
      '<button onclick="window.close()">Закрыть</button>';
  });
} else {
  box.innerHTML='<div style="font-size:2rem">❌</div><h2>Ошибка авторизации</h2>';
}
</script></body></html>"""

# ─────────────────────────────────────────────────────────────
# КАМПАНИЯ — запуск полного цикла
# ─────────────────────────────────────────────────────────────
_campaign_status = {"running": False, "stage": "", "progress": 0, "log": [], "result": None}

@app.route("/api/campaign/start", methods=["POST"])
def api_campaign_start():
    global _campaign_status
    data     = request.json or {}
    site_url = data.get("site_url", "").strip() or get_setting("site_url", "")
    count    = int(data.get("count", 30))
    use_wordstat = str(data.get("use_wordstat", get_setting("use_wordstat", "false"))).lower() in ("1", "true", "yes", "on")
    if not site_url:
        return jsonify({"success": False, "error": "Укажи сайт в настройках"})
    if _campaign_status.get("running"):
        return jsonify({"success": False, "error": "Кампания уже запущена"})

    _campaign_status = {"running": True, "stage": "parse", "progress": 5,
                        "site_url": site_url, "log": [], "result": None}

    def run():
        global _campaign_status
        try:
            import json as _j, random as _r
            from datetime import datetime as _dt, timedelta as _td

            def log(msg, stage="", pct=0):
                _campaign_status["log"].append(msg)
                if stage: _campaign_status["stage"] = stage
                if pct:   _campaign_status["progress"] = pct
                db_log("INFO", "campaign", msg)

            log(f"Парсинг сайта {site_url}...", "parse", 10)
            from core.site_parser import parse_site
            site = parse_site(site_url)
            log(f"Обработано {site.get('pages_visited',0)} страниц", "analyze", 25)

            from core.ai_content import analyze_niche, generate_keywords, check_ollama_status
            from core.keyword_base import detect_niche, expand_keywords
            from core.wordstat import get_keywords_with_frequency, get_region_id

            site_data = {}
            if site.get("text"):
                if check_ollama_status()["running"]:
                    log("AI определяет нишу...", "analyze", 35)
                    site_data = analyze_niche(site["text"])
                else:
                    site_data["niche"] = detect_niche(site["text"])

            niche    = site_data.get("niche","")
            brand    = site_data.get("brand","") or get_setting("brand_name","")
            region   = site_data.get("region","") or get_setting("region","")
            services = site_data.get("services",[])
            log(f"Ниша: {niche or '—'} | Бренд: {brand} | Регион: {region}", "keywords", 45)

            if check_ollama_status()["running"]:
                log(f"AI генерирует {count} ключей...", "keywords", 55)
                keywords = generate_keywords(niche or brand, region, services, brand, count)
            else:
                log(f"Генерация {count} ключей из базы...", "keywords", 55)
                keywords = expand_keywords(niche or brand, region, services, count)

            if use_wordstat:
                ws_token = get_setting("yandex_wordstat_token", "")
                ws_user = get_setting("yandex_wordstat_username", "")
                if ws_token and ws_user:
                    log("Уточняю ключи через Wordstat...", "keywords", 62)
                    ws_keywords = get_keywords_with_frequency(
                        phrases=keywords[:50],
                        token=ws_token,
                        username=ws_user,
                        region_id=get_region_id(region),
                        min_shows=50,
                        max_shows=500,
                    )
                    if ws_keywords:
                        seen = set()
                        keywords = [k for k in ws_keywords if not (k in seen or seen.add(k))][:count]
                        log(f"Wordstat подтвердил {len(keywords)} ключей", "keywords", 66)
                    else:
                        log("Wordstat не дал данных — оставляю AI/шаблонные ключи", "keywords", 66)
                else:
                    log("Wordstat включен, но нет токена/логина — шаг пропущен", "keywords", 66)

            log(f"Готово {len(keywords)} ключей", "schedule", 70)

            day = count_today = scheduled = 0
            MAX_PER_DAY = 2
            for kw in keywords:
                ex = fetchone("SELECT id FROM vk_keywords WHERE keyword=?", (kw,))
                kid = ex["id"] if ex else execute(
                    "INSERT INTO vk_keywords(keyword,region,used) VALUES(?,?,0)", (kw, region))
                if count_today >= MAX_PER_DAY:
                    day += 1; count_today = 0
                sched = (_dt.now() + _td(days=day)).replace(
                    hour=_r.randint(10,20), minute=_r.randint(0,59), second=0)
                execute(
                    "INSERT INTO tasks(agent,type,payload,scheduled_time,status)"
                    " VALUES('vk_groups','create',?,?,'pending')",
                    (_j.dumps({"keyword_id":kid,"keyword":kw,"site_data":site_data},ensure_ascii=False),
                     sched.strftime("%Y-%m-%d %H:%M:%S")))
                count_today += 1; scheduled += 1

            log(f"✅ {scheduled} групп запланировано на {day+1} дней", "done", 100)
            _campaign_status.update({
                "running": False, "stage": "done",
                "result": {"keywords": len(keywords), "scheduled": scheduled,
                           "days": day+1, "niche": niche, "brand": brand, "region": region}
            })
@@ -736,25 +782,60 @@ def api_site_analyze():
            site_data = analyze_niche(site["text"])
        else:
            site_data["niche"] = detect_niche(site["text"])
    site_data["pages_visited"] = site.get("pages_visited", 0)
    site_data["contacts"]      = site.get("contacts", {})
    return jsonify({"success": True, "data": site_data})

# ─────────────────────────────────────────────────────────────
# ПОЗИЦИИ
# ─────────────────────────────────────────────────────────────
@app.route("/api/positions")
def api_positions():
    groups = fetchall(
        "SELECT name,vk_group_url,status,posts_count,reposts_done "
        "FROM vk_groups ORDER BY created_at DESC LIMIT 50")
    done     = sum(1 for g in groups if g["status"]=="done")
    creating = sum(1 for g in groups if g["status"]=="creating")
    pending  = fetchall("SELECT COUNT(*) as n FROM tasks WHERE agent='vk_groups' AND status='pending'")
    return jsonify({
        "groups_total":    len(groups),
        "groups_done":     done,
        "groups_creating": creating,
        "groups_planned":  pending[0]["n"] if pending else 0,
        "groups":          [dict(g) for g in groups[:20]],
    })


@app.route("/api/meta/routes")
def api_meta_routes():
    routes = sorted({str(rule.rule) for rule in app.url_map.iter_rules()})
    return jsonify({"count": len(routes), "routes": routes})


@app.route("/api/system/checks")
def api_system_checks():
    """Быстрая самопроверка: показывает, применены ли ключевые изменения."""
    conn = get_conn()
    c = conn.cursor()

    if DB_URL.startswith("postgres"):
        c.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_name='vk_groups'"""
        )
        cols = {row[0] for row in c.fetchall()}
    else:
        c.execute("PRAGMA table_info(vk_groups)")
        cols = {row[1] for row in c.fetchall()}

    return jsonify({
        "success": True,
        "checks": {
            "vk_groups_has_posts_count": "posts_count" in cols,
            "vk_groups_has_discussions_count": "discussions_count" in cols,
            "meta_routes_endpoint": True,
            "oauth_public_base_url_set": bool(get_setting("public_base_url", "").strip()),
            "wordstat_opt_in_setting": get_setting("use_wordstat", "false"),
            "vk_client_id": get_setting("vk_client_id", VK_CLIENT_ID),
        },
    })
