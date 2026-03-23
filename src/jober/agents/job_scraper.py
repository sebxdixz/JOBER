"""Agente scraper de ofertas.

Prefiere HTTP simple y usa Playwright solo como fallback.
"""

from __future__ import annotations

from urllib.request import Request, urlopen

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


def fetch_job_page_http(url: str) -> str:
    """Obtiene HTML de una oferta usando HTTP simple."""
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        },
    )
    with urlopen(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


async def scrape_job_page(url: str) -> str:
    """Obtiene el contenido de la pagina de la oferta.

    Estrategia:
    1. HTTP simple
    2. Fallback a Playwright si la pagina viene vacia o muy pobre
    """
    try:
        html = fetch_job_page_http(url)
        if html and len(html) > 2000:
            return html
    except Exception:
        pass

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        try:
            # Usar domcontentloaded en lugar de networkidle para mayor velocidad
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            # Reducir timeout de espera
            await page.wait_for_timeout(1000)
            content = await page.content()
        except Exception as e:
            # Si falla, intentar con una espera más larga
            try:
                await page.wait_for_timeout(2000)
                content = await page.content()
            except Exception:
                raise e
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

    response = None
    for attempt in range(3):
        try:
            response = await llm.ainvoke([
                SystemMessage(content=EXTRACTION_PROMPT),
                HumanMessage(content=f"URL: {url}\nPlataforma: {platform}\n\nContenido:\n{page_text}"),
            ])
            break
        except Exception as exc:
            if "429" in str(exc) or "rate" in str(exc).lower():
                import asyncio

                await asyncio.sleep(5 * (attempt + 1))
                continue
            return {"error": f"Error extrayendo oferta con LLM: {exc}"}

    if response is None:
        return {"error": "No se pudo extraer la oferta: rate limit del LLM."}

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
