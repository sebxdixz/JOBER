"""Agente de búsqueda autónoma — recorre plataformas y encuentra ofertas relevantes."""

from __future__ import annotations

import asyncio
from datetime import datetime

from playwright.async_api import async_playwright

from jober.core.models import OfertaTrabajo, PerfilMaestro


# ── Scrapers por plataforma ────────────────────────────────────────────────

async def search_getonbrd(keywords: list[str], max_results: int = 20) -> list[str]:
    """Busca ofertas en GetOnBrd y devuelve lista de URLs."""
    urls: list[str] = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # GetOnBrd tiene búsqueda por keywords
            search_query = "+".join(keywords[:3])  # Limitar a 3 keywords
            url = f"https://www.getonbrd.com/empleos?query={search_query}"
            
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Extraer links de ofertas
            links = await page.query_selector_all("a[href*='/empleos/']")
            for link in links[:max_results]:
                href = await link.get_attribute("href")
                if href and "/empleos/" in href and not href.endswith("/empleos"):
                    full_url = f"https://www.getonbrd.com{href}" if href.startswith("/") else href
                    if full_url not in urls:
                        urls.append(full_url)
        
        finally:
            await browser.close()
    
    return urls


async def search_linkedin(keywords: list[str], max_results: int = 20) -> list[str]:
    """Busca ofertas en LinkedIn Jobs (guest view, sin login) y devuelve lista de URLs."""
    urls: list[str] = []
    
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
            search_query = " ".join(keywords[:3])
            # LinkedIn guest job search (no login required)
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={search_query.replace(' ', '%20')}"
                f"&location=&f_TPR=r604800"  # Last week
            )
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Scroll to load more results
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)
            
            # Extract job listing links
            links = await page.query_selector_all(
                "a.base-card__full-link, "
                "a[href*='/jobs/view/'], "
                "a.base-search-card__full-link"
            )
            for link in links[:max_results]:
                href = await link.get_attribute("href")
                if href and "/jobs/view/" in href:
                    # Clean URL (remove tracking params)
                    clean_url = href.split("?")[0]
                    if clean_url not in urls:
                        urls.append(clean_url)
        
        except Exception:
            pass  # LinkedIn may block; fail silently
        finally:
            await browser.close()
    
    return urls


async def search_meetfrank(keywords: list[str], max_results: int = 20) -> list[str]:
    """Busca ofertas en MeetFrank y devuelve lista de URLs."""
    urls: list[str] = []
    
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
            search_query = " ".join(keywords[:3])
            url = f"https://meetfrank.com/jobs?search={search_query.replace(' ', '%20')}"
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Scroll to load more
            for _ in range(2):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)
            
            # Extract job links
            links = await page.query_selector_all(
                "a[href*='/jobs/'], "
                "a[href*='/offer/']"
            )
            for link in links[:max_results]:
                href = await link.get_attribute("href")
                if href:
                    full_url = f"https://meetfrank.com{href}" if href.startswith("/") else href
                    if full_url not in urls and ("/jobs/" in full_url or "/offer/" in full_url):
                        urls.append(full_url)
        
        except Exception:
            pass  # MeetFrank may change structure; fail silently
        finally:
            await browser.close()
    
    return urls


# ── Filtrado inteligente ───────────────────────────────────────────────────

def is_relevant_offer(oferta: OfertaTrabajo, perfil: PerfilMaestro) -> bool:
    """Determina si una oferta es relevante según el perfil y preferencias."""
    prefs = perfil.preferencias
    
    # 1. Verificar modalidad
    if prefs.modalidad and oferta.modalidad:
        if oferta.modalidad.lower() not in [m.lower() for m in prefs.modalidad]:
            return False
    
    # 2. Verificar ubicación (si se especificó)
    if prefs.ubicaciones and oferta.ubicacion:
        ubicacion_match = any(
            loc.lower() in oferta.ubicacion.lower() or oferta.ubicacion.lower() in loc.lower()
            for loc in prefs.ubicaciones
        )
        if not ubicacion_match:
            return False
    
    # 3. Verificar roles deseados (match en título)
    if prefs.roles_deseados:
        titulo_lower = oferta.titulo.lower()
        role_match = any(role.lower() in titulo_lower for role in prefs.roles_deseados)
        if not role_match:
            return False
    
    # 4. Verificar habilidades must-have (al menos una debe aparecer)
    if prefs.habilidades_must_have:
        desc_lower = (oferta.descripcion + " " + " ".join(oferta.requisitos)).lower()
        has_must_have = any(
            skill.lower() in desc_lower
            for skill in prefs.habilidades_must_have
        )
        if not has_must_have:
            return False
    
    return True


async def find_new_opportunities(perfil: PerfilMaestro, max_per_platform: int = 20) -> list[str]:
    """Busca nuevas oportunidades en todas las plataformas activas."""
    prefs = perfil.preferencias
    all_urls: list[str] = []
    
    # Keywords de búsqueda basados en roles deseados + habilidades must-have
    keywords = prefs.roles_deseados[:3] + prefs.habilidades_must_have[:2]
    if not keywords:
        keywords = [perfil.titulo_profesional] if perfil.titulo_profesional else ["developer"]
    
    # Buscar en cada plataforma activa
    tasks = []
    
    if "getonbrd" in prefs.plataformas_activas:
        tasks.append(search_getonbrd(keywords, max_per_platform))
    
    if "linkedin" in prefs.plataformas_activas:
        tasks.append(search_linkedin(keywords, max_per_platform))
    
    if "meetfrank" in prefs.plataformas_activas:
        tasks.append(search_meetfrank(keywords, max_per_platform))
    
    # Ejecutar búsquedas en paralelo
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, list):
            all_urls.extend(result)
    
    # Eliminar duplicados manteniendo orden
    seen = set()
    unique_urls = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    return unique_urls
