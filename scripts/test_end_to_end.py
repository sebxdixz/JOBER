"""Test end-to-end completo: scraping, generación de documentos y aplicación automática."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jober.core.models import OfertaTrabajo
from jober.utils.file_io import load_perfil_maestro
from jober.agents.auto_apply import auto_apply_to_job
from jober.agents.job_scraper import scrape_job_page, detect_platform
from jober.agents.cv_writer import write_cv


async def test_end_to_end(url: str):
    """Test completo del flujo de aplicación automática."""
    
    print("=" * 80)
    print("TEST END-TO-END: FLUJO COMPLETO DE APLICACIÓN")
    print("=" * 80)
    print(f"\nURL: {url}\n")
    
    # 1. SCRAPING
    print("=" * 80)
    print("PASO 1: SCRAPING DE OFERTA")
    print("=" * 80)
    
    try:
        # Detectar plataforma
        platform = detect_platform(url)
        print(f"  Plataforma detectada: {platform}")
        
        # Scrapear página
        html_content = await scrape_job_page(url)
        print(f"  HTML obtenido: {len(html_content)} caracteres")
        
        # Por ahora, crear oferta manualmente con datos básicos
        # En producción, esto usaría el LLM para extraer datos estructurados
        oferta = OfertaTrabajo(
            titulo="Junior AI/ML Engineer - Remote",
            empresa="FocusKPI",
            url=url,
            plataforma=platform,
            ubicacion="Remote",
            modalidad="remoto",
            descripcion=html_content[:1000],  # Primeros 1000 chars
            requisitos=["Python", "Machine Learning", "AI"],
            salario="",
            fecha_publicacion="2024-03-25"
        )
        
        print(f"✓ Oferta creada")
        print(f"  Título: {oferta.titulo}")
        print(f"  Empresa: {oferta.empresa}")
        print(f"  Ubicación: {oferta.ubicacion}")
        print(f"  Modalidad: {oferta.modalidad}")
        
    except Exception as e:
        print(f"✗ Error en scraping: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 2. CARGAR PERFIL
    print("\n" + "=" * 80)
    print("PASO 2: CARGAR PERFIL MAESTRO")
    print("=" * 80)
    
    perfil = load_perfil_maestro()
    if not perfil:
        print("✗ No se encontró perfil maestro")
        return
    
    print(f"✓ Perfil cargado: {perfil.nombre}")
    print(f"  Email: {perfil.email}")
    print(f"  Experiencias: {len(perfil.experiencias) if perfil.experiencias else 0}")
    print(f"  Educación: {len(perfil.educacion) if perfil.educacion else 0}")
    
    # 3. GENERAR CV
    print("\n" + "=" * 80)
    print("PASO 3: GENERAR CV ADAPTADO")
    print("=" * 80)
    
    try:
        output_dir = Path("temp_end_to_end")
        output_dir.mkdir(exist_ok=True)
        
        # Usar write_cv del sistema existente
        cv_result = await write_cv(
            perfil=perfil,
            oferta=oferta
        )
        
        # Guardar el CV
        cv_path = output_dir / f"cv_{oferta.empresa.replace(' ', '_')}.pdf"
        cv_path.write_bytes(cv_result.pdf_bytes)
        
        print(f"✓ CV generado exitosamente")
        print(f"  Ruta: {cv_path}")
        print(f"  Tamaño: {cv_path.stat().st_size / 1024:.2f} KB")
        
    except Exception as e:
        print(f"✗ Error generando CV: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 4. GENERAR COVER LETTER
    print("\n" + "=" * 80)
    print("PASO 4: GENERAR COVER LETTER")
    print("=" * 80)
    
    # Por ahora, crear cover letter simple
    cover_letter_md = f"""Estimado equipo de {oferta.empresa},

Me dirijo a ustedes para expresar mi interés en la posición de {oferta.titulo}.

Con experiencia en desarrollo de sistemas multi-agente, automatización y LLMs, creo que puedo aportar valor significativo a su equipo.

Saludos cordiales,
{perfil.nombre}"""
    
    cover_letter_pdf = None
    print(f"✓ Cover letter generada (markdown)")
    print(f"  Markdown: {len(cover_letter_md)} caracteres")
    
    # 5. APLICAR AUTOMÁTICAMENTE
    print("\n" + "=" * 80)
    print("PASO 5: APLICACIÓN AUTOMÁTICA")
    print("=" * 80)
    print("\nIniciando aplicación automática...")
    print("El agente universal con browser-use se encargará del proceso.")
    print("Observa el navegador que se abrirá...\n")
    
    try:
        resultado = await auto_apply_to_job(
            oferta=oferta,
            perfil=perfil,
            cv_pdf=cv_path,
            cover_letter_pdf=cover_letter_pdf,
            cover_letter_md=cover_letter_md
        )
        
        print("\n" + "=" * 80)
        print("RESULTADO DE LA APLICACIÓN")
        print("=" * 80)
        
        print(f"\n{'✓' if resultado.enviado else '✗'} Enviado: {resultado.enviado}")
        print(f"  Método: {resultado.metodo}")
        print(f"  Plataforma: {resultado.plataforma}")
        print(f"  Mensaje: {resultado.mensaje}")
        
        if resultado.detalles:
            print(f"\n  Trace del proceso:")
            for key, value in sorted(resultado.detalles.items()):
                if key.startswith("trace_"):
                    print(f"    {value}")
        
        # 6. ENVIAR EMAIL (si fue exitoso)
        if resultado.enviado:
            print("\n" + "=" * 80)
            print("PASO 6: ENVIAR EMAIL DE CONFIRMACIÓN")
            print("=" * 80)
            
            try:
                # Simular envío de email por ahora
                print(f"📧 Email simulado enviado a {perfil.email}")
                print(f"   Asunto: Aplicación completada - {oferta.titulo}")
                print(f"   Empresa: {oferta.empresa}")
                print(f"   Documentos adjuntos:")
                print(f"     - CV: {cv_path.name}")
                if cover_letter_pdf:
                    print(f"     - Cover Letter: {cover_letter_pdf.name}")
                
            except Exception as e:
                print(f"⚠ No se pudo enviar email: {e}")
        
        print("\n" + "=" * 80)
        if resultado.enviado:
            print("✓✓✓ APLICACIÓN EXITOSA ✓✓✓")
            print("=" * 80)
            print(f"\n🎉 ¡Aplicación completada para {oferta.titulo} en {oferta.empresa}!")
            print(f"📧 Revisa tu email ({perfil.email}) para la confirmación.")
        else:
            print("⚠️  APLICACIÓN INCOMPLETA")
            print("=" * 80)
            print(f"\nRazón: {resultado.mensaje}")
            print("\nDocumentos generados:")
            print(f"  - CV: {cv_path}")
            if cover_letter_pdf:
                print(f"  - Cover Letter: {cover_letter_pdf}")
        
    except Exception as e:
        print(f"\n✗ Error durante aplicación: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Limpiar archivos temporales si no fue exitoso
        # Si fue exitoso, mantener los documentos
        pass
    
    print("\n" + "=" * 80)
    print("TEST END-TO-END COMPLETADO")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("=" * 80)
        print("USO: python scripts\\test_end_to_end.py <URL>")
        print("=" * 80)
        print("\nEjemplo:")
        print('  python scripts\\test_end_to_end.py "https://chatgpt-jobs.com/job/..."')
        print("\nEste script ejecutará el flujo completo:")
        print("  1. Scraping de la oferta")
        print("  2. Generación de CV adaptado")
        print("  3. Generación de cover letter")
        print("  4. Aplicación automática")
        print("  5. Notificación por email")
        sys.exit(1)
    
    url = sys.argv[1]
    asyncio.run(test_end_to_end(url))
