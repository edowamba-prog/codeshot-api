"""
User system — registration, login, JWT auth, SQLite storage.
"""

import os
import time
import uuid
import json
import hashlib
import secrets
import sqlite3
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "users.db"

# JWT secret — set in env, or auto-generate
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))

# ── Database ──

def get_db() -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT,
            plan TEXT DEFAULT 'free',
            stripe_customer_id TEXT,
            created_at REAL NOT NULL,
            last_login REAL
        );
        
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            key_hash TEXT UNIQUE NOT NULL,
            plan TEXT DEFAULT 'free',
            created_at REAL NOT NULL,
            enabled INTEGER DEFAULT 1
        );
        
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            timestamp REAL NOT NULL
        );
        
        CREATE INDEX IF NOT EXISTS idx_usage_key ON usage_log(key_hash);
        CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_keys_user ON api_keys(user_id);
    """)
    conn.commit()
    conn.close()


# ── Password hashing (sha256 + salt — simple, no external deps) ──

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{h}"


def verify_password(password: str, stored: str) -> bool:
    salt, h = stored.split(":", 1)
    return h == hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


# ── Models ──

class UserCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)
    name: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


# ── User operations ──

def create_user(email: str, password: str, name: Optional[str] = None) -> dict:
    """Create a new user. Returns user dict. Raises ValueError if email exists."""
    conn = get_db()
    try:
        user_id = str(uuid.uuid4())
        now = time.time()
        conn.execute(
            "INSERT INTO users (id, email, password_hash, name, plan, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, email.lower().strip(), hash_password(password), name, "free", now)
        )
        conn.commit()
        return {"id": user_id, "email": email, "name": name, "plan": "free", "created_at": now}
    except sqlite3.IntegrityError:
        raise ValueError("Email already registered")
    finally:
        conn.close()


def authenticate(email: str, password: str) -> Optional[dict]:
    """Authenticate user by email + password. Returns user dict or None."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.lower().strip(),)
        ).fetchone()
        if row and verify_password(password, row["password_hash"]):
            conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (time.time(), row["id"]))
            conn.commit()
            return dict(row)
        return None
    finally:
        conn.close()


def get_user(user_id: str) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_users() -> list[dict]:
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()]
    finally:
        conn.close()


def update_user_plan(user_id: str, plan: str):
    conn = get_db()
    try:
        conn.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))
        conn.commit()
    finally:
        conn.close()


# ── JWT ──

def create_token(user_id: str) -> str:
    """Create a simple JWT-like token."""
    header = json.dumps({"alg": "HS256", "typ": "JWT"})
    payload = json.dumps({"sub": user_id, "iat": int(time.time()), "exp": int(time.time()) + 86400 * 30})
    
    def b64(s):
        import base64
        return base64.urlsafe_b64encode(s.encode()).rstrip(b'=').decode()
    
    unsigned = f"{b64(header)}.{b64(payload)}"
    sig = hashlib.sha256(f"{unsigned}:{JWT_SECRET}".encode()).hexdigest()[:32]
    return f"{unsigned}.{sig}"


def verify_token(token: str) -> Optional[str]:
    """Verify a JWT token. Returns user_id or None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        
        import base64
        def deb64(s):
            s += '=' * (4 - len(s) % 4)
            return json.loads(base64.urlsafe_b64decode(s))
        
        payload = deb64(parts[1])
        
        if payload.get("exp", 0) < time.time():
            return None
        
        # Verify signature
        unsigned = f"{parts[0]}.{parts[1]}"
        expected = hashlib.sha256(f"{unsigned}:{JWT_SECRET}".encode()).hexdigest()[:32]
        if parts[2] != expected:
            return None
        
        return payload["sub"]
    except Exception:
        return None


# ── User API keys ──

def create_user_api_key(user_id: str, name: str, plan: str = "free") -> str:
    """Create an API key for a user. Returns the raw key."""
    raw_key = f"cs_{uuid.uuid4().hex[:24]}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO api_keys (id, user_id, name, key_hash, plan, created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), user_id, name, key_hash, plan, time.time())
        )
        conn.commit()
        return raw_key
    finally:
        conn.close()


def get_user_api_keys(user_id: str) -> list[dict]:
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, name, plan, created_at, enabled FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()]
    finally:
        conn.close()


def get_user_usage(user_id: str) -> dict:
    """Get usage stats for all keys belonging to a user."""
    conn = get_db()
    try:
        now = time.time()
        hour_ago = now - 3600
        day_ago = now - 86400
        
        keys = [r["key_hash"] for r in conn.execute(
            "SELECT key_hash FROM api_keys WHERE user_id = ?", (user_id,)
        ).fetchall()]
        
        if not keys:
            return {"hourly": 0, "daily": 0, "total": 0}
        
        placeholders = ",".join("?" * len(keys))
        hourly = conn.execute(
            f"SELECT COUNT(*) FROM usage_log WHERE key_hash IN ({placeholders}) AND timestamp > ?",
            (*keys, hour_ago)
        ).fetchone()[0]
        
        daily = conn.execute(
            f"SELECT COUNT(*) FROM usage_log WHERE key_hash IN ({placeholders}) AND timestamp > ?",
            (*keys, day_ago)
        ).fetchone()[0]
        
        total = conn.execute(
            f"SELECT COUNT(*) FROM usage_log WHERE key_hash IN ({placeholders})",
            keys
        ).fetchone()[0]
        
        return {"hourly": hourly, "daily": daily, "total": total}
    finally:
        conn.close()


def log_usage(key_hash: str, endpoint: str):
    """Log an API request for usage tracking."""
    conn = get_db()
    try:
        conn.execute("INSERT INTO usage_log (key_hash, endpoint, timestamp) VALUES (?,?,?)",
                     (key_hash, endpoint, time.time()))
        conn.commit()
    finally:
        conn.close()


# ── Admin stats ──

def get_admin_stats() -> dict:
    """Get aggregate stats for admin dashboard."""
    conn = get_db()
    try:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_keys = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        now = time.time()
        today_requests = conn.execute(
            "SELECT COUNT(*) FROM usage_log WHERE timestamp > ?", (now - 86400,)
        ).fetchone()[0]
        
        # Plan distribution
        plans = {}
        for row in conn.execute("SELECT plan, COUNT(*) as c FROM users GROUP BY plan"):
            plans[row["plan"]] = row["c"]
        
        return {
            "total_users": total_users,
            "total_keys": total_keys,
            "today_requests": today_requests,
            "plans": plans,
        }
    finally:
        conn.close()


# Initialize on import
init_db()
