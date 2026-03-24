"""Job scraping agent.

Prefers structured JSON-LD extraction, then plain HTTP, and falls back to Playwright.
"""

from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from langchain_core.messages import HumanMessage, SystemMessage

from jober.core.config import get_llm
from jober.core.logging import logger
from jober.core.models import OfertaTrabajo
from jober.core.prompts import get_prompt
from jober.core.state import JoberState, view_state
from jober.utils.llm_helpers import ainvoke_with_retry, strip_markdown_fences


def detect_platform(url: str) -> str:
    """Detect the platform from the job URL."""
    url_lower = url.lower()
    if "getonbrd" in url_lower:
        return "getonbrd"
    if "meetfrank" in url_lower:
        return "meetfrank"
    if "linkedin" in url_lower:
        return "linkedin"
    return "unknown"


def fetch_job_page_http(url: str) -> str:
    """Fetch job HTML through a standard HTTP request."""
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
    """Fetch job page content.

    Strategy:
    1. Plain HTTP
    2. Playwright fallback if HTML is empty or too small
    """
    try:
        html = fetch_job_page_http(url)
        if html and len(html) > 2000:
            return html
    except Exception:
        logger.exception("HTTP scraping failed for {}; using Playwright fallback", url)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)
            content = await page.content()
        except Exception as exc:
            logger.warning("Primary Playwright navigation failed for {}: {}", url, exc)
            try:
                await page.wait_for_timeout(2000)
                content = await page.content()
            except Exception:
                raise exc
        finally:
            await browser.close()

    return content


def clean_html_to_text(html: str) -> str:
    """Convert HTML to plain text with BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return " ".join(BeautifulSoup(text, "html.parser").get_text(" ", strip=True).split())


def _iter_jobposting_nodes(payload) -> list[dict]:
    nodes: list[dict] = []

    def _walk(value) -> None:
        if isinstance(value, list):
            for item in value:
                _walk(item)
            return
        if not isinstance(value, dict):
            return

        node_type = value.get("@type") or value.get("type")
        if isinstance(node_type, list):
            node_types = [str(item) for item in node_type]
        elif node_type:
            node_types = [str(node_type)]
        else:
            node_types = []

        if any(item.lower() == "jobposting" for item in node_types):
            nodes.append(value)

        for key in ("@graph", "mainEntity", "mainEntityOfPage"):
            nested = value.get(key)
            if nested:
                _walk(nested)

    _walk(payload)
    return nodes


def _json_ld_script_payloads(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    payloads: list[dict] = []

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        payloads.extend(_iter_jobposting_nodes(payload))

    return payloads


def _json_ld_company_name(job_data: dict) -> str:
    org = job_data.get("hiringOrganization")
    if isinstance(org, dict):
        return str(org.get("name", "")).strip()
    if isinstance(org, list):
        for item in org:
            if isinstance(item, dict) and item.get("name"):
                return str(item.get("name", "")).strip()
    return ""


def _json_ld_location(job_data: dict) -> str:
    locations = job_data.get("jobLocation")
    if not locations:
        locations = job_data.get("applicantLocationRequirements")
    if isinstance(locations, dict):
        locations = [locations]
    if not isinstance(locations, list):
        locations = []

    parts: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address", location)
        if not isinstance(address, dict):
            continue
        for key in ("addressLocality", "addressRegion", "addressCountry", "name"):
            value = str(address.get(key, "")).strip()
            if value and value not in parts:
                parts.append(value)
        if parts:
            break

    return ", ".join(parts)


def _split_requirement_text(value) -> list[str]:
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(_split_requirement_text(item))
        return items
    if not value:
        return []

    text = _strip_html(str(value))
    raw_parts = [
        part.strip(" -•\t")
        for part in re.split(r"(?:\n+|•| - |;|\|)", text)
        if part.strip(" -•\t")
    ]

    items: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        if len(part) < 3:
            continue
        key = part.lower()
        if key not in seen:
            seen.add(key)
            items.append(part)
    return items


def _json_ld_requirements(job_data: dict) -> list[str]:
    requirements: list[str] = []
    for key in ("qualifications", "skills", "experienceRequirements", "responsibilities"):
        requirements.extend(_split_requirement_text(job_data.get(key)))

    seen: set[str] = set()
    unique: list[str] = []
    for item in requirements:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:20]


def _json_ld_salary(job_data: dict) -> str:
    salary = job_data.get("baseSalary")
    if not isinstance(salary, dict):
        return ""
    currency = str(salary.get("currency", "")).strip()
    value = salary.get("value")
    if isinstance(value, dict):
        min_value = value.get("minValue")
        max_value = value.get("maxValue")
        unit = str(value.get("unitText", "")).strip()
        if min_value and max_value:
            return f"{min_value}-{max_value} {currency} {unit}".strip()
        if min_value:
            return f"{min_value} {currency} {unit}".strip()
    elif value:
        return f"{value} {currency}".strip()
    return currency


def _infer_modalidad(title: str, description: str, job_data: dict) -> str:
    blob = f"{title} {description}".lower()
    job_location_type = str(job_data.get("jobLocationType", "")).upper()
    if job_location_type == "TELECOMMUTE" or any(marker in blob for marker in ["remote", "remoto", "work from home", "anywhere"]):
        return "remoto"
    if any(marker in blob for marker in ["hybrid", "hibrido", "híbrido"]):
        return "hibrido"
    if any(marker in blob for marker in ["onsite", "presencial"]):
        return "presencial"
    return ""


def extract_jobposting_json_ld(html: str, url: str, platform: str) -> OfertaTrabajo | None:
    """Try to extract a job directly from schema.org JobPosting JSON-LD."""
    for job_data in _json_ld_script_payloads(html):
        title = str(job_data.get("title") or job_data.get("name") or "").strip()
        description = _strip_html(str(job_data.get("description", "")))
        if not title and not description:
            continue

        oferta = OfertaTrabajo(
            url=url,
            titulo=title,
            empresa=_json_ld_company_name(job_data),
            ubicacion=_json_ld_location(job_data),
            modalidad=_infer_modalidad(title, description, job_data),
            descripcion=description,
            requisitos=_json_ld_requirements(job_data),
            nice_to_have=[],
            salario=_json_ld_salary(job_data),
            plataforma=platform,
        )
        return oferta

    return None


async def job_scraper_node(state: JoberState) -> dict:
    """LangGraph node that scrapes a job page and extracts structured data."""
    state = view_state(state)
    url = state.job_url
    if not url:
        return {"error": "No se proporciono URL de oferta."}

    platform = detect_platform(url)

    try:
        html = await scrape_job_page(url)
    except Exception as exc:
        logger.exception("Error scraping {}", url)
        return {"error": f"Error al scrapear {url}: {exc}"}

    structured_offer = extract_jobposting_json_ld(html, url, platform)
    if structured_offer is not None:
        logger.info("Using JSON-LD job extraction for {}", url)
        return {
            "oferta": structured_offer,
            "current_agent": "job_scraper",
            "next_step": "cv_writer",
        }

    page_text = clean_html_to_text(html)
    if len(page_text) > 8000:
        page_text = page_text[:8000] + "\n...[truncado]"

    llm = get_llm(temperature=0.0)
    try:
        response = await ainvoke_with_retry(
            llm,
            [
                SystemMessage(content=get_prompt("job_scraper_extraction")),
                HumanMessage(content=f"URL: {url}\nPlataforma: {platform}\n\nContenido:\n{page_text}"),
            ],
            operation=f"job extraction for {url}",
        )
    except Exception as exc:
        logger.exception("LLM extraction failed for {}", url)
        return {"error": f"Error extrayendo oferta con LLM: {exc}"}

    try:
        clean_json = strip_markdown_fences(response.content)
        oferta = OfertaTrabajo.model_validate_json(clean_json)
        oferta.url = url
        oferta.plataforma = platform
    except Exception:
        logger.exception("Could not parse extracted job payload for {}", url)
        oferta = OfertaTrabajo(url=url, plataforma=platform, descripcion=page_text[:2000])

    return {
        "oferta": oferta,
        "current_agent": "job_scraper",
        "next_step": "cv_writer",
    }
