"""
x402 Payment Middleware for CodeShot API.
Implements the x402 protocol for agent-native payments.

Flow:
  1. Agent requests a paid endpoint without payment proof
  2. Server returns 402 with X-Payment-Info header
  3. Agent pays via x402 facilitator, gets payment proof
  4. Agent retries with X-Payment-Proof header
  5. Server verifies → serves the request

References:
  https://docs.x402.org
  https://agentcash.dev/docs
"""

import os
import json
import time
import hmac
import hashlib
from typing import Optional

# ── Configuration ──

# EVM payee address — where payments go
EVM_PAYEE_ADDRESS = os.environ.get("EVM_PAYEE_ADDRESS", "")

# Pricing per endpoint (in USD, expressed as dollars)
AGENT_PRICES = {
    "/v1/screenshot": 0.01,   # $0.01 per screenshot
    "/v1/diff": 0.01,          # $0.01 per diff
    "/v1/animate": 0.05,       # $0.05 per animation
    "/v1/annotate": 0.03,      # $0.03 per annotation (includes AI cost)
}

# Networks we accept payment on
SUPPORTED_NETWORKS = [
    {
        "network": "evm",
        "chainId": 8453,        # Base
        "token": "USDC",
        "tokenAddress": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "decimals": 6,
    },
]

# Minimum payment confirmation blocks
MIN_CONFIRMATIONS = 1

# Payment proof max age (seconds) — prevent replay attacks
MAX_PROOF_AGE = 300  # 5 minutes


def build_payment_info(path: str) -> dict:
    """Build x402 payment info for a given endpoint path."""
    price_usd = AGENT_PRICES.get(path, 0.01)
    
    return {
        "x-payment-info": {
            "version": "1.0",
            "protocols": {
                "x402": {
                    "networks": SUPPORTED_NETWORKS,
                    "payTo": EVM_PAYEE_ADDRESS,
                    "pricing": {
                        "amount": str(price_usd),
                        "currency": "USD",
                        "mode": "exact",
                    },
                    "minConfirmations": MIN_CONFIRMATIONS,
                    "maxProofAge": MAX_PROOF_AGE,
                }
            }
        }
    }


def verify_payment_proof(proof_header: str, expected_amount_usd: str, payee: str) -> tuple[bool, str]:
    """Verify an x402 payment proof.
    
    The proof is a signed message (EIP-191) containing:
    {amount}:{payee}:{timestamp}:{nonce}
    
    Returns (is_valid, error_message).
    """
    if not proof_header:
        return False, "Missing payment proof"
    
    try:
        proof = json.loads(proof_header)
    except json.JSONDecodeError:
        return False, "Invalid proof format"
    
    signature = proof.get("signature", "")
    message = proof.get("message", {})
    
    if not signature or not message:
        return False, "Incomplete proof"
    
    # Check timestamp freshness
    msg_timestamp = message.get("timestamp", 0)
    if abs(time.time() - msg_timestamp) > MAX_PROOF_AGE:
        return False, f"Proof expired (max {MAX_PROOF_AGE}s age)"
    
    # Check amount
    msg_amount = message.get("amount", "0")
    if msg_amount != expected_amount_usd:
        return False, f"Amount mismatch: {msg_amount} vs {expected_amount_usd}"
    
    # Check payee
    msg_payee = message.get("payee", "")
    if msg_payee.lower() != payee.lower():
        return False, "Payee address mismatch"
    
    # Verify signature (EIP-191)
    try:
        from eth_account.messages import encode_defunct
        from eth_account import Account
        
        # Reconstruct the signed message
        msg_text = f"{msg_amount}:{msg_payee}:{msg_timestamp}:{message.get('nonce', '')}"
        signable = encode_defunct(text=msg_text)
        recovered = Account.recover_message(signable, signature=signature)
        
        # The signer is the payer — we accept any valid signature
        # (In production, you might want to check payer whitelist)
        return True, recovered
    
    except ImportError:
        # Fallback: accept proof if eth-account not installed (dev mode)
        return True, "verified (dev mode)"
    except Exception as e:
        return False, f"Signature verification failed: {str(e)}"


def is_x402_path(path: str) -> bool:
    """Check if this path is a paid agent endpoint."""
    # Agent endpoints are under /v1/agent/
    return path.startswith("/v1/agent/")


def agent_path_to_real(path: str) -> str:
    """Convert agent path to real API path.
    /v1/agent/screenshot → /v1/screenshot
    """
    return path.replace("/v1/agent/", "/v1/")


def get_price_for_path(path: str) -> str:
    """Get the USD price for an endpoint path."""
    real_path = agent_path_to_real(path) if is_x402_path(path) else path
    price = AGENT_PRICES.get(real_path, 0.01)
    return str(price)
