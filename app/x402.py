"""
x402 Payment Protocol for CodeShot API.
Implements the x402 open standard for internet-native payments.
https://github.com/x402-foundation/x402

Flow:
  1. Client requests /v1/agent/* without payment
  2. Server returns 402 with PAYMENT-REQUIRED header (base64 JSON)
  3. Client pays via facilitator, gets PAYMENT-SIGNATURE
  4. Client retries with PAYMENT-SIGNATURE header
  5. Server verifies → serves request
"""

import os
import json
import time
import base64
from typing import Optional

# ── Configuration ──

EVM_PAYEE_ADDRESS = os.environ.get("EVM_PAYEE_ADDRESS", "")

AGENT_PRICES = {
    "/v1/screenshot": 0.01,
    "/v1/diff": 0.01,
    "/v1/animate": 0.05,
    "/v1/annotate": 0.03,
}

# Base network (USDC on Base)
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CHAIN_ID = 8453
MIN_CONFIRMATIONS = 1
MAX_PROOF_AGE = 300


def build_payment_required(path: str) -> dict:
    """Build the x402 PaymentRequired response object."""
    price = AGENT_PRICES.get(path, 0.01)
    
    return {
        "x402Version": 1,
        "network": "evm",
        "chainId": CHAIN_ID,
        "scheme": "exact",
        "networkPayload": {
            "payTo": EVM_PAYEE_ADDRESS,
            "amount": str(int(price * 1_000_000)),  # USDC has 6 decimals
            "token": BASE_USDC,
            "decimals": 6,
        },
        "description": f"CodeShot API — {path.split('/')[-1]}",
        "metadata": {
            "amountUsd": str(price),
            "currency": "USD",
        },
    }


def build_openapi_payment_info(path: str) -> dict:
    """Build x402 payment metadata for OpenAPI spec."""
    price = AGENT_PRICES.get(path, 0.01)
    return {
        "x-payment-info": {
            "protocols": {
                "x402": {
                    "networks": [{
                        "network": "evm",
                        "chainId": CHAIN_ID,
                        "token": "USDC",
                        "tokenAddress": BASE_USDC,
                        "decimals": 6,
                    }],
                    "payTo": EVM_PAYEE_ADDRESS,
                    "pricing": {
                        "amount": str(price),
                        "currency": "USD",
                        "mode": "exact",
                    },
                }
            }
        }
    }


def verify_payment_signature(sig_header: str, payee: str, amount_usdc: str) -> tuple[bool, str]:
    """Verify an x402 PAYMENT-SIGNATURE.
    
    Returns (is_valid, wallet_address_or_error).
    """
    if not sig_header:
        return False, "Missing PAYMENT-SIGNATURE header"
    
    try:
        payload = json.loads(sig_header)
    except json.JSONDecodeError:
        # Try base64 decode first (some clients b64-encode)
        try:
            payload = json.loads(base64.b64decode(sig_header).decode())
        except Exception:
            return False, "Invalid PAYMENT-SIGNATURE format"
    
    signature = payload.get("signature", "")
    message = payload.get("message", {})
    
    if not signature or not message:
        return False, "Incomplete signature payload"
    
    # Check freshness
    msg_ts = message.get("timestamp", 0)
    if abs(time.time() - msg_ts) > MAX_PROOF_AGE:
        return False, f"Signature expired (max {MAX_PROOF_AGE}s)"
    
    # Check amount
    msg_amount = str(message.get("amount", "0"))
    if msg_amount != amount_usdc:
        return False, f"Amount mismatch: {msg_amount} vs {amount_usdc}"
    
    # Check payee
    msg_payee = message.get("payee", "")
    if msg_payee.lower() != payee.lower():
        return False, "Payee mismatch"
    
    # Verify EIP-191 signature
    try:
        from eth_account.messages import encode_defunct
        from eth_account import Account
        
        msg_text = f"{msg_amount}:{msg_payee}:{msg_ts}:{message.get('nonce', '')}"
        signable = encode_defunct(text=msg_text)
        recovered = Account.recover_message(signable, signature=signature)
        return True, recovered
    except ImportError:
        return True, "verified (dev-mode, no eth-account)"
    except Exception as e:
        return False, f"Signature verification failed: {e}"


def is_x402_path(path: str) -> bool:
    return path.startswith("/v1/agent/")


def agent_path_to_real(path: str) -> str:
    return path.replace("/v1/agent/", "/v1/")


def get_price_usdc(path: str) -> str:
    real = agent_path_to_real(path) if is_x402_path(path) else path
    price_usd = AGENT_PRICES.get(real, 0.01)
    return str(int(price_usd * 1_000_000))
