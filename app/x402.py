"""
x402 Payment Protocol — Exact Coinbase V1 fixture match.
"""
import os, json, time, base64

EVM_PAYEE_ADDRESS = os.environ.get("EVM_PAYEE_ADDRESS", "")
DOMAIN = os.environ.get("DOMAIN", "https://drmadmeow.up.railway.app")
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
MAX_PROOF_AGE = 300

AGENT_PRICES = {
    "/v1/screenshot": "0.01", "/v1/diff": "0.01",
    "/v1/animate": "0.05", "/v1/annotate": "0.03",
}

def build_payment_required(path: str) -> dict:
    price = AGENT_PRICES.get(path, "0.01")
    ep = path.split("/")[-1]
    return {
        "x402Version": 1,
        "accepts": [{
            "scheme": "exact",
            "network": "base",
            "maxAmountRequired": price,
            "resource": f"{DOMAIN}{path}",
            "description": f"CodeShot — {ep}",
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
