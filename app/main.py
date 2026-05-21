"""
CodeShot API — Beautiful code screenshots via REST API.
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Literal
import time

from .themes import THEMES, SOCIAL_PRESETS, LANGUAGES
from .renderer import build_html
from .screenshot import render_screenshot, shutdown
from .brands import brand_store
from .routers import brands as brands_router
from .diff import build_diff_html, compute_diff, count_changes
from .animate import build_animated_html, render_animation, ANIMATION_EFFECTS
from .annotate import analyze_code, build_annotated_html
from .auth import APIKeyMiddleware, key_store, rate_limiter, create_default_key
from .billing import create_checkout_session, create_lifetime_checkout, handle_webhook, get_key_for_session
from .users import (
    create_user, authenticate, get_user, get_user_by_email, list_users,
    create_token, verify_token, create_user_api_key, get_user_api_keys,
    get_user_usage, get_admin_stats, log_usage, UserCreate, UserLogin,
    update_user_plan,
)

app = FastAPI(
    title="CodeShot API",
    description="Generate beautiful code screenshots programmatically. 10 themes, social presets, brand kits, and more.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add auth middleware
app.add_middleware(APIKeyMiddleware)

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


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "codeshot-api"}


# ── Billing endpoints ──

@app.post("/v1/billing/checkout")
async def billing_checkout(plan: str = "pro"):
    """Create a Stripe Checkout session. Returns URL to redirect user to."""
    try:
        result = await create_checkout_session(plan)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/v1/billing/checkout-lifetime")
async def billing_lifetime():
    """Create a one-time payment checkout for lifetime Pro access ($49)."""
    try:
        result = await create_lifetime_checkout()
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


# ── Dashboard pages ──

@app.get("/dashboard")
async def user_dashboard():
    """User dashboard HTML page."""
    return HTMLResponse("""
<!DOCTYPE html><html><head><title>CodeShot — Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui;background:#0a0a0a;color:#e2e8f0;min-height:100vh}
.nav{display:flex;justify-content:space-between;align-items:center;padding:16px 24px;background:#111827;border-bottom:1px solid #1e293b}
.nav h1{font-size:18px;color:#f8fafc}
.nav a{color:#3b82f6;text-decoration:none;font-size:14px}
.container{max-width:900px;margin:0 auto;padding:32px 24px}
.card{background:#111827;border:1px solid #1e293b;border-radius:12px;padding:24px;margin-bottom:20px}
.card h2{font-size:16px;color:#f8fafc;margin-bottom:16px}
.stats{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px}
.stat{flex:1;min-width:120px;background:#0f172a;border-radius:8px;padding:16px;text-align:center}
.stat-num{font-size:24px;font-weight:800;color:#3b82f6}
.stat-label{font-size:12px;color:#64748b;margin-top:4px}
.key-row{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#0f172a;border-radius:8px;margin-bottom:8px;font-family:monospace;font-size:14px}
.key-row .name{color:#e2e8f0}
.key-row .plan{color:#10b981;font-size:12px}
.btn{padding:10px 20px;border-radius:8px;font-size:14px;font-weight:600;border:none;cursor:pointer;transition:.2s}
.btn-primary{background:#3b82f6;color:#fff}.btn-primary:hover{background:#2563eb}
.btn-secondary{background:#1e293b;color:#e2e8f0;border:1px solid #334155}
.form-group{margin-bottom:16px}
.form-group label{display:block;font-size:13px;color:#94a3b8;margin-bottom:6px}
.form-group input{width:100%;padding:10px 14px;background:#0f172a;border:1px solid #1e293b;border-radius:8px;color:#e2e8f0;font-size:14px;font-family:monospace}
.hidden{display:none}
.error{color:#ef4444;font-size:13px;margin-top:8px}
.success{color:#10b981;font-size:13px;margin-top:8px}
</style></head><body>
<div class="nav">
  <h1>⚡ CodeShot Dashboard</h1>
  <div>
    <span id="userEmail" style="color:#64748b;font-size:13px;margin-right:16px"></span>
    <a href="/docs">API Docs</a>
  </div>
</div>
<div class="container">
  <div id="loginForm" class="card">
    <h2>Login or Register</h2>
    <div class="form-group"><label>Email</label><input type="email" id="email" placeholder="you@example.com"></div>
    <div class="form-group"><label>Password</label><input type="password" id="password" placeholder="Min 6 characters"></div>
    <div style="display:flex;gap:12px">
      <button class="btn btn-primary" onclick="login()">Login</button>
      <button class="btn btn-secondary" onclick="register()">Register</button>
    </div>
    <div id="authError" class="error"></div>
  </div>
  
  <div id="dashboardView" class="hidden">
    <div class="stats" id="usageStats"></div>
    
    <div class="card">
      <h2>Your API Keys</h2>
      <div id="keyList"></div>
      <button class="btn btn-primary" onclick="createKey()" style="margin-top:12px">+ New API Key</button>
      <div id="newKey" class="success" style="margin-top:8px"></div>
    </div>
    
    <div class="card">
      <h2>Quick Test</h2>
      <div style="font-family:monospace;font-size:13px;color:#64748b;margin-bottom:8px">
        curl -X POST https://codeshot-api-production.up.railway.app/v1/screenshot \\
        <br>  -H "Authorization: Bearer <span style="color:#3b82f6">YOUR_KEY</span>" \\
        <br>  -H "Content-Type: application/json" \\
        <br>  -d '{"code":"print(42)","language":"python","theme":"dracula"}'
      </div>
    </div>
  </div>
</div>
<script>
const API = '/v1';
let token = localStorage.getItem('codeshot_token');
if (token) checkAuth();

async function login() {
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  try {
    const resp = await fetch(API+'/auth/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
    const data = await resp.json();
    if (resp.ok) { token = data.token; localStorage.setItem('codeshot_token', token); showDashboard(data.user); }
    else document.getElementById('authError').textContent = data.detail || 'Login failed';
  } catch(e) { document.getElementById('authError').textContent = 'Network error'; }
}

async function register() {
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  try {
    const resp = await fetch(API+'/auth/register', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
    const data = await resp.json();
    if (resp.ok) { token = data.token; localStorage.setItem('codeshot_token', token); showDashboard(data.user); }
    else document.getElementById('authError').textContent = data.detail || 'Registration failed';
  } catch(e) { document.getElementById('authError').textContent = 'Network error'; }
}

async function checkAuth() {
  try {
    const resp = await fetch(API+'/me', {headers:{'Authorization':'Bearer '+token}});
    const data = await resp.json();
    if (resp.ok) showDashboard(data.user, data);
    else { localStorage.removeItem('codeshot_token'); }
  } catch(e) {}
}

function showDashboard(user, data) {
  document.getElementById('loginForm').classList.add('hidden');
  document.getElementById('dashboardView').classList.remove('hidden');
  document.getElementById('userEmail').textContent = user.email;
  if (data) {
    document.getElementById('usageStats').innerHTML = `
      <div class="stat"><div class="stat-num">${data.usage.hourly}</div><div class="stat-label">Requests (hour)</div></div>
      <div class="stat"><div class="stat-num">${data.usage.daily}</div><div class="stat-label">Requests (day)</div></div>
      <div class="stat"><div class="stat-num">${data.usage.total}</div><div class="stat-label">Total</div></div>
      <div class="stat"><div class="stat-num" style="color:#10b981">${user.plan.toUpperCase()}</div><div class="stat-label">Plan</div></div>
    `;
    document.getElementById('keyList').innerHTML = data.api_keys.map(k => 
      `<div class="key-row"><span class="name">${k.name}</span><span class="plan">${k.plan}</span></div>`
    ).join('') || '<p style="color:#64748b;font-size:14px">No API keys yet. Create one below.</p>';
  }
}

async function createKey() {
  try {
    const resp = await fetch(API+'/me/keys?name=my-key', {method:'POST',headers:{'Authorization':'Bearer '+token}});
    const data = await resp.json();
    if (resp.ok) {
      document.getElementById('newKey').textContent = '✅ New key: ' + data.key + ' (save this — it won\\'t be shown again)';
      checkAuth();
    }
  } catch(e) {}
}
</script></body></html>""")


@app.get("/admin")
async def admin_dashboard():
    """Admin dashboard HTML page."""
    stats = get_admin_stats()
    users = list_users()
    
    user_rows = ""
    for u in users:
        user_rows += f"""<tr>
            <td>{u['email']}</td>
            <td>{u.get('name','—')}</td>
            <td style="color:{'#10b981' if u['plan']=='pro' else '#f59e0b' if u['plan']=='team' else '#8b5cf6' if u['plan']=='business' else '#64748b'}">{u['plan'].upper()}</td>
            <td>{u.get('last_login','—') and '✓' or '—'}</td>
        </tr>"""
    
    return HTMLResponse(f"""
<!DOCTYPE html><html><head><title>CodeShot — Admin</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui;background:#0a0a0a;color:#e2e8f0;min-height:100vh}}
.nav{{display:flex;justify-content:space-between;align-items:center;padding:16px 24px;background:#111827;border-bottom:1px solid #1e293b}}
.nav h1{{font-size:18px;color:#f8fafc}}
.container{{max-width:1000px;margin:0 auto;padding:32px 24px}}
.stats{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}}
.stat{{flex:1;min-width:150px;background:#111827;border:1px solid #1e293b;border-radius:12px;padding:20px;text-align:center}}
.stat-num{{font-size:28px;font-weight:800;color:#3b82f6}}
.stat-label{{font-size:12px;color:#64748b;margin-top:6px;text-transform:uppercase;letter-spacing:0.5px}}
.card{{background:#111827;border:1px solid #1e293b;border-radius:12px;padding:24px;margin-bottom:20px}}
.card h2{{font-size:16px;color:#f8fafc;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th,td{{padding:12px 16px;text-align:left;border-bottom:1px solid #1e293b}}
th{{color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:0.5px}}
.plan-badges{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}}
.plan-badge{{padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}}
</style></head><body>
<div class="nav"><h1>⚡ CodeShot Admin</h1><a href="/dashboard" style="color:#3b82f6;text-decoration:none;font-size:14px">User Dashboard →</a></div>
<div class="container">
  <div class="stats">
    <div class="stat"><div class="stat-num">{stats['total_users']}</div><div class="stat-label">Total Users</div></div>
    <div class="stat"><div class="stat-num">{stats['total_keys']}</div><div class="stat-label">API Keys</div></div>
    <div class="stat"><div class="stat-num">{stats['today_requests']}</div><div class="stat-label">Requests Today</div></div>
  </div>
  <div class="plan-badges">
    {''.join(f'<span class="plan-badge" style="background:#1e293b;color:#94a3b8">{p}: {c}</span>' for p,c in stats.get('plans',{}).items())}
  </div>
  <div class="card" style="margin-top:24px">
    <h2>Users</h2>
    <table>
      <tr><th>Email</th><th>Name</th><th>Plan</th><th>Logged In</th></tr>
      {user_rows}
    </table>
  </div>
</div></body></html>""")


# ── Admin endpoints ──

@app.post("/v1/admin/keys")
async def create_api_key(name: str = "default", plan: str = "free"):
    """Create a new API key. Returns the key — save it, it won't be shown again."""
    if plan not in ("free", "pro", "team", "business"):
        raise HTTPException(400, f"Invalid plan. Choose: free, pro, team, business")
    raw_key = await key_store.create(name, plan)
    return {"key": raw_key, "name": name, "plan": plan, "warning": "Save this key — it will not be shown again."}


@app.get("/v1/admin/keys")
async def list_keys():
    """List all API keys (without their secret values)."""
    return {"keys": await key_store.list_keys()}


@app.on_event("startup")
async def on_startup():
    await create_default_key()


@app.on_event("shutdown")
async def on_shutdown():
    await shutdown()
