"""
x402 Protocol — exact x402scan validator fixture format (V1).
After extensive trial-and-error, V1 with network:"base" + outputSchema passes probes.
V2 with CAIP-2 and extensions.bazaar.info is silently rejected by the validator.
"""
import os, json, time, base64

EVM_PAYEE_ADDRESS = os.environ.get("EVM_PAYEE_ADDRESS", "0xed6881b56690C26189d914F2302C9af79685CB97")
DOMAIN = os.environ.get("DOMAIN", "https://drmadmeow.up.railway.app")
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
MAX_PROOF_AGE = 300

# Prices in smallest USDC unit (6 decimals). $0.01 = 10000 units.
AGENT_PRICES_USDC = {
    "/v1/screenshot": 10000,
    "/v1/diff":      10000,
    "/v1/animate":   50000,
    "/v1/annotate":  30000,
    "/v1/webshot":   10000,
    "/v1/scrape":    10000,
    "/v1/preview":    5000,
}

# Dollar string prices for OpenAPI display
AGENT_PRICES_USD = {
    "/v1/screenshot": "0.01",
    "/v1/diff":      "0.01",
    "/v1/animate":   "0.05",
    "/v1/annotate":  "0.03",
    "/v1/webshot":   "0.01",
    "/v1/scrape":    "0.01",
    "/v1/preview":   "0.005",
}


def _schema(ep):
    s = {
        "screenshot": {"type": "object", "required": ["code"], "properties": {"code": {"type": "string"}, "language": {"type": "string"}}},
        "diff":       {"type": "object", "required": ["old_code", "new_code"], "properties": {"old_code": {"type": "string"}, "new_code": {"type": "string"}}},
        "animate":    {"type": "object", "required": ["code"], "properties": {"code": {"type": "string"}, "effect": {"type": "string", "enum": ["typewriter", "reveal-line", "fade-in"]}}},
        "annotate":   {"type": "object", "required": ["code"], "properties": {"code": {"type": "string"}, "focus": {"type": "string", "enum": ["general", "error-handling", "performance", "security", "patterns"]}}},
        "webshot":    {"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "full_page": {"type": "boolean"}}},
        "scrape":     {"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}, "format": {"type": "string"}}},
        "preview":    {"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}}},
    }
    return s.get(ep, s["screenshot"])


def build_payment_required(path: str) -> dict:
    """V1 format — matches x402scan validator fixture baseV1 exactly."""
    # Strip /v1/agent/ prefix to match AGENT_PRICES keys
    lookup = _strip_agent(path)
    price = AGENT_PRICES_USDC.get(lookup, 10000)
    ep = path.split("/")[-1]
    body = _schema(ep)
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
                "input": {"type": "http", "method": "POST", "bodyType": "json", "body": body},
                "output": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
            },
        }],
    }


def build_openapi_payment_info(path: str) -> dict:
    price_str = AGENT_PRICES_USD.get(_strip_agent(path), "0.01")
    # Format with 6 decimal places for AgentCash compatibility
    price_formatted = f"{float(price_str):.6f}"
    return {
        "x-payment-info": {
            "protocols": [
                {"x402": {}},
                {"mpp": {"method": "", "intent": "", "currency": ""}},
            ],
            "price": {
                "mode": "fixed",
                "currency": "USD",
                "amount": price_formatted,
            },
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


# ── Path helpers ──

def is_x402_path(p: str) -> bool:
    return p.startswith("/v1/agent/")


def agent_path_to_real(p: str) -> str:
    return p.replace("/v1/agent/", "/v1/")


def _strip_agent(p: str) -> str:
    """Strip /v1/agent/ prefix to match AGENT_PRICES keys."""
    return p.replace("/v1/agent/", "/v1/") if p.startswith("/v1/agent/") else p


def get_price(path: str) -> str:
    """Get USD price string for OpenAPI display."""
    if is_x402_path(path):
        real = agent_path_to_real(path)
    else:
        real = path
    return AGENT_PRICES_USD.get(real, "0.01")


def get_price_usdc(path: str) -> int:
    """Get USDC unit price for payment verification."""
    if is_x402_path(path):
        real = agent_path_to_real(path)
    else:
        real = path
    return AGENT_PRICES_USDC.get(real, 10000)
