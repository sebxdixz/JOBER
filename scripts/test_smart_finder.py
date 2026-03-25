"""Test del smart button finder con la URL específica de LinkedIn."""

import asyncio
from playwright.async_api import async_playwright
import sys
import os

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jober.agents.smart_button_finder import find_apply_button_smart, click_apply_button_smart


async def test_smart_finder():
    url = "https://www.linkedin.com/jobs/view/junior-ai-ml-engineer-remote-at-chatgpt-jobs-4373181012"
    
    print("=" * 70)
    print("TEST: SMART BUTTON FINDER CON ANALISIS LLM")
    print("=" * 70)
    print(f"\nURL: {url}")
    
    async with async_playwright() as p:
        print("\nLanzando navegador...")
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        
        try:
            print("Navegando a la URL...")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            
            print("\n" + "=" * 70)
            print("FASE 1: ANALISIS DE BOTONES CON LLM")
            print("=" * 70)
            
            result = await find_apply_button_smart(page)
            
            print(f"\nResultado del análisis:")
            print(f"  Selector: {result['selector']}")
            print(f"  Índice: {result['index']}")
            print(f"  Confianza: {result['confidence']:.2f}")
            print(f"  Requiere auth: {result['requires_auth']}")
            print(f"  Razón: {result['reason']}")
            
            if result['selector']:
                print("\n" + "=" * 70)
                print("FASE 2: INTENTANDO HACER CLIC")
                print("=" * 70)
                
                success, message = await click_apply_button_smart(page)
                
                if success:
                    print(f"\n✓ EXITO: {message}")
                    
                    # Esperar a ver qué pasa
                    print("\nEsperando 5 segundos para ver el resultado...")
                    await page.wait_for_timeout(5000)
                    
                    print(f"\nURL actual: {page.url}")
                    
                    # Verificar si se abrió modal
                    modal_count = await page.locator("div[role='dialog']").count()
                    if modal_count > 0:
                        print(f"✓ Modal de aplicación detectado")
                    
                else:
                    print(f"\n✗ FALLO: {message}")
            else:
                print("\n✗ No se pudo identificar un botón de aplicación")
            
            print("\n" + "=" * 70)
            print("TEST COMPLETADO")
            print("=" * 70)
            
            print("\nPresiona Enter para cerrar el navegador...")
            input()
            
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_smart_finder())
