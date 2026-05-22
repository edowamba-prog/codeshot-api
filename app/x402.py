"""
x402 Payment Protocol — V1 format for x402scan compatibility.
Matches the x402scan validator fixture V1 format exactly.
"""

import os, json, time, base64

EVM_PAYEE_ADDRESS = os.environ.get("EVM_PAYEE_ADDRESS", "")
DOMAIN = os.environ.get("DOMAIN", "https://drmadmeow.up.railway.app")

AGENT_PRICES = {
    "/v1/screenshot": "0.01", "/v1/diff": "0.01",
    "/v1/animate": "0.05", "/v1/annotate": "0.03",
}

BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CHAIN_ID = 8453
MAX_PROOF_AGE = 300


def _schema_for(endpoint: str) -> dict:
    schemas = {
        "screenshot": {"type": "object", "required": ["code"], "properties": {
            "code": {"type": "string"}, "language": {"type": "string"},
            "theme": {"type": "string"}, "format": {"type": "string", "enum": ["png", "html"]},
        }},
        "diff": {"type": "object", "required": ["old_code", "new_code"], "properties": {
            "old_code": {"type": "string"}, "new_code": {"type": "string"},
            "language": {"type": "string"}, "theme": {"type": "string"},
        }},
        "animate": {"type": "object", "required": ["code"], "properties": {
            "code": {"type": "string"}, "language": {"type": "string"},
            "effect": {"type": "string", "enum": ["typewriter", "reveal-line", "fade-in"]},
        }},
        "annotate": {"type": "object", "required": ["code"], "properties": {
            "code": {"type": "string"}, "language": {"type": "string"},
            "focus": {"type": "string", "enum": ["general", "error-handling", "performance", "security", "patterns"]},
        }},
    }
    return schemas.get(endpoint, schemas["screenshot"])


def build_payment_required(path: str) -> dict:
    """V1 format matching x402scan fixture."""
    price = AGENT_PRICES.get(path, "0.01")
    endpoint = path.split("/")[-1]
    
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": "base",
            "maxAmountRequired": price,
            "resource": f"{DOMAIN}{path}",
            "description": f"CodeShot — {endpoint}",
            "mimeType": "application/json",
            "payTo": EVM_PAYEE_ADDRESS,
            "maxTimeoutSeconds": MAX_PROOF_AGE,
            "asset": BASE_USDC,
            "outputSchema": {
                "input": {"type": "http", "method": "POST"},
                "output": {"type": "object"},
            },
        }],
    }


def build_openapi_payment_info(path: str) -> dict:
    price = get_price(path)
    return {
        "x-payment-info": {
            "protocols": [{"x402": {}}],
            "price": {"mode": "fixed", "currency": "USD", "amount": price},
        }
    }


def verify_payment_signature(sig_header, payee, amount):
    if not sig_header: return False, "Missing PAYMENT-SIGNATURE"
    try: payload = json.loads(sig_header)
    except: return False, "Invalid format"
    s, m = payload.get("signature",""), payload.get("message",{})
    if not s or not m: return False, "Incomplete"
    if abs(time.time()-m.get("timestamp",0)) > MAX_PROOF_AGE: return False, "Expired"
    if str(m.get("amount","")) != amount: return False, "Amount mismatch"
    if m.get("payee","").lower() != payee.lower(): return False, "Payee mismatch"
    try:
        from eth_account.messages import encode_defunct
        from eth_account import Account
        t = f"{amount}:{payee}:{m.get('timestamp','')}:{m.get('nonce','')}"
        return True, Account.recover_message(encode_defunct(text=t), signature=s)
    except ImportError: return True, "dev-mode"
    except Exception as e: return False, str(e)


is_x402_path = lambda p: p.startswith("/v1/agent/")
agent_path_to_real = lambda p: p.replace("/v1/agent/", "/v1/")
get_price = lambda p: AGENT_PRICES.get(agent_path_to_real(p), "0.01")
