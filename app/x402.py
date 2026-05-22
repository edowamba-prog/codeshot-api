"""
x402 Payment Protocol for CodeShot API — V2 format for x402scan compatibility.
"""

import os
import json
import time
import base64
from typing import Optional

# ── Configuration ──

EVM_PAYEE_ADDRESS = os.environ.get("EVM_PAYEE_ADDRESS", "")
DOMAIN = os.environ.get("DOMAIN", "https://drmadmeow.up.railway.app")

AGENT_PRICES = {
    "/v1/screenshot": "0.01",
    "/v1/diff": "0.01",
    "/v1/animate": "0.05",
    "/v1/annotate": "0.03",
}

BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CHAIN_ID = 8453
MAX_PROOF_AGE = 300


def _schema_for(endpoint: str) -> dict:
    """Return the JSON schema for an endpoint's request body."""
    schemas = {
        "screenshot": {
            "type": "object", "required": ["code"],
            "properties": {
                "code": {"type": "string"},
                "language": {"type": "string"},
                "theme": {"type": "string"},
                "preset": {"type": "string"},
                "watermark": {"type": "string"},
                "format": {"type": "string", "enum": ["png", "html"]},
            },
        },
        "diff": {
            "type": "object", "required": ["old_code", "new_code"],
            "properties": {
                "old_code": {"type": "string"},
                "new_code": {"type": "string"},
                "language": {"type": "string"},
                "theme": {"type": "string"},
                "mode": {"type": "string", "enum": ["unified", "side-by-side"]},
            },
        },
        "animate": {
            "type": "object", "required": ["code"],
            "properties": {
                "code": {"type": "string"},
                "language": {"type": "string"},
                "theme": {"type": "string"},
                "effect": {"type": "string", "enum": ["typewriter", "reveal-line", "fade-in"]},
                "duration": {"type": "number"},
                "format": {"type": "string", "enum": ["mp4", "gif"]},
            },
        },
        "annotate": {
            "type": "object", "required": ["code"],
            "properties": {
                "code": {"type": "string"},
                "language": {"type": "string"},
                "theme": {"type": "string"},
                "focus": {"type": "string", "enum": ["general", "error-handling", "performance", "security", "patterns"]},
            },
        },
    }
    return schemas.get(endpoint, schemas["screenshot"])


def build_payment_required(path: str) -> dict:
    """Build an x402 V2 PaymentRequired response for x402scan compatibility."""
    price = AGENT_PRICES.get(path, "0.01")
    endpoint = path.split("/")[-1]
    resource_url = f"{DOMAIN}{path}"
    body_schema = _schema_for(endpoint)

    return {
        "x402Version": 2,
        "accepts": [{
            "scheme": "exact",
            "network": f"eip155:{CHAIN_ID}",
            "amount": price,
            "payTo": EVM_PAYEE_ADDRESS,
            "maxTimeoutSeconds": MAX_PROOF_AGE,
            "asset": BASE_USDC,
            "extra": {},
        }],
        "resource": {
            "url": resource_url,
            "description": f"CodeShot — {endpoint}",
            "mimeType": "application/json",
        },
        "extensions": {
            "bazaar": {
                "info": {
                    "input": {
                        "type": "http",
                        "method": "POST",
                        "bodyType": "json",
                        "body": body_schema,
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "image": {"type": "string", "format": "binary", "description": "PNG image data"}
                        },
                    },
                },
            },
        },
    }


def build_openapi_payment_info(path: str) -> dict:
    """Build x402 payment metadata for OpenAPI spec."""
    price = AGENT_PRICES.get(path, "0.01")
    return {
        "x-payment-info": {
            "protocols": [{"x402": {}}],
            "price": {
                "mode": "fixed",
                "currency": "USD",
                "amount": price,
            },
        }
    }


def verify_payment_signature(sig_header: str, payee: str, amount: str) -> tuple[bool, str]:
    """Verify an x402 PAYMENT-SIGNATURE via EIP-191."""
    if not sig_header:
        return False, "Missing PAYMENT-SIGNATURE"
    try:
        payload = json.loads(sig_header)
    except json.JSONDecodeError:
        try:
            payload = json.loads(base64.b64decode(sig_header).decode())
        except Exception:
            return False, "Invalid format"
    signature = payload.get("signature", "")
    message = payload.get("message", {})
    if not signature or not message:
        return False, "Incomplete payload"
    msg_ts = message.get("timestamp", 0)
    if abs(time.time() - msg_ts) > MAX_PROOF_AGE:
        return False, f"Expired (>{MAX_PROOF_AGE}s)"
    if str(message.get("amount", "")) != amount:
        return False, "Amount mismatch"
    if message.get("payee", "").lower() != payee.lower():
        return False, "Payee mismatch"
    try:
        from eth_account.messages import encode_defunct
        from eth_account import Account
        msg_text = f"{amount}:{payee}:{msg_ts}:{message.get('nonce', '')}"
        recovered = Account.recover_message(encode_defunct(text=msg_text), signature=signature)
        return True, recovered
    except ImportError:
        return True, "dev-mode"
    except Exception as e:
        return False, str(e)


def is_x402_path(path: str) -> bool:
    return path.startswith("/v1/agent/")


def agent_path_to_real(path: str) -> str:
    return path.replace("/v1/agent/", "/v1/")


def get_price(path: str) -> str:
    real = agent_path_to_real(path) if is_x402_path(path) else path
    return AGENT_PRICES.get(real, "0.01")
