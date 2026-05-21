"""
Screenshot service — renders HTML code shots to PNG using Playwright.
"""

import io
import asyncio
from typing import Optional
from pathlib import Path
from playwright.async_api import async_playwright

# Singleton browser instance
_browser = None
_browser_lock = asyncio.Lock()


async def get_browser():
    """Get or create a persistent browser instance."""
    global _browser
    if _browser is None or not _browser.is_connected():
        async with _browser_lock:
            if _browser is None or not _browser.is_connected():
                playwright = await async_playwright().start()
                _browser = await playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-web-security',
                        '--font-render-hinting=none',
                    ]
                )
    return _browser


async def render_screenshot(
    html: str,
    width: int = 900,
    height: int = 500,
    device_scale_factor: float = 2.0,
    full_page: bool = False,
) -> bytes:
    """Render an HTML string to a PNG screenshot.
    
    Args:
        html: Full HTML document string
        width: Viewport width in CSS pixels
        height: Viewport height in CSS pixels
        device_scale_factor: 2.0 = retina quality (2x pixel density)
        full_page: If True, capture full page height instead of viewport
    
    Returns:
        PNG image bytes
    """
    browser = await get_browser()
    context = await browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=device_scale_factor,
    )
    page = await context.new_page()
    
    try:
        await page.set_content(html, wait_until="networkidle", timeout=15000)
        # Wait for highlight.js to finish syntax highlighting
        await page.wait_for_timeout(500)
        
        if full_page:
            screenshot = await page.screenshot(full_page=True, type="png")
        else:
            screenshot = await page.screenshot(type="png")
        
        return screenshot
    finally:
        await context.close()


async def shutdown():
    """Clean up the browser instance."""
    global _browser
    if _browser:
        await _browser.close()
        _browser = None
