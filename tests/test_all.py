#!/usr/bin/env python3
"""
CodeShot API — Full Feature Test Suite
Run: python3 tests/test_all.py [--base https://drmadmeow.up.railway.app]
"""

import sys, json, time, os
import urllib.request
import urllib.error

BASE = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--base" else "http://localhost:8000"
PASS = 0
FAIL = 0
TOKEN = None
API_KEY = None
ADMIN_TOKEN = None

def req(method, path, body=None, headers=None, code=200):
    """Make an HTTP request and assert status code."""
    global PASS, FAIL
    url = f"{BASE}{path}"
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body else None
    
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h, method=method))
        status = r.status
        content_type = r.headers.get("Content-Type", "")
        if "application/json" in content_type or "application/problem" in content_type:
            resp = json.loads(r.read())
        else:
            resp = {"_html": True, "_len": len(r.read())}
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            resp = json.loads(e.read())
        except:
            resp = {"detail": str(e)}
    except Exception as e:
        status = 0
        resp = {"error": str(e)}
    
    if status == code:
        PASS += 1
        print(f"  ✅ {method} {path} → {status}")
    else:
        FAIL += 1
        print(f"  ❌ {method} {path} → {status} (expected {code}): {json.dumps(resp)[:120]}")
    return resp


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ═══════════════════════════════════════════════════════════
section("1. HEALTH & PUBLIC PAGES")

resp = req("GET", "/health")
assert resp.get("status") == "ok", f"Health check failed: {resp}"
print(f"     Service: {resp.get('service', '?')}")

req("GET", "/", code=200)
req("GET", "/docs", code=200)
req("GET", "/v1/themes", code=200)
req("GET", "/v1/presets", code=200)
req("GET", "/v1/languages", code=200)
req("GET", "/v1/effects", code=200)


# ═══════════════════════════════════════════════════════════
section("2. AUTH — Registration & Login")

email = f"test-{int(time.time())}@codeshot.dev"
password = "testpass123"

# Register
resp = req("POST", "/v1/auth/register", body={
    "email": email, "password": password, "name": "Test User"
})
TOKEN = resp.get("token")
assert TOKEN, f"Registration failed: {resp}"
print(f"     User: {resp['user']['email']} | Plan: {resp['user']['plan']}")

# Login
resp = req("POST", "/v1/auth/login", body={"email": email, "password": password})
assert resp.get("token"), f"Login failed: {resp}"
print(f"     Login OK: {resp['user']['email']}")

# Login with wrong password
req("POST", "/v1/auth/login", body={"email": email, "password": "wrongpass"}, code=401)


# ═══════════════════════════════════════════════════════════
section("3. AGENT API KEY — One-shot register+key")

agent_email = f"agent-{int(time.time())}@bot.dev"
resp = req("POST", "/v1/auth/api-key", body={
    "email": agent_email, "password": "agentpass456"
})
API_KEY = resp.get("api_key")
assert API_KEY and API_KEY.startswith("cs_"), f"Agent key failed: {resp}"
print(f"     Key: {API_KEY[:25]}... | Plan: {resp.get('plan')} | Token: {resp.get('token','')[:20]}...")


# ═══════════════════════════════════════════════════════════
section("4. API ENDPOINTS — Screenshot, Diff, Animate, Annotate")

auth = {"Authorization": f"Bearer {API_KEY}"}

# Screenshot
resp = req("POST", "/v1/screenshot", body={
    "code": "def hello():\n    print('Hello, World!')",
    "language": "python",
    "theme": "dracula",
    "format": "png"
}, headers=auth)
print(f"     Screenshot: {resp.get('width','?')}x{resp.get('height','?')} — theme: {resp.get('theme','?')}")

# Screenshot HTML format
req("POST", "/v1/screenshot", body={
    "code": "console.log('test')",
    "language": "javascript",
    "theme": "tokyo-night",
    "format": "html"
}, headers=auth)

# Screenshot with preset
resp = req("POST", "/v1/screenshot", body={
    "code": "fn main() { println!(\"Rust\"); }",
    "language": "rust",
    "theme": "github-dark",
    "preset": "twitter-post",
    "watermark": "@test"
}, headers=auth)
print(f"     Twitter preset: {resp.get('preset','?')} — {resp.get('width','?')}x{resp.get('height','?')}")

# Diff
req("POST", "/v1/diff", body={
    "old_code": "x = 1\ny = 2",
    "new_code": "x = 1\ny = 3\nz = 4",
    "language": "python",
    "theme": "dracula",
    "mode": "unified"
}, headers=auth)

# Diff side-by-side
req("POST", "/v1/diff", body={
    "old_code": "const a = 1;",
    "new_code": "const a = 2;",
    "language": "javascript",
    "theme": "monokai",
    "mode": "side-by-side"
}, headers=auth)

# Animate
req("POST", "/v1/animate", body={
    "code": "package main\n\nfunc main() {\n    println(\"go\")\n}",
    "language": "go",
    "theme": "dracula",
    "effect": "typewriter",
    "duration": 1.0,
    "fps": 12,
    "format": "mp4"
}, headers=auth)

# Animate GIF
req("POST", "/v1/animate", body={
    "code": "print('short')",
    "language": "python",
    "effect": "fade-in",
    "duration": 1.0,
    "fps": 12,
    "format": "gif"
}, headers=auth)


# ═══════════════════════════════════════════════════════════
section("5. AUTH GATES — Unauthenticated requests")

req("POST", "/v1/screenshot", body={"code": "x"}, code=401)
req("POST", "/v1/diff", body={"old_code": "a", "new_code": "b"}, code=401)
req("POST", "/v1/billing/checkout?plan=pro", code=401)
req("POST", "/v1/me/upgrade?plan=pro", code=401)


# ═══════════════════════════════════════════════════════════
section("6. USER DASHBOARD — Me, Keys, Usage, History")

resp = req("GET", "/v1/me", headers={"Authorization": f"Bearer {TOKEN}"})
print(f"     User: {resp['user']['email']} | Plan: {resp['user']['plan']}")
print(f"     Keys: {len(resp.get('api_keys',[]))} | Usage: {resp['usage']}")

# Create API key
resp = req("POST", "/v1/me/keys?name=cli-key", headers={"Authorization": f"Bearer {TOKEN}"})
new_key = resp.get("key")
assert new_key and new_key.startswith("cs_"), f"Key creation failed: {resp}"
print(f"     New key: {new_key[:25]}...")

# Usage history
resp = req("GET", "/v1/me/usage/history?days=7", headers={"Authorization": f"Bearer {TOKEN}"})
print(f"     History: {len(resp.get('history',[]))} days")


# ═══════════════════════════════════════════════════════════
section("7. DASHBOARD & ADMIN PAGES")

req("GET", "/dashboard", code=200)
resp = req("GET", "/admin", code=200)
print(f"     Admin page loaded (password-protected)")


# ═══════════════════════════════════════════════════════════
section("8. ADMIN AUTH — Login & Protected Endpoints")

# Try admin endpoints without auth
req("GET", "/v1/admin/keys", code=401)
# Wrong password returns 401 when configured, 400 when not
try:
    req("POST", "/v1/admin/login", body={"password": "wrong"}, code=401)
except AssertionError:
    req("POST", "/v1/admin/login", body={"password": "wrong"}, code=400)

# Check if ADMIN_PASSWORD is configured
admin_pass = os.environ.get("ADMIN_PASSWORD", "")
if admin_pass:
    resp = req("POST", "/v1/admin/login", body={"password": admin_pass})
    ADMIN_TOKEN = resp.get("token")
    assert ADMIN_TOKEN, f"Admin login failed: {resp}"
    print(f"     Admin logged in: {ADMIN_TOKEN[:30]}...")
    
    # Verify session
    req("GET", "/v1/admin/login", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
    
    # List keys with admin auth
    resp = req("GET", "/v1/admin/keys", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
    print(f"     Keys listed: {len(resp.get('keys', []))} keys")
    
    # List all keys
    resp = req("GET", "/v1/admin/all-keys", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
    print(f"     All keys: {len(resp.get('keys', []))}")
else:
    print(f"     ⚠️  ADMIN_PASSWORD not set — skipping admin tests")


# ═══════════════════════════════════════════════════════════
section("9. ERROR HANDLING")

# Invalid theme
req("POST", "/v1/screenshot", body={
    "code": "x", "theme": "nonexistent"
}, headers=auth, code=400)

# Missing code
req("POST", "/v1/screenshot", body={}, headers=auth, code=422)

# Invalid format
req("POST", "/v1/animate", body={
    "code": "x", "effect": "nonexistent", "duration": 1, "fps": 12
}, headers=auth, code=422)

print(f"\n{'='*60}")
print(f"  RESULTS: {PASS} passed, {FAIL} failed out of {PASS+FAIL}")
print(f"{'='*60}")

sys.exit(0 if FAIL == 0 else 1)
