"""
Email notifications and user feedback system.
Sends emails via SMTP (Resend, SendGrid, or any SMTP provider).
Stores feedback/complaints in JSON with email notifications.
"""
import os
import json
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "edowamba@gmail.com")
FROM_EMAIL = os.environ.get("FROM_EMAIL", SMTP_USER or "noreply@codeshot.dev")

# Feedback storage
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
FEEDBACK_PATH = DATA_DIR / "feedback.json"


def _send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via SMTP. Returns True on success."""
    if not SMTP_HOST or not SMTP_USER:
        print(f"[notify] SMTP not configured — would send: {subject}")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = FROM_EMAIL
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, [to], msg.as_string())
        return True
    except Exception as e:
        print(f"[notify] Email failed: {e}")
        return False


def notify_new_user(email: str, name: str, plan: str = "free"):
    """Send notification when a new user registers."""
    subject = f"📝 New CodeShot User: {email}"
    body = f"""New user registered on CodeShot API:

  Email: {email}
  Name:  {name}
  Plan:  {plan}
  Time:  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

Manage users: https://drmadmeow.up.railway.app/admin
"""
    _send_email(NOTIFY_EMAIL, subject, body)


def notify_payment(user_email: str, plan: str):
    """Send notification when a user subscribes/pays."""
    subject = f"💰 New Subscriber: {user_email} → {plan.upper()}"
    body = f"""Payment received on CodeShot API:

  User:  {user_email}
  Plan:  {plan.upper()}
  Time:  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

View: https://drmadmeow.up.railway.app/admin
"""
    _send_email(NOTIFY_EMAIL, subject, body)


# ── Feedback / Complaints ──

def load_feedback() -> list[dict]:
    """Load all feedback entries."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if FEEDBACK_PATH.exists():
        with open(FEEDBACK_PATH) as f:
            return json.load(f)
    return []


def save_feedback(entries: list[dict]):
    """Save feedback entries."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def submit_feedback(email: str, category: str, message: str) -> dict:
    """Submit a feedback/complaint entry. Emails Edo and stores to JSON."""
    entry = {
        "id": str(int(time.time() * 1000)),
        "email": email,
        "category": category,  # bug, feature, complaint, praise, other
        "message": message[:2000],
        "created_at": datetime.utcnow().isoformat(),
        "resolved": False,
    }

    entries = load_feedback()
    entries.append(entry)
    save_feedback(entries)

    # Email Edo
    category_emoji = {
        "bug": "🐛", "feature": "💡", "complaint": "🚨",
        "praise": "🎉", "other": "📬",
    }
    emoji = category_emoji.get(category, "📬")
    subject = f"{emoji} CodeShot Feedback: {category} from {email}"
    body = f"""New feedback submitted on CodeShot:

  From:     {email}
  Category: {category}
  Time:     {entry['created_at']}
  ID:       {entry['id']}

Message:
---
{message}
---

View all feedback: https://drmadmeow.up.railway.app/admin/feedback
"""
    _send_email(NOTIFY_EMAIL, subject, body)

    return {"status": "received", "id": entry["id"]}


def get_feedback_stats() -> dict:
    """Get feedback statistics."""
    entries = load_feedback()
    total = len(entries)
    unresolved = sum(1 for e in entries if not e["resolved"])
    by_category = {}
    for e in entries:
        cat = e.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total": total,
        "unresolved": unresolved,
        "by_category": by_category,
        "recent": entries[-5:],
    }
