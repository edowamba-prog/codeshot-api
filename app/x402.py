"""
x402 Payment Protocol for CodeShot API.
Uses the official x402 Python SDK for spec-compliant 402 responses.
https://github.com/x402-foundation/x402
"""

import os
import json
import time
import base64
from typing import Optional

from x402 import PaymentRequiredV1

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


def build_payment_required(path: str) -> PaymentRequiredV1:
    """Build an x402 PaymentRequiredV1 response using the official SDK."""
    price = AGENT_PRICES.get(path, "0.01")
    resource = f"{DOMAIN}{path}"
    
    # Input schema for each endpoint (derived from OpenAPI)
    endpoint = path.split("/")[-1]
    schemas = {
        "screenshot": {
            "type": "object",
            "required": ["code"],
            "properties": {
                "code": {"type": "string", "description": "Source code to render"},
                "language": {"type": "string", "default": "plaintext"},
                "theme": {"type": "string", "default": "dracula"},
                "preset": {"type": "string"},
                "watermark": {"type": "string"},
                "format": {"type": "string", "enum": ["png", "html"], "default": "png"},
            },
            "example": {"code": "print('hello')", "language": "python", "theme": "dracula"},
        },
        "diff": {
            "type": "object",
            "required": ["old_code", "new_code"],
            "properties": {
                "old_code": {"type": "string"},
                "new_code": {"type": "string"},
                "language": {"type": "string", "default": "plaintext"},
                "theme": {"type": "string", "default": "dracula"},
                "mode": {"type": "string", "enum": ["unified", "side-by-side"], "default": "unified"},
            },
            "example": {"old_code": "x=1", "new_code": "x=2", "language": "python"},
        },
        "animate": {
            "type": "object",
            "required": ["code"],
            "properties": {
                "code": {"type": "string"},
                "language": {"type": "string", "default": "plaintext"},
                "theme": {"type": "string", "default": "dracula"},
                "effect": {"type": "string", "enum": ["typewriter", "reveal-line", "fade-in"], "default": "typewriter"},
                "duration": {"type": "number", "default": 4.0},
                "format": {"type": "string", "enum": ["mp4", "gif"], "default": "mp4"},
            },
            "example": {"code": "print('hello')", "effect": "typewriter"},
        },
        "annotate": {
            "type": "object",
            "required": ["code"],
            "properties": {
                "code": {"type": "string"},
                "language": {"type": "string", "default": "plaintext"},
                "theme": {"type": "string", "default": "dracula"},
                "focus": {"type": "string", "enum": ["general", "error-handling", "performance", "security", "patterns"], "default": "general"},
            },
            "example": {"code": "def foo(): pass", "focus": "general"},
        },
    }
    schema = schemas.get(endpoint, schemas["screenshot"])
    
    return PaymentRequiredV1(
        accepts=[{
            "scheme": "exact",
            "network": "evm",
            "payTo": EVM_PAYEE_ADDRESS,
            "asset": "USDC",
            "resource": resource,
            "maxAmountRequired": price,
            "maxTimeoutSeconds": MAX_PROOF_AGE,
            "description": f"CodeShot — {endpoint}",
            "networkPayload": {
                "token": BASE_USDC,
                "chainId": CHAIN_ID,
            },
            "extra": {
                "bazaar": {
                    "info": {
                        "inputSchema": schema,
                    }
                }
            },
        }]
    )


def build_openapi_payment_info(path: str) -> dict:
    """Build x402 payment metadata for OpenAPI spec — matches x402scan discovery spec."""
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
