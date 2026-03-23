"""Agente scraper de ofertas — usa Playwright para extraer datos de ofertas laborales."""

from __future__ import annotations

from langchain_core.messages import SystemMessage, HumanMessage

from jober.core.config import get_llm
from jober.core.models import OfertaTrabajo
from jober.core.state import JoberState
from jober.utils.llm_helpers import strip_markdown_fences


EXTRACTION_PROMPT = """Eres un experto en extracción de datos de ofertas laborales.
Recibirás el HTML/texto de una página de oferta de trabajo.

Extrae la siguiente información y responde en JSON válido:
{{
    "titulo": "...",
    "empresa": "...",
    "ubicacion": "...",
    "modalidad": "remoto|hibrido|presencial",
    "descripcion": "...",
    "requisitos": ["req1", "req2"],
    "nice_to_have": ["nice1", "nice2"],
    "salario": "..."
}}

Si un campo no está disponible, usa string vacío o lista vacía.
Responde SOLO con el JSON."""


def detect_platform(url: str) -> str:
    """Detecta la plataforma a partir de la URL."""
    url_lower = url.lower()
    if "getonbrd" in url_lower:
        return "getonbrd"
    elif "meetfrank" in url_lower:
        return "meetfrank"
    elif "linkedin" in url_lower:
        return "linkedin"
    return "unknown"


async def scrape_job_page(url: str) -> str:
    """Usa Playwright para obtener el contenido de la página de la oferta."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            content = await page.content()
        finally:
            await browser.close()

    return content


def clean_html_to_text(html: str) -> str:
    """Convierte HTML a texto plano usando BeautifulSoup."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


async def job_scraper_node(state: JoberState) -> dict:
    """Nodo LangGraph: scrapea una oferta y extrae datos estructurados."""
    url = state.job_url
    if not url:
        return {"error": "No se proporcionó URL de oferta."}

    platform = detect_platform(url)

    try:
        html = await scrape_job_page(url)
    except Exception as e:
        return {"error": f"Error al scrapear {url}: {e}"}

    page_text = clean_html_to_text(html)

    # Limitar texto para no exceder contexto del LLM
    max_chars = 8000
    if len(page_text) > max_chars:
        page_text = page_text[:max_chars] + "\n...[truncado]"

    llm = get_llm(temperature=0.0)

    response = await llm.ainvoke([
        SystemMessage(content=EXTRACTION_PROMPT),
        HumanMessage(content=f"URL: {url}\nPlataforma: {platform}\n\nContenido:\n{page_text}"),
    ])

    try:
        clean_json = strip_markdown_fences(response.content)
        oferta = OfertaTrabajo.model_validate_json(clean_json)
        oferta.url = url
        oferta.plataforma = platform
    except Exception:
        oferta = OfertaTrabajo(url=url, plataforma=platform, descripcion=page_text[:2000])

    return {
        "oferta": oferta,
        "current_agent": "job_scraper",
        "next_step": "cv_writer",
    }
