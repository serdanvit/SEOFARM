"""
core/token_manager.py — Шифрование токенов (чистый Python, без зависимостей)
Работает на Python 3.8+ включая 3.14 alpha.
Использует AES-256-like XOR stream cipher с ключом из PBKDF2.
"""
import os, sys, hashlib, secrets, base64, hmac, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import SECRET_KEY_FILE, DATA_DIR

logger = logging.getLogger("token_manager")


def _get_master_key() -> bytes:
    """
    Получает или создаёт мастер-ключ.
    Ключ хранится в data/.secret_key — не удалять!
    Если удалить — все токены станут нечитаемы.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SECRET_KEY_FILE):
        raw = open(SECRET_KEY_FILE, "rb").read().strip()
        return base64.b64decode(raw)

    # Генерируем новый 32-байтный ключ
    key = secrets.token_bytes(32)
    with open(SECRET_KEY_FILE, "wb") as f:
        f.write(base64.b64encode(key))
    logger.info("[tokens] Создан новый мастер-ключ")
    return key


def _derive_key(master: bytes, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256: из мастер-ключа и соли делает рабочий ключ"""
    return hashlib.pbkdf2_hmac("sha256", master, salt, iterations=100_000, dklen=32)


def _xor_stream(data: bytes, key: bytes) -> bytes:
    """
    XOR stream cipher: генерирует бесконечный поток из ключа через SHA-256 chain.
    Простой, быстрый, криптографически стойкий при случайном ключе.
    """
    result = bytearray(len(data))
    stream_pos = 0
    block = hashlib.sha256(key).digest()
    block_pos = 0

    for i, byte in enumerate(data):
        if block_pos >= 32:
            block = hashlib.sha256(block + key + stream_pos.to_bytes(8, "big")).digest()
            block_pos = 0
            stream_pos += 1
        result[i] = byte ^ block[block_pos]
        block_pos += 1

    return bytes(result)


def encrypt_token(token: str) -> str:
    """
    Шифрует токен VK:
    1. Генерируем случайную соль
    2. Выводим ключ из мастер-ключа + соль
    3. XOR-шифруем токен
    4. Добавляем HMAC для проверки целостности
    5. Кодируем в base64
    """
    master = _get_master_key()
    salt   = secrets.token_bytes(16)
    key    = _derive_key(master, salt)

    ciphertext = _xor_stream(token.encode("utf-8"), key)

    # HMAC для защиты от подделки
    mac = hmac.new(key, salt + ciphertext, hashlib.sha256).digest()

    # Итог: salt(16) + mac(32) + ciphertext
    payload = salt + mac + ciphertext
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decrypt_token(encrypted: str) -> str:
    """Расшифровывает токен. При ошибке возвращает исходную строку."""
    try:
        payload = base64.urlsafe_b64decode(encrypted.encode("ascii"))
        if len(payload) < 49:  # 16 + 32 + минимум 1
            return encrypted   # старый незашифрованный токен

        salt       = payload[:16]
        mac_stored = payload[16:48]
        ciphertext = payload[48:]

        master = _get_master_key()
        key    = _derive_key(master, salt)

        # Проверяем целостность
        mac_calc = hmac.new(key, salt + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(mac_stored, mac_calc):
            logger.error("[tokens] Ошибка HMAC — токен повреждён или подменён")
            return encrypted

        return _xor_stream(ciphertext, key).decode("utf-8")

    except Exception as e:
        logger.warning(f"[tokens] decrypt fallback: {e}")
        return encrypted  # fallback для не-зашифрованных токенов


# ── CRUD аккаунтов ────────────────────────────────────────────

def add_vk_account(token: str, notes: str = "") -> dict:
    from core.vk_api import check_token
    from core.database import db_log
    from core.db import fetchone, execute

    valid, info = check_token(token)
    if not valid:
        return {"success": False, "error": info.get("error", "Токен недействителен")}

    hint = f"...{token[-6:]}"
    enc  = encrypt_token(token)

    existing = fetchone("SELECT id FROM vk_accounts WHERE token_hint=?", (hint,))
    if existing:
        return {"success": False, "error": f"Токен {hint} уже добавлен"}

    aid = execute(
        """INSERT INTO vk_accounts
           (token_encrypted, token_hint, user_id, user_name, status, last_reset_date, notes)
           VALUES (?,?,?,?,'active',date('now'),?)""",
        (enc, hint, str(info.get("id", "")), info.get("name", ""), notes)
    )

    db_log("SUCCESS", "token_manager", f"Добавлен аккаунт {info.get('name')} ({hint})")
    return {"success": True, "account_id": aid, "hint": hint, "user_info": info}


def get_all_accounts() -> list:
    from core.db import fetchall
    return fetchall(
        "SELECT id,token_hint,user_name,status,daily_actions,daily_groups,last_used,notes "
        "FROM vk_accounts ORDER BY id"
    )


def get_active_tokens() -> list:
    """Возвращает [(account_id, token), ...] всех активных аккаунтов"""
    from core.db import fetchall
    rows = fetchall("SELECT id, token_encrypted FROM vk_accounts WHERE status='active'")
    return [(r["id"], decrypt_token(r["token_encrypted"])) for r in rows]
