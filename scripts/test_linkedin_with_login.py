"""Test completo de aplicación en LinkedIn con login manual previo."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from playwright.async_api import async_playwright
from jober.core.models import OfertaTrabajo, PerfilMaestro
from jober.utils.file_io import load_perfil_maestro
from jober.agents.auto_apply import _apply_linkedin, _new_result
from jober.core.config import ensure_profile_dirs, get_active_profile_id


async def test_linkedin_with_manual_login():
    url = "https://www.linkedin.com/jobs/view/junior-ai-ml-engineer-remote-at-chatgpt-jobs-4373181012"
    
    print("=" * 80)
    print("TEST: APLICACION EN LINKEDIN CON LOGIN MANUAL")
    print("=" * 80)
    print(f"\nURL: {url}")
    
    # Cargar perfil
    print("\n[1/5] Cargando perfil maestro...")
    perfil = load_perfil_maestro()
    if not perfil:
        print("  ✗ No se encontró perfil maestro")
        return
    print(f"  ✓ Perfil cargado: {perfil.nombre}")
    
    # Crear oferta
    print("\n[2/5] Creando oferta de trabajo...")
    oferta = OfertaTrabajo(
        titulo="Junior AI/ML Engineer (Remote)",
        empresa="ChatGPT Jobs",
        url=url,
        plataforma="linkedin",
        ubicacion="Remote",
        modalidad="remoto",
        descripcion="AI/ML Engineer position",
        requisitos=["Python", "Machine Learning"],
        salario="",
        fecha_publicacion="2024-03-24"
    )
    print(f"  ✓ Oferta creada: {oferta.titulo}")
    
    # Preparar documentos
    print("\n[3/5] Preparando documentos...")
    temp_dir = Path("temp_test_docs")
    temp_dir.mkdir(exist_ok=True)
    
    cv_path = temp_dir / "cv_test.pdf"
    cover_letter_path = temp_dir / "cover_letter_test.pdf"
    
    cv_path.write_text("CV Test Content")
    cover_letter_path.write_text("Cover Letter Test Content")
    
    cover_letter_text = f"""Estimado equipo de {oferta.empresa},

Me dirijo a ustedes para expresar mi interés en la posición de {oferta.titulo}.

Con experiencia en LangGraph, Pydantic, y orquestación de LLMs, he desarrollado sistemas 
multi-agente en producción. Mi trabajo incluye arquitectura de pipelines autónomos, 
reducción de alucinación en OCR, y despliegue con Docker y Kubernetes.

Saludos cordiales,
{perfil.nombre}"""
    
    print(f"  ✓ Documentos preparados")
    
    # Lanzar navegador y permitir login manual
    print("\n[4/5] Lanzando navegador para login manual...")
    print("-" * 80)
    print("INSTRUCCIONES:")
    print("1. Se abrirá un navegador en LinkedIn")
    print("2. Haz login manualmente con tu cuenta")
    print("3. Navega a la URL de la oferta si quieres verificarla")
    print("4. Presiona ENTER en esta consola cuando estés listo")
    print("-" * 80)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        
        # Cargar sesión guardada si existe
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
        
        # Ir a LinkedIn para login
        await page.goto("https://www.linkedin.com", wait_until="domcontentloaded")
        
        print("\nNavegador abierto. Haz login y presiona ENTER cuando estés listo...")
        input()
        
        # Guardar sesión
        await context.storage_state(path=str(storage_state_path))
        print("✓ Sesión guardada")
        
        # Ir a la oferta
        print(f"\n[5/5] Navegando a la oferta y ejecutando aplicación...")
        print("-" * 80)
        
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        
        # Ejecutar flujo de aplicación
        trace_log = []
        
        def trace(msg):
            trace_log.append(msg)
            print(f"[auto-apply] {msg}")
        
        try:
            resultado = await _apply_linkedin(
                page=page,
                oferta=oferta,
                perfil=perfil,
                cv_pdf=cv_path,
                cover_letter_pdf=cover_letter_path,
                cover_letter_text=cover_letter_text,
                trace=trace
            )
            
            print("\n" + "=" * 80)
            print("RESULTADO DE LA APLICACION")
            print("=" * 80)
            
            print(f"\nEnviado: {resultado.enviado}")
            print(f"Método: {resultado.metodo}")
            print(f"Mensaje: {resultado.mensaje}")
            
            if resultado.detalles:
                print(f"\nDetalles:")
                for key, value in resultado.detalles.items():
                    print(f"  {key}: {value}")
            
            if resultado.enviado:
                print("\n✓✓✓ APLICACION EXITOSA ✓✓✓")
            else:
                print("\n✗✗✗ APLICACION FALLIDA ✗✗✗")
                print(f"\nRazón: {resultado.mensaje}")
                
                # Tomar screenshot para debug
                screenshot_path = "linkedin_failed_debug.png"
                await page.screenshot(path=screenshot_path, full_page=False)
                print(f"\nScreenshot guardado: {screenshot_path}")
            
            print("\nPresiona ENTER para cerrar el navegador...")
            input()
            
        except Exception as e:
            print(f"\n✗ Error durante la aplicación: {e}")
            import traceback
            traceback.print_exc()
            
            # Tomar screenshot
            screenshot_path = "linkedin_error_debug.png"
            await page.screenshot(path=screenshot_path, full_page=False)
            print(f"\nScreenshot guardado: {screenshot_path}")
            
            print("\nPresiona ENTER para cerrar el navegador...")
            input()
        
        finally:
            await browser.close()
            
            # Limpiar archivos temporales
            try:
                cv_path.unlink()
                cover_letter_path.unlink()
                temp_dir.rmdir()
            except:
                pass
    
    print("\n" + "=" * 80)
    print("TEST COMPLETADO")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_linkedin_with_manual_login())
