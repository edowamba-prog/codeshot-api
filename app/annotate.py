"""
AI Annotation engine — uses DeepSeek to analyze code and generate explanatory callouts.
"""

import json
import re
from typing import Optional, Literal
import httpx

DEEPSEEK_BASE = "https://api.deepseek.com"

# Load API key from Hermes env
import os
from pathlib import Path
_env_path = Path.home() / ".hermes" / ".env"
_api_key = None
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            _api_key = line.split("=", 1)[1].strip()
            break


ANNOTATION_PROMPT = """You are a code annotation engine. Analyze the following {language} code and generate educational annotations.

For each annotation, identify:
- The line number (1-based)
- A short type: "explain" (what it does), "tip" (improvement suggestion), "warning" (potential issue), "highlight" (key concept)
- A concise annotation text (max 120 characters, clear, educational)

Focus on: {focus}

Code:
```{language}
{code}
```

Return ONLY valid JSON in this exact format, no other text:
{{
  "summary": "One sentence summary of what this code does",
  "annotations": [
    {{"line": 1, "type": "explain", "text": "..."}},
    {{"line": 5, "type": "warning", "text": "..."}}
  ]
}}

Rules:
- Max 5 annotations total
- Only annotate non-trivial, interesting lines
- Skip obvious boilerplate (imports, closing braces, etc.)
- If you see nothing worth annotating, return empty annotations array
- Annotation text must be concise and beginner-friendly
"""


async def analyze_code(
    code: str,
    language: str = "python",
    focus: str = "general",
    max_annotations: int = 5,
) -> dict:
    """Send code to DeepSeek for analysis and return annotations.
    
    Returns:
        {"summary": str, "annotations": [{"line": int, "type": str, "text": str}]}
    """
    if not _api_key:
        return {"summary": "", "annotations": [], "error": "no_api_key"}
    
    prompt = ANNOTATION_PROMPT.format(
        language=language,
        focus=focus,
        code=code[:4000],  # Limit code length for cost
    )
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{DEEPSEEK_BASE}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            data = response.json()
            
            content = data["choices"][0]["message"]["content"]
            
            # Parse JSON from response (may have markdown code blocks)
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                result = json.loads(json_match.group())
                # Validate and limit annotations
                annotations = result.get("annotations", [])[:max_annotations]
                # Ensure line numbers are valid
                code_lines = code.count('\n') + 1
                valid_annotations = [
                    a for a in annotations
                    if 1 <= a.get("line", 0) <= code_lines
                    and a.get("type") in ("explain", "tip", "warning", "highlight")
                    and len(a.get("text", "")) > 0
                ]
                return {
                    "summary": result.get("summary", ""),
                    "annotations": valid_annotations,
                }
            
            return {"summary": "", "annotations": [], "error": "parse_failed"}
        
        except Exception as e:
            return {"summary": "", "annotations": [], "error": str(e)[:200]}


def build_annotated_html(
    code: str,
    language: str,
    annotations: list[dict],
    theme: str = "dracula",
    title: Optional[str] = None,
    watermark: Optional[str] = None,
    brand: Optional[dict] = None,
    preset: Optional[str] = None,
) -> str:
    """Build HTML with annotation callouts overlaid on code.
    
    Annotations are rendered as numbered callout bubbles connected to their target lines.
    """
    from .themes import THEMES, SOCIAL_PRESETS, LANGUAGES
    
    t = THEMES.get(theme, THEMES["dracula"])
    if brand:
        # Sanitize brand CSS
        import re as _re
        def _sanitize(v):
            if not isinstance(v, str): return v
            return _re.sub(r'</?style[^>]*>', '', v, flags=_re.IGNORECASE)[:200]
        clean = {k: _sanitize(v) for k, v in brand.items() if v is not None}
        t = {**t, **clean}
    
    esc = lambda s: s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    
    lang_name = LANGUAGES.get(language, esc(language[:30]))
    lines = code.split('\n')
    line_count = len(lines)
    
    esc = lambda s: s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    
    # Annotation type colors
    type_colors = {
        "explain": "#3b82f6",    # blue
        "tip": "#10b981",        # green  
        "warning": "#f59e0b",    # amber
        "highlight": "#8b5cf6",  # purple
    }
    type_icons = {
        "explain": "💡",
        "tip": "✨",
        "warning": "⚠️",
        "highlight": "🔑",
    }
    
    # Build annotation overlay elements
    annotation_overlays = []
    for i, ann in enumerate(annotations):
        line_num = ann["line"]
        ann_type = ann["type"]
        color = type_colors.get(ann_type, "#3b82f6")
        icon = type_icons.get(ann_type, "")
        
        # Position: each annotation gets a vertical slot
        # We'll position them absolutely on the right side
        annotation_overlays.append(f"""
        <div class="annotation ann-{i}" style="top: {(line_num - 1) * 1.6 + 0.4}em;">
            <div class="ann-connector" style="border-color: {color};"></div>
            <div class="ann-badge" style="background: {color};">
                <span class="ann-number">{i + 1}</span>
            </div>
            <div class="ann-callout" style="border-left: 3px solid {color};">
                <span class="ann-type">{icon} {ann_type.upper()}</span>
                <span class="ann-text">{esc(ann['text'])}</span>
            </div>
        </div>
        """)
    
    annotations_html = '\n'.join(annotation_overlays)
    
    # Determine width: wider to accommodate annotations on the right
    has_annotations = len(annotations) > 0
    body_width = 1200 if has_annotations else 900
    
    # Line HTML
    line_html = ""
    for i, line in enumerate(lines, 1):
        escaped = esc(line) if line else ' '
        # Highlight annotated lines
        is_annotated = any(a["line"] == i for a in annotations)
        hl_class = ' annotated-line' if is_annotated else ''
        line_html += f'<div class="line{hl_class}"><span class="ln">{i}</span><span class="lc">{escaped}</span></div>\n'
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  
  body {{
    width: {body_width}px;
    min-height: 500px;
    background: {t['background']};
    font-family: {t['font_family']};
    font-size: {t['font_size']};
    color: {t['text']};
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  
  .container {{
    width: 100%;
    height: 100%;
    padding: {t['padding']};
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  
  .window {{
    width: 100%;
    max-height: 100%;
    background: {t['background']};
    border: 1px solid {t['border']};
    border-radius: {t['border_radius']};
    box-shadow: {t['shadow']};
    overflow: hidden;
    display: flex;
    flex-direction: column;
    position: relative;
  }}
  
  .window-controls {{
    display: flex;
    align-items: center;
    padding: 12px 16px;
    background: rgba(0,0,0,0.15);
    border-bottom: 1px solid {t['border']};
    gap: 8px;
    flex-shrink: 0;
  }}
  .dot {{ width: 11px; height: 11px; border-radius: 50%; }}
  .dot-red {{ background: #ff5f56; }}
  .dot-yellow {{ background: #ffbd2e; }}
  .dot-green {{ background: #27c93f; }}
  .window-title {{
    flex: 1; text-align: center; font-size: 11px;
    color: {t['gutter']}; margin-right: 38px;
  }}
  
  .main-area {{
    flex: 1;
    display: flex;
    position: relative;
  }}
  
  .code-pane {{
    flex: 0 0 60%;
    position: relative;
    padding: 14px 20px;
    font-family: {t['font_family']};
    font-size: {t['font_size']};
    line-height: 1.6;
    overflow: hidden;
    border-right: 1px solid {t['border']};
  }}
  
  .annotations-pane {{
    flex: 1;
    position: relative;
    padding: 14px 8px;
    overflow: hidden;
  }}
  
  .line {{
    display: flex;
    min-height: 1.6em;
    white-space: pre;
    tab-size: 4;
    transition: background 0.3s;
  }}
  .annotated-line {{
    background: rgba(59,130,246,0.08);
    border-radius: 3px;
  }}
  .ln {{
    width: 36px;
    flex-shrink: 0;
    text-align: right;
    padding-right: 12px;
    color: {t['gutter']};
    font-size: 0.82em;
    opacity: 0.45;
    user-select: none;
  }}
  .lc {{ flex: 1; }}
  
  .annotation {{
    position: absolute;
    left: 8px;
    right: 4px;
    display: flex;
    align-items: flex-start;
    gap: 6px;
  }}
  
  .ann-badge {{
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    margin-top: 2px;
  }}
  .ann-number {{
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    font-family: {t['font_family']};
  }}
  
  .ann-callout {{
    flex: 1;
    background: rgba(255,255,255,0.04);
    border-radius: 6px;
    padding: 6px 10px;
    font-family: {t['font_family']};
  }}
  .ann-type {{
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.5px;
    margin-bottom: 2px;
    display: block;
    color: {t['gutter']};
  }}
  .ann-text {{
    font-size: 11px;
    line-height: 1.4;
    color: {t['text']};
  }}
  
  .watermark {{
    position: absolute;
    bottom: 10px;
    right: 16px;
    font-size: 10px;
    color: {t['watermark_color']};
    pointer-events: none;
    z-index: 20;
  }}
  
  .lang-badge {{
    position: absolute;
    top: 10px;
    right: 16px;
    background: {t['accent']};
    color: {t['background']};
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    z-index: 20;
  }}
</style>
</head>
<body>
<div class="container">
  <div class="window">
    <div class="window-controls">
      <span class="dot dot-red"></span><span class="dot dot-yellow"></span><span class="dot dot-green"></span>
      <span class="window-title">{esc(title or f'{lang_name} • Annotated')}</span>
    </div>
    <div class="main-area">
      <div class="code-pane">
        <div class="lang-badge">{lang_name}</div>
        {line_html}
      </div>
      <div class="annotations-pane">
        {annotations_html}
      </div>
    </div>
    {f'<div class="watermark">{esc(watermark)}</div>' if watermark else ''}
  </div>
</div>
</body>
</html>"""
