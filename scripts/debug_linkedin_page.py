"""Debug: Muestra TODOS los botones y elementos de la página de LinkedIn."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from playwright.async_api import async_playwright
from jober.core.config import ensure_profile_dirs, get_active_profile_id


async def debug_page():
    url = "https://www.linkedin.com/jobs/view/junior-ai-ml-engineer-remote-at-chatgpt-jobs-4373181012"
    
    print("=" * 80)
    print("DEBUG: ANALISIS COMPLETO DE PAGINA LINKEDIN")
    print("=" * 80)
    print(f"\nURL: {url}\n")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        
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
        
        print("Navegando a la página...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        
        print("\n" + "=" * 80)
        print("TODOS LOS BOTONES EN LA PAGINA:")
        print("=" * 80)
        
        all_buttons = await page.locator("button").all()
        print(f"\nTotal de botones: {len(all_buttons)}\n")
        
        for i, btn in enumerate(all_buttons, 1):
            try:
                is_visible = await btn.is_visible()
                text = await btn.inner_text()
                aria = await btn.get_attribute("aria-label")
                classes = await btn.get_attribute("class")
                
                if is_visible:
                    print(f"Botón {i} (VISIBLE):")
                    print(f"  Texto: '{text[:100]}'")
                    print(f"  ARIA: '{aria[:100] if aria else 'N/A'}'")
                    print(f"  Clases: '{classes[:100] if classes else 'N/A'}'")
                    print()
            except:
                continue
        
        print("\n" + "=" * 80)
        print("TODOS LOS ENLACES (a) EN LA PAGINA:")
        print("=" * 80)
        
        all_links = await page.locator("a").all()
        print(f"\nTotal de enlaces: {len(all_links)}\n")
        
        apply_related = []
        for i, link in enumerate(all_links[:50], 1):  # Primeros 50
            try:
                is_visible = await link.is_visible()
                text = await link.inner_text()
                href = await link.get_attribute("href")
                
                if is_visible and text:
                    text_lower = text.lower()
                    if any(word in text_lower for word in ["apply", "solicitar", "postular", "aplicar"]):
                        apply_related.append({
                            "text": text[:100],
                            "href": href[:100] if href else "N/A"
                        })
            except:
                continue
        
        if apply_related:
            print("Enlaces relacionados con aplicación:")
            for link in apply_related:
                print(f"  Texto: '{link['text']}'")
                print(f"  Href: '{link['href']}'")
                print()
        else:
            print("NO HAY ENLACES RELACIONADOS CON APLICACION\n")
        
        print("\n" + "=" * 80)
        print("VERIFICACIONES:")
        print("=" * 80)
        
        # Verificar si requiere login
        login_count = await page.locator("text=/sign in|log in|iniciar sesión/i").count()
        print(f"\nRequiere login: {'SÍ' if login_count > 0 else 'NO'}")
        
        # Verificar si expiró
        expired_count = await page.locator("text=/expired|no longer|ya no está|expiró|closed/i").count()
        print(f"Oferta expirada: {'SÍ' if expired_count > 0 else 'NO'}")
        
        # Verificar mensajes de error
        error_messages = await page.locator("text=/not available|unavailable|removed/i").all()
        if error_messages:
            print(f"\nMensajes de error encontrados: {len(error_messages)}")
            for msg in error_messages[:3]:
                text = await msg.inner_text()
                print(f"  - {text[:100]}")
        
        # Tomar screenshot
        screenshot_path = "linkedin_debug_full.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"\nScreenshot completo guardado: {screenshot_path}")
        
        print("\n" + "=" * 80)
        print("NAVEGADOR ABIERTO - Revisa manualmente la página")
        print("Presiona ENTER para cerrar...")
        print("=" * 80)
        
        await asyncio.get_event_loop().run_in_executor(None, input)
        
        await browser.close()
    
    print("\n✓ Debug completado")


if __name__ == "__main__":
    asyncio.run(debug_page())
