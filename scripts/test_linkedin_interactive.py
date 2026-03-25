"""Test interactivo de aplicación en LinkedIn - mantiene navegador abierto."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from playwright.async_api import async_playwright
from jober.core.models import OfertaTrabajo
from jober.utils.file_io import load_perfil_maestro
from jober.core.config import ensure_profile_dirs, get_active_profile_id


async def test_interactive():
    url = "https://www.linkedin.com/jobs/view/junior-ai-ml-engineer-remote-at-chatgpt-jobs-4373181012"
    
    print("=" * 80)
    print("TEST INTERACTIVO: LINKEDIN AUTO-APPLY")
    print("=" * 80)
    
    # Cargar perfil
    perfil = load_perfil_maestro()
    if not perfil:
        print("✗ No se encontró perfil maestro")
        return
    
    print(f"\n✓ Perfil: {perfil.nombre}")
    print(f"✓ Email: {perfil.email}")
    print(f"✓ Teléfono: {perfil.telefono}")
    
    # Preparar documentos
    temp_dir = Path("temp_test_docs")
    temp_dir.mkdir(exist_ok=True)
    cv_path = temp_dir / "cv_test.pdf"
    cv_path.write_text("CV Test")
    
    print("\n" + "=" * 80)
    print("INSTRUCCIONES:")
    print("1. Se abrirá LinkedIn en el navegador")
    print("2. Si no estás logueado, haz login manualmente")
    print("3. El script intentará encontrar y clickear el botón de aplicación")
    print("4. Observa si el modal de Easy Apply se abre")
    print("5. El navegador se quedará abierto para que veas qué pasa")
    print("=" * 80)
    
    input("\nPresiona ENTER para comenzar...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        
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
        
        try:
            print("\n[1] Navegando a la oferta...")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            
            print("[2] Analizando página...")
            
            # Verificar si está logueado
            login_button_count = await page.locator("a:has-text('Iniciar sesión'), a:has-text('Sign in')").count()
            if login_button_count > 0:
                print("\n⚠ NO ESTÁS LOGUEADO EN LINKEDIN")
                print("Por favor, haz login manualmente en el navegador")
                input("Presiona ENTER cuando hayas hecho login...")
                await page.reload(wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
            else:
                print("✓ Sesión de LinkedIn activa")
            
            # Guardar sesión
            await context.storage_state(path=str(storage_state_path))
            
            print("\n[3] Buscando botón de aplicación con smart button finder...")
            
            # Importar smart button finder
            from jober.agents.smart_button_finder import find_apply_button_smart, click_apply_button_smart
            
            result = await find_apply_button_smart(page)
            
            print(f"\nResultado del análisis:")
            print(f"  Selector: {result['selector']}")
            print(f"  Confianza: {result['confidence']:.2f}")
            print(f"  Requiere auth: {result['requires_auth']}")
            print(f"  Razón: {result['reason']}")
            
            if result['selector'] and result['confidence'] > 0.5:
                print(f"\n[4] Haciendo clic en el botón...")
                
                success, message = await click_apply_button_smart(page)
                
                if success:
                    print(f"✓ Clic exitoso: {message}")
                    
                    # Esperar a que se abra el modal o cambie la página
                    await page.wait_for_timeout(3000)
                    
                    print(f"\n[5] Verificando qué se abrió...")
                    
                    # Buscar modal de Easy Apply
                    modal_selectors = [
                        "div[role='dialog']",
                        "div.jobs-easy-apply-modal",
                        "div[aria-label*='Easy Apply']",
                        "div[aria-label*='Solicitud']",
                    ]
                    
                    modal_found = False
                    for selector in modal_selectors:
                        count = await page.locator(selector).count()
                        if count > 0:
                            print(f"✓ Modal encontrado: {selector}")
                            modal_found = True
                            
                            # Buscar formulario
                            form_count = await page.locator("form").count()
                            print(f"✓ Formularios detectados: {form_count}")
                            
                            # Buscar campos
                            inputs = await page.locator("input[type='text'], input[type='email'], input[type='tel']").all()
                            print(f"✓ Campos de texto: {len(inputs)}")
                            
                            for i, inp in enumerate(inputs[:5], 1):
                                name = await inp.get_attribute("name")
                                placeholder = await inp.get_attribute("placeholder")
                                print(f"  Campo {i}: name='{name}', placeholder='{placeholder}'")
                            
                            break
                    
                    if not modal_found:
                        print("✗ No se detectó modal de Easy Apply")
                        print("Posibles razones:")
                        print("  - La oferta no tiene Easy Apply habilitado")
                        print("  - Se requiere aplicación externa")
                        print("  - Se abrió una página diferente")
                        
                        # Verificar URL actual
                        current_url = page.url
                        print(f"\nURL actual: {current_url}")
                        
                        # Verificar si hay mensaje de error
                        error_text = await page.locator("text=/no disponible|not available|expired/i").count()
                        if error_text > 0:
                            print("⚠ La oferta puede haber expirado o no estar disponible")
                    
                else:
                    print(f"✗ Fallo al hacer clic: {message}")
            else:
                print(f"\n✗ No se pudo identificar botón de aplicación")
            
            # Tomar screenshot
            screenshot_path = "linkedin_interactive_result.png"
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"\n✓ Screenshot guardado: {screenshot_path}")
            
            print("\n" + "=" * 80)
            print("NAVEGADOR ABIERTO - Revisa manualmente qué pasó")
            print("Presiona ENTER para cerrar el navegador...")
            print("=" * 80)
            
            # Esperar input del usuario
            await asyncio.get_event_loop().run_in_executor(None, input)
            
        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
            
            screenshot_path = "linkedin_interactive_error.png"
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"\nScreenshot guardado: {screenshot_path}")
            
            await asyncio.get_event_loop().run_in_executor(None, input, "\nPresiona ENTER para cerrar...")
        
        finally:
            await browser.close()
            
            # Limpiar
            try:
                cv_path.unlink()
                temp_dir.rmdir()
            except:
                pass
    
    print("\n✓ Test completado")


if __name__ == "__main__":
    asyncio.run(test_interactive())
