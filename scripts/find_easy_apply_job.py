"""Script para encontrar una oferta de LinkedIn con Easy Apply activo."""

import asyncio
from playwright.async_api import async_playwright
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jober.core.config import ensure_profile_dirs, get_active_profile_id


async def find_easy_apply_job():
    print("=" * 80)
    print("BUSCADOR DE OFERTAS CON EASY APPLY EN LINKEDIN")
    print("=" * 80)
    
    print("\nINSTRUCCIONES:")
    print("1. Se abrirá LinkedIn")
    print("2. Busca ofertas de AI Engineer / ML Engineer")
    print("3. Filtra por 'Easy Apply' en el sidebar izquierdo")
    print("4. Abre una oferta que tenga el botón verde 'Easy Apply'")
    print("5. Copia la URL de esa oferta")
    print("6. Cierra el navegador y pega la URL aquí")
    print("=" * 80)
    
    input("\nPresiona ENTER para abrir LinkedIn...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        
        # Cargar sesión
        profile_id = get_active_profile_id()
        paths = ensure_profile_dirs(profile_id)
        storage_state_path = paths.profile_dir / "playwright_storage.json"
        
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 1600},
            storage_state=str(storage_state_path) if storage_state_path.exists() else None,
        )
        
        page = await context.new_page()
        
        # Ir a búsqueda de empleos
        search_url = "https://www.linkedin.com/jobs/search/?keywords=AI%20Engineer&location=Remote&f_AL=true"
        await page.goto(search_url, wait_until="domcontentloaded")
        
        print("\n✓ LinkedIn abierto con búsqueda de 'AI Engineer' + filtro Easy Apply")
        print("\nBusca una oferta activa con Easy Apply y copia su URL")
        print("Presiona ENTER aquí cuando hayas copiado la URL...")
        
        await asyncio.get_event_loop().run_in_executor(None, input)
        
        # Guardar sesión
        await context.storage_state(path=str(storage_state_path))
        
        await browser.close()
    
    print("\n" + "=" * 80)
    print("Pega la URL de la oferta con Easy Apply:")
    url = input("> ")
    
    if url.strip():
        print(f"\n✓ URL guardada: {url}")
        print("\nAhora ejecuta:")
        print(f"  python scripts\\test_linkedin_complete.py \"{url}\"")
    else:
        print("\n✗ No se proporcionó URL")


if __name__ == "__main__":
    asyncio.run(find_easy_apply_job())
