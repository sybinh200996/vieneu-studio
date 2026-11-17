import os
import sqlite3
import secrets
import hashlib
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

# Cấu hình tài khoản và mật khẩu theo yêu cầu của Sỹ Bình
ALLOWED_USERS = {"sybinh", "dangnam"}
ALLOWED_PASSWORDS = {"200996", "241204"}

# Đường dẫn database SQLite lưu trữ API Keys
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "admin.db"

# Quản lý phiên đăng nhập Admin trong bộ nhớ (Token -> {username, expires_at})
ADMIN_SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_TTL_SECONDS = 7 * 24 * 3600  # 7 ngày

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Khởi tạo bảng lưu trữ API Keys nếu chưa tồn tại"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            is_active INTEGER DEFAULT 1,
            total_requests INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

# Khởi tạo DB khi load module
init_db()

# --- ADMIN AUTHENTICATION ---
def verify_admin_login(username: str, password: str) -> Optional[str]:
    """
    Xác thực tài khoản sybinh / dangnam với 2 mật khẩu 200996 và 241204.
    Trả về session_token nếu thành công, None nếu thất bại.
    """
    clean_user = username.strip().lower()
    clean_pass = password.strip()

    if clean_user in ALLOWED_USERS and clean_pass in ALLOWED_PASSWORDS:
        # Sinh session token an toàn
        token = secrets.token_hex(24)
        ADMIN_SESSIONS[token] = {
            "username": clean_user,
            "expires_at": time.time() + SESSION_TTL_SECONDS
        }
        return token
    return None

def verify_admin_token(token: Optional[str]) -> Optional[str]:
    """
    Kiểm tra token admin hợp lệ và chưa hết hạn.
    Trả về username nếu hợp lệ, ngược lại trả về None.
    """
    if not token:
        return None

    # Hỗ trợ format Bearer <token>
    if token.startswith("Bearer "):
        token = token[7:].strip()

    session = ADMIN_SESSIONS.get(token)
    if not session:
        return None

    if time.time() > session["expires_at"]:
        del ADMIN_SESSIONS[token]
        return None

    return session["username"]

def revoke_admin_token(token: Optional[str]):
    if not token:
        return
    if token.startswith("Bearer "):
        token = token[7:].strip()
    if token in ADMIN_SESSIONS:
        del ADMIN_SESSIONS[token]

# --- API KEY MANAGEMENT ---
def create_api_key(name: str) -> Dict[str, Any]:
    """Tạo API key mới cho website khác kết nối"""
    clean_name = name.strip() if name else "Website kết nối"
    new_key = f"vne_live_{secrets.token_hex(16)}"
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO api_keys (key, name, created_at, is_active, total_requests)
        VALUES (?, ?, ?, 1, 0)
    """, (new_key, clean_name, created_at))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": new_id,
        "key": new_key,
        "name": clean_name,
        "created_at": created_at,
        "is_active": True,
        "total_requests": 0
    }

def list_api_keys() -> List[Dict[str, Any]]:
    """Lấy danh sách tất cả API Keys"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, key, name, created_at, last_used_at, is_active, total_requests FROM api_keys ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    keys = []
    for r in rows:
        keys.append({
            "id": r["id"],
            "key": r["key"],
            "name": r["name"],
            "created_at": r["created_at"],
            "last_used_at": r["last_used_at"],
            "is_active": bool(r["is_active"]),
            "total_requests": r["total_requests"]
        })
    return keys

def toggle_api_key(key_id: int) -> bool:
    """Bật hoặc tắt trạng thái hoạt động của key"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM api_keys WHERE id = ?", (key_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    new_state = 0 if row["is_active"] == 1 else 1
    cursor.execute("UPDATE api_keys SET is_active = ? WHERE id = ?", (new_state, key_id))
    conn.commit()
    conn.close()
    return True

def delete_api_key(key_id: int) -> bool:
    """Xóa vĩnh viễn một API Key"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def validate_api_key(key_str: Optional[str]) -> bool:
    """
    Xác thực API Key gửi từ các website ngoài.
    Nếu hợp lệ, tự động cập nhật số lần request và thời gian sử dụng.
    """
    if not key_str:
        return False

    if key_str.startswith("Bearer "):
        key_str = key_str[7:].strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, is_active FROM api_keys WHERE key = ?", (key_str,))
    row = cursor.fetchone()

    if not row or row["is_active"] != 1:
        conn.close()
        return False

    # Cập nhật thống kê
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE api_keys
        SET total_requests = total_requests + 1, last_used_at = ?
        WHERE id = ?
    """, (now, row["id"]))
    conn.commit()
    conn.close()
    return True
