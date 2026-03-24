"""Markdown to PDF export.

Primary path uses Playwright for high-fidelity rendering.
Fallback path uses ReportLab so PDF generation still works when Chromium
cannot be launched in the current environment.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown
from bs4 import BeautifulSoup

from jober.core.logging import logger


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
    """Convert Markdown to HTML with the requested template."""
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br"],
    )

    if template == "cover_letter":
        return COVER_LETTER_HTML_TEMPLATE.format(content=html_body)
    return CV_HTML_TEMPLATE.format(content=html_body)


async def html_to_pdf(html_content: str, output_path: Path) -> Path:
    """Render HTML to PDF.

    Default engine is ReportLab for reliability.
    Set JOBER_PDF_ENGINE=playwright to force Chromium rendering.
    """
    engine = os.getenv("JOBER_PDF_ENGINE", "reportlab").strip().lower()
    if engine != "playwright":
        _html_to_pdf_reportlab(html_content, output_path)
        return output_path

    try:
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
    except Exception:
        _html_to_pdf_reportlab(html_content, output_path)
        return output_path


async def export_cv_to_pdf(md_text: str, output_path: Path) -> Path:
    """Convert CV Markdown to PDF."""
    html = markdown_to_html(md_text, template="cv")
    return await html_to_pdf(html, output_path)


async def export_cover_letter_to_pdf(md_text: str, output_path: Path) -> Path:
    """Convert cover-letter Markdown to PDF."""
    html = markdown_to_html(md_text, template="cover_letter")
    return await html_to_pdf(html, output_path)


def export_cv_to_pdf_sync(md_text: str, output_path: Path) -> Path:
    """Synchronous wrapper for CV PDF export."""
    return asyncio.run(export_cv_to_pdf(md_text, output_path))


def export_cover_letter_to_pdf_sync(md_text: str, output_path: Path) -> Path:
    """Synchronous wrapper for cover-letter PDF export."""
    return asyncio.run(export_cover_letter_to_pdf(md_text, output_path))


def export_latex_to_pdf_sync(tex_text: str, output_path: Path) -> Path | None:
    """Compile standalone LaTeX to PDF if a local engine is available."""
    engine = shutil.which("pdflatex") or shutil.which("xelatex")
    if not engine or not tex_text.strip():
        return None
    timeout_seconds = 15

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        tex_file = tmp_path / "document.tex"
        tex_file.write_text(tex_text, encoding="utf-8")

        try:
            result = subprocess.run(
                [
                    engine,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    str(tex_file.name),
                ],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            logger.error(
                "LaTeX compilation timed out after {}s using {} for {}",
                timeout_seconds,
                Path(engine).name,
                output_path.name,
            )
            return None
        except OSError:
            logger.exception("Failed to start LaTeX engine {}", engine)
            return None
        if result.returncode != 0:
            logger.error(
                "LaTeX compilation failed with {} for {}: {}",
                Path(engine).name,
                output_path.name,
                (result.stderr or result.stdout or "unknown error")[:500],
            )
            return None

        compiled_pdf = tmp_path / "document.pdf"
        if not compiled_pdf.exists():
            logger.error(
                "LaTeX compilation reported success but no PDF was produced for {}",
                output_path.name,
            )
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(compiled_pdf.read_bytes())
        return output_path


def _html_to_pdf_reportlab(html_content: str, output_path: Path) -> None:
    """Pure-Python PDF fallback using ReportLab."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    soup = BeautifulSoup(html_content, "html.parser")
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "JoberNormal",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        spaceAfter=6,
        alignment=TA_JUSTIFY,
    )
    heading1 = ParagraphStyle(
        "JoberH1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0A2540"),
        spaceAfter=10,
    )
    heading2 = ParagraphStyle(
        "JoberH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0A2540"),
        spaceBefore=8,
        spaceAfter=5,
    )
    heading3 = ParagraphStyle(
        "JoberH3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#2C3E50"),
        spaceBefore=6,
        spaceAfter=4,
    )

    story = []
    container = soup.body or soup

    for node in container.find_all(recursive=False):
        tag = getattr(node, "name", None)
        text = " ".join(node.stripped_strings)
        if tag is None:
            continue

        if tag == "h1":
            story.append(Paragraph(escape(text), heading1))
        elif tag == "h2":
            story.append(Paragraph(escape(text.upper()), heading2))
        elif tag == "h3":
            story.append(Paragraph(escape(text), heading3))
        elif tag == "p":
            story.append(Paragraph(_node_to_reportlab_html(node), normal))
        elif tag == "ul":
            items = []
            for li in node.find_all("li", recursive=False):
                items.append(ListItem(Paragraph(_node_to_reportlab_html(li), normal)))
            if items:
                story.append(ListFlowable(items, bulletType="bullet", leftIndent=14))
                story.append(Spacer(1, 4))
        elif tag == "hr":
            story.append(HRFlowable(color=colors.HexColor("#DDE3EA"), thickness=1, width="100%"))
            story.append(Spacer(1, 8))
        elif text:
            story.append(Paragraph(escape(text), normal))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )
    doc.build(story)


def _node_to_reportlab_html(node) -> str:
    """Convert a simple HTML node to ReportLab paragraph markup."""
    from xml.sax.saxutils import escape

    parts: list[str] = []
    for child in node.children:
        child_name = getattr(child, "name", None)
        if child_name is None:
            parts.append(escape(str(child)))
            continue
        text = _node_to_reportlab_html(child)
        if child_name in {"strong", "b"}:
            parts.append(f"<b>{text}</b>")
        elif child_name in {"em", "i"}:
            parts.append(f"<i>{text}</i>")
        elif child_name == "br":
            parts.append("<br/>")
        elif child_name == "code":
            parts.append(f"<font name='Courier'>{text}</font>")
        else:
            parts.append(text)
    return "".join(parts).strip()
