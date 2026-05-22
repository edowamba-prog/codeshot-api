"""
Admin API — user management, plan changes, key revocation.
"""

from .users import get_db, list_users, get_user, update_user_plan
import time


def admin_delete_user(user_id: str) -> bool:
    """Delete a user and all their API keys."""
    conn = get_db()
    try:
        # Delete keys first (foreign key)
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
