"""
x402 Agent Routes — using the official x402 Python SDK middleware.
This wraps our existing API endpoints with x402 payment handling.
"""
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from x402.server import x402ResourceServer
from x402.http import FacilitatorConfig, HTTPFacilitatorClient
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import PaymentOption, RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme

DOMAIN = os.environ.get("DOMAIN", "https://drmadmeow.up.railway.app")
PAY_TO = os.environ.get("EVM_PAYEE_ADDRESS", "0xed6881b56690C26189d914F2302C9af79685CB97")
NETWORK = "eip155:8453"  # Base mainnet

# Facilitator (Coinbase Developer Platform reference)
facilitator_url = os.environ.get("X402_FACILITATOR_URL", "https://x402.org/facilitator")
facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=facilitator_url))

# Create x402 server
server = x402ResourceServer(facilitator)
server.register(NETWORK, ExactEvmServerScheme())

# Define paid agent routes
ROUTES = {
    "POST /v1/agent/screenshot": RouteConfig(
        accepts=[PaymentOption(
            scheme="exact", price="0.01", network=NETWORK, pay_to=PAY_TO
        )],
        description="Generate a code screenshot as PNG",
    ),
    "POST /v1/agent/diff": RouteConfig(
        accepts=[PaymentOption(
            scheme="exact", price="0.01", network=NETWORK, pay_to=PAY_TO
        )],
        description="Generate a code diff as PNG",
    ),
    "POST /v1/agent/animate": RouteConfig(
        accepts=[PaymentOption(
            scheme="exact", price="0.05", network=NETWORK, pay_to=PAY_TO
        )],
        description="Generate an animated code screenshot",
    ),
    "POST /v1/agent/annotate": RouteConfig(
        accepts=[PaymentOption(
            scheme="exact", price="0.03", network=NETWORK, pay_to=PAY_TO
        )],
        description="Generate AI-annotated code screenshot",
    ),
}


def create_x402_app(main_app: FastAPI) -> FastAPI:
    """Create a proxy app that wraps the main app with x402 middleware."""
    proxy = FastAPI(title="CodeShot x402 Gateway")
    
    # Add x402 middleware first (runs before our routes)
    proxy.add_middleware(
        PaymentMiddlewareASGI,
        routes=ROUTES,
        server=server,
    )
    
    # Forward paid requests to the real backend
    import httpx
    from starlette.responses import Response as StarletteResponse
    
    @proxy.api_route("/v1/agent/{path:path}", methods=["POST"])
    async def proxy_agent(request: Request, path: str):
        """Forward x402-paid requests to the real API."""
        # When this runs, payment has been verified by the middleware
        real_path = f"/v1/{path}"
        body = await request.body()
        
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method="POST",
                url=f"http://127.0.0.1:8001{real_path}",
                content=body,
                headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
                timeout=30,
            )
            return StarletteResponse(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
                media_type=resp.headers.get("Content-Type", "application/octet-stream"),
            )
    
    return proxy
