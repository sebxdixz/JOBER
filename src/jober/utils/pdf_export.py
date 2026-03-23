"""Exportación de Markdown a PDF usando Playwright como motor de renderizado."""

from __future__ import annotations

import asyncio
from pathlib import Path

import markdown


# ── Plantilla HTML profesional para CVs ────────────────────────────────────

CV_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4;
    margin: 20mm 18mm 20mm 18mm;
  }}
  * {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }}
  body {{
    font-family: 'Segoe UI', Calibri, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.5;
    color: #1a1a1a;
    background: #fff;
  }}
  h1 {{
    font-size: 22pt;
    font-weight: 700;
    color: #0a2540;
    margin-bottom: 4px;
    border-bottom: 2.5px solid #0a2540;
    padding-bottom: 6px;
  }}
  h2 {{
    font-size: 13pt;
    font-weight: 700;
    color: #0a2540;
    margin-top: 16px;
    margin-bottom: 6px;
    border-bottom: 1px solid #c8d6e5;
    padding-bottom: 3px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  h3 {{
    font-size: 11pt;
    font-weight: 600;
    color: #2c3e50;
    margin-top: 10px;
    margin-bottom: 2px;
  }}
  p {{
    margin-bottom: 6px;
  }}
  ul {{
    margin-left: 18px;
    margin-bottom: 8px;
  }}
  li {{
    margin-bottom: 2px;
  }}
  strong {{
    color: #0a2540;
  }}
  em {{
    color: #555;
  }}
  a {{
    color: #2563eb;
    text-decoration: none;
  }}
  hr {{
    border: none;
    border-top: 1px solid #dde3ea;
    margin: 12px 0;
  }}
  code {{
    background: #f0f4f8;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 9.5pt;
  }}
  .content {{
    max-width: 100%;
  }}
</style>
</head>
<body>
<div class="content">
{content}
</div>
</body>
</html>"""


# ── Plantilla HTML para cartas de presentación ────────────────────────────

COVER_LETTER_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4;
    margin: 25mm 22mm 25mm 22mm;
  }}
  * {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }}
  body {{
    font-family: 'Segoe UI', Calibri, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.65;
    color: #1a1a1a;
    background: #fff;
  }}
  h1 {{
    font-size: 18pt;
    font-weight: 700;
    color: #0a2540;
    margin-bottom: 18px;
  }}
  h2 {{
    font-size: 13pt;
    font-weight: 600;
    color: #0a2540;
    margin-top: 14px;
    margin-bottom: 8px;
  }}
  p {{
    margin-bottom: 12px;
    text-align: justify;
  }}
  strong {{
    color: #0a2540;
  }}
  .content {{
    max-width: 100%;
  }}
</style>
</head>
<body>
<div class="content">
{content}
</div>
</body>
</html>"""


def markdown_to_html(md_text: str, template: str = "cv") -> str:
    """Convierte Markdown a HTML con la plantilla correspondiente."""
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br"],
    )
    
    if template == "cover_letter":
        return COVER_LETTER_HTML_TEMPLATE.format(content=html_body)
    return CV_HTML_TEMPLATE.format(content=html_body)


async def html_to_pdf(html_content: str, output_path: Path) -> Path:
    """Renderiza HTML a PDF usando Playwright Chromium."""
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.set_content(html_content, wait_until="networkidle")
        
        await page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            margin={
                "top": "0mm",
                "bottom": "0mm",
                "left": "0mm",
                "right": "0mm",
            },
        )
        
        await browser.close()
    
    return output_path


async def export_cv_to_pdf(md_text: str, output_path: Path) -> Path:
    """Convierte un CV en Markdown a PDF profesional."""
    html = markdown_to_html(md_text, template="cv")
    return await html_to_pdf(html, output_path)


async def export_cover_letter_to_pdf(md_text: str, output_path: Path) -> Path:
    """Convierte una carta de presentación en Markdown a PDF profesional."""
    html = markdown_to_html(md_text, template="cover_letter")
    return await html_to_pdf(html, output_path)


def export_cv_to_pdf_sync(md_text: str, output_path: Path) -> Path:
    """Versión sincrónica de export_cv_to_pdf."""
    return asyncio.run(export_cv_to_pdf(md_text, output_path))


def export_cover_letter_to_pdf_sync(md_text: str, output_path: Path) -> Path:
    """Versión sincrónica de export_cover_letter_to_pdf."""
    return asyncio.run(export_cover_letter_to_pdf(md_text, output_path))
