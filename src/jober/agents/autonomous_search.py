"""Agente de busqueda autonoma.

Descubre ofertas con HTTP + parsing HTML simple.
Playwright queda reservado para paginas dificiles y flujos de aplicacion.
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


async def find_new_opportunities(perfil: PerfilMaestro, max_per_platform: int = 20) -> list[str]:
    """Busca nuevas oportunidades en todas las plataformas activas."""
    prefs = perfil.preferencias
    all_urls: list[str] = []

    # Mapeo inteligente de roles a keywords de búsqueda más amplias
    role_keyword_map = {
        "ai engineer": ["AI Engineer", "Machine Learning", "Python", "Data Scientist"],
        "ml engineer": ["ML Engineer", "Machine Learning", "Python", "Data Scientist"],
        "ml ops": ["MLOps", "DevOps", "Machine Learning", "Python"],
        "machine learning engineer": ["Machine Learning", "ML Engineer", "Python", "Data Scientist"],
        "data scientist": ["Data Scientist", "Machine Learning", "Python", "Analytics"],
        "backend developer": ["Backend", "Python", "Node.js", "API"],
        "frontend developer": ["Frontend", "React", "JavaScript", "Vue"],
        "full stack": ["Full Stack", "Python", "JavaScript", "React"],
    }
    
    # Expandir keywords basados en roles
    expanded_keywords = []
    for role in prefs.roles_deseados[:2]:
        role_lower = role.lower()
        if role_lower in role_keyword_map:
            expanded_keywords.extend(role_keyword_map[role_lower][:2])
        else:
            expanded_keywords.append(role)
    
    # Agregar habilidades must-have
    expanded_keywords.extend(prefs.habilidades_must_have[:2])
    
    # Remover duplicados manteniendo orden
    seen = set()
    keywords = []
    for kw in expanded_keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            keywords.append(kw)
    
    if not keywords:
        keywords = [perfil.titulo_profesional] if perfil.titulo_profesional else ["developer"]

    tasks = []

    if "getonbrd" in prefs.plataformas_activas:
        tasks.append(search_getonbrd(keywords, max_per_platform))

    if "linkedin" in prefs.plataformas_activas:
        tasks.append(search_linkedin(keywords, max_per_platform))

    if "meetfrank" in prefs.plataformas_activas:
        tasks.append(search_meetfrank(keywords, max_per_platform))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, list):
            all_urls.extend(result)

    seen: set[str] = set()
    unique_urls: list[str] = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    return unique_urls
