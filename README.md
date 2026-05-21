# CodeShot API

**Beautiful code screenshots via REST API.** No editor. No clicking. Just ship.

Generate syntax-highlighted PNGs, animated GIFs, AI-annotated diffs — all programmatically. Built for developers who need to generate code screenshots at scale.

[![API Docs](https://img.shields.io/badge/docs-OpenAPI-blue)](http://localhost:8000/docs)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/edowamba-prog/codeshot-api.git
cd codeshot-api

# 2. Install
pip install -r requirements.txt
python3 -m playwright install chromium

# 3. Set your DeepSeek API key (for AI annotations)
export DEEPSEEK_API_KEY=sk-your-key-here

# 4. Run
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5. Get your API key
curl -X POST http://localhost:8000/v1/admin/keys?name=my-key&plan=free
# → {"key": "cs_abc123...", "plan": "free"}
```

Server is live at `http://localhost:8000`. Full docs at `/docs`.

---

## Docker

```bash
docker compose up -d
```

The container includes Chromium, ffmpeg, and all Python dependencies. Single command.

---

## Authentication

All protected endpoints require an API key. Pass it via header:

```bash
curl -H "Authorization: Bearer cs_your_key_here" ...
# or
curl -H "x-api-key: cs_your_key_here" ...
```

**Get a key:**

```bash
# Create a free key
curl -X POST "http://localhost:8000/v1/admin/keys?name=my-app&plan=free"

# Create a pro key
curl -X POST "http://localhost:8000/v1/admin/keys?name=my-app&plan=pro"
```

Plans: `free` (50 req/hr), `pro` (1,000/hr), `team` (5,000/hr), `business` (20,000/hr).

---

## API Reference

### `POST /v1/screenshot` — Generate Code Screenshot

Generate a PNG screenshot of code with syntax highlighting.

**Request:**

```json
{
  "code": "def hello():\n    print('Hello, World!')\n    return 42",
  "language": "python",
  "theme": "dracula",
  "preset": "twitter-post",
  "watermark": "@yourhandle",
  "show_line_numbers": true,
  "show_window_controls": true,
  "show_language_badge": true,
  "device_scale_factor": 2.0,
  "format": "png"
}
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `code` | string | *required* | Source code (max 50,000 chars) |
| `language` | string | `"plaintext"` | One of 25 supported languages |
| `theme` | string | `"dracula"` | Theme name (see `/v1/themes`) |
| `preset` | string | — | Social media size preset |
| `width` | int | 900 | Custom width in pixels |
| `height` | int | 500 | Custom height in pixels |
| `watermark` | string | — | Text watermark (e.g. `@username`) |
| `brand_name` | string | — | Reference a saved brand kit |
| `brand` | object | — | Inline brand override |
| `show_line_numbers` | bool | `true` | Show line number gutter |
| `show_window_controls` | bool | `true` | Show macOS-style dots |
| `show_language_badge` | bool | `true` | Show language label |
| `device_scale_factor` | float | `2.0` | 1.0 = 1x, 2.0 = retina |
| `format` | string | `"png"` | `"png"` or `"html"` |

**Response:** `image/png` with headers:
- `X-Render-Time-Ms` — render duration
- `X-Theme` — theme used
- `X-Preset` — preset used

**Example:**

```bash
curl -X POST http://localhost:8000/v1/screenshot \
  -H "Authorization: Bearer cs_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "export default function App() {\n  return <div>Hello</div>;\n}",
    "language": "javascript",
    "theme": "tokyo-night",
    "preset": "twitter-post",
    "watermark": "@yourhandle"
  }' \
  -o tweet.png
```

---

### `POST /v1/diff` — Generate Code Diff

Beautiful side-by-side or unified diff visualization. Perfect for changelogs and release notes.

**Request:**

```json
{
  "old_code": "function fetch(id) {\n  return db.get(id);\n}",
  "new_code": "async function fetch(id: string) {\n  const user = await db.get(id);\n  if (!user) throw new Error('Not found');\n  return user;\n}",
  "language": "typescript",
  "theme": "github-dark",
  "mode": "side-by-side",
  "title": "fix: add error handling",
  "watermark": "@yourhandle"
}
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `old_code` | string | *required* | Original code |
| `new_code` | string | *required* | Updated code |
| `language` | string | `"plaintext"` | Language for context |
| `theme` | string | `"dracula"` | Theme |
| `mode` | string | `"unified"` | `"unified"` or `"side-by-side"` |
| `title` | string | — | Window title |
| `watermark` | string | — | Watermark text |

**Response headers:**

- `X-Additions` — lines added
- `X-Deletions` — lines removed
- `X-Diff-Mode` — mode used

---

### `POST /v1/animate` — Generate Animated Code

Typewriter, line-reveal, or fade-in animations. GIF or MP4 output.

**Request:**

```json
{
  "code": "fn main() {\n    println!(\"Hello, world!\");\n}",
  "language": "rust",
  "theme": "one-dark",
  "effect": "typewriter",
  "duration": 4.0,
  "fps": 24,
  "format": "mp4",
  "cursor": true,
  "watermark": "@yourhandle"
}
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `code` | string | *required* | Code to animate (max 5,000 chars) |
| `effect` | string | `"typewriter"` | `"typewriter"`, `"reveal-line"`, or `"fade-in"` |
| `duration` | float | `4.0` | Animation length in seconds (1-30) |
| `fps` | int | `24` | Frames per second (12-60) |
| `format` | string | `"mp4"` | `"mp4"` or `"gif"` |
| `cursor` | bool | `true` | Show blinking cursor (typewriter mode) |

**Render times:**

| Config | Time |
|---|---|
| 2s GIF @ 15fps | ~5s |
| 3s MP4 @ 20fps | ~7s |
| 5s MP4 @ 24fps | ~12s |

---

### `POST /v1/annotate` — AI-Annotated Code

DeepSeek analyzes your code and adds explanatory callout bubbles.

**Request:**

```json
{
  "code": "def divide(a, b):\n    if b == 0:\n        raise ValueError('Cannot divide by zero')\n    return a / b",
  "language": "python",
  "theme": "dracula",
  "focus": "error-handling",
  "watermark": "@yourhandle"
}
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `code` | string | *required* | Code to analyze (max 10,000 chars) |
| `focus` | string | `"general"` | `"general"`, `"error-handling"`, `"performance"`, `"security"`, `"patterns"` |

**Response headers:**

- `X-Annotation-Count` — number of callouts generated
- `X-Summary` — AI-generated one-sentence summary

**Requires:** `DEEPSEEK_API_KEY` environment variable.

---

### Brand Kits

Save your brand once, apply it to every screenshot.

**Create a brand:**

```bash
curl -X POST http://localhost:8000/v1/brands \
  -H "Authorization: Bearer cs_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "acme-corp",
    "label": "ACME Corp",
    "background": "#0A0E27",
    "text": "#E2E8F0",
    "accent": "#6C63FF",
    "font_family": "JetBrains Mono, monospace",
    "font_size": "15px",
    "border_radius": "16px",
    "watermark": "@acmehq"
  }'
```

**Use a brand:**

```json
{
  "code": "...",
  "language": "python",
  "brand_name": "acme-corp"
}
```

Inline overrides merge on top of saved brands:

```json
{
  "brand_name": "acme-corp",
  "brand": {"accent": "#FF006E"}
}
```

---

### Reference Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/v1/themes` | GET | No | List 10 themes with preview URLs |
| `/v1/presets` | GET | No | List 8 social media size presets |
| `/v1/languages` | GET | No | List 25 supported languages |
| `/v1/effects` | GET | No | List 3 animation effects |
| `/v1/preview` | GET | No | Interactive HTML preview |
| `/v1/brands` | GET | Yes | List saved brand kits |
| `/v1/brands/{name}` | GET | Yes | Get a specific brand kit |
| `/v1/brands/{name}` | PUT | Yes | Update a brand kit |
| `/v1/brands/{name}` | DELETE | Yes | Delete a brand kit |

---

## Themes

| Theme | Dark/Light | Preview |
|---|---|---|
| `dracula` | Dark | Purple-tinted dark |
| `github-dark` | Dark | GitHub's dark theme |
| `monokai` | Dark | Classic Sublime Text |
| `nord` | Dark | Arctic blue-grey |
| `solarized-dark` | Dark | Warm blue-green |
| `one-dark` | Dark | Atom editor |
| `light-plus` | Light | VS Code light |
| `tokyo-night` | Dark | Neon city vibes |
| `catppuccin` | Dark | Pastel mocha |
| `everforest` | Dark | Earthy green tones |

---

## Social Presets

| Preset | Dimensions | Use For |
|---|---|---|
| `twitter-post` | 1200×675 | Twitter/X feed posts |
| `twitter-card` | 800×418 | Twitter link cards |
| `linkedin` | 1200×627 | LinkedIn posts |
| `instagram-square` | 1080×1080 | Instagram feed |
| `instagram-story` | 1080×1920 | Instagram stories |
| `og-image` | 1200×630 | Open Graph / link previews |
| `github-readme` | 900×500 | GitHub README badges |
| `blog-header` | 1600×840 | Blog post headers |

---

## Supported Languages

`javascript`, `typescript`, `python`, `rust`, `go`, `java`, `kotlin`, `swift`, `ruby`, `php`, `c`, `cpp`, `csharp`, `sql`, `bash`, `yaml`, `json`, `html`, `css`, `dockerfile`, `graphql`, `markdown`, `terraform`, `toml`, `plaintext`

---

## Tutorial: Automate Your Changelog Images

Here's a complete workflow to auto-generate code screenshots for your changelog.

### Step 1: Create a brand kit

```bash
curl -X POST http://localhost:8000/v1/brands \
  -H "Authorization: Bearer cs_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-project",
    "label": "My Project",
    "background": "#0d1117",
    "accent": "#58a6ff",
    "font_family": "Fira Code, monospace",
    "watermark": "@myproject"
  }'
```

### Step 2: Write a script

```bash
#!/bin/bash
# generate-changelog-images.sh
# Generates before/after screenshots for each commit in the last release

KEY="cs_your_key_here"
BASE="http://localhost:8000/v1"

# For each commit in the changelog
git log v1.0.0..HEAD --oneline | while read hash msg; do
  # Get the diff
  OLD=$(git show $hash^:src/main.ts 2>/dev/null)
  NEW=$(git show $hash:src/main.ts 2>/dev/null)
  
  # Generate diff screenshot
  curl -s -X POST $BASE/diff \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d "$(jq -n \
      --arg old "$OLD" \
      --arg new "$NEW" \
      '{old_code: $old, new_code: $new, language: "typescript", 
        theme: "github-dark", mode: "side-by-side",
        brand_name: "my-project", title: $hash}')" \
    -o "changelog/${hash}.png"
  
  echo "Generated changelog/${hash}.png"
done
```

### Step 3: Generate social cards for the release

```bash
curl -s -X POST $BASE/screenshot \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "// v2.0: Added async pipeline\n// 3x faster, 0 breaking changes\n\nasync function process(data: Input) {\n  return await pipeline(data);\n}",
    "language": "typescript",
    "theme": "tokyo-night",
    "preset": "twitter-post",
    "brand_name": "my-project",
    "title": "v2.0 Release Notes"
  }' \
  -o social/twitter-announcement.png
```

---

## Tutorial: Animated Social Media Content

Turn code snippets into engaging animated content for social media.

### Typewriter effect for Twitter

```bash
curl -X POST http://localhost:8000/v1/animate \
  -H "Authorization: Bearer cs_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "async function deploy() {\n  await build();\n  await test();\n  await ship();\n  console.log(\"🚀 Live!\");\n}",
    "language": "javascript",
    "theme": "dracula",
    "effect": "typewriter",
    "duration": 5.0,
    "fps": 24,
    "format": "mp4",
    "watermark": "@yourhandle"
  }' \
  -o deploy-animation.mp4
```

### Line-by-line reveal for educational content

```bash
curl -X POST http://localhost:8000/v1/animate \
  -H "Authorization: Bearer cs_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "# Step 1: Read the file\nwith open(\"data.txt\") as f:\n    content = f.read()\n\n# Step 2: Parse JSON\ndata = json.loads(content)\n\n# Step 3: Process\nresult = transform(data)",
    "language": "python",
    "theme": "one-dark",
    "effect": "reveal-line",
    "duration": 6.0,
    "format": "gif",
    "watermark": "@pythontips"
  }' \
  -o python-tutorial.gif
```

---

## Tutorial: AI-Annotated Code Reviews

Generate explanatory code screenshots for documentation or teaching.

```python
import requests

API = "http://localhost:8000/v1"
KEY = "cs_your_key_here"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

examples = [
    {
        "code": "def process(items):\n    results = []\n    for item in items:\n        if item.valid:\n            results.append(item.transform())\n    return results",
        "language": "python",
        "focus": "performance"
    },
    {
        "code": "app.get('/user/:id', async (req, res) => {\n  const user = await db.users.findOne({ _id: req.params.id });\n  res.json(user);\n});",
        "language": "javascript", 
        "focus": "security"
    }
]

for i, ex in enumerate(examples):
    resp = requests.post(f"{API}/annotate", headers=HEADERS, json={
        **ex, "theme": "github-dark", "watermark": "@codedocs"
    })
    
    with open(f"annotated-{i}.png", "wb") as f:
        f.write(resp.content)
    
    print(f"Example {i}: {resp.headers.get('X-Annotation-Count')} annotations")
    print(f"Summary: {resp.headers.get('X-Summary')}")
    print(f"Rendered in {resp.headers.get('X-Render-Time-Ms')}ms\n")
```

---

## Rate Limiting

All endpoints return standard rate limit headers:

```
X-RateLimit-Limit-Hourly: 1000
X-RateLimit-Limit-Daily: 10000
X-RateLimit-Remaining-Hourly: 998
X-RateLimit-Remaining-Daily: 9998
```

When exceeded: `429 Too Many Requests`

---

## Deployment

### Fly.io

```bash
fly launch
fly secrets set DEEPSEEK_API_KEY=sk-...
fly deploy
```

### Railway

```bash
railway up
railway variables set DEEPSEEK_API_KEY=sk-...
```

### Any Docker host

```bash
docker build -t codeshot-api .
docker run -p 8000:8000 -e DEEPSEEK_API_KEY=sk-... -v $(pwd)/data:/app/data codeshot-api
```

---

## Architecture

```
Client → FastAPI → build_html() → Playwright (headless Chromium) → PNG/MP4/GIF
                          ↑
                    highlight.js (CDN)
                          ↑
                 DeepSeek API (annotations only)
```

See [BUILD.md](BUILD.md) for the full build log, design decisions, and pitfalls.

---

## License

MIT — see [LICENSE](LICENSE)
