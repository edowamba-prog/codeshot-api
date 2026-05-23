"""
CodeShot API — Beautiful code screenshots via REST API.
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Literal
import time
import os
import json

from .themes import THEMES, SOCIAL_PRESETS, LANGUAGES
from .renderer import build_html
from .screenshot import render_screenshot, shutdown
from .brands import brand_store
from .routers import brands as brands_router
from .diff import build_diff_html, compute_diff, count_changes
from .animate import build_animated_html, render_animation, ANIMATION_EFFECTS
from .annotate import analyze_code, build_annotated_html
from .auth import APIKeyMiddleware, key_store, rate_limiter, create_default_key
from .webtools import capture_url_screenshot, scrape_url_text, get_link_preview
from .billing import create_checkout_session, handle_webhook, get_key_for_session
from .users import (
    create_user, authenticate, get_user, get_user_by_email, list_users,
    create_token, verify_token, create_user_api_key, get_user_api_keys,
    get_user_usage, get_admin_stats, log_usage, UserCreate, UserLogin,
    update_user_plan, get_user_usage_history, ensure_user_api_key,
)
from . import admin_api
from .x402 import (
    is_x402_path, agent_path_to_real, build_payment_required,
    get_price, get_price_usdc, verify_payment_signature, EVM_PAYEE_ADDRESS,
    build_openapi_payment_info,
)

app = FastAPI(
    title="CodeShot API",
    description="Generate beautiful code screenshots programmatically. 10 themes, social presets, brand kits, and more.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,       # disable redoc (relies on openapi.json)
    openapi_url="/openapi.json",  # point swagger to our custom x402 spec
)

# CORS — allow x402scan frontend to probe our endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["PAYMENT-REQUIRED", "PAYMENT-SIGNATURE", "SIGN-IN-WITH-X"],
)

# Override FastAPI's auto-generated OpenAPI with x402 agent spec
def custom_openapi():
    """Return x402 agent discovery spec instead of FastAPI auto-gen."""
    domain = os.environ.get("DOMAIN", "https://drmadmeow.up.railway.app")
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "CodeShot API",
            "description": "Beautiful code screenshots and web tools via API. Pay-per-use for AI agents via x402 and MPP.",
            "version": "1.0.0",
            "x-guidance": "Use POST /v1/agent/screenshot for code screenshots, POST /v1/agent/webshot for URL screenshots, POST /v1/agent/scrape for web scraping, POST /v1/agent/preview for link previews. All endpoints require payment via x402 or MPP. Send PAYMENT-SIGNATURE header.",
        },
        "x-discovery": {
            "ownershipProofs": []
        },
        "servers": [{"url": domain}],
        "paths": {
            "/v1/agent/screenshot": {
                "post": {
                    "summary": "Code screenshot — $0.01",
                    "description": "Render code as a beautiful PNG screenshot. Pay-per-use via x402.",
                    "operationId": "createScreenshot",
                    "security": [],
                    
                    "x-payment-info": build_openapi_payment_info("/v1/agent/screenshot")["x-payment-info"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["code"],
                                    "properties": {
                                        "code": {"type": "string", "description": "Source code to render"},
                                        "language": {"type": "string", "default": "plaintext"},
                                        "theme": {"type": "string", "default": "dracula"},
                                        "preset": {"type": "string", "description": "Social media preset"},
                                        "watermark": {"type": "string"},
                                        "format": {"type": "string", "enum": ["png", "html"], "default": "png"},
                                    },
                                },
                                "example": {"code": "def hello():\n    print('World')", "language": "python", "theme": "dracula"},
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Rendered code screenshot as PNG image", "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}},
                        "402": {"description": "Payment required — send X-Payment-Proof header with signed proof"},
                    },
                }
            },
            "/v1/agent/diff": {
                "post": {
                    "summary": "Code diff — $0.01",
                    "description": "Render code diff as PNG. Pay-per-use via x402.",
                    "operationId": "createDiff",
                    "security": [],
                    
                    "x-payment-info": build_openapi_payment_info("/v1/agent/diff")["x-payment-info"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["old_code", "new_code"],
                                    "properties": {
                                        "old_code": {"type": "string", "description": "Original code"},
                                        "new_code": {"type": "string", "description": "Updated code"},
                                        "language": {"type": "string", "default": "plaintext"},
                                        "theme": {"type": "string", "default": "dracula"},
                                        "mode": {"type": "string", "enum": ["unified", "side-by-side"], "default": "unified"},
                                    },
                                },
                                "example": {"old_code": "x = 1", "new_code": "x = 2", "language": "python", "theme": "dracula"},
                            }
                        },
                    },
                    "responses": {"200": {"description": "Rendered code diff as PNG image", "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}, "402": {"description": "Payment required"}},
                }
            },
            "/v1/agent/animate": {
                "post": {
                    "summary": "Animated code — $0.05",
                    "description": "Render animated code as MP4/GIF. Pay-per-use via x402.",
                    "operationId": "createAnimation",
                    "security": [],
                    
                    "x-payment-info": build_openapi_payment_info("/v1/agent/animate")["x-payment-info"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["code"],
                                    "properties": {
                                        "code": {"type": "string", "description": "Source code"},
                                        "language": {"type": "string", "default": "plaintext"},
                                        "theme": {"type": "string", "default": "dracula"},
                                        "effect": {"type": "string", "enum": ["typewriter", "reveal-line", "fade-in"], "default": "typewriter"},
                                        "duration": {"type": "number", "default": 4.0},
                                        "format": {"type": "string", "enum": ["mp4", "gif"], "default": "mp4"},
                                    },
                                },
                                "example": {"code": "print('hello')", "language": "python", "effect": "typewriter", "duration": 2.0},
                            }
                        },
                    },
                    "responses": {"200": {"description": "Animated code as MP4 video or GIF", "content": {"video/mp4": {"schema": {"type": "string", "format": "binary"}}}}, "402": {"description": "Payment required"}},
                }
            },
            "/v1/agent/annotate": {
                "post": {
                    "summary": "AI-annotated code — $0.03",
                    "description": "AI analyzes and annotates code. Pay-per-use via x402.",
                    "operationId": "createAnnotation",
                    "security": [],
                    
                    "x-payment-info": build_openapi_payment_info("/v1/agent/annotate")["x-payment-info"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["code"],
                                    "properties": {
                                        "code": {"type": "string", "description": "Source code to annotate"},
                                        "language": {"type": "string", "default": "plaintext"},
                                        "theme": {"type": "string", "default": "dracula"},
                                        "focus": {"type": "string", "enum": ["general", "error-handling", "performance", "security", "patterns"], "default": "general"},
                                    },
                                },
                                "example": {"code": "def foo():\\n    pass", "language": "python", "focus": "general"},
                            }
                        },
                    },
                    "responses": {"200": {"description": "Rendered code diff as PNG image", "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}, "402": {"description": "Payment required"}},
                }
            },
            "/v1/agent/health": {
                "get": {
                    "summary": "API health check (free)",
                    "description": "Free SIWX-authenticated health check. No payment required.",
                    "operationId": "agentHealth",
                    "security": [{"siwx": []}],
                    "responses": {"200": {"description": "Service status"}},
                }
            },
            "/v1/agent/webshot": {
                "post": {
                    "summary": "Web screenshot — $0.01",
                    "description": "Take a screenshot of any URL. Pay-per-use via x402.",
                    "operationId": "createWebshot",
                    "security": [],
                    "x-payment-info": build_openapi_payment_info("/v1/agent/webshot")["x-payment-info"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["url"],
                                    "properties": {
                                        "url": {"type": "string", "description": "URL to screenshot"},
                                        "width": {"type": "integer", "default": 1280},
                                        "height": {"type": "integer", "default": 800},
                                        "full_page": {"type": "boolean", "default": True},
                                    },
                                },
                                "example": {"url": "https://example.com", "width": 1280, "full_page": True},
                            }
                        },
                    },
                    "responses": {"200": {"description": "PNG screenshot", "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}, "402": {"description": "Payment required"}},
                }
            },
            "/v1/agent/scrape": {
                "post": {
                    "summary": "Web scrape — $0.01",
                    "description": "Scrape clean text/markdown from any URL. Pay-per-use via x402.",
                    "operationId": "createScrape",
                    "security": [],
                    "x-payment-info": build_openapi_payment_info("/v1/agent/scrape")["x-payment-info"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["url"],
                                    "properties": {
                                        "url": {"type": "string", "description": "URL to scrape"},
                                        "format": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
                                    },
                                },
                                "example": {"url": "https://example.com", "format": "markdown"},
                            }
                        },
                    },
                    "responses": {"200": {"description": "Scraped content as JSON with title, text, links, metadata"}, "402": {"description": "Payment required"}},
                }
            },
            "/v1/agent/preview": {
                "post": {
                    "summary": "Link preview — $0.005",
                    "description": "Get Open Graph / Twitter Card metadata for any URL. Pay-per-use via x402.",
                    "operationId": "createPreview",
                    "security": [],
                    "x-payment-info": build_openapi_payment_info("/v1/agent/preview")["x-payment-info"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["url"],
                                    "properties": {
                                        "url": {"type": "string", "description": "URL to preview"},
                                    },
                                },
                                "example": {"url": "https://example.com"},
                            }
                        },
                    },
                    "responses": {"200": {"description": "Link preview metadata as JSON"}, "402": {"description": "Payment required"}},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "siwx": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Sign-In-With-X wallet authentication"
                }
            }
        },
    }

app.openapi = custom_openapi

# Free SIWX endpoint — wallet-verified, no payment
@app.get("/v1/agent/health")
async def agent_health():
    return {"status": "ok", "service": "codeshot-api", "auth": "siwx"}

# ── x402 Well-Known (compatibility discovery) ──

@app.get("/.well-known/x402")
async def x402_well_known():
    """x402scan compatibility discovery — lists payable resources."""
    domain = os.environ.get("DOMAIN", "https://drmadmeow.up.railway.app")
    return {
        "version": 1,
        "resources": [
            f"{domain}/v1/agent/screenshot",
            f"{domain}/v1/agent/diff",
            f"{domain}/v1/agent/animate",
            f"{domain}/v1/agent/annotate",
            f"{domain}/v1/agent/webshot",
            f"{domain}/v1/agent/scrape",
            f"{domain}/v1/agent/preview",
        ],
    }


# Add auth middleware
app.add_middleware(APIKeyMiddleware)

# Add x402 payment middleware for agent endpoints
from starlette.middleware.base import BaseHTTPMiddleware as _BaseMW
class X402Middleware(_BaseMW):
    """Middleware that enforces x402 payment on /v1/agent/* paths."""
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        if is_x402_path(path):
            proof = request.headers.get("PAYMENT-SIGNATURE", "")
            price_usd = get_price(path)
            price_usdc = get_price_usdc(path)
            
            if not proof:
                pr = build_payment_required(path)
                return JSONResponse(
                    pr,
                    status_code=402,
                    headers={"PAYMENT-REQUIRED": "1"},
                )
            
            # Verify payment signature (uses USDC integer amount)
            valid, result = verify_payment_signature(proof, EVM_PAYEE_ADDRESS, price_usdc)
            if not valid:
                return JSONResponse(
                    {"detail": f"Payment verification failed: {result}"},
                    status_code=402,
                )
            
            # Rewrite path to real endpoint and mark as internally paid
            real_path = agent_path_to_real(path)
            request.scope["path"] = real_path
            request.scope["raw_path"] = real_path.encode()
            request.state.x402_paid = result  # wallet address
            request.state.x402_path = path
        
        return await call_next(request)

app.add_middleware(X402Middleware)

# Include routers
app.include_router(brands_router.router)

# ── Models ──

class BrandKit(BaseModel):
    """Custom branding for code screenshots."""
    name: str = Field(..., description="Brand kit name for reference")
    background: Optional[str] = Field(None, description="Background color (hex, rgba, hsl)")
    text: Optional[str] = Field(None, description="Text color")
    accent: Optional[str] = Field(None, description="Accent color for badges and highlights")
    font_family: Optional[str] = Field(None, description="CSS font-family string")
    font_size: Optional[str] = Field(None, description="CSS font-size (e.g., '14px')")
    padding: Optional[str] = Field(None, description="CSS padding around the code window")
    border_radius: Optional[str] = Field(None, description="Window border radius")
    line_highlight: Optional[str] = Field(None, description="Line highlight color")
    watermark_color: Optional[str] = Field(None, description="Watermark text color")
    logo_url: Optional[str] = Field(None, description="URL to brand logo (future)")
    watermark: Optional[str] = Field(None, description="Watermark text (e.g., '@yourbrand')")


class ScreenshotRequest(BaseModel):
    """Request to generate a code screenshot."""
    code: str = Field(..., description="Source code to render", min_length=1, max_length=50000)
    language: str = Field("plaintext", description="Programming language for syntax highlighting")
    theme: str = Field("dracula", description="Theme name")
    width: Optional[int] = Field(None, description="Output width in pixels", ge=200, le=3840)
    height: Optional[int] = Field(None, description="Output height in pixels", ge=100, le=3840)
    preset: Optional[str] = Field(None, description="Social media preset (twitter-post, linkedin, etc.)")
    brand_name: Optional[str] = Field(None, description="Saved brand kit name to apply")
    brand: Optional[BrandKit] = Field(None, description="Inline custom brand kit (overrides brand_name)")
    show_line_numbers: bool = Field(True, description="Show line numbers in gutter")
    show_window_controls: bool = Field(True, description="Show macOS-style window controls")
    show_language_badge: bool = Field(True, description="Show language badge")
    title: Optional[str] = Field(None, description="Window title text")
    watermark: Optional[str] = Field(None, description="Watermark text (e.g., '@username')")
    device_scale_factor: float = Field(2.0, description="Pixel density (1.0 = 1x, 2.0 = retina)", ge=1.0, le=4.0)
    format: Literal["png", "html"] = Field("png", description="Output format")


class ScreenshotResponse(BaseModel):
    """Metadata about a generated screenshot."""
    width: int
    height: int
    theme: str
    language: str
    preset: Optional[str]
    render_time_ms: float


class DiffRequest(BaseModel):
    """Request to generate a code diff screenshot."""
    old_code: str = Field(..., description="Original code (before changes)", min_length=1, max_length=50000)
    new_code: str = Field(..., description="Updated code (after changes)", min_length=1, max_length=50000)
    language: str = Field("plaintext", description="Programming language")
    theme: str = Field("dracula", description="Theme name")
    mode: Literal["unified", "side-by-side"] = Field("unified", description="Diff display mode")
    title: Optional[str] = Field(None, description="Window title")
    watermark: Optional[str] = Field(None, description="Watermark text")
    device_scale_factor: float = Field(2.0, ge=1.0, le=4.0)
    format: Literal["png", "html"] = Field("png")


class AnimateRequest(BaseModel):
    """Request to generate an animated code screenshot."""
    code: str = Field(..., min_length=1, max_length=5000)
    language: str = Field("plaintext")
    theme: str = Field("dracula")
    effect: Literal["typewriter", "reveal-line", "fade-in"] = Field("typewriter")
    duration: float = Field(4.0, ge=1.0, le=30.0, description="Animation duration in seconds")
    fps: int = Field(24, ge=12, le=60, description="Frames per second")
    format: Literal["mp4", "gif"] = Field("mp4", description="Output format")
    title: Optional[str] = Field(None)
    watermark: Optional[str] = Field(None)
    cursor: bool = Field(True, description="Show blinking cursor (typewriter mode)")
    device_scale_factor: float = Field(2.0, ge=1.0, le=4.0)


class AnnotateRequest(BaseModel):
    """Request to generate an AI-annotated code screenshot."""
    code: str = Field(..., min_length=1, max_length=10000)
    language: str = Field("plaintext")
    theme: str = Field("dracula")
    focus: str = Field("general", description="What to focus annotations on: general, error-handling, performance, security, patterns")
    title: Optional[str] = Field(None)
    watermark: Optional[str] = Field(None)
    brand_name: Optional[str] = Field(None, description="Saved brand kit name")
    brand: Optional[BrandKit] = Field(None)
    device_scale_factor: float = Field(2.0, ge=1.0, le=4.0)
    format: Literal["png", "html"] = Field("png")


class WebShotRequest(BaseModel):
    """Request to take a screenshot of any URL."""
    url: str = Field(..., description="URL to screenshot", min_length=1, max_length=2000)
    width: int = Field(1280, ge=320, le=3840, description="Viewport width")
    height: int = Field(800, ge=200, le=3840, description="Viewport height")
    full_page: bool = Field(True, description="Capture full page or just viewport")
    device_scale_factor: float = Field(2.0, ge=1.0, le=4.0)


class ScrapeRequest(BaseModel):
    """Request to scrape text content from a URL."""
    url: str = Field(..., min_length=1, max_length=2000)
    format: str = Field("markdown", description="Output format: markdown or text")


class PreviewRequest(BaseModel):
    """Request to get link preview metadata."""
    url: str = Field(..., min_length=1, max_length=2000)


# ── Routes ──

@app.get("/")
async def root():
    """Landing page."""
    from fastapi.responses import FileResponse
    import os
    landing_path = os.path.join(os.path.dirname(__file__), "static", "landing.html")
    if os.path.exists(landing_path):
        return FileResponse(landing_path)
    return {
        "name": "CodeShot API",
        "version": "1.0.0",
        "docs": "/docs",
        "themes": list(THEMES.keys()),
        "presets": list(SOCIAL_PRESETS.keys()),
        "languages": list(LANGUAGES.keys()),
        "endpoints": {
            "POST /v1/screenshot": "Generate a code screenshot",
            "POST /v1/diff": "Generate a code diff screenshot",
            "POST /v1/animate": "Generate an animated code screenshot",
            "POST /v1/annotate": "Generate AI-annotated code screenshot",
            "GET /v1/themes": "List available themes",
            "GET /v1/presets": "List social media presets",
            "GET /v1/languages": "List supported languages",
            "GET /v1/effects": "List animation effects",
            "GET /v1/preview": "Interactive preview page",
            "POST /v1/brands": "Save a brand kit",
            "GET /v1/brands": "List saved brand kits",
            "POST /v1/webshot": "Take a screenshot of any URL",
            "POST /v1/scrape": "Scrape clean text/markdown from a URL",
            "POST /v1/preview": "Get Open Graph / link preview metadata",
            "POST /v1/feedback": "Submit feedback or complaint",
        }
    }


@app.get("/v1/themes")
async def list_themes():
    """List all available themes with their color values."""
    return {
        "themes": {
            name: {
                "name": t["name"],
                "background": t["background"],
                "text": t["text"],
                "accent": t["accent"],
                "preview_url": f"/v1/preview?theme={name}&code=console.log('Hello+World')&language=javascript",
            }
            for name, t in THEMES.items()
        }
    }


@app.get("/v1/presets")
async def list_presets():
    """List available social media presets with dimensions."""
    return {"presets": SOCIAL_PRESETS}


@app.get("/v1/languages")
async def list_languages():
    """List supported programming languages."""
    return {"languages": LANGUAGES}


@app.get("/v1/preview")
async def preview(
    code: str = Query("console.log('Hello, World!')", description="Code to preview"),
    language: str = Query("javascript", description="Language"),
    theme: str = Query("dracula", description="Theme"),
    preset: Optional[str] = Query(None, description="Social preset"),
    title: Optional[str] = Query(None, description="Window title"),
    watermark: Optional[str] = Query(None, description="Watermark"),
):
    """Interactive HTML preview of a code screenshot."""
    try:
        html = build_html(
            code=code,
            language=language,
            theme=theme,
            preset=preset,
            title=title,
            watermark=watermark,
        )
        return HTMLResponse(content=html)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/v1/screenshot", response_model=None)
async def create_screenshot(req: ScreenshotRequest):
    """Generate a code screenshot. Returns PNG by default, or HTML if format='html'."""
    t0 = time.time()
    
    # Validate theme
    if req.theme not in THEMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown theme '{req.theme}'. Available: {list(THEMES.keys())}"
        )
    
    # Validate preset
    if req.preset and req.preset not in SOCIAL_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown preset '{req.preset}'. Available: {list(SOCIAL_PRESETS.keys())}"
        )
    
    # Resolve dimensions
    width = req.width
    height = req.height
    if req.preset:
        p = SOCIAL_PRESETS[req.preset]
        width = width or p["width"]
        height = height or p["height"]
    width = width or 900
    height = height or 500
    
    # Build brand dict — resolve brand_name first, then inline brand overrides
    brand_dict = None
    if req.brand_name:
        saved_brand = await brand_store.get(req.brand_name)
        if saved_brand:
            brand_dict = brand_store.to_theme_dict(saved_brand)
    if req.brand:
        inline = req.brand.model_dump(exclude_none=True, exclude={"name"})
        if brand_dict:
            brand_dict = {**brand_dict, **inline}  # inline overrides saved
        else:
            brand_dict = inline
    
    try:
        html = build_html(
            code=req.code,
            language=req.language,
            theme=req.theme,
            width=width,
            height=height,
            preset=req.preset,
            brand=brand_dict,
            show_line_numbers=req.show_line_numbers,
            show_window_controls=req.show_window_controls,
            show_language_badge=req.show_language_badge,
            title=req.title,
            watermark=req.watermark,
        )
        
        if req.format == "html":
            render_time = (time.time() - t0) * 1000
            return HTMLResponse(content=html, headers={"X-Render-Time-Ms": str(render_time)})
        
        # Render to PNG
        png_bytes = await render_screenshot(
            html=html,
            width=width,
            height=height,
            device_scale_factor=req.device_scale_factor,
        )
        
        render_time = (time.time() - t0) * 1000
        
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "X-Render-Time-Ms": f"{render_time:.1f}",
                "X-Theme": req.theme,
                "X-Preset": req.preset or "custom",
                "X-Dimensions": f"{width}x{height}",
                "Cache-Control": "public, max-age=3600",
            }
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {str(e)}")


@app.post("/v1/diff")
async def create_diff(req: DiffRequest):
    """Generate a code diff screenshot. Beautiful side-by-side or unified diff view."""
    t0 = time.time()
    
    if req.theme not in THEMES:
        raise HTTPException(400, f"Unknown theme '{req.theme}'")
    
    try:
        html = build_diff_html(
            old_code=req.old_code,
            new_code=req.new_code,
            language=req.language,
            theme=req.theme,
            title=req.title,
            watermark=req.watermark,
            mode=req.mode,
        )
        
        if req.format == "html":
            return HTMLResponse(content=html)
        
        png_bytes = await render_screenshot(
            html=html,
            width=1000 if req.mode == "unified" else 1200,
            height=600,
            device_scale_factor=req.device_scale_factor,
            full_page=True,
        )
        
        changes = count_changes(req.old_code, req.new_code)
        
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "X-Render-Time-Ms": f"{(time.time() - t0) * 1000:.1f}",
                "X-Additions": str(changes["added"]),
                "X-Deletions": str(changes["removed"]),
                "X-Diff-Mode": req.mode,
            }
        )
    except Exception as e:
        raise HTTPException(500, f"Diff render failed: {str(e)}")


@app.post("/v1/animate")
async def create_animation(req: AnimateRequest):
    """Generate an animated code screenshot — typewriter, reveal, or fade-in effect.
    
    Returns MP4 (default) or GIF. Render time depends on duration and fps.
    A 4-second animation at 24fps takes ~5-10 seconds to render.
    """
    t0 = time.time()
    
    if req.theme not in THEMES:
        raise HTTPException(400, f"Unknown theme '{req.theme}'")
    
    try:
        html = build_animated_html(
            code=req.code,
            language=req.language,
            theme=req.theme,
            effect=req.effect,
            title=req.title,
            watermark=req.watermark,
            duration=req.duration,
            cursor=req.cursor,
        )
        
        video_bytes = await render_animation(
            html=html,
            width=900,
            height=500,
            duration=req.duration,
            fps=req.fps,
            format=req.format,
            device_scale_factor=req.device_scale_factor,
        )
        
        media_type = "video/mp4" if req.format == "mp4" else "image/gif"
        
        return Response(
            content=video_bytes,
            media_type=media_type,
            headers={
                "X-Render-Time-Ms": f"{(time.time() - t0) * 1000:.1f}",
                "X-Effect": req.effect,
                "X-Duration": str(req.duration),
                "X-FPS": str(req.fps),
            }
        )
    except Exception as e:
        raise HTTPException(500, f"Animation render failed: {str(e)}")


@app.get("/v1/effects")
async def list_effects():
    """List available animation effects."""
    return {"effects": ANIMATION_EFFECTS}


@app.post("/v1/annotate")
async def create_annotation(req: AnnotateRequest):
    """Generate a code screenshot with AI-powered explanatory annotations.
    
    DeepSeek analyzes the code and adds callout bubbles explaining key lines.
    Returns PNG with numbered annotations overlaid on the code.
    """
    t0 = time.time()
    
    if req.theme not in THEMES:
        raise HTTPException(400, f"Unknown theme '{req.theme}'")
    
    # Run AI analysis
    analysis = await analyze_code(
        code=req.code,
        language=req.language,
        focus=req.focus,
    )
    
    # Build brand dict
    brand_dict = None
    if req.brand_name:
        saved = await brand_store.get(req.brand_name)
        if saved:
            brand_dict = brand_store.to_theme_dict(saved)
    if req.brand:
        inline = req.brand.model_dump(exclude_none=True, exclude={"name"})
        brand_dict = {**(brand_dict or {}), **inline} if brand_dict else inline
    
    try:
        html = build_annotated_html(
            code=req.code,
            language=req.language,
            annotations=analysis.get("annotations", []),
            theme=req.theme,
            title=req.title,
            watermark=req.watermark,
            brand=brand_dict,
        )
        
        if req.format == "html":
            return HTMLResponse(content=html)
        
        png_bytes = await render_screenshot(
            html=html,
            width=1200 if analysis.get("annotations") else 900,
            height=600,
            device_scale_factor=req.device_scale_factor,
            full_page=True,
        )
        
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "X-Render-Time-Ms": f"{(time.time() - t0) * 1000:.1f}",
                "X-Annotation-Count": str(len(analysis.get("annotations", []))),
                "X-Focus": req.focus,
                "X-Summary": analysis.get("summary", "")[:200],
            }
        )
    except Exception as e:
        raise HTTPException(500, f"Annotation render failed: {str(e)}")


# ── Web Tools Routes ──

@app.post("/v1/webshot")
async def create_webshot(req: WebShotRequest):
    """Take a screenshot of any URL. Returns PNG image."""
    t0 = time.time()
    
    try:
        png_bytes = await capture_url_screenshot(
            url=req.url,
            width=req.width,
            height=req.height,
            full_page=req.full_page,
            device_scale_factor=req.device_scale_factor,
        )
        
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "X-Render-Time-Ms": f"{(time.time() - t0) * 1000:.1f}",
                "X-Url": req.url[:200],
                "Cache-Control": "public, max-age=300",
            }
        )
    except Exception as e:
        raise HTTPException(500, f"Webshot failed: {str(e)}")


@app.post("/v1/scrape")
async def create_scrape(req: ScrapeRequest):
    """Scrape clean text content from a URL. Returns JSON with title, text, links, metadata."""
    t0 = time.time()
    
    try:
        data = await scrape_url_text(url=req.url, format=req.format)
        data["render_time_ms"] = round((time.time() - t0) * 1000, 1)
        return data
    except Exception as e:
        raise HTTPException(500, f"Scrape failed: {str(e)}")


@app.post("/v1/preview")
async def create_preview(req: PreviewRequest):
    """Get Open Graph / Twitter Card metadata for a URL. Returns JSON."""
    t0 = time.time()
    
    try:
        metadata = await get_link_preview(url=req.url)
        metadata["render_time_ms"] = round((time.time() - t0) * 1000, 1)
        return metadata
    except Exception as e:
        raise HTTPException(500, f"Preview failed: {str(e)}")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "codeshot-api"}


# ── Billing endpoints ──

@app.post("/v1/billing/checkout")
async def billing_checkout(plan: str = "pro", request: Request = None):
    """Create a Stripe Checkout session. Requires authentication."""
    # Require auth — redirect unauthenticated users to dashboard
    from fastapi import Request as _Request
    token = None
    if request:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if not token or not verify_token(token):
        raise HTTPException(401, "Login required. Visit /dashboard to create an account, then use /v1/me/upgrade.")
    
    user_id = verify_token(token)
    user = get_user(user_id) if user_id else None
    
    try:
        result = await create_checkout_session(plan)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/v1/billing/webhook")
async def billing_webhook(request: Request):
    """Stripe webhook endpoint. Processes checkout.session.completed events."""
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    result = await handle_webhook(payload, signature)
    return result


@app.get("/v1/billing/success")
async def billing_success(session_id: str = ""):
    """Success page shown after Stripe payment. Shows the generated API key."""
    if not session_id:
        return HTMLResponse("<h1>Payment confirmed!</h1><p>Check your email for API key.</p>")
    
    key_data = await get_key_for_session(session_id)
    if key_data:
        return HTMLResponse(f"""
        <!DOCTYPE html><html><head><title>CodeShot — API Key</title>
        <style>body{{font-family:system-ui;background:#0a0a0a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}} .card{{background:#111827;border:1px solid #1e293b;border-radius:12px;padding:40px;max-width:500px;text-align:center}} h1{{color:#f8fafc;margin-bottom:8px}} .key{{background:#1e293b;color:#3b82f6;padding:16px 24px;border-radius:8px;font-family:monospace;font-size:18px;margin:24px 0;word-break:break-all}} .plan{{color:#10b981;font-weight:600}} p{{color:#94a3b8;margin:8px 0}}</style></head><body>
        <div class="card">
          <h1>🎉 Payment Confirmed</h1>
          <p class="plan">{key_data['plan'].upper()} Plan</p>
          <p>Here's your API key. Save it — it won't be shown again.</p>
          <div class="key">{key_data['api_key']}</div>
          <p>Use it in the Authorization header:</p>
          <p style="font-family:monospace;color:#64748b">Bearer {key_data['api_key']}</p>
          <p style="margin-top:24px"><a href="/docs" style="color:#3b82f6">View API Docs →</a></p>
        </div></body></html>""")
    
    return HTMLResponse("<h1>Payment confirmed!</h1><p>Your API key has been generated. Check your email.</p>")


# ── User auth endpoints ──

@app.post("/v1/auth/register")
async def auth_register(data: UserCreate):
    """Register a new user account."""
    try:
        user = create_user(data.email, data.password, data.name)
        token = create_token(user["id"])
        return {"token": token, "user": {"email": user["email"], "name": user["name"], "plan": user["plan"]}}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/v1/auth/login")
async def auth_login(data: UserLogin):
    """Login and get a JWT token."""
    user = authenticate(data.email, data.password)
    if not user:
        raise HTTPException(401, "Invalid email or password")
    token = create_token(user["id"])
    return {"token": token, "user": {"email": user["email"], "name": user["name"], "plan": user["plan"]}}


@app.get("/v1/me")
async def user_me(request: Request):
    """Get current user info, API keys, and usage stats."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    token = auth_header[7:]
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid or expired token")
    
    user = get_user(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    
    keys = get_user_api_keys(user_id)
    usage = get_user_usage(user_id)
    
    return {
        "user": {"email": user["email"], "name": user["name"], "plan": user["plan"]},
        "api_keys": keys,
        "usage": usage,
    }


@app.post("/v1/me/keys")
async def user_create_key(request: Request, name: str = "default"):
    """Create a new API key for the authenticated user."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid token")
    
    user = get_user(user_id)
    raw_key = create_user_api_key(user_id, name, user["plan"])
    return {"key": raw_key, "name": name, "plan": user["plan"]}


@app.get("/v1/me/usage/history")
async def user_usage_history(request: Request, days: int = 30):
    """Get daily usage history for charts."""
    token = _get_token(request)
    if not token:
        raise HTTPException(401, "Authentication required")
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid token")
    history = get_user_usage_history(user_id, days)
    return {"days": days, "history": history}


@app.post("/v1/me/upgrade")
async def user_upgrade(request: Request, plan: str = "pro"):
    """Create a Stripe checkout session for an authenticated user upgrading."""
    token = _get_token(request)
    if not token:
        raise HTTPException(401, "Login required to upgrade. Visit /dashboard first.")
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid token")
    user = get_user(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    
    # Pass user email to Stripe for pre-fill
    from .billing import create_checkout_session, DOMAIN
    import stripe as _stripe
    _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    PRICE_IDS = {
        "pro": os.environ.get("STRIPE_PRICE_PRO", "price_1TZfqJHMkYtoDU24yPATdwHt"),
        "team": os.environ.get("STRIPE_PRICE_TEAM", "price_1TZft1HMkYtoDU24ogtfAbqL"),
        "business": os.environ.get("STRIPE_PRICE_BUSINESS", "price_1TZfw3HMkYtoDU24U9ngLp6y"),
    }
    
    if not _stripe.api_key:
        raise HTTPException(400, "Stripe not configured")
    
    price_id = PRICE_IDS.get(plan, PRICE_IDS["pro"])
    session = _stripe.checkout.Session.create(
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{DOMAIN}/v1/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{DOMAIN}/dashboard",
        metadata={"plan": plan, "user_id": user_id},
        customer_email=user["email"],
        allow_promotion_codes=True,
    )
    return {"url": session.url, "session_id": session.id}


@app.post("/v1/auth/api-key")
async def auth_api_key(data: UserCreate):
    """Register or login and get an API key directly. Agent-friendly endpoint."""
    # Try to find existing user
    user = get_user_by_email(data.email)
    if not user:
        # Register new user
        try:
            user = create_user(data.email, data.password, data.name)
        except ValueError:
            # Race condition: try login instead
            user = get_user_by_email(data.email)
            if not user:
                raise HTTPException(400, "Registration failed")
    
    # Generate API key
    raw_key = ensure_user_api_key(user["id"])
    token = create_token(user["id"])
    
    return {
        "api_key": raw_key,
        "token": token,
        "plan": user["plan"],
        "email": user["email"],
        "message": "Use this key in Authorization: Bearer header. Save it — it won't be shown again.",
    }


# Helper
def _get_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


# ── Dashboard pages ──

@app.get("/dashboard")
async def user_dashboard():
    """User dashboard HTML page."""
    from fastapi.responses import FileResponse
    import os as _os
    path = _os.path.join(_os.path.dirname(__file__), "static", "dashboard.html")
    return FileResponse(path)



@app.get("/admin")
async def admin_dashboard():
    """Admin dashboard. Password-protected."""
    from fastapi.responses import FileResponse
    import os as _os
    p = _os.path.join(_os.path.dirname(__file__), "static", "admin.html")
    return FileResponse(p)


# ── Admin auth dependency ──

from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

admin_auth_scheme = HTTPBearer(auto_error=False)

def require_admin(credentials: HTTPAuthorizationCredentials = Depends(admin_auth_scheme)):
    """Dependency that validates admin JWT."""
    if not credentials:
        raise HTTPException(401, "Admin authentication required")
    if not admin_api.admin_verify(credentials.credentials):
        raise HTTPException(403, "Invalid admin credentials")
    return True


@app.post("/v1/admin/login")
async def admin_login(request: Request):
    """Login as admin. Send {"password": "..."} in body. Returns JWT valid 24h."""
    try:
        body = await request.json()
        password = body.get("password", "")
    except Exception:
        password = ""
    token = admin_api.admin_login(password)
    if not token:
        if not admin_api.ADMIN_PASSWORD:
            raise HTTPException(400, "ADMIN_PASSWORD not configured on server")
        raise HTTPException(401, "Invalid admin password")
    return {"token": token, "expires_in": 86400}


@app.get("/v1/admin/login")
async def admin_verify_session(_admin: bool = Depends(require_admin)):
    """Verify admin session is still valid."""
    return {"status": "ok", "role": "admin"}


# ── Admin endpoints (all protected) ──

@app.post("/v1/admin/keys")
async def create_api_key(name: str = "default", plan: str = "free", _admin: bool = Depends(require_admin)):
    """Create a new API key. Returns the key — save it, it won't be shown again."""
    if plan not in ("free", "pro", "team", "business"):
        raise HTTPException(400, f"Invalid plan. Choose: free, pro, team, business")
    raw_key = await key_store.create(name, plan)
    return {"key": raw_key, "name": name, "plan": plan, "warning": "Save this key — it will not be shown again."}


@app.get("/v1/admin/keys")
async def list_keys(_admin: bool = Depends(require_admin)):
    """List all API keys (without their secret values)."""
    return {"keys": await key_store.list_keys()}


@app.get("/v1/admin/all-keys")
async def list_all_keys(_admin: bool = Depends(require_admin)):
    """List all API keys with user info."""
    return {"keys": admin_api.admin_list_all_keys()}


@app.post("/v1/admin/users/{user_id}/plan")
async def admin_set_plan(user_id: str, plan: str = "pro", _admin: bool = Depends(require_admin)):
    """Change a user's plan."""
    ok = admin_api.admin_change_user_plan(user_id, plan)
    if not ok:
        raise HTTPException(400, "Invalid plan or user not found")
    return {"status": "ok", "user_id": user_id, "plan": plan}


@app.delete("/v1/admin/users/{user_id}")
async def admin_delete_user(user_id: str, _admin: bool = Depends(require_admin)):
    """Delete a user and all their keys."""
    ok = admin_api.admin_delete_user(user_id)
    if not ok:
        raise HTTPException(404, "User not found")
    return {"status": "deleted", "user_id": user_id}


@app.get("/v1/admin/users/{user_id}")
async def admin_user_detail(user_id: str, _admin: bool = Depends(require_admin)):
    """Get user details with all keys."""
    detail = admin_api.admin_user_detail(user_id)
    if not detail:
        raise HTTPException(404, "User not found")
    return detail


@app.post("/v1/admin/keys/{key_id}/toggle")
async def admin_toggle_key(key_id: str, enabled: bool = True, _admin: bool = Depends(require_admin)):
    """Enable or disable an API key."""
    ok = admin_api.admin_toggle_key(key_id, enabled)
    return {"status": "ok", "key_id": key_id, "enabled": enabled}


@app.delete("/v1/admin/keys/{key_id}")
async def admin_revoke_key(key_id: str, _admin: bool = Depends(require_admin)):
    """Permanently delete an API key."""
    ok = admin_api.admin_revoke_key(key_id)
    if not ok:
        raise HTTPException(404, "Key not found")
    return {"status": "revoked", "key_id": key_id}



@app.on_event("startup")
async def on_startup():
    await create_default_key()


# ── Feedback / Complaints ──

from pydantic import BaseModel as _BM

class FeedbackRequest(_BM):
    email: str
    category: str = "other"  # bug, feature, complaint, praise, other
    message: str


@app.post("/v1/feedback")
async def submit_feedback(req: FeedbackRequest):
    """Submit feedback or a complaint. Stored and emailed to admin."""
    from .notify import submit_feedback as sf
    result = sf(req.email, req.category, req.message)
    return result


@app.get("/admin/feedback")
async def admin_feedback(_admin: bool = Depends(require_admin)):
    """Admin page showing all feedback entries."""
    from .notify import load_feedback, get_feedback_stats
    stats = get_feedback_stats()
    entries = load_feedback()
    
    rows = ""
    for e in reversed(entries):
        emoji = {"bug":"🐛","feature":"💡","complaint":"🚨","praise":"🎉","other":"📬"}.get(e["category"],"📬")
        resolved = "✅" if e["resolved"] else "❌"
        rows += f"""
        <tr>
          <td>{emoji} {e['category']}</td>
          <td>{e['email']}</td>
          <td style="max-width:400px;word-break:break-word">{e['message']}</td>
          <td>{e['created_at'][:19]}</td>
          <td>{resolved}</td>
        </tr>"""
    
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><title>CodeShot — Feedback</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui;background:#0a0a0a;color:#e2e8f0}}
.nav{{display:flex;justify-content:space-between;align-items:center;padding:14px 24px;background:#111827;border-bottom:1px solid #1e293b}}
.nav h1{{font-size:17px;color:#f8fafc}}.nav a{{color:#3b82f6;text-decoration:none;font-size:13px}}
.container{{max-width:1000px;margin:0 auto;padding:24px}}
.stats{{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
.stat{{background:#111827;border:1px solid #1e293b;border-radius:10px;padding:16px 20px;text-align:center}}
.stat-num{{font-size:24px;font-weight:800;color:#3b82f6}}.stat-label{{font-size:11px;color:#64748b;text-transform:uppercase}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:10px 14px;text-align:left;border-bottom:1px solid #1e293b}}
th{{color:#64748b;font-size:11px;text-transform:uppercase}}
</style></head><body>
<div class="nav"><h1>📬 CodeShot — Feedback</h1>
<div><a href="/admin">← Admin</a></div></div>
<div class="container">
<div class="stats">
  <div class="stat"><div class="stat-num">{stats['total']}</div><div class="stat-label">Total</div></div>
  <div class="stat"><div class="stat-num">{stats['unresolved']}</div><div class="stat-label">Unresolved</div></div>
</div>
<table><thead><tr><th>Category</th><th>Email</th><th>Message</th><th>Time</th><th>Status</th></tr></thead>
<tbody>{rows}</tbody></table>
</div></body></html>""")


@app.on_event("shutdown")
async def on_shutdown():
    await shutdown()
