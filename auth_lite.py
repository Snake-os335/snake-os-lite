
"""Auth de Snake OS Lite: mismas cuentas @dogaemail.com que snake-os-vp."""
from __future__ import annotations
import os, sqlite3, time
from pathlib import Path
from uuid import uuid4
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
COOKIE_NAME = "lite_session_id"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
DATA = Path(__file__).resolve().parent / "data"
SESS_DB = DATA / "lite_sessions.db"
VP_DB = Path(os.environ.get("SNAKEOS_VP_DB") or "/app/vp-data/snakeos.db")

def _sess_conn():
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(SESS_DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at REAL NOT NULL)")
    c.commit()
    return c

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False

def get_user_by_email(email: str):
    email_n = (email or "").strip().lower()
    if not email_n or not VP_DB.exists():
        return None
    conn = sqlite3.connect(str(VP_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM users WHERE lower(email)=?", (email_n,)).fetchone()
    finally:
        conn.close()

def start_session(user_id: int) -> str:
    sid = str(uuid4())
    with _sess_conn() as c:
        c.execute("INSERT INTO sessions(id,user_id,created_at) VALUES(?,?,?)", (sid, int(user_id), time.time()))
        c.commit()
    return sid

def end_session(sid: str | None) -> None:
    if not sid: return
    with _sess_conn() as c:
        c.execute("DELETE FROM sessions WHERE id=?", (sid,))
        c.commit()

def user_from_session(sid: str | None):
    if not sid or not VP_DB.exists():
        return None
    with _sess_conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        return None
    if time.time() - float(row["created_at"]) > SESSION_MAX_AGE:
        end_session(sid)
        return None
    conn = sqlite3.connect(str(VP_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM users WHERE id=?", (int(row["user_id"]),)).fetchone()
    finally:
        conn.close()
