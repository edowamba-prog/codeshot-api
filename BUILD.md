# How CodeShot Was Built

A behind-the-scenes build log of taking an API from idea to production in one session. No fluff. Real code. Real decisions.

---

## The Problem

Every developer shares code screenshots. But the tools are all manual:

- **Carbon.sh** — beautiful, but no API. One screenshot at a time. Click. Download. Upload. Repeat.
- **Ray.so** — same story. Gorgeous UI. Zero automation.
- **Snappify** — has an API, but it's an afterthought bolted onto an editor product.

If you need 100 screenshots for your docs site, your changelog, your social media — you're clicking buttons 100 times. That's broken.

**The gap**: An API-first code screenshot tool. Built for developers. Every feature available programmatically.

---

## The Stack (and why)

| Layer | Choice | Reasoning |
|---|---|---|
| API Server | **FastAPI** (Python) | Async, auto-docs, Pydantic validation. Best DX for REST APIs. |
| Rendering | **Playwright** (headless Chromium) | The only way to get pixel-perfect screenshots of syntax-highlighted code. Puppeteer's Python cousin. |
| Syntax Highlighting | **highlight.js** (CDN) | 190+ languages. Loaded in the headless browser. No server-side parsing needed. |
| Animation | **ffmpeg** | Compile frame sequences into GIF/MP4. Battle-tested, fast, free. |
| AI Annotations | **DeepSeek Chat API** | $0.14/M input tokens. Analyze code → return structured JSON annotations. |
| Auth | **Custom middleware** | API keys + sliding-window rate limiter. No external auth service. |

**Why not Node.js?** Could have used Puppeteer natively in Node. But FastAPI's auto-generated OpenAPI docs (`/docs`) are worth the Python/Node bridge. The headless browser runs as a subprocess either way.

---

## Architecture: The Rendering Pipeline

The core challenge: turn code text into a beautiful PNG via API. Here's the pipeline:

```
POST /v1/screenshot
  │
  ▼
build_html()           ← Python generates an HTML page with:
  │                       - highlight.js CDN for syntax colors
  │                       - Theme CSS (colors, fonts, shadows)
  │                       - Window chrome (dots, title bar)
  │                       - Watermark, language badge
  ▼
render_screenshot()    ← Playwright loads the HTML in headless Chromium
  │                       - 2x device scale factor (retina quality)
  │                       - Waits for highlight.js to finish
  │                       - Captures viewport as PNG
  ▼
200 OK  image/png      ← Returns raw PNG bytes + render time header
```

**The key insight**: Don't parse syntax trees server-side. Let the browser do it. highlight.js runs in the headless Chromium context, so we get perfect rendering for 25 languages without maintaining any parsing code.

---

## Day 1: Core Engine (Items 1-4)

### Step 1: Project Setup

```bash
mkdir code-shot-api
cd code-shot-api
pip install fastapi uvicorn pydantic playwright
python3 -m playwright install chromium
```

Project structure:
```
app/
├── main.py          # FastAPI routes
├── themes.py        # Theme definitions
├── renderer.py      # HTML generation
└── screenshot.py    # Playwright wrapper
```

### Step 2: Theme System

Rather than hardcoding colors, each theme is a Python dict:

```python
THEMES = {
    "dracula": {
        "background": "#282a36",
        "text": "#f8f8f2",
        "accent": "#bd93f9",
        "border_radius": "12px",
        "shadow": "0 20px 60px rgba(0,0,0,0.5)",
        # ...
    },
    # ... 9 more
}
```

This makes themes **data, not code**. Adding a theme is 15 lines of config. Brand kits override any subset of these values.

### Step 3: The HTML Generator

`renderer.py` builds a complete HTML document with:
- highlight.js CDN for syntax colors
- Inline CSS with theme variables injected
- Optional window controls (macOS-style dots)
- Optional line numbers, language badge, watermark

The template uses Python f-strings — simple, fast, no template engine overhead.

### Step 4: Playwright Screenshot Service

```python
async def render_screenshot(html, width, height, device_scale_factor=2.0):
    browser = await get_browser()         # singleton browser instance
    page = await browser.new_page()
    await page.set_content(html, ...)     # load HTML
    await page.wait_for_timeout(500)      # wait for highlight.js
    return await page.screenshot()        # capture PNG
```

The browser is a **singleton** — launched once, reused across requests. This saves ~1 second per render vs launching a new browser each time.

### The First Test

```bash
curl -X POST http://localhost:8000/v1/screenshot \
  -H "Content-Type: application/json" \
  -d '{"code":"print(42)","language":"python","theme":"dracula"}' \
  -o test.png
# → 200 OK, 50KB PNG, rendered in 1.2 seconds
```

It works. One API call. One PNG. No editor. No clicking.

---

## Day 2: The Differentiators (Items 5-8)

Carbon.sh, Ray.so, and CodeSnap all do screenshots. To compete, CodeShot needed features they can't or won't build. Five differentiators:

### Diff Mode

Turns code changes into designed artifacts. Uses Python's `difflib` for the diff engine, then renders two modes:

- **Unified**: Single view with green/red gutters. Like `git diff` but beautiful.
- **Side-by-side**: Old on the left, new on the right. Missing lines aligned with empty rows.

The HTML uses `SequenceMatcher.get_opcodes()` to classify each line as equal/replace/delete/insert, then applies CSS classes.

```bash
curl -X POST http://localhost:8000/v1/diff \
  -d '{"old_code":"function f() { return 1 }",
       "new_code":"async function f() { return await get() }",
       "mode":"side-by-side"}'
# → Side-by-side diff with red/green highlights
```

### Brand Kits

Every company shares code screenshots. Every company uses a random theme that doesn't match their brand. Brand kits fix this:

1. **Save a brand once**: `POST /v1/brands` with your colors, fonts, watermark
2. **Reference it by name**: `"brand_name": "acme-corp"` in any screenshot request
3. **Override inline**: `"brand": {"accent": "#FF006E"}` for one-off tweaks

Brands persist to a JSON file. Survives server restarts. Zero external database.

### Animation Engine

The hardest feature. Requirements: typewriter effect, cursor blink, GIF + MP4 output.

**Approach 1 (failed)**: CSS animation + frame capture. The idea was to use `animation-delay: -N` to "seek" CSS animations. Doesn't work — CSS doesn't support seeking.

**Approach 2 (works)**: JS-driven frame capture:
1. Load one HTML page with a `.reveal-mask` div covering the code
2. For each frame, use `page.evaluate()` to set the mask width via JS
3. Screenshot at each step
4. Compile frames with ffmpeg

```python
for i in range(total_frames):
    progress = (i + 1) / total_frames
    mask_width_pct = (1.0 - progress) * 100
    await page.evaluate(f"""
        document.querySelector('.reveal-mask').style.width = '{mask_width_pct}%';
    """)
    await page.screenshot(path=f"frame_{i:04d}.png")
```

ffmpeg compiles the frames:
```bash
ffmpeg -framerate 24 -i frame_%04d.png -c:v mpeg4 output.mp4
```

**Pitfall**: `libx264` encoder wasn't available on this system. Switched to `mpeg4` encoder — works everywhere and Twitter/LinkedIn accept it.

### Real-World Render Times

| Feature | Frames | Time |
|---|---|---|
| Screenshot | 1 | 1.2s |
| Diff (unified) | 1 | 1.5s |
| Animation (2s @ 15fps GIF) | 30 | 5.4s |
| Animation (3s @ 20fps MP4) | 60 | ~8s |

---

## Day 3: AI + Ship (Items 9-12)

### AI Annotations

The feature nobody else has. How it works:

1. Send code to DeepSeek Chat API with a structured prompt
2. DeepSeek returns JSON: `{"annotations": [{"line": 3, "type": "warning", "text": "..."}]}`
3. Render annotations as numbered callout bubbles on the code

The prompt:
```
You are a code annotation engine. Analyze the following Python code.
Focus on: error-handling

Return ONLY valid JSON:
{
  "summary": "One sentence summary",
  "annotations": [
    {"line": 1, "type": "explain", "text": "..."},
    {"line": 5, "type": "warning", "text": "..."}
  ]
}

Rules: Max 5 annotations. Only annotate non-trivial lines.
```

**Cost**: ~$0.001 per annotation request. At $9/mo Pro plan, this is profitable at scale.

### API Keys + Rate Limiting

Two components built from scratch:

**API Key System**:
- Keys generated as `cs_` + 24 random hex chars
- Hashed with SHA-256 before storage
- Stored in JSON file (no database dependency)
- Plans: free, pro, team, business — each with different limits

**Rate Limiter**:
- Sliding window (not fixed window — no burst-at-boundary problem)
- Per-key counters for hourly and daily windows
- Returns standard `X-RateLimit-*` headers

```python
class RateLimiter:
    async def check(self, key, plan="free"):
        now = time.time()
        # Clean old timestamps
        self._hourly[key] = [t for t in self._hourly[key] if t > now - 3600]
        self._daily[key] = [t for t in self._daily[key] if t > now - 86400]
        
        if len(self._hourly[key]) >= limit:
            return False  # rate limited
        # Record + allow
        self._hourly[key].append(now)
        return True
```

### Landing Page

Single HTML file served by FastAPI at `/`. Dark theme. Sections:

1. **Hero** — headline, CTA, code example
2. **Features grid** — 6 cards highlighting differentiators
3. **Comparison table** — CodeShot vs Carbon.sh vs Ray.so vs Snappify
4. **Pricing** — 4 tiers: Free, Pro ($9), Team ($29), Business ($99)

Built with pure HTML/CSS. No framework. No build step. Fast to load, easy to edit.

---

## The Complete API

```
POST /v1/screenshot   Generate PNG code screenshot
POST /v1/diff          Generate code diff screenshot
POST /v1/animate       Generate animated GIF/MP4
POST /v1/annotate      Generate AI-annotated screenshot
GET  /v1/preview       Interactive HTML preview
GET  /v1/themes        List 10 themes
GET  /v1/presets       List 8 social media sizes
GET  /v1/languages     List 25 supported languages
GET  /v1/effects       List 3 animation effects
POST /v1/brands        Save a brand kit
GET  /v1/brands         List saved brand kits
POST /v1/admin/keys     Create API key
GET  /v1/admin/keys     List API keys
```

---

## What I'd Do Differently

**1. Use a proper database for brand kits and API keys.**
JSON files work for launch but won't scale past ~100 keys. SQLite would be a drop-in upgrade.

**2. Queue long-running renders.**
Animation generation takes 5-8 seconds. At scale, this should be async: return a job ID, poll for completion. FastAPI's `BackgroundTasks` could handle this.

**3. Add a CDN cache layer.**
Identical requests (same code + theme + preset) could be cached at the CDN level. The `Cache-Control: public, max-age=3600` header is already set — just needs a CDN in front.

**4. Webhook for render completion.**
For the animation endpoint: `POST /v1/animate` → 202 Accepted → webhook fires when done. Better UX for long renders.

**5. ffmpeg streaming.**
Currently all frames are written to disk, then compiled. Could pipe frames directly to ffmpeg stdin for lower latency and no disk I/O.

---

## Key Takeaways

1. **Headless browsers are underrated as rendering engines.** If you need pixel-perfect output of web content, Playwright/Puppeteer beats any server-side rendering approach.

2. **JSON files are fine for launch.** Don't over-engineer persistence. A JSON file with an async lock got us to production. Upgrade when you have users.

3. **CSS animation seeking doesn't work.** If you need frame-by-frame control of animations, use JavaScript. `animation-delay` with negative values only sets the initial state — it doesn't seek an already-loaded animation.

4. **Check your ffmpeg encoders.** Not every system has `libx264`. `mpeg4` is universally available and works for social media.

5. **API-first means every feature is an endpoint.** The web editor is secondary. The API is the product. This flips the traditional model and is why CodeShot can do things Carbon.sh can't.

---

Built in one session. 21 files. 3,100 lines. Zero dependencies beyond FastAPI + Playwright + ffmpeg. Ships as a single Docker container.

**→ [API Documentation](../README.md)**

**→ [Live Demo](http://localhost:8000)**
