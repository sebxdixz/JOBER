"""Agente de busqueda autonoma.

Descubre ofertas con HTTP + parsing HTML simple.
Entrega resultados agrupados por plataforma y tambien intercalados.
"""

from __future__ import annotations

import asyncio
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from jober.core.models import PerfilMaestro


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}

PLATFORM_ORDER = ["linkedin", "getonbrd", "meetfrank"]


def _fetch_html(url: str, timeout: int = 20) -> str:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _extract_links(html: str, base_url: str, matcher) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        full_url = urljoin(base_url, href).split("#")[0]
        if full_url in seen:
            continue
        if matcher(full_url):
            seen.add(full_url)
            urls.append(full_url)

    return urls


def _build_keywords(perfil: PerfilMaestro) -> list[str]:
    prefs = perfil.preferencias
    role_keyword_map = {
        "ai engineer": ["AI Engineer", "Machine Learning", "Python", "Data Scientist"],
        "llm engineer": ["LLM Engineer", "Generative AI", "Python", "LangChain"],
        "ml engineer": ["ML Engineer", "Machine Learning", "Python", "Data Scientist"],
        "mlops engineer": ["MLOps", "Machine Learning", "Python", "Docker"],
        "ai automation engineer": ["AI Automation", "Automation", "Python", "LLMs"],
        "machine learning engineer": ["Machine Learning", "ML Engineer", "Python", "Data Scientist"],
        "data scientist": ["Data Scientist", "Machine Learning", "Python", "Analytics"],
        "backend developer": ["Backend", "Python", "Node.js", "API"],
        "frontend developer": ["Frontend", "React", "JavaScript", "Vue"],
        "full stack": ["Full Stack", "Python", "JavaScript", "React"],
    }

    expanded_keywords: list[str] = []
    for role in prefs.roles_deseados[:3]:
        role_lower = role.lower()
        if role_lower in role_keyword_map:
            expanded_keywords.extend(role_keyword_map[role_lower][:2])
        else:
            expanded_keywords.append(role)

    expanded_keywords.extend(prefs.habilidades_must_have[:2])

    seen: set[str] = set()
    keywords: list[str] = []
    for kw in expanded_keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            keywords.append(kw)

    if not keywords:
        keywords = [perfil.titulo_profesional] if perfil.titulo_profesional else ["developer"]
    return keywords


def _interleave_platform_results(platform_results: dict[str, list[str]]) -> list[str]:
    interleaved: list[str] = []
    max_len = max((len(platform_results.get(platform, [])) for platform in PLATFORM_ORDER), default=0)

    for idx in range(max_len):
        for platform in PLATFORM_ORDER:
            urls = platform_results.get(platform, [])
            if idx < len(urls):
                interleaved.append(urls[idx])

    seen: set[str] = set()
    unique_urls: list[str] = []
    for url in interleaved:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls


async def search_getonbrd(keywords: list[str], max_results: int = 20) -> list[str]:
    """Busca ofertas en GetOnBrd y devuelve lista de URLs."""
    search_query = quote_plus(" ".join(keywords[:3]))
    url = f"https://www.getonbrd.com/empleos?query={search_query}"

    try:
        html = await asyncio.to_thread(_fetch_html, url)
    except Exception:
        return []

    return _extract_links(
        html,
        "https://www.getonbrd.com",
        lambda href: "/empleos/" in href and not href.rstrip("/").endswith("/empleos"),
    )[:max_results]


async def search_linkedin(keywords: list[str], max_results: int = 20) -> list[str]:
    """Busca ofertas en LinkedIn Jobs guest search y devuelve URLs."""
    search_query = quote_plus(" ".join(keywords[:3]))
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        f"?keywords={search_query}&location=&f_TPR=r604800&start=0"
    )

    try:
        html = await asyncio.to_thread(_fetch_html, url)
    except Exception:
        return []

    urls = _extract_links(
        html,
        "https://www.linkedin.com",
        lambda href: "/jobs/view/" in href,
    )
    return [href.split("?")[0] for href in urls[:max_results]]


async def search_meetfrank(keywords: list[str], max_results: int = 20) -> list[str]:
    """Busca ofertas en MeetFrank y devuelve lista de URLs."""
    search_query = quote_plus(" ".join(keywords[:3]))
    url = f"https://meetfrank.com/jobs?search={search_query}"

    try:
        html = await asyncio.to_thread(_fetch_html, url)
    except Exception:
        return []

    return _extract_links(
        html,
        "https://meetfrank.com",
        lambda href: "/jobs/" in href or "/offer/" in href,
    )[:max_results]


async def find_new_opportunities_by_platform(perfil: PerfilMaestro, max_per_platform: int = 20) -> dict[str, list[str]]:
    """Busca oportunidades agrupadas por plataforma."""
    prefs = perfil.preferencias
    keywords = _build_keywords(perfil)
    grouped: dict[str, list[str]] = {platform: [] for platform in PLATFORM_ORDER if platform in prefs.plataformas_activas}

    task_specs: list[tuple[str, object]] = []
    if "linkedin" in prefs.plataformas_activas:
        task_specs.append(("linkedin", search_linkedin(keywords, max_per_platform)))
    if "getonbrd" in prefs.plataformas_activas:
        task_specs.append(("getonbrd", search_getonbrd(keywords, max_per_platform)))
    if "meetfrank" in prefs.plataformas_activas:
        task_specs.append(("meetfrank", search_meetfrank(keywords, max_per_platform)))

    results = await asyncio.gather(*(task for _, task in task_specs), return_exceptions=True)
    for (platform, _), result in zip(task_specs, results):
        if isinstance(result, list):
            grouped[platform] = result

    return grouped


async def find_new_opportunities(perfil: PerfilMaestro, max_per_platform: int = 20) -> list[str]:
    """Busca nuevas oportunidades en todas las plataformas activas e intercala plataformas."""
    grouped = await find_new_opportunities_by_platform(perfil, max_per_platform=max_per_platform)
    return _interleave_platform_results(grouped)
