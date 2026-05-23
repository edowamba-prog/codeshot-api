"""
x402 V2 Protocol — exact x402scan fixture format.
"""
import os, json, time, base64

EVM_PAYEE_ADDRESS = os.environ.get("EVM_PAYEE_ADDRESS", "0xed6881b56690C26189d914F2302C9af79685CB97")
DOMAIN = os.environ.get("DOMAIN", "https://drmadmeow.up.railway.app")
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
MAX_PROOF_AGE = 300
AGENT_PRICES = {
    "/v1/screenshot": "0.01",
    "/v1/diff": "0.01",
    "/v1/animate": "0.05",
    "/v1/annotate": "0.03",
    "/v1/webshot": "0.01",
    "/v1/scrape": "0.01",
    "/v1/preview": "0.005",
}

def _schema(ep):
    s = {
        "screenshot": {"type": "object", "required": ["code"], "properties": {"code": {"type": "string"}, "language": {"type": "string"}}},
        "diff": {"type": "object", "required": ["old_code", "new_code"], "properties": {"old_code": {"type": "string"}, "new_code": {"type": "string"}}},
        "animate": {"type": "object", "required": ["code"], "properties": {"code": {"type": "string"}, "effect": {"type": "string", "enum": ["typewriter", "reveal-line", "fade-in"]}}},
        "annotate": {"type": "object", "required": ["code"], "properties": {"code": {"type": "string"}, "focus": {"type": "string", "enum": ["general", "error-handling", "performance", "security", "patterns"]}}},
        "webshot": {"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "full_page": {"type": "boolean"}}},
        "scrape": {"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}, "format": {"type": "string"}}},
        "preview": {"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}}},
    }
    return s.get(ep, s["screenshot"])

def build_payment_required(path: str) -> dict:
    price = AGENT_PRICES.get(path, "0.01")
    ep = path.split("/")[-1]
    body = _schema(ep)
    return {
        "x402Version": 2,
        "accepts": [{
            "scheme": "exact",
            "network": "eip155:8453",
            "amount": price,
            "payTo": EVM_PAYEE_ADDRESS,
            "maxTimeoutSeconds": MAX_PROOF_AGE,
            "asset": BASE_USDC,
            "extra": {},
        }],
        "resource": {"url": f"{DOMAIN}{path}", "description": f"CodeShot — {ep}", "mimeType": "application/json"},
        "extensions": {
            "bazaar": {
                "info": {
                    "input": {"type": "http", "method": "POST", "bodyType": "json", "body": body},
                    "output": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                }
            }
        },
    }

def build_openapi_payment_info(path: str) -> dict:
    return {"x-payment-info":{"protocols":[{"x402":{}}],"price":{"mode":"fixed","currency":"USD","amount":get_price(path)}}}

def verify_payment_signature(sig, payee, amount):
    if not sig: return False, "Missing"
    try: p = json.loads(sig)
    except: return False, "Invalid"
    s, m = p.get("signature",""), p.get("message",{})
    if not s or not m: return False, "Incomplete"
    if abs(time.time()-m.get("timestamp",0)) > MAX_PROOF_AGE: return False, "Expired"
    try:
        from eth_account.messages import encode_defunct
        from eth_account import Account
        t = f"{amount}:{payee}:{m.get('timestamp','')}:{m.get('nonce','')}"
        return True, Account.recover_message(encode_defunct(text=t), signature=s)
    except ImportError: return True, "dev"
    except Exception as e: return False, str(e)

is_x402_path = lambda p: p.startswith("/v1/agent/")
agent_path_to_real = lambda p: p.replace("/v1/agent/", "/v1/")
get_price = lambda p: AGENT_PRICES.get(agent_path_to_real(p), "0.01") if is_x402_path(p) else AGENT_PRICES.get(p, "0.01")
