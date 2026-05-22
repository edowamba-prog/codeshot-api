"""
CodeShot rendering engine.
Generates an HTML page with syntax-highlighted code, then screenshots it with Playwright.
"""

import json
import base64
from typing import Optional
from .themes import THEMES, SOCIAL_PRESETS, LANGUAGES

HIGHLIGHT_JS_CDN = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"
HIGHLIGHT_CSS_CDN = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/{theme}.min.css"

# Map our theme names to highlight.js theme names for base syntax colors
HIGHLIGHT_THEME_MAP = {
    "dracula": "dracula",
    "github-dark": "github-dark",
    "monokai": "monokai-sublime",
    "nord": "nord",
    "solarized-dark": "solarized-dark",
    "one-dark": "atom-one-dark",
    "light-plus": "github",
    "tokyo-night": "tokyo-night-dark",
    "catppuccin": "catppuccin-mocha",  # custom
    "everforest": "everforest",  # custom
}

HIGHLIGHT_THEME_CDN = {
    # Themes available on cdnjs
    "dracula": "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/dracula.min.css",
    "github-dark": "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css",
    "monokai-sublime": "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/monokai-sublime.min.css",
    "nord": "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/nord.min.css",
    "atom-one-dark": "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css",
    "github": "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css",
    "tokyo-night-dark": "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/tokyo-night-dark.min.css",
}

HI_THEME = {
    "dracula": "dracula",
    "github-dark": "github-dark",
    "monokai": "monokai-sublime",
    "nord": "nord",
    "solarized-dark": "solarized-dark",
    "one-dark": "atom-one-dark",
    "light-plus": "github",
    "tokyo-night": "tokyo-night-dark",
}


def build_html(
    code: str,
    language: str,
    theme: str = "dracula",
    width: Optional[int] = None,
    height: Optional[int] = None,
    preset: Optional[str] = None,
    brand: Optional[dict] = None,
    show_line_numbers: bool = True,
    show_window_controls: bool = True,
    show_language_badge: bool = True,
    title: Optional[str] = None,
    watermark: Optional[str] = None,
) -> str:
    """Build the full HTML page for rendering a code screenshot."""
    
    # Resolve theme
    t = THEMES.get(theme, THEMES["dracula"])
    if brand:
        # Sanitize brand CSS: strip style-close / HTML injection patterns
        import re as _re
        def _sanitize_css(v):
            if not isinstance(v, str):
                return v
            v = _re.sub(r'</?style[^>]*>', '', v, flags=_re.IGNORECASE)
            return v[:200]
        clean_brand = {k: _sanitize_css(v) for k, v in brand.items() if v is not None}
        t = {**t, **clean_brand}
    
    # Resolve preset dimensions
    if preset and preset in SOCIAL_PRESETS:
        width = width or SOCIAL_PRESETS[preset]["width"]
        height = height or SOCIAL_PRESETS[preset]["height"]
    
    width = width or 900
    height = height or 500
    
    # Escape helpers
    def esc(s: str) -> str:
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    
    # Language badge
    lang_name = LANGUAGES.get(language, esc(language[:30]))
    
    # Resolve highlight.js theme
    hl_theme = HIGHLIGHT_THEME_MAP.get(theme, "dracula")
    hl_css_url = HIGHLIGHT_THEME_CDN.get(hl_theme, HIGHLIGHT_THEME_CDN["dracula"])
    
    # Line count
    lines = code.split('\n')
    line_count = len(lines)
    gutter_width = max(40, len(str(line_count)) * 12 + 28)
    
    # Generate line HTML
    line_html = ""
    for i, line in enumerate(lines, 1):
        # Escape HTML
        escaped = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        if escaped == '':
            escaped = ' '
        line_html += f'<div class="line"><span class="ln">{i}</span><span class="lc">{escaped}</span></div>\n'
    
    # Window controls HTML
    window_html = ""
    if show_window_controls:
        window_html = f"""
        <div class="window-controls">
            <span class="dot dot-red"></span>
            <span class="dot dot-yellow"></span>
            <span class="dot dot-green"></span>
            <span class="window-title">{esc(title) if title else f'{lang_name} • {line_count} lines'}</span>
        </div>
        """
    
    # Watermark
    watermark_html = ""
    if watermark:
        watermark_html = f'<div class="watermark">{esc(watermark)}</div>'
    
    # Language badge
    badge_html = ""
    if show_language_badge:
        badge_html = f'<div class="lang-badge">{lang_name}</div>'
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="{hl_css_url}">
<script src="{HIGHLIGHT_JS_CDN}"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  
  body {{
    width: {width}px;
    height: {height}px;
    background: {t['background']};
    font-family: {t['font_family']};
    font-size: {t['font_size']};
    color: {t['text']};
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
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
    padding: 14px 18px;
    background: rgba(0,0,0,0.15);
    border-bottom: 1px solid {t['border']};
    gap: 8px;
    flex-shrink: 0;
  }}
  
  .dot {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
  }}
  .dot-red {{ background: #ff5f56; }}
  .dot-yellow {{ background: #ffbd2e; }}
  .dot-green {{ background: #27c93f; }}
  
  .window-title {{
    flex: 1;
    text-align: center;
    font-size: 12px;
    color: {t['gutter']};
    margin-right: 44px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  
  .code-area {{
    flex: 1;
    overflow: hidden;
    display: flex;
    position: relative;
  }}
  
  .gutter {{
    width: {gutter_width}px;
    flex-shrink: 0;
    background: rgba(0,0,0,0.12);
    border-right: 1px solid {t['border']};
    padding-top: 16px;
    text-align: right;
    user-select: none;
  }}
  
  .code-content {{
    flex: 1;
    overflow: hidden;
    padding: 16px 24px;
    position: relative;
  }}
  
  .line {{
    display: flex;
    min-height: 1.65em;
    line-height: 1.65em;
    position: relative;
  }}
  
  .ln {{
    display: inline-block;
    width: {gutter_width - 16}px;
    padding-right: 14px;
    text-align: right;
    color: {t['gutter']};
    font-size: 0.85em;
    user-select: none;
    flex-shrink: 0;
    opacity: 0.5;
  }}
  
  .lc {{
    flex: 1;
    white-space: pre;
    tab-size: 4;
  }}
  
  .watermark {{
    position: absolute;
    bottom: 16px;
    right: 24px;
    font-size: 12px;
    color: {t['watermark_color']};
    font-family: {t['font_family']};
    pointer-events: none;
    z-index: 10;
  }}
  
  .lang-badge {{
    position: absolute;
    top: 16px;
    right: 24px;
    background: {t['accent']};
    color: {t['background']};
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.3px;
    z-index: 10;
  }}
</style>
</head>
<body>
<div class="container">
  <div class="window">
    {window_html}
    <div class="code-area">
      <div class="gutter">
        {'<br>'.join(str(i) for i in range(1, line_count + 1))}
      </div>
      <div class="code-content">
        <pre><code class="language-{language}">{code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</code></pre>
        {badge_html}
        {watermark_html}
      </div>
    </div>
  </div>
</div>
<script>hljs.highlightAll();</script>
</body>
</html>"""
