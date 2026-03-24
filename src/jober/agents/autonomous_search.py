"""Agente de busqueda autonoma.

Descubre ofertas con HTTP + parsing HTML simple.
Entrega resultados agrupados por plataforma y tambien intercalados.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from jober.core.models import JobLead, OfertaTrabajo, PerfilMaestro
from jober.utils.web_search import get_search_config, search_web


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}

PLATFORM_ORDER = ["linkedin", "getonbrd", "meetfrank"]
LEAD_PLATFORM_ORDER = ["linkedin", "getonbrd", "meetfrank", "rss"]


def _fetch_html(url: str, timeout: int = 20) -> str:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _fetch_html_playwright_sync(url: str, timeout: int = 30000) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout)
        content = page.content()
        browser.close()
    return content


async def _fetch_html_with_engine(url: str, engine: str, timeout: int = 20) -> str:
    if engine == "playwright":
        return await asyncio.to_thread(_fetch_html_playwright_sync, url, timeout * 1000)
    return await asyncio.to_thread(_fetch_html, url, timeout)


def _canonical_job_key(url: str) -> str:
    clean = (url or "").split("#")[0].split("?", 1)[0].strip().lower()
    if "linkedin.com/jobs/view/" in clean:
        match = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)", clean)
        if match:
            return f"linkedin:{match.group(1)}"
    if "getonbrd.com/empleos/" in clean:
        return f"getonbrd:{clean.rsplit('/', 1)[-1]}"
    if "meetfrank.com/" in clean:
        return f"meetfrank:{clean}"
    return clean


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


def _strip_html(text: str) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return " ".join(soup.get_text(" ", strip=True).split())


def _normalize_terms(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value and value.strip()]


def _build_location_terms(perfil: PerfilMaestro) -> list[str]:
    prefs = perfil.preferencias
    terms = []
    terms.extend(_normalize_terms(prefs.ubicaciones[:3]))
    terms.extend(_normalize_terms(prefs.paises_permitidos[:3]))

    modalidad_blob = " ".join(_normalize_terms(prefs.modalidad)).lower()
    if any(marker in modalidad_blob for marker in ["remote", "remoto"]):
        terms.extend(["remote", "remoto"])

    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            unique.append(term)
    return unique


def _remote_only_required(modalidades: list[str]) -> bool:
    normalized = [value.strip().lower() for value in modalidades if value and value.strip()]
    if not normalized:
        return False
    remote_markers = {"remoto", "remote", "work from home"}
    has_remote = any(marker in modality for modality in normalized for marker in remote_markers)
    has_onsite = any(marker in modality for modality in normalized for marker in ["presencial", "onsite"])
    has_hybrid = any(marker in modality for modality in normalized for marker in ["hibrido", "hybrid"])
    return has_remote and not (has_onsite or has_hybrid)


def _slugify_keyword(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def _build_meetfrank_listing_urls(
    keywords: list[str],
    remote_only: bool,
) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    for keyword in keywords[:6]:
        slug = _slugify_keyword(keyword)
        if not slug:
            continue

        variants = []
        if remote_only:
            variants.append(f"https://meetfrank.com/latest-remote-{slug}-jobs")
        variants.append(f"https://meetfrank.com/latest-{slug}-jobs")
        variants.append(f"https://meetfrank.com/jobs?search={quote_plus(keyword)}")

        for url in variants:
            if url not in seen:
                seen.add(url)
                urls.append(url)

    return urls


def _rotate_values(values: list[str], seed: int) -> list[str]:
    if not values:
        return values
    shift = seed % len(values)
    return values[shift:] + values[:shift]


def _build_keywords(perfil: PerfilMaestro, search_round: int = 0) -> list[str]:
    prefs = perfil.preferencias
    role_keyword_map = {
        "ai engineer": ["AI Engineer", "Agentic AI Engineer", "Generative AI Engineer"],
        "llm engineer": ["LLM Engineer", "Generative AI Engineer", "Prompt Engineer"],
        "ml engineer": ["ML Engineer", "Machine Learning Engineer", "Applied ML Engineer"],
        "mlops engineer": ["MLOps Engineer", "ML Platform Engineer", "Machine Learning Ops"],
        "ai ops": ["AIOps", "AI Ops Engineer", "AI Platform Engineer"],
        "llm ops": ["LLMOps", "LLM Ops Engineer", "LLM Platform Engineer"],
        "ai automation engineer": ["AI Automation Engineer", "AI Automation", "Automation Engineer"],
        "machine learning engineer": ["Machine Learning Engineer", "ML Engineer", "Applied ML Engineer"],
        "data scientist": ["Data Scientist", "Applied Scientist", "ML Scientist"],
        "data analyst": ["Data Analyst", "Analytics Engineer", "BI Analyst"],
        "data engineer": ["Data Engineer", "Analytics Engineer", "Data Platform Engineer"],
        "backend developer": ["Backend Engineer", "Backend Developer", "Software Engineer Backend"],
        "frontend developer": ["Frontend Engineer", "Frontend Developer", "React Engineer"],
        "full stack": ["Full Stack Engineer", "Full Stack Developer", "Software Engineer Full Stack"],
    }

    expanded_keywords: list[str] = []
    roles_lower = [role.lower() for role in prefs.roles_deseados]

    for role in prefs.roles_deseados:
        role_lower = role.lower()
        if role_lower in role_keyword_map:
            expanded_keywords.extend(role_keyword_map[role_lower])
        else:
            expanded_keywords.append(role)

    if any(any(marker in role for marker in ["ai", "llm", "ml", "mlops"]) for role in roles_lower):
        expanded_keywords.extend(["Data Scientist", "Applied Scientist"])
    if any("data scientist" in role for role in roles_lower):
        expanded_keywords.extend(["Data Analyst"])

    seen: set[str] = set()
    keywords: list[str] = []
    for kw in expanded_keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            keywords.append(kw)

    if not keywords:
        keywords = [perfil.titulo_profesional] if perfil.titulo_profesional else ["developer"]
    return _rotate_values(keywords, search_round)


def _get_rss_feed_urls() -> list[str]:
    raw = os.getenv("JOBER_RSS_FEEDS", "").strip()
    if not raw:
        return []
    parts = re.split(r"[,\n]+", raw)
    return [part.strip() for part in parts if part.strip()]


def _extract_rss_leads(xml: str, max_results: int) -> list[JobLead]:
    try:
        soup = BeautifulSoup(xml, "xml")
    except Exception:
        soup = BeautifulSoup(xml, "html.parser")
    items = soup.find_all("item")
    if not items:
        items = soup.find_all("entry")

    leads: list[JobLead] = []
    seen: set[str] = set()

    for item in items:
        link_tag = item.find("link")
        url = ""
        if link_tag:
            url = link_tag.get("href", "").strip() or link_tag.get_text(strip=True)
        if not url or url in seen:
            continue

        title_tag = item.find("title")
        title = title_tag.get_text(" ", strip=True) if title_tag else ""

        desc_tag = item.find("description") or item.find("summary") or item.find("content")
        snippet = ""
        if desc_tag:
            snippet = _strip_html(desc_tag.get_text(" ", strip=True))[:240]

        leads.append(JobLead(
            url=url,
            titulo=title,
            empresa="",
            ubicacion="",
            plataforma="rss",
            snippet=snippet,
            source="rss",
        ))
        seen.add(url)

        if len(leads) >= max_results:
            break

    return leads


async def search_rss_leads(feed_urls: list[str], max_results: int = 20) -> list[JobLead]:
    """Busca leads en feeds RSS configurados via JOBER_RSS_FEEDS."""
    leads: list[JobLead] = []
    seen: set[str] = set()

    for feed_url in feed_urls:
        try:
            xml = await asyncio.to_thread(_fetch_html, feed_url)
        except Exception:
            continue

        for lead in _extract_rss_leads(xml, max_results):
            if lead.url in seen:
                continue
            seen.add(lead.url)
            leads.append(lead)
            if len(leads) >= max_results:
                return leads

    return leads


def lead_to_oferta(lead: JobLead) -> OfertaTrabajo:
    """Convierte un lead liviano en OfertaTrabajo para filtros locales."""
    modalidad = ""
    location_blob = f"{lead.ubicacion} {lead.titulo} {lead.snippet}".lower()
    if any(marker in location_blob for marker in ["remote", "remoto", "work from home", "anywhere"]):
        modalidad = "remoto"
    return OfertaTrabajo(
        url=lead.url or "",
        titulo=lead.titulo or "",
        empresa=lead.empresa or "",
        ubicacion=lead.ubicacion or "",
        modalidad=modalidad,
        descripcion=lead.snippet or "",
        requisitos=[],
        nice_to_have=[],
        salario="",
        plataforma=lead.plataforma or "",
    )


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
        key = _canonical_job_key(url)
        if key not in seen:
            seen.add(key)
            unique_urls.append(url)
    return unique_urls


async def _search_getonbrd_query(query: str, max_results: int) -> list[str]:
    search_query = quote_plus(query)
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


async def search_getonbrd(keywords: list[str], max_results: int = 20) -> list[str]:
    """Busca ofertas en GetOnBrd y devuelve lista de URLs."""
    queries = [kw for kw in keywords[:4] if kw]
    if not queries:
        queries = ["developer"]

    results = await asyncio.gather(
        *[_search_getonbrd_query(query, max_results) for query in queries],
        return_exceptions=True,
    )
    urls: list[str] = []
    seen: set[str] = set()
    for result in results:
        if not isinstance(result, list):
            continue
        for url in result:
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls[:max_results]


async def search_getonbrd_leads(keywords: list[str], max_results: int = 20) -> list[JobLead]:
    """Busca ofertas en GetOnBrd usando API publica."""
    queries = [kw for kw in keywords[:4] if kw]
    if not queries:
        queries = ["developer"]

    async def _fetch_query(query: str) -> list[JobLead]:
        url = f"https://www.getonbrd.com/api/v0/search/jobs?query={quote_plus(query)}"
        try:
            html = await asyncio.to_thread(_fetch_html, url)
            payload = json.loads(html)
        except Exception:
            return []

        items: list[JobLead] = []
        for item in payload.get("data", []):
            if not isinstance(item, dict):
                continue
            attrs = item.get("attributes", {}) if isinstance(item.get("attributes"), dict) else {}
            slug = item.get("id", "")
            if not slug:
                continue
            job_url = f"https://www.getonbrd.com/empleos/{slug}"
            title = attrs.get("title", "")
            description = _strip_html(attrs.get("description", ""))
            snippet = description[:240]
            location = ""
            if attrs.get("remote"):
                location = "Remote"
            elif attrs.get("location_cities"):
                cities = attrs.get("location_cities", [])
                if isinstance(cities, list) and cities:
                    location = ", ".join(cities[:2])
            items.append(JobLead(
                url=job_url,
                titulo=title,
                empresa="",
                ubicacion=location,
                plataforma="getonbrd",
                snippet=snippet,
                source="getonbrd_api",
            ))
        return items

    results = await asyncio.gather(*[_fetch_query(query) for query in queries], return_exceptions=True)
    leads: list[JobLead] = []
    seen: set[str] = set()
    for result in results:
        if not isinstance(result, list):
            continue
        for lead in result:
            key = _canonical_job_key(lead.url)
            if key in seen:
                continue
            seen.add(key)
            leads.append(lead)
            if len(leads) >= max_results:
                return leads

    return leads


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


def _parse_linkedin_leads(html: str, max_results: int) -> list[JobLead]:
    soup = BeautifulSoup(html, "html.parser")
    leads: list[JobLead] = []
    for card in soup.select("div.base-search-card")[: max_results * 2]:
        link = card.select_one("a.base-card__full-link")
        if not link:
            continue
        url = link.get("href", "").split("?")[0].strip()
        title = ""
        title_el = card.select_one("h3.base-search-card__title")
        if title_el:
            title = " ".join(title_el.get_text(" ", strip=True).split())
        company = ""
        company_el = card.select_one("h4.base-search-card__subtitle")
        if company_el:
            company = " ".join(company_el.get_text(" ", strip=True).split())
        location = ""
        location_el = card.select_one("span.job-search-card__location")
        if location_el:
            location = " ".join(location_el.get_text(" ", strip=True).split())
        if not url:
            continue
        leads.append(JobLead(
            url=url,
            titulo=title,
            empresa=company,
            ubicacion=location,
            plataforma="linkedin",
            snippet="",
            source="linkedin_guest",
        ))
        if len(leads) >= max_results:
            break
    return leads


def _build_linkedin_query(
    keyword: str,
    location: str,
    start: int,
    remote_only: bool,
    tpr: str | None = None,
) -> str:
    search_query = quote_plus(keyword)
    location_query = quote_plus(location) if location else ""
    base = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        f"?keywords={search_query}&location={location_query}&start={start}"
    )
    if tpr:
        base = f"{base}&f_TPR={tpr}"
    if remote_only:
        return f"{base}&f_WT=2"
    return base


async def search_linkedin_leads(
    keywords: list[str],
    max_results: int = 20,
    location_terms: list[str] | None = None,
    remote_only: bool = False,
) -> list[JobLead]:
    """Busca ofertas en LinkedIn Jobs guest search y devuelve leads."""
    keywords = [kw for kw in keywords[:4] if kw]
    if not keywords:
        keywords = ["developer"]

    locations = [term for term in (location_terms or []) if term]
    if not locations:
        locations = [""]

    tpr = os.getenv("JOBER_LINKEDIN_TPR", "").strip() or None
    remote_only_flag = os.getenv("JOBER_LINKEDIN_REMOTE_ONLY", "").strip().lower() in {"1", "true", "yes"}

    request_specs: list[tuple[str, str, int, bool]] = []
    for keyword in keywords:
        for location in locations[:3] + [""]:
            remote_flag = remote_only_flag or remote_only
            for start in (0, 25, 50):
                request_specs.append((keyword, location, start, remote_flag))

    # Fuerza bruta pero acotada para no castigar latencia.
    request_budget = max(12, min(len(request_specs), max_results * 3))
    request_specs = request_specs[:request_budget]

    async def _fetch_spec(spec: tuple[str, str, int, bool]) -> list[JobLead]:
        keyword, location, start, remote_flag = spec
        url = _build_linkedin_query(keyword, location, start, remote_flag, tpr)
        try:
            html = await asyncio.to_thread(_fetch_html, url)
        except Exception:
            return []
        return _parse_linkedin_leads(html, max_results)

    results = await asyncio.gather(*[_fetch_spec(spec) for spec in request_specs], return_exceptions=True)
    leads: list[JobLead] = []
    seen: set[str] = set()
    for result in results:
        if not isinstance(result, list):
            continue
        for lead in result:
            key = _canonical_job_key(lead.url)
            if not lead.url or key in seen:
                continue
            seen.add(key)
            leads.append(lead)
            if len(leads) >= max_results:
                return leads

    return leads


async def search_meetfrank(keywords: list[str], max_results: int = 20) -> list[str]:
    """Busca ofertas en MeetFrank y devuelve lista de URLs."""
    engine = os.getenv("JOBER_MEETFRANK_ENGINE", "").strip().lower()
    urls = _build_meetfrank_listing_urls(keywords, remote_only=True)

    async def _fetch_listing(url: str) -> list[str]:
        try:
            html = await _fetch_html_with_engine(url, engine)
        except Exception:
            return []
        return _extract_links(
            html,
            "https://meetfrank.com",
            lambda href: "/jobs/" in href or "/offer/" in href,
        )

    results = await asyncio.gather(*[_fetch_listing(url) for url in urls[:8]], return_exceptions=True)
    collected: list[str] = []
    seen: set[str] = set()
    for result in results:
        if not isinstance(result, list):
            continue
        for url in result:
            key = _canonical_job_key(url)
            if key in seen:
                continue
            seen.add(key)
            collected.append(url)
            if len(collected) >= max_results:
                return collected
    return collected


async def search_meetfrank_leads(
    keywords: list[str],
    max_results: int = 20,
    location_terms: list[str] | None = None,
    remote_only: bool = False,
) -> list[JobLead]:
    """Busca ofertas en MeetFrank y devuelve leads simples."""
    keywords = [kw for kw in keywords[:4] if kw]
    if not keywords:
        keywords = ["developer"]

    engine = os.getenv("JOBER_MEETFRANK_ENGINE", "").strip().lower()
    request_specs = _build_meetfrank_listing_urls(keywords, remote_only=remote_only)

    request_budget = max(8, min(len(request_specs), max_results * 2))
    request_specs = request_specs[:request_budget]

    async def _fetch_url(url: str) -> list[JobLead]:
        try:
            html = await _fetch_html_with_engine(url, engine)
        except Exception:
            return []

        soup = BeautifulSoup(html, "html.parser")
        items: list[JobLead] = []
        for link in soup.select("a[href]"):
            href = link.get("href", "").strip()
            if not href:
                continue
            full_url = urljoin("https://meetfrank.com", href).split("#")[0]
            if "/jobs/" not in full_url and "/offer/" not in full_url:
                continue
            title = " ".join(link.get_text(" ", strip=True).split())
            items.append(JobLead(
                url=full_url,
                titulo=title,
                empresa="",
                ubicacion="",
                plataforma="meetfrank",
                snippet="",
                source="meetfrank_html",
            ))
        return items

    results = await asyncio.gather(*[_fetch_url(url) for url in request_specs], return_exceptions=True)
    leads: list[JobLead] = []
    seen: set[str] = set()
    for result in results:
        if not isinstance(result, list):
            continue
        for lead in result:
            key = _canonical_job_key(lead.url)
            if key in seen:
                continue
            seen.add(key)
            leads.append(lead)
            if len(leads) >= max_results:
                return leads

    return leads


def _interleave_platform_leads(platform_results: dict[str, list[JobLead]]) -> list[JobLead]:
    interleaved: list[JobLead] = []
    max_len = max((len(platform_results.get(platform, [])) for platform in LEAD_PLATFORM_ORDER), default=0)

    for idx in range(max_len):
        for platform in LEAD_PLATFORM_ORDER:
            leads = platform_results.get(platform, [])
            if idx < len(leads):
                interleaved.append(leads[idx])

    seen: set[str] = set()
    unique: list[JobLead] = []
    for lead in interleaved:
        key = _canonical_job_key(lead.url)
        if lead.url and key not in seen:
            seen.add(key)
            unique.append(lead)
    return unique


async def _search_platform_via_web(
    platform: str,
    keywords: list[str],
    max_results: int = 20,
    location_terms: list[str] | None = None,
) -> list[str]:
    location_terms = location_terms or []
    keyword_terms = keywords[:6] if keywords else ["developer"]

    def _quote(term: str) -> str:
        return f"\"{term}\"" if " " in term else term

    keyword_block = " OR ".join(_quote(term) for term in keyword_terms if term)
    location_block = ""
    if location_terms:
        location_block = f" ({' OR '.join(_quote(term) for term in location_terms[:4])})"

    if platform == "linkedin":
        query = f"site:linkedin.com/jobs/view/ ({keyword_block}){location_block} remote"
        matcher = lambda href: "linkedin.com/jobs/view/" in href
    elif platform == "meetfrank":
        query = f"site:meetfrank.com ({keyword_block}){location_block}"
        matcher = lambda href: "meetfrank.com/jobs/" in href or "meetfrank.com/offer/" in href
    else:
        query = f"site:getonbrd.com/empleos ({keyword_block}){location_block}"
        matcher = lambda href: "getonbrd.com/empleos/" in href

    config = get_search_config()
    try:
        urls = await asyncio.to_thread(search_web, query, max_results * 2, config)
    except Exception:
        return []

    filtered: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if matcher(url):
            clean = url.split("#")[0]
            if clean not in seen:
                seen.add(clean)
                filtered.append(clean)
        if len(filtered) >= max_results:
            break
    return filtered


async def find_new_opportunities_by_platform(perfil: PerfilMaestro, max_per_platform: int = 20) -> dict[str, list[str]]:
    """Busca oportunidades agrupadas por plataforma."""
    prefs = perfil.preferencias
    keywords = _build_keywords(perfil)
    location_terms = _build_location_terms(perfil)
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

    # Fallback web search if a platform is empty
    fallback_tasks: list[tuple[str, object]] = []
    for platform in grouped:
        if not grouped.get(platform):
            fallback_tasks.append((
                platform,
                _search_platform_via_web(platform, keywords, max_per_platform, location_terms),
            ))

    if fallback_tasks:
        fallback_results = await asyncio.gather(*(task for _, task in fallback_tasks), return_exceptions=True)
        for (platform, _), result in zip(fallback_tasks, fallback_results):
            if isinstance(result, list) and result:
                grouped[platform] = result

    return grouped


async def find_new_opportunities(perfil: PerfilMaestro, max_per_platform: int = 20) -> list[str]:
    """Busca nuevas oportunidades en todas las plataformas activas e intercala plataformas."""
    grouped = await find_new_opportunities_by_platform(perfil, max_per_platform=max_per_platform)
    return _interleave_platform_results(grouped)


async def find_new_leads_by_platform(
    perfil: PerfilMaestro,
    max_per_platform: int = 20,
    search_round: int = 0,
) -> dict[str, list[JobLead]]:
    """Busca leads agrupados por plataforma (sin LLM)."""
    prefs = perfil.preferencias
    keywords = _build_keywords(perfil, search_round=search_round)
    location_terms = _build_location_terms(perfil)
    remote_only = _remote_only_required(prefs.modalidad)
    feed_urls = _get_rss_feed_urls()
    active_platforms = [platform for platform in PLATFORM_ORDER if platform in prefs.plataformas_activas]
    if feed_urls:
        active_platforms.append("rss")

    grouped: dict[str, list[JobLead]] = {platform: [] for platform in active_platforms}

    task_specs: list[tuple[str, object]] = []
    if "linkedin" in active_platforms:
        task_specs.append((
            "linkedin",
            search_linkedin_leads(keywords, max_per_platform, location_terms, remote_only=remote_only),
        ))
    if "getonbrd" in active_platforms:
        task_specs.append(("getonbrd", search_getonbrd_leads(keywords, max_per_platform)))
    if "meetfrank" in active_platforms:
        task_specs.append((
            "meetfrank",
            search_meetfrank_leads(
                keywords,
                max_per_platform,
                location_terms,
                remote_only=remote_only,
            ),
        ))
    if "rss" in active_platforms:
        task_specs.append(("rss", search_rss_leads(feed_urls, max_per_platform)))

    results = await asyncio.gather(*(task for _, task in task_specs), return_exceptions=True)
    for (platform, _), result in zip(task_specs, results):
        if isinstance(result, list):
            grouped[platform] = result

    # Fallback web search if a platform is empty
    fallback_tasks: list[tuple[str, object]] = []
    for platform in grouped:
        if platform == "rss":
            continue
        if not grouped.get(platform):
            fallback_tasks.append((
                platform,
                _search_platform_via_web(platform, keywords, max_per_platform, location_terms),
            ))

    if fallback_tasks:
        fallback_results = await asyncio.gather(*(task for _, task in fallback_tasks), return_exceptions=True)
        for (platform, _), result in zip(fallback_tasks, fallback_results):
            if isinstance(result, list) and result:
                grouped[platform] = [
                    JobLead(url=url, plataforma=platform, source="web_search")
                    for url in result
                ]

    return grouped


async def find_new_leads(
    perfil: PerfilMaestro,
    max_per_platform: int = 20,
    search_round: int = 0,
) -> list[JobLead]:
    """Busca leads e intercala plataformas."""
    grouped = await find_new_leads_by_platform(
        perfil,
        max_per_platform=max_per_platform,
        search_round=search_round,
    )
    return _interleave_platform_leads(grouped)
