"""
API key management and rate limiting middleware.
"""

import time
import uuid
import hashlib
import asyncio
import json
from pathlib import Path
from typing import Optional
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"
KEYS_PATH = DATA_DIR / "api_keys.json"
USAGE_PATH = DATA_DIR / "usage.json"


# ── API Key Store ──

class APIKeyStore:
    """Simple API key storage with JSON persistence."""
    
    def __init__(self):
        self._keys: dict[str, dict] = {}  # key_hash -> {name, plan, created, ...}
        self._lock = asyncio.Lock()
        self._load()
    
    def _load(self):
        KEYS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if KEYS_PATH.exists():
            with open(KEYS_PATH) as f:
                self._keys = json.load(f)
    
    def _save(self):
        with open(KEYS_PATH, 'w') as f:
            json.dump(self._keys, f, indent=2)
    
    def _hash(self, key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()
    
    async def create(self, name: str, plan: str = "free") -> str:
        """Create a new API key. Returns the plaintext key (shown once)."""
        raw_key = f"cs_{uuid.uuid4().hex[:24]}"
        key_hash = self._hash(raw_key)
        
        async with self._lock:
            self._keys[key_hash] = {
                "name": name,
                "plan": plan,
                "created": time.time(),
                "enabled": True,
            }
            self._save()
        
        return raw_key
    
    async def validate(self, key: str) -> Optional[dict]:
        """Validate an API key. Returns key info dict or None."""
        key_hash = self._hash(key)
        info = self._keys.get(key_hash)
        if info and info.get("enabled", True):
            return info
        return None
    
    async def list_keys(self) -> list[dict]:
        """List all keys (without the secret)."""
        return [
            {"name": v["name"], "plan": v["plan"], "created": v["created"], "enabled": v.get("enabled", True)}
            for v in self._keys.values()
        ]
    
    async def disable(self, name: str) -> bool:
        async with self._lock:
            for k, v in self._keys.items():
                if v["name"] == name:
                    v["enabled"] = False
                    self._save()
                    return True
        return False


# ── Rate Limiter ──

PLAN_LIMITS = {
    "free": {"requests_per_hour": 50, "requests_per_day": 200},
    "pro": {"requests_per_hour": 1000, "requests_per_day": 10000},
    "team": {"requests_per_hour": 5000, "requests_per_day": 50000},
    "business": {"requests_per_hour": 20000, "requests_per_day": 200000},
    "unlimited": {"requests_per_hour": 100000, "requests_per_day": 1000000},
}


class RateLimiter:
    """In-memory sliding window rate limiter."""
    
    def __init__(self):
        self._hourly: dict[str, list[float]] = defaultdict(list)
        self._daily: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def check(self, key: str, plan: str = "free") -> tuple[bool, dict]:
        """Check if a request is allowed. Returns (allowed, headers)."""
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
        now = time.time()
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        
        async with self._lock:
            # Clean old timestamps
            hour_ago = now - 3600
            day_ago = now - 86400
            
            self._hourly[key_hash] = [t for t in self._hourly[key_hash] if t > hour_ago]
            self._daily[key_hash] = [t for t in self._daily[key_hash] if t > day_ago]
            
            hourly_count = len(self._hourly[key_hash])
            daily_count = len(self._daily[key_hash])
            
            hourly_limit = limits["requests_per_hour"]
            daily_limit = limits["requests_per_day"]
            
            if hourly_count >= hourly_limit or daily_count >= daily_limit:
                return False, {
                    "X-RateLimit-Limit-Hourly": str(hourly_limit),
                    "X-RateLimit-Limit-Daily": str(daily_limit),
                    "X-RateLimit-Remaining-Hourly": "0",
                    "X-RateLimit-Remaining-Daily": "0",
                    "X-RateLimit-Reset": str(int(now + 3600)),
                }
            
            # Record this request
            self._hourly[key_hash].append(now)
            self._daily[key_hash].append(now)
            
            return True, {
                "X-RateLimit-Limit-Hourly": str(hourly_limit),
                "X-RateLimit-Limit-Daily": str(daily_limit),
                "X-RateLimit-Remaining-Hourly": str(hourly_limit - hourly_count - 1),
                "X-RateLimit-Remaining-Daily": str(daily_limit - daily_count - 1),
            }


# ── Middleware ──

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json", "/v1/preview", "/v1/themes", "/v1/presets", "/v1/languages", "/v1/effects", "/v1/admin/keys", "/v1/admin/keys"}

key_store = APIKeyStore()
rate_limiter = RateLimiter()


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces API key auth + rate limiting on protected endpoints."""
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Skip auth for public paths and static files
        if path in PUBLIC_PATHS or path.startswith("/static") or path.startswith("/v1/admin") or path.startswith("/v1/billing"):
            return await call_next(request)
        
        # Check API key
        auth_header = request.headers.get("Authorization", "")
        api_key = None
        
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
        elif "x-api-key" in request.headers:
            api_key = request.headers["x-api-key"]
        
        if not api_key:
            return JSONResponse(
                {"detail": "API key required. Get one at https://codeshot.io"},
                status_code=401
            )
        
        key_info = await key_store.validate(api_key)
        if not key_info:
            return JSONResponse(
                {"detail": "Invalid or disabled API key"},
                status_code=403
            )
        
        # Rate limit check
        plan = key_info.get("plan", "free")
        allowed, headers = await rate_limiter.check(api_key, plan)
        
        if not allowed:
            return JSONResponse(
                {"detail": "Rate limit exceeded. Upgrade at https://codeshot.io/pricing"},
                status_code=429,
                headers=headers
            )
        
        # Proceed
        response = await call_next(request)
        
        # Add rate limit headers
        for k, v in headers.items():
            response.headers[k] = v
        
        response.headers["X-Plan"] = plan
        return response


async def create_default_key():
    """Create a default free key for testing if none exist."""
    keys = await key_store.list_keys()
    if not keys:
        raw = await key_store.create("default", "free")
        print(f"\n  DEFAULT API KEY: {raw}\n  Save this — it won't be shown again.\n")
        return raw
    return None
