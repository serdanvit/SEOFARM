"""
app.py — Главный сервер SEO FARM платформы
Запуск: python app.py
Панель: http://localhost:5000
"""
import os, sys, json, logging, threading, sqlite3
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.config import FLASK_HOST, FLASK_PORT, LOG_FILE, LOGS_DIR, DATA_DIR, UPLOADS_DIR
from core.database import (get_conn, db_log, init_all_tables, get_logs,
                            get_platform_stats, get_setting, set_setting, get_all_settings)
from core.token_manager import add_vk_account, get_all_accounts
import core.scheduler as scheduler

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("app")

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

# ── ГЛАВНАЯ ──────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

# ── ПЛАТФОРМА ────────────────────────────────────────────────
@app.route("/api/stats")
def api_stats():
    return jsonify({"success": True, "stats": get_platform_stats(),
                    "scheduler": scheduler.status()})

@app.route("/api/logs")
def api_logs():
    limit = request.args.get("limit", 150, type=int)
    agent = request.args.get("agent", None)
    return jsonify({"success": True, "logs": get_logs(limit, agent)})

@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify({"success": True, "settings": get_all_settings()})

@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    data = request.json or {}
    for k, v in data.items():
        set_setting(k, v)
    db_log("INFO", "app", "Настройки сохранены")
    return jsonify({"success": True})

# ── ПЛАНИРОВЩИК ──────────────────────────────────────────────
@app.route("/api/scheduler/start",  methods=["POST"])
def sched_start():  return jsonify(scheduler.start())

@app.route("/api/scheduler/stop",   methods=["POST"])
def sched_stop():   return jsonify(scheduler.stop())

@app.route("/api/scheduler/pause",  methods=["POST"])
def sched_pause():  return jsonify(scheduler.pause())

@app.route("/api/scheduler/resume", methods=["POST"])
def sched_resume(): return jsonify(scheduler.resume())

@app.route("/api/scheduler/status")
def sched_status(): return jsonify(scheduler.status())

# ── АККАУНТЫ VK (общие для всех агентов) ─────────────────────
@app.route("/api/accounts")
def api_accounts():
    return jsonify({"success": True, "accounts": get_all_accounts()})

@app.route("/api/accounts/add", methods=["POST"])
def api_add_account():
    data = request.json or {}
    token = (data.get("token") or "").strip()
    if not token:
        return jsonify({"success": False, "error": "Токен не указан"})
    result = add_vk_account(token, data.get("notes",""))
    return jsonify(result)

@app.route("/api/accounts/<int:aid>", methods=["DELETE"])
def api_del_account(aid):
    conn = get_conn()
    conn.execute("DELETE FROM vk_accounts WHERE id=?", (aid,))
    conn.commit(); conn.close()
    return jsonify({"success": True})

@app.route("/api/accounts/check", methods=["POST"])
def api_check_accounts():
    from core.vk_api import check_token
    from core.token_manager import decrypt_token
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM vk_accounts")
    accounts = [dict(r) for r in c.fetchall()]
    conn.close()
    results = []
    for acc in accounts:
        token = decrypt_token(acc["token_encrypted"])
        valid, info = check_token(token)
        status = "active" if valid else "invalid"
        conn = get_conn()
        conn.execute("UPDATE vk_accounts SET status=? WHERE id=?", (status, acc["id"]))
        conn.commit(); conn.close()
        results.append({"id": acc["id"], "hint": acc["token_hint"],
                        "valid": valid, "status": status, "info": info})
    return jsonify({"success": True, "results": results})

# ════════════════════════════════════════════════════════════
# АГЕНТ 1 — VK ГРУППЫ
# ════════════════════════════════════════════════════════════

@app.route("/api/vk/keywords")
def vk_keywords():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM vk_keywords ORDER BY id")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify({"success": True, "keywords": rows})

@app.route("/api/vk/keywords/add", methods=["POST"])
def vk_add_keyword():
    data = request.json or {}
    kw = (data.get("keyword") or "").strip()
    if not kw:
        return jsonify({"success": False, "error": "Пустой ключ"})
    conn = get_conn()
    try:
        conn.execute("INSERT INTO vk_keywords (keyword, region) VALUES (?,?)",
                     (kw, data.get("region","")))
        conn.commit(); conn.close()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "error": f"Ключ '{kw}' уже есть"})

@app.route("/api/vk/keywords/import", methods=["POST"])
def vk_import_keywords():
    data = request.json or {}
    text = data.get("text","")
    kws  = [l.strip() for l in text.split("\n") if l.strip()]
    conn = get_conn()
    added = skipped = 0
    for kw in kws:
        try:
            conn.execute("INSERT INTO vk_keywords (keyword) VALUES (?)", (kw,))
            added += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit(); conn.close()
    return jsonify({"success": True, "added": added, "skipped": skipped})

@app.route("/api/vk/keywords/<int:kid>", methods=["DELETE"])
def vk_del_keyword(kid):
    conn = get_conn()
    conn.execute("DELETE FROM vk_keywords WHERE id=?", (kid,))
    conn.commit(); conn.close()
    return jsonify({"success": True})

@app.route("/api/vk/groups")
def vk_groups():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM vk_groups ORDER BY created_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify({"success": True, "groups": rows})

@app.route("/api/vk/groups/start", methods=["POST"])
def vk_start_groups():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM vk_keywords WHERE used=0")
    unused = [dict(r) for r in c.fetchall()]
    conn.close()
    if not unused:
        return jsonify({"success": False, "error": "Нет неиспользованных ключей"})
    def run():
        import time
        from agents.vk_groups.creator import create_group_pipeline
        for kw in unused:
            create_group_pipeline(kw["id"], kw["keyword"])
            time.sleep(120 + (hash(kw["keyword"]) % 60))
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "queued": len(unused)})

@app.route("/api/vk/groups/create-one", methods=["POST"])
def vk_create_one():
    data = request.json or {}
    kid = data.get("keyword_id")
    kw  = data.get("keyword","").strip()
    if not kw:
        return jsonify({"success": False, "error": "Нет ключа"})
    def run():
        from agents.vk_groups.creator import create_group_pipeline
        create_group_pipeline(kid, kw)
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True})

@app.route("/api/vk/reposts-now", methods=["POST"])
def vk_reposts_now():
    return jsonify(scheduler.run_vk_reposts_now())

@app.route("/api/vk/activity-now", methods=["POST"])
def vk_activity_now():
    data = request.json or {}
    return jsonify(scheduler.run_vk_activity_now(
        data.get("likes", 3), data.get("comments", 1)
    ))

@app.route("/api/vk/preview-name", methods=["POST"])
def vk_preview_name():
    from agents.vk_groups.content_gen import generate_name
    data = request.json or {}
    return jsonify({"name": generate_name(
        data.get("keyword",""), data.get("brand",""), data.get("region","")
    )})

# Загрузка медиа
@app.route("/api/vk/upload/<subfolder>", methods=["POST"])
def vk_upload(subfolder):
    if subfolder not in ("avatars","covers","media"):
        return jsonify({"success": False, "error": "Неверная папка"})
    if "file" not in request.files:
        return jsonify({"success": False, "error": "Нет файла"})
    f = request.files["file"]
    from werkzeug.utils import secure_filename
    fname = secure_filename(f.filename)
    folder = os.path.join(UPLOADS_DIR, subfolder)
    os.makedirs(folder, exist_ok=True)
    f.save(os.path.join(folder, fname))
    return jsonify({"success": True, "filename": fname})

@app.route("/api/vk/upload/list/<subfolder>")
def vk_upload_list(subfolder):
    import glob
    folder = os.path.join(UPLOADS_DIR, subfolder)
    if not os.path.exists(folder):
        return jsonify({"files": []})
    files = []
    for ext in ["*.jpg","*.jpeg","*.png","*.mp4","*.mov"]:
        files += [os.path.basename(x) for x in glob.glob(os.path.join(folder, ext))]
    return jsonify({"files": files})

# ════════════════════════════════════════════════════════════
# АГЕНТ 2 — МОНИТОРИНГ КОММЕНТАРИЕВ
# ════════════════════════════════════════════════════════════

@app.route("/api/monitor/queries")
def monitor_queries():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM monitor_queries ORDER BY id")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify({"success": True, "queries": rows})

@app.route("/api/monitor/queries/add", methods=["POST"])
def monitor_add_query():
    data = request.json or {}
    q = (data.get("query") or "").strip()
    if not q:
        return jsonify({"success": False, "error": "Пустой запрос"})
    conn = get_conn()
    conn.execute("INSERT INTO monitor_queries (query, source, region) VALUES (?,?,?)",
                 (q, data.get("source","vk"), data.get("region","")))
    conn.commit(); conn.close()
    db_log("INFO", "monitor", f"Добавлен запрос мониторинга: «{q}»")
    return jsonify({"success": True})

@app.route("/api/monitor/queries/import", methods=["POST"])
def monitor_import_queries():
    data = request.json or {}
    text = data.get("text","")
    qs = [l.strip() for l in text.split("\n") if l.strip()]
    conn = get_conn()
    added = 0
    for q in qs:
        conn.execute("INSERT INTO monitor_queries (query) VALUES (?)", (q,))
        added += 1
    conn.commit(); conn.close()
    return jsonify({"success": True, "added": added})

@app.route("/api/monitor/queries/<int:qid>", methods=["DELETE"])
def monitor_del_query(qid):
    conn = get_conn()
    conn.execute("DELETE FROM monitor_queries WHERE id=?", (qid,))
    conn.commit(); conn.close()
    return jsonify({"success": True})

@app.route("/api/monitor/queries/<int:qid>/toggle", methods=["POST"])
def monitor_toggle_query(qid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT status FROM monitor_queries WHERE id=?", (qid,))
    row = c.fetchone()
    new_status = "paused" if row and row["status"]=="active" else "active"
    conn.execute("UPDATE monitor_queries SET status=? WHERE id=?", (new_status, qid))
    conn.commit(); conn.close()
    return jsonify({"success": True, "status": new_status})

@app.route("/api/monitor/leads")
def monitor_leads():
    status = request.args.get("status", None)
    limit  = request.args.get("limit", 100, type=int)
    conn = get_conn()
    c = conn.cursor()
    if status:
        c.execute("SELECT * FROM monitor_leads WHERE status=? ORDER BY found_at DESC LIMIT ?",
                  (status, limit))
    else:
        c.execute("SELECT * FROM monitor_leads ORDER BY found_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify({"success": True, "leads": rows})

@app.route("/api/monitor/leads/<int:lid>/status", methods=["POST"])
def monitor_lead_status(lid):
    data = request.json or {}
    new_status = data.get("status", "processed")
    note = data.get("note", "")
    conn = get_conn()
    conn.execute("UPDATE monitor_leads SET status=?, manager_note=? WHERE id=?",
                 (new_status, note, lid))
    conn.commit(); conn.close()
    return jsonify({"success": True})

@app.route("/api/monitor/scan-now", methods=["POST"])
def monitor_scan_now():
    return jsonify(scheduler.run_monitor_now())

# ════════════════════════════════════════════════════════════
# АГЕНТ 3 — СТАТЬИ
# ════════════════════════════════════════════════════════════

@app.route("/api/articles")
def api_articles():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id,title,status,created_at FROM articles ORDER BY created_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify({"success": True, "articles": rows})

@app.route("/api/articles/add", methods=["POST"])
def api_add_article():
    data = request.json or {}
    title   = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    tags    = data.get("tags","")
    if not title or not content:
        return jsonify({"success": False, "error": "Нужны заголовок и текст"})
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO articles (title,content,tags,status) VALUES (?,?,?,'draft')",
              (title, content, tags))
    aid = c.lastrowid
    conn.commit(); conn.close()
    db_log("INFO","articles", f"Добавлена статья: {title}")
    return jsonify({"success": True, "article_id": aid})

@app.route("/api/articles/<int:aid>")
def api_get_article(aid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM articles WHERE id=?", (aid,))
    row = c.fetchone()
    conn.close()
    return jsonify({"success": True, "article": dict(row) if row else None})

@app.route("/api/articles/<int:aid>/publish", methods=["POST"])
def api_publish_article(aid):
    data = request.json or {}
    platforms = data.get("platforms", [])
    if not platforms:
        return jsonify({"success": False, "error": "Выбери хотя бы одну платформу"})
    def run():
        from agents.article_publisher.publisher import publish_to_platforms
        publish_to_platforms(aid, platforms)
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "message": f"Публикация на {len(platforms)} платформах запущена"})

@app.route("/api/articles/publications")
def api_publications():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT p.*, a.title as article_title
                 FROM article_publications p
                 JOIN articles a ON a.id = p.article_id
                 ORDER BY p.published_at DESC LIMIT 100""")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify({"success": True, "publications": rows})

# ── ЗАПУСК ────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  🌱 SEO FARM — Мультиагентная платформа")
    print("=" * 60)
    init_all_tables()
    scheduler.start()
    print(f"  📱 Панель: http://localhost:{FLASK_PORT}")
    print(f"  📋 Консоль: python console.py")
    print("=" * 60)
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)
