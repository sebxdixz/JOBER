"""Test del modo visión con GLM-4V para detectar botones."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from playwright.async_api import async_playwright
from jober.core.config import ensure_profile_dirs, get_active_profile_id
from jober.agents.vision_button_finder import find_and_click_with_vision


async def test_vision():
    url = "https://www.linkedin.com/jobs/view/junior-ai-ml-engineer-remote-at-chatgpt-jobs-4373181012"
    
    print("=" * 80)
    print("TEST: MODO VISION CON GLM-4V")
    print("=" * 80)
    print(f"\nURL: {url}")
    print("\nEl agente usará VISIÓN para:")
    print("1. Tomar un screenshot de la página")
    print("2. Analizar la imagen con GLM-4V")
    print("3. Identificar el botón de aplicación visualmente")
    print("4. Hacer clic en él")
    print("=" * 80)
    
    input("\nPresiona ENTER para comenzar...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        
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
        
        try:
            print("\n[1] Navegando a la página...")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            
            print("[2] Tomando screenshot y analizando con GLM-4V...")
            print("    (Esto puede tomar 10-20 segundos)")
            
            success, message = await find_and_click_with_vision(page)
            
            print("\n" + "=" * 80)
            print("RESULTADO")
            print("=" * 80)
            
            if success:
                print(f"\n✓ ÉXITO: {message}")
                
                # Esperar a ver qué pasa
                print("\nEsperando 5 segundos para ver el resultado...")
                await page.wait_for_timeout(5000)
                
                print(f"\nURL actual: {page.url}")
                
                # Verificar si se abrió modal
                modal_count = await page.locator("div[role='dialog']").count()
                if modal_count > 0:
                    print("✓ Modal de aplicación detectado")
                
            else:
                print(f"\n✗ FALLO: {message}")
            
            # Tomar screenshot final
            screenshot_path = "vision_test_result.png"
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"\n✓ Screenshot guardado: {screenshot_path}")
            
            print("\n" + "=" * 80)
            print("NAVEGADOR ABIERTO - Revisa el resultado")
            print("Presiona ENTER para cerrar...")
            print("=" * 80)
            
            await asyncio.get_event_loop().run_in_executor(None, input)
            
        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
            
            await asyncio.get_event_loop().run_in_executor(None, input, "\nPresiona ENTER para cerrar...")
        
        finally:
            await browser.close()
    
    print("\n✓ Test completado")


if __name__ == "__main__":
    asyncio.run(test_vision())
