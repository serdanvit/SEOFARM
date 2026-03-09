"""
core/token_manager.py — Шифрование токенов (общее для всех агентов)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import SECRET_KEY_FILE, DATA_DIR

try:
    from cryptography.fernet import Fernet
    CRYPTO = True
except ImportError:
    CRYPTO = False

def _get_key():
    if not CRYPTO: return None
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SECRET_KEY_FILE):
        return open(SECRET_KEY_FILE, "rb").read()
    key = Fernet.generate_key()
    open(SECRET_KEY_FILE, "wb").write(key)
    return key

def encrypt_token(token):
    if not CRYPTO: return token
    return Fernet(_get_key()).encrypt(token.encode()).decode()

def decrypt_token(encrypted):
    if not CRYPTO: return encrypted
    try:
        return Fernet(_get_key()).decrypt(encrypted.encode()).decode()
    except Exception:
        return encrypted

def add_vk_account(token, notes=""):
    from core.vk_api import check_token
    from core.database import get_conn, db_log
    valid, info = check_token(token)
    if not valid:
        return {"success": False, "error": info.get("error", "Токен недействителен")}
    hint = f"...{token[-6:]}"
    enc  = encrypt_token(token)
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT id FROM vk_accounts WHERE token_hint=?", (hint,))
    if c.fetchone():
        conn.close()
        return {"success": False, "error": f"Токен {hint} уже добавлен"}
    c.execute("""INSERT INTO vk_accounts
        (token_encrypted, token_hint, user_id, user_name, status, last_reset_date, notes)
        VALUES (?,?,?,?,'active',date('now'),?)""",
        (enc, hint, str(info.get("id","")), info.get("name",""), notes))
    conn.commit()
    aid = c.lastrowid
    conn.close()
    db_log("SUCCESS", "token_manager", f"Добавлен аккаунт {info.get('name')} ({hint})")
    return {"success": True, "account_id": aid, "hint": hint, "user_info": info}

def get_all_accounts():
    from core.database import get_conn
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id,token_hint,user_name,status,daily_actions,daily_groups,last_used,notes FROM vk_accounts ORDER BY id")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_active_tokens():
    """Возвращает список (account_id, token) всех активных аккаунтов"""
    from core.database import get_conn
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, token_encrypted FROM vk_accounts WHERE status='active'")
    rows = c.fetchall()
    conn.close()
    return [(r["id"], decrypt_token(r["token_encrypted"])) for r in rows]
