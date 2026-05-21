"""
Diff mode — beautiful code change visualization for changelogs and PRs.
"""

import difflib
from typing import Optional
from .themes import THEMES


def compute_diff(old_code: str, new_code: str, context_lines: int = 3) -> list[dict]:
    """Compute a unified diff between old and new code.
    
    Returns a list of hunks, each containing lines with change type markers.
    """
    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)
    
    differ = difflib.unified_diff(
        old_lines, new_lines,
        fromfile='old', tofile='new',
        n=context_lines
    )
    
    hunks = []
    current_hunk = {"header": "", "lines": []}
    
    for line in differ:
        if line.startswith('@@'):
            if current_hunk["lines"]:
                hunks.append(current_hunk)
            current_hunk = {"header": line.strip(), "lines": []}
        elif line.startswith('---') or line.startswith('+++'):
            continue
        else:
            change_type = "context"
            if line.startswith('-'):
                change_type = "removed"
            elif line.startswith('+'):
                change_type = "added"
            current_hunk["lines"].append({
                "text": line[1:].rstrip('\n') if len(line) > 1 else line.rstrip('\n'),
                "type": change_type
            })
    
    if current_hunk["lines"]:
        hunks.append(current_hunk)
    
    return hunks


def count_changes(old_code: str, new_code: str) -> dict:
    """Count additions and deletions."""
    added = 0
    removed = 0
    for line in difflib.unified_diff(
        old_code.splitlines(keepends=True),
        new_code.splitlines(keepends=True),
        n=0
    ):
        if line.startswith('+') and not line.startswith('+++'):
            added += 1
        elif line.startswith('-') and not line.startswith('---'):
            removed += 1
    return {"added": added, "removed": removed, "total_changes": added + removed}


def build_diff_html(
    old_code: str,
    new_code: str,
    language: str = "plaintext",
    theme: str = "dracula",
    title: Optional[str] = None,
    watermark: Optional[str] = None,
    mode: str = "unified",
) -> str:
    """Build HTML for a diff screenshot.
    
    Args:
        old_code: Original code
        new_code: Updated code
        language: Programming language
        theme: Theme name
        title: Window title
        watermark: Watermark text
        mode: 'unified' (single view) or 'side-by-side' (two columns)
    """
    t = THEMES.get(theme, THEMES["dracula"])
    changes = count_changes(old_code, new_code)
    hunks = compute_diff(old_code, new_code)
    
    # Escape HTML
    def esc(s):
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    
    if mode == "side-by-side":
        return _build_side_by_side(old_code, new_code, language, t, changes, title, watermark)
    
    # Unified mode
    diff_lines = []
    for hunk in hunks:
        if hunk["header"]:
            diff_lines.append(f'<div class="hunk-header">{esc(hunk["header"])}</div>')
        for line in hunk["lines"]:
            css_class = f"diff-{line['type']}"
            prefix = {"added": "+", "removed": "-", "context": " "}[line["type"]]
            diff_lines.append(
                f'<div class="diff-line {css_class}">'
                f'<span class="diff-prefix">{prefix}</span>'
                f'<span class="diff-text">{esc(line["text"]) if line["text"] else " "}</span>'
                f'</div>'
            )
    
    diff_body = '\n'.join(diff_lines)
    
    summary = f"+{changes['added']} −{changes['removed']}"
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  
  body {{
    width: 1000px;
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
    padding: 40px;
  }}
  
  .window {{
    background: {t['background']};
    border: 1px solid {t['border']};
    border-radius: {t['border_radius']};
    box-shadow: {t['shadow']};
    overflow: hidden;
    position: relative;
  }}
  
  .window-controls {{
    display: flex;
    align-items: center;
    padding: 14px 18px;
    background: rgba(0,0,0,0.15);
    border-bottom: 1px solid {t['border']};
    gap: 8px;
  }}
  .dot {{ width: 12px; height: 12px; border-radius: 50%; }}
  .dot-red {{ background: #ff5f56; }}
  .dot-yellow {{ background: #ffbd2e; }}
  .dot-green {{ background: #27c93f; }}
  .window-title {{
    flex: 1; text-align: center; font-size: 12px;
    color: {t['gutter']}; margin-right: 44px;
  }}
  
  .diff-summary {{
    display: flex;
    gap: 16px;
    padding: 12px 20px;
    background: rgba(0,0,0,0.08);
    border-bottom: 1px solid {t['border']};
    font-size: 12px;
  }}
  .diff-stat {{ display: flex; align-items: center; gap: 6px; }}
  .diff-stat.added {{ color: #3fb950; }}
  .diff-stat.removed {{ color: #f85149; }}
  .diff-stat.total {{ color: {t['gutter']}; }}
  
  .diff-body {{
    padding: 16px 20px;
    font-family: {t['font_family']};
    font-size: {t['font_size']};
    line-height: 1.65;
  }}
  
  .hunk-header {{
    color: {t['accent']};
    font-size: 0.85em;
    padding: 8px 0 4px;
  }}
  
  .diff-line {{
    display: flex;
    min-height: 1.65em;
    line-height: 1.65em;
  }}
  .diff-line.diff-added {{
    background: rgba(63,185,80,0.12);
    border-left: 3px solid #3fb950;
  }}
  .diff-line.diff-removed {{
    background: rgba(248,81,73,0.12);
    border-left: 3px solid #f85149;
  }}
  .diff-line.diff-context {{
    opacity: 0.7;
  }}
  
  .diff-prefix {{
    width: 20px;
    flex-shrink: 0;
    text-align: center;
    font-weight: 700;
    user-select: none;
  }}
  .diff-added .diff-prefix {{ color: #3fb950; }}
  .diff-removed .diff-prefix {{ color: #f85149; }}
  .diff-context .diff-prefix {{ color: {t['gutter']}; }}
  
  .diff-text {{
    flex: 1;
    white-space: pre;
    tab-size: 4;
  }}
  
  .watermark {{
    position: absolute;
    bottom: 12px;
    right: 20px;
    font-size: 11px;
    color: {t['watermark_color']};
    pointer-events: none;
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
      <span class="window-title">{esc(title or 'Code Diff')}</span>
    </div>
    <div class="diff-summary">
      <div class="diff-stat added">🟢 +{changes['added']} additions</div>
      <div class="diff-stat removed">🔴 −{changes['removed']} deletions</div>
      <div class="diff-stat total">{changes['total_changes']} changes</div>
    </div>
    <div class="diff-body">
      {diff_body}
    </div>
    {f'<div class="watermark">{esc(watermark)}</div>' if watermark else ''}
  </div>
</div>
</body>
</html>"""


def _build_side_by_side(
    old_code: str,
    new_code: str,
    language: str,
    t: dict,
    changes: dict,
    title: Optional[str],
    watermark: Optional[str],
) -> str:
    """Build side-by-side diff HTML."""
    def esc(s):
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    
    old_lines = [esc(l) for l in old_code.split('\n')]
    new_lines = [esc(l) for l in new_code.split('\n')]
    
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    
    left_rows = []
    right_rows = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for k in range(i1, i2):
                left_rows.append(f'<div class="sbs-line sbs-context"><span class="sbs-ln">{k+1}</span><span class="sbs-text">{old_lines[k] if old_lines[k] else " "}</span></div>')
            for k in range(j1, j2):
                right_rows.append(f'<div class="sbs-line sbs-context"><span class="sbs-ln">{k+1}</span><span class="sbs-text">{new_lines[k] if new_lines[k] else " "}</span></div>')
        elif tag == 'replace':
            for k in range(i1, i2):
                left_rows.append(f'<div class="sbs-line sbs-removed"><span class="sbs-ln">{k+1}</span><span class="sbs-text">{old_lines[k] if old_lines[k] else " "}</span></div>')
            for k in range(j1, j2):
                right_rows.append(f'<div class="sbs-line sbs-added"><span class="sbs-ln">{k+1}</span><span class="sbs-text">{new_lines[k] if new_lines[k] else " "}</span></div>')
        elif tag == 'delete':
            for k in range(i1, i2):
                left_rows.append(f'<div class="sbs-line sbs-removed"><span class="sbs-ln">{k+1}</span><span class="sbs-text">{old_lines[k] if old_lines[k] else " "}</span></div>')
                right_rows.append(f'<div class="sbs-line sbs-empty"></div>')
        elif tag == 'insert':
            for k in range(j1, j2):
                left_rows.append(f'<div class="sbs-line sbs-empty"></div>')
                right_rows.append(f'<div class="sbs-line sbs-added"><span class="sbs-ln">{k+1}</span><span class="sbs-text">{new_lines[k] if new_lines[k] else " "}</span></div>')
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1200px;
    min-height: 500px;
    background: {t['background']};
    font-family: {t['font_family']};
    font-size: {t['font_size']};
    color: {t['text']};
    display: flex; align-items: center; justify-content: center;
  }}
  .container {{ width: 100%; padding: 30px; }}
  .window {{
    background: {t['background']};
    border: 1px solid {t['border']};
    border-radius: {t['border_radius']};
    box-shadow: {t['shadow']};
    overflow: hidden;
    position: relative;
  }}
  .window-controls {{
    display: flex; align-items: center; padding: 12px 16px;
    background: rgba(0,0,0,0.15); border-bottom: 1px solid {t['border']}; gap: 8px;
  }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .dot-red {{ background: #ff5f56; }} .dot-yellow {{ background: #ffbd2e; }} .dot-green {{ background: #27c93f; }}
  .window-title {{ flex: 1; text-align: center; font-size: 11px; color: {t['gutter']}; margin-right: 36px; }}
  
  .diff-summary {{
    display: flex; gap: 16px; padding: 10px 16px;
    background: rgba(0,0,0,0.08); border-bottom: 1px solid {t['border']}; font-size: 11px;
  }}
  .diff-stat.added {{ color: #3fb950; }} .diff-stat.removed {{ color: #f85149; }} .diff-stat.total {{ color: {t['gutter']}; }}
  
  .sbs-container {{ display: flex; }}
  .sbs-pane {{ flex: 1; padding: 8px 12px; overflow: hidden; }}
  .sbs-pane.left {{ border-right: 1px solid {t['border']}; }}
  .sbs-pane-header {{
    font-size: 10px; color: {t['gutter']}; padding: 4px 0 8px;
    text-transform: uppercase; letter-spacing: 1px; font-weight: 600;
  }}
  .sbs-pane.left .sbs-pane-header {{ color: #f85149; }}
  .sbs-pane.right .sbs-pane-header {{ color: #3fb950; }}
  
  .sbs-line {{
    display: flex; min-height: 1.55em; line-height: 1.55em;
    font-family: {t['font_family']}; font-size: {t['font_size']};
  }}
  .sbs-line.sbs-added {{ background: rgba(63,185,80,0.12); }}
  .sbs-line.sbs-removed {{ background: rgba(248,81,73,0.12); }}
  .sbs-line.sbs-context {{ opacity: 0.65; }}
  .sbs-line.sbs-empty {{ min-height: 1.55em; }}
  .sbs-ln {{
    width: 36px; flex-shrink: 0; text-align: right; padding-right: 10px;
    color: {t['gutter']}; font-size: 0.8em; user-select: none; opacity: 0.5;
  }}
  .sbs-text {{ flex: 1; white-space: pre; tab-size: 4; }}
  .watermark {{
    position: absolute; bottom: 10px; right: 16px; font-size: 10px;
    color: {t['watermark_color']}; pointer-events: none;
  }}
</style>
</head>
<body>
<div class="container">
  <div class="window">
    <div class="window-controls">
      <span class="dot dot-red"></span><span class="dot dot-yellow"></span><span class="dot dot-green"></span>
      <span class="window-title">{esc(title or 'Code Diff — Side by Side')}</span>
    </div>
    <div class="diff-summary">
      <div class="diff-stat added">+{changes['added']} added</div>
      <div class="diff-stat removed">−{changes['removed']} removed</div>
      <div class="diff-stat total">{changes['total_changes']} changes</div>
    </div>
    <div class="sbs-container">
      <div class="sbs-pane left">
        <div class="sbs-pane-header">− Old</div>
        {''.join(left_rows)}
      </div>
      <div class="sbs-pane right">
        <div class="sbs-pane-header">+ New</div>
        {''.join(right_rows)}
      </div>
    </div>
    {f'<div class="watermark">{esc(watermark)}</div>' if watermark else ''}
  </div>
</div>
</body>
</html>"""
