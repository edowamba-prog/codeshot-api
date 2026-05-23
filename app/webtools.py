"""
Agent Web Tools — URL screenshot, scraping, and link preview for AI agents.
Leverages the existing Playwright browser singleton from screenshot.py.
"""

import io
import re
from typing import Optional
from playwright.async_api import async_playwright
from .screenshot import get_browser, render_screenshot


async def capture_url_screenshot(
    url: str,
    width: int = 1280,
    height: int = 800,
    full_page: bool = True,
    device_scale_factor: float = 2.0,
    wait_until: str = "load",
    timeout: int = 30000,
) -> bytes:
    """Take a screenshot of any URL. Returns PNG bytes."""
    browser = await get_browser()
    context = await browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=device_scale_factor,
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until=wait_until, timeout=timeout)
        await page.wait_for_timeout(1000)  # let dynamic content settle
        
        if full_page:
            screenshot = await page.screenshot(full_page=True, type="png")
        else:
            screenshot = await page.screenshot(type="png")
        
        return screenshot
    finally:
        await context.close()


async def scrape_url_text(
    url: str,
    format: str = "markdown",
    timeout: int = 30000,
) -> dict:
    """Scrape a URL and return clean text or markdown content.
    
    Returns dict with: title, text (cleaned), url, metadata
    """
    browser = await get_browser()
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await page.wait_for_timeout(1000)
        
        # Extract page data via JavaScript
        data = await page.evaluate("""() => {
            // Get title
            const title = document.title || '';
            
            // Get meta description
            const metaDesc = document.querySelector('meta[name="description"]')?.content || '';
            
            // Get main content - prefer article/main tags, fall back to body
            const mainEl = document.querySelector('article, main, [role="main"]');
            const contentEl = mainEl || document.body;
            
            // Remove script, style, nav, footer, header elements
            const clone = contentEl.cloneNode(true);
            const removeSelectors = 'script, style, nav, footer, header, iframe, noscript, [aria-hidden="true"], .nav, .navbar, .footer, .sidebar, .ad, .advertisement';
            clone.querySelectorAll(removeSelectors).forEach(el => el.remove());
            
            // Get clean text
            let text = clone.innerText || clone.textContent || '';
            
            // Collapse whitespace
            text = text.replace(/\\n{3,}/g, '\\n\\n').trim();
            
            // Get metadata
            const ogImage = document.querySelector('meta[property="og:image"]')?.content || '';
            const ogTitle = document.querySelector('meta[property="og:title"]')?.content || title;
            const ogDescription = document.querySelector('meta[property="og:description"]')?.content || metaDesc;
            const siteName = document.querySelector('meta[property="og:site_name"]')?.content || '';
            const favicon = document.querySelector('link[rel="icon"]')?.href || 
                           document.querySelector('link[rel="shortcut icon"]')?.href || '';
            
            // Get all links
            const links = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href;
                const linkText = (a.innerText || a.textContent || '').trim().substring(0, 100);
                if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
                    links.push({url: href, text: linkText});
                }
            });
            
            return {
                title: ogTitle,
                description: ogDescription,
                site_name: siteName,
                og_image: ogImage,
                favicon: favicon,
                text: text.substring(0, 50000),
                links: links.slice(0, 100),
            };
        }""")
        
        # Format text as markdown if requested
        if format == "markdown" and data.get("text"):
            # Convert basic structure to markdown
            md_parts = []
            if data.get("title"):
                md_parts.append(f"# {data['title']}\n")
            if data.get("description"):
                md_parts.append(f"> {data['description']}\n")
            md_parts.append(data["text"])
            data["markdown"] = "\n".join(md_parts)
        
        return data
    finally:
        await context.close()


async def get_link_preview(
    url: str,
    timeout: int = 15000,
) -> dict:
    """Get Open Graph / Twitter Card metadata for a URL.
    
    Returns dict with: title, description, image, site_name, url, type
    """
    browser = await get_browser()
    context = await browser.new_context(
        viewport={"width": 1200, "height": 800},
        user_agent=(
            "Mozilla/5.0 (compatible; LinkPreviewBot/1.0; +https://agentkit.dev)"
        ),
    )
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await page.wait_for_timeout(500)
        
        metadata = await page.evaluate("""() => {
            function getMeta(property) {
                // Try og: first
                let el = document.querySelector(`meta[property="og:${property}"]`);
                if (el) return el.content;
                // Try twitter:
                el = document.querySelector(`meta[name="twitter:${property}"]`);
                if (el) return el.content;
                // Fallbacks
                if (property === 'title') return document.title || '';
                if (property === 'description') {
                    el = document.querySelector('meta[name="description"]');
                    return el ? el.content : '';
                }
                if (property === 'image') {
                    el = document.querySelector('meta[property="og:image"]');
                    if (el) return el.content;
                    el = document.querySelector('meta[name="twitter:image"]');
                    return el ? el.content : '';
                }
                return '';
            }
            
            return {
                title: getMeta('title'),
                description: getMeta('description'),
                image: getMeta('image'),
                site_name: getMeta('site_name'),
                type: getMeta('type'),
                url: document.querySelector('meta[property="og:url"]')?.content || window.location.href,
                favicon: document.querySelector('link[rel="icon"]')?.href || 
                         document.querySelector('link[rel="shortcut icon"]')?.href || '',
                theme_color: document.querySelector('meta[name="theme-color"]')?.content || '',
            };
        }""")
        
        return metadata
    finally:
        await context.close()
