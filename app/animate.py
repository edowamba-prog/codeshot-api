"""
Animation engine — generates animated code typing GIF/MP4 from code screenshots.
Uses CSS masking for efficient frame capture (one page load, many frames).
"""

import os
import io
import tempfile
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Literal
from playwright.async_api import async_playwright
from .renderer import build_html


ANIMATION_EFFECTS = {
    "typewriter": "Characters type out one by one with a blinking cursor",
    "reveal-line": "Lines appear one at a time from top to bottom",
    "fade-in": "Code fades in all at once with a smooth transition",
}


def build_animated_html(
    code: str,
    language: str,
    theme: str = "dracula",
    effect: str = "typewriter",
    title: Optional[str] = None,
    watermark: Optional[str] = None,
    duration: float = 4.0,
    cursor: bool = True,
    preset: Optional[str] = None,
    brand: Optional[dict] = None,
) -> str:
    """Build an HTML page with CSS animation for code reveal."""
    from .themes import THEMES, SOCIAL_PRESETS, LANGUAGES
    
    t = THEMES.get(theme, THEMES["dracula"])
    if brand:
        t = {**t, **{k: v for k, v in brand.items() if v is not None}}
    
    lang_name = LANGUAGES.get(language, language.capitalize())
    lines = code.split('\n')
    line_count = len(lines)
    total_chars = sum(len(l) + 1 for l in lines)
    
    # Generate syntax-highlighted code
    esc = lambda s: s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    
    line_html = ""
    for i, line in enumerate(lines, 1):
        escaped = esc(line) if line else ' '
        line_html += f'<div class="line"><span class="ln">{i}</span><span class="lc">{escaped}</span></div>\n'
    
    # CSS animation based on effect
    if effect == "typewriter":
        animation_css = f"""
        .reveal-mask {{
            position: absolute;
            top: 0; right: 0;
            width: 100%; height: 100%;
            background: {t['background']};
            animation: typewrite {duration}s steps({min(total_chars, 200)}, end) forwards;
            pointer-events: none;
        }}
        @keyframes typewrite {{
            0% {{ width: 100%; }}
            100% {{ width: 0%; }}
        }}
        .cursor {{
            display: {'inline-block' if cursor else 'none'};
            width: 2px;
            height: 1.2em;
            background: {t['accent']};
            animation: blink 0.8s step-end infinite;
            vertical-align: text-bottom;
            margin-left: 2px;
        }}
        @keyframes blink {{
            50% {{ opacity: 0; }}
        }}
        """
    elif effect == "reveal-line":
        animation_css = f"""
        .code-content .line {{
            opacity: 0;
            animation: revealLine 0.3s ease-out forwards;
        }}
        {''.join(f'.code-content .line:nth-child({i+1}) {{ animation-delay: {i * duration / max(line_count, 1)}s; }}' for i in range(line_count))}
        @keyframes revealLine {{
            0% {{ opacity: 0; transform: translateY(8px); }}
            100% {{ opacity: 1; transform: translateY(0); }}
        }}
        """
    else:  # fade-in
        animation_css = f"""
        .code-content {{
            animation: fadeIn {duration}s ease-out forwards;
        }}
        @keyframes fadeIn {{
            0% {{ opacity: 0; filter: blur(4px); }}
            100% {{ opacity: 1; filter: blur(0); }}
        }}
        """
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  
  body {{
    width: 900px;
    height: 500px;
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
    flex: 1;
    text-align: center;
    font-size: 11px;
    color: {t['gutter']};
    margin-right: 38px;
  }}
  
  .code-area {{
    flex: 1;
    display: flex;
    position: relative;
    overflow: hidden;
  }}
  
  .code-content {{
    flex: 1;
    padding: 14px 20px;
    font-family: {t['font_family']};
    font-size: {t['font_size']};
    line-height: 1.6;
    position: relative;
  }}
  
  .line {{
    display: flex;
    min-height: 1.6em;
    white-space: pre;
    tab-size: 4;
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
  .lc {{ flex: 1; position: relative; }}
  
  {animation_css}
  
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
      <span class="dot dot-red"></span>
      <span class="dot dot-yellow"></span>
      <span class="dot dot-green"></span>
      <span class="window-title">{esc(title or f'{lang_name} • {line_count} lines')}</span>
    </div>
    <div class="code-area">
      <div class="code-content">
        {line_html}
        <div class="reveal-mask"></div>
        {'<span class="cursor"></span>' if cursor else ''}
        <div class="lang-badge">{lang_name}</div>
        {f'<div class="watermark">{esc(watermark)}</div>' if watermark else ''}
      </div>
    </div>
  </div>
</div>
</body>
</html>"""


async def render_animation(
    html: str,
    width: int = 900,
    height: int = 500,
    duration: float = 4.0,
    fps: int = 24,
    format: Literal["mp4", "gif"] = "mp4",
    device_scale_factor: float = 2.0,
) -> bytes:
    """Render an animated code screenshot to MP4 or GIF.
    
    Uses JavaScript-driven frame capture for precise animation control.
    """
    playwright = await async_playwright().start()
    
    try:
        browser = await playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        )
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=device_scale_factor,
        )
        page = await context.new_page()
        
        total_frames = int(duration * fps)
        frame_interval_ms = int((duration / total_frames) * 1000)
        
        # Load the page with the reveal mask
        await page.set_content(html, wait_until="networkidle", timeout=15000)
        
        # Find the reveal mask element and animate it via JS
        # Instead of CSS animation, we manually set the mask width each frame
        with tempfile.TemporaryDirectory() as tmpdir:
            frames = []
            
            for i in range(total_frames):
                progress = (i + 1) / total_frames  # 0.0 → 1.0
                
                # Set mask width: 100% at start, 0% at end
                mask_width_pct = (1.0 - progress) * 100
                
                await page.evaluate(f"""
                    const mask = document.querySelector('.reveal-mask');
                    if (mask) {{
                        mask.style.width = '{mask_width_pct}%';
                        mask.style.transition = 'none';
                    }}
                """)
                
                # Small wait for render
                await page.wait_for_timeout(10)
                
                frame_path = os.path.join(tmpdir, f"frame_{i:04d}.png")
                await page.screenshot(path=frame_path, type="png")
                frames.append(frame_path)
            
            # Use ffmpeg to compile frames
            output_path = os.path.join(tmpdir, f"output.{format}")
            
            if format == "mp4":
                cmd = [
                    "ffmpeg", "-y",
                    "-framerate", str(fps),
                    "-i", os.path.join(tmpdir, "frame_%04d.png"),
                    "-c:v", "mpeg4",
                    "-q:v", "5",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    output_path
                ]
            else:  # gif
                palette_path = os.path.join(tmpdir, "palette.png")
                subprocess.run([
                    "ffmpeg", "-y",
                    "-framerate", str(fps),
                    "-i", os.path.join(tmpdir, "frame_%04d.png"),
                    "-vf", f"fps={fps},palettegen=stats_mode=diff",
                    palette_path
                ], capture_output=True, timeout=30)
                
                cmd = [
                    "ffmpeg", "-y",
                    "-framerate", str(fps),
                    "-i", os.path.join(tmpdir, "frame_%04d.png"),
                    "-i", palette_path,
                    "-lavfi", f"fps={fps},paletteuse=dither=bayer:bayer_scale=5",
                    "-loop", "0",
                    output_path
                ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[:300]}")
            
            with open(output_path, 'rb') as f:
                return f.read()
    
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()
