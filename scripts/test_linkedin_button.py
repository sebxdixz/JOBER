"""Test de detección de botón de aplicación en LinkedIn."""

import asyncio
from playwright.async_api import async_playwright


LINKEDIN_EASY_APPLY_SELECTORS = (
    "button:has-text('Easy Apply')",
    "button:has-text('Solicitud sencilla')",
    "button:has-text('Solicitud fácil')",
    "button:has-text('Solicitar')",
    "button:has-text('Apply')",
    "button:has-text('Postular')",
    "button:has-text('Postularme')",
    "button.jobs-apply-button",
    "button[data-job-id]",
    "button[aria-label*='Apply']",
    "button[aria-label*='Solicitar']",
    "button[aria-label*='Postular']",
)


async def test_linkedin_button_detection():
    url = "https://www.linkedin.com/jobs/view/junior-ai-ml-engineer-remote-at-chatgpt-jobs-4373181012"
    
    print("=" * 70)
    print("TEST: DETECCION DE BOTON DE APLICACION EN LINKEDIN")
    print("=" * 70)
    print(f"\nURL: {url}")
    
    async with async_playwright() as p:
        print("\nLanzando navegador...")
        browser = await p.chromium.launch(headless=False)  # headless=False para ver qué pasa
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
            await page.wait_for_timeout(3000)  # Esperar a que cargue completamente
            
            print("\nBuscando botones de aplicación...")
            print("-" * 70)
            
            found = False
            for i, selector in enumerate(LINKEDIN_EASY_APPLY_SELECTORS, 1):
                print(f"\n[{i}/{len(LINKEDIN_EASY_APPLY_SELECTORS)}] Probando: {selector}")
                
                try:
                    # Verificar si existe
                    locator = page.locator(selector).first
                    count = await page.locator(selector).count()
                    
                    if count > 0:
                        # Verificar si es visible
                        is_visible = await locator.is_visible()
                        
                        if is_visible:
                            # Obtener texto e información
                            text = await locator.inner_text()
                            aria_label = await locator.get_attribute("aria-label")
                            
                            print(f"  ✓ ENCONTRADO Y VISIBLE")
                            print(f"    Texto: '{text}'")
                            print(f"    ARIA Label: '{aria_label}'")
                            print(f"    Cantidad: {count}")
                            
                            # Intentar hacer clic
                            print(f"  Intentando hacer clic...")
                            await locator.scroll_into_view_if_needed()
                            await locator.click(timeout=5000)
                            print(f"  ✓ CLIC EXITOSO")
                            
                            found = True
                            break
                        else:
                            print(f"  ✗ Encontrado pero NO visible (count: {count})")
                    else:
                        print(f"  ✗ No encontrado")
                        
                except Exception as e:
                    print(f"  ✗ Error: {str(e)[:60]}")
            
            print("\n" + "=" * 70)
            if found:
                print("RESULTADO: BOTON ENCONTRADO Y CLICKEADO")
                print("=" * 70)
                
                # Esperar a ver qué pasa después del clic
                print("\nEsperando 5 segundos para ver el resultado...")
                await page.wait_for_timeout(5000)
                
                # Verificar si se abrió un modal o cambió la página
                print(f"\nURL actual: {page.url}")
                
                # Buscar modal de aplicación
                modal_selectors = [
                    "div[role='dialog']",
                    "div.jobs-easy-apply-modal",
                    "div[aria-label*='Apply']",
                ]
                
                for modal_sel in modal_selectors:
                    if await page.locator(modal_sel).count() > 0:
                        print(f"✓ Modal detectado: {modal_sel}")
                        break
                
            else:
                print("RESULTADO: NINGUN BOTON ENCONTRADO")
                print("=" * 70)
                
                # Análisis de DOM para ver qué botones hay
                print("\nANALISIS DE BOTONES EN LA PAGINA:")
                print("-" * 70)
                
                all_buttons = await page.locator("button").all()
                print(f"\nTotal de botones en la página: {len(all_buttons)}")
                
                print("\nPrimeros 10 botones visibles:")
                visible_count = 0
                for i, btn in enumerate(all_buttons[:20]):
                    try:
                        is_visible = await btn.is_visible()
                        if is_visible:
                            text = await btn.inner_text()
                            aria = await btn.get_attribute("aria-label")
                            classes = await btn.get_attribute("class")
                            
                            visible_count += 1
                            print(f"\n  Botón {visible_count}:")
                            print(f"    Texto: '{text[:50]}'")
                            print(f"    ARIA: '{aria[:50] if aria else 'N/A'}'")
                            print(f"    Clases: '{classes[:60] if classes else 'N/A'}'")
                            
                            if visible_count >= 10:
                                break
                    except:
                        continue
                
                # Tomar screenshot para análisis
                screenshot_path = "linkedin_button_debug.png"
                await page.screenshot(path=screenshot_path, full_page=False)
                print(f"\n✓ Screenshot guardado: {screenshot_path}")
            
            print("\nPresiona Enter para cerrar el navegador...")
            input()
            
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_linkedin_button_detection())
