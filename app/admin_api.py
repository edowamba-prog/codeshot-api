"""
Admin API — user management, plan changes, key revocation.
Protected by ADMIN_PASSWORD env var + JWT.
"""

import os
import time
import hashlib
import secrets
from .users import get_db, list_users, get_user, update_user_plan

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_JWT_SECRET = os.environ.get("ADMIN_JWT_SECRET", secrets.token_hex(32))

# ── Admin Auth ──

def admin_login(password: str) -> str | None:
    """Verify admin password and return a JWT. Returns None if wrong."""
    if not ADMIN_PASSWORD:
        return None  # Admin not configured
    if password != ADMIN_PASSWORD:
        return None

    import json, base64
    header = json.dumps({"alg": "HS256", "typ": "JWT"})
    payload = json.dumps({
        "sub": "admin",
        "role": "admin",
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400,  # 24 hours
    })

    def b64(s):
        return base64.urlsafe_b64encode(s.encode()).rstrip(b'=').decode()

    unsigned = f"{b64(header)}.{b64(payload)}"
    sig = hashlib.sha256(f"{unsigned}:{ADMIN_JWT_SECRET}".encode()).hexdigest()[:32]
    return f"{unsigned}.{sig}"


def admin_verify(token: str) -> bool:
    """Verify an admin JWT. Returns True if valid."""
    if not ADMIN_PASSWORD:
        return False
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False

        import json, base64
        def deb64(s):
            s += '=' * (4 - len(s) % 4)
            return json.loads(base64.urlsafe_b64decode(s))

        payload = deb64(parts[1])
        if payload.get("exp", 0) < time.time():
            return False
        if payload.get("role") != "admin":
            return False

        unsigned = f"{parts[0]}.{parts[1]}"
        expected = hashlib.sha256(f"{unsigned}:{ADMIN_JWT_SECRET}".encode()).hexdigest()[:32]
        return parts[2] == expected
    except Exception:
        return False


# ── Admin operations ──

def admin_delete_user(user_id: str) -> bool:
    """Delete a user and all their API keys."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM api_keys WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def admin_list_all_keys() -> list[dict]:
    """List all API keys with user info."""
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("""
            SELECT k.id, k.name, k.plan, k.created_at, k.enabled,
                   u.email as user_email, u.id as user_id
            FROM api_keys k JOIN users u ON k.user_id = u.id
            ORDER BY k.created_at DESC
        """).fetchall()]
    finally:
        conn.close()


def admin_toggle_key(key_id: str, enabled: bool) -> bool:
    """Enable or disable an API key."""
    conn = get_db()
    try:
        conn.execute("UPDATE api_keys SET enabled = ? WHERE id = ?",
                     (1 if enabled else 0, key_id))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def admin_revoke_key(key_id: str) -> bool:
    """Permanently delete an API key."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def admin_change_user_plan(user_id: str, plan: str) -> bool:
    """Change a user's plan and update all their keys."""
    if plan not in ("free", "pro", "team", "business"):
        return False
    conn = get_db()
    try:
        conn.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))
        conn.execute("UPDATE api_keys SET plan = ? WHERE user_id = ?", (plan, user_id))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def admin_user_detail(user_id: str) -> dict | None:
    """Get a user with all their API keys."""
    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return None
        keys = conn.execute("SELECT * FROM api_keys WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        return {
            "user": dict(user),
            "keys": [dict(k) for k in keys],
        }
    finally:
        conn.close()
