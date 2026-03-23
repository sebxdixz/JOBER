"""Test completo del pipeline de Jober: init → onboarding → run (loop autónomo)."""

import asyncio
import sys
import os
import time
from pathlib import Path

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from jober.agents.onboarding_preferences import onboarding_preferences_node, extract_preferences_node
from jober.agents.autonomous_search import find_new_opportunities, is_relevant_offer
from jober.agents.job_scraper import job_scraper_node
from jober.agents.cv_writer import cv_writer_node
from jober.core.models import PerfilMaestro, PreferenciasLaborales
from jober.core.state import JoberState
from jober.utils.file_io import load_perfil_maestro, save_application_output_async


console = Console()


async def simulate_onboarding():
    """Simula un onboarding completo con respuestas de prueba."""
    console.print("\n[bold cyan]=== Simulando Onboarding ===[/bold cyan]")
    
    # Crear perfil de prueba
    perfil = PerfilMaestro(
        nombre="Ana García",
        titulo_profesional="Desarrolladora Full Stack",
        resumen="Desarrolladora con 5 años de experiencia en React y Node.js",
        habilidades_tecnicas=["JavaScript", "React", "Node.js", "Python", "SQL"],
        habilidades_blandas=["Trabajo en equipo", "Comunicación", "Resolución de problemas"],
        idiomas=["Español (Nativo)", "Inglés (B2)"],
        links={"linkedin": "https://linkedin.com/in/ana-garcia", "github": "https://github.com/anagarcia"}
    )
    
    # Preferencias de prueba
    preferencias = PreferenciasLaborales(
        roles_deseados=["Full Stack Developer", "Frontend Developer"],
        nivel_experiencia="mid",
        anos_experiencia=5,
        resumen_candidato="Desarrolladora Full Stack con experiencia en React y Node.js",
        habilidades_dominadas=["JavaScript", "React", "Node.js", "TypeScript"],
        habilidades_en_aprendizaje=["Python", "Docker"],
        habilidades_must_have=["JavaScript", "React"],
        habilidades_nice_to_have=["TypeScript", "Docker"],
        herramientas_y_tecnologias=["VS Code", "Git", "Docker", "AWS"],
        industrias_preferidas=["FinTech", "E-commerce"],
        tipo_empresa=["startup", "pyme"],
        modalidad=["remoto", "hibrido"],
        ubicaciones=["Remote", "Santiago", "Buenos Aires"],
        disponibilidad="inmediata",
        jornada="full-time",
        salario_minimo="$1500 USD",
        salario_ideal="$2000 USD",
        moneda_preferida="USD",
        acepta_negociar_salario=True,
        min_match_score=0.6,
        aplicar_sin_100_requisitos=True,
        max_anos_experiencia_extra=2,
        abierto_a_roles_similares=True,
        deal_breakers=["presencial obligatorio", "viajes frecuentes"],
        idiomas_requeridos=["Español", "Inglés"],
        motivacion="Busco crecer profesionalmente y trabajar en proyectos desafiantes",
        fortalezas_clave=["Aprendizaje rápido", "Resolución de problemas", "Trabajo en equipo"],
        areas_mejora=["Experiencia en arquitectura de microservicios"],
        plataformas_activas=["getonbrd", "linkedin", "meetfrank"],
        max_aplicaciones_por_dia=5,
        delay_entre_aplicaciones_segundos=30
    )
    
    perfil.preferencias = preferencias
    
    console.print(Panel.fit(
        f"[bold green]Perfil Configurado[/bold green]\n\n"
        f"Nombre: {perfil.nombre}\n"
        f"Rol: {perfil.titulo_profesional}\n"
        f"Experiencia: {preferencias.anos_experiencia} años ({preferencias.nivel_experiencia})\n"
        f"Roles buscados: {', '.join(preferencias.roles_deseados)}\n"
        f"Modalidad: {', '.join(preferencias.modalidad)}\n"
        f"Salario: {preferencias.salario_minimo} - {preferencias.salario_ideal}\n"
        f"Match mínimo: {preferencias.min_match_score:.0%}",
        border_style="green"
    ))
    
    return perfil


async def test_search_and_filter(perfil):
    """Prueba la búsqueda y filtrado de ofertas."""
    console.print("\n[bold cyan]=== Probando Búsqueda y Filtrado ===[/bold cyan]")
    
    # Buscar ofertas
    console.print(f"Buscando ofertas según perfil...")
    
    start_time = time.time()
    urls = await find_new_opportunities(perfil, max_per_platform=3)
    search_time = time.time() - start_time
    
    console.print(f"✅ Búsqueda completada en {search_time:.1f}s")
    console.print(f"   URLs encontradas: {len(urls)}")
    
    if not urls:
        console.print("⚠️  No se encontraron ofertas. Usando URL de prueba...")
        urls = ["https://www.getonbrd.com/empleos/programacion/frontend-developer-react-santiago-remote/?gb_medium=widget"]
    
    # Filtrar ofertas relevantes
    console.print("\nFiltrando ofertas relevantes...")
    relevant_urls = []
    
    for url in urls[:5]:  # Limitar a 5 para el test
        try:
            # Scrapear oferta
            console.print(f"   Scraping: {url[:60]}...")
            scrape_start = time.time()
            state = JoberState(job_url=url, perfil=perfil)
            scrape_result = await job_scraper_node(state)
            scrape_time = time.time() - scrape_start
            
            if scrape_result.get("error"):
                console.print(f"     ❌ Error: {scrape_result['error']}")
                continue
            
            oferta = scrape_result["oferta"]
            console.print(f"     ✅ {oferta.titulo} @ {oferta.empresa} ({scrape_time:.1f}s)")
            
            # Verificar relevancia
            if is_relevant_offer(oferta, perfil):
                console.print(f"     ✅ Relevante (match potencial)")
                relevant_urls.append((url, oferta))
            else:
                console.print(f"     ⏸️  No relevante (no cumple filtros)")
                
        except Exception as e:
            console.print(f"     ❌ Excepción: {str(e)[:50]}...")
    
    console.print(f"\n📊 Resultados:")
    console.print(f"   Totales scrapeadas: {len(urls)}")
    console.print(f"   Relevantes: {len(relevant_urls)}")
    
    return relevant_urls


async def test_cv_generation(perfil, ofertas):
    """Prueba la generación de CV y cover letter."""
    console.print("\n[bold cyan]=== Probando Generación de CV y Cover Letter ===[/bold cyan]")
    
    if not ofertas:
        console.print("⚠️  No hay ofertas para probar")
        return
    
    # Tomar primera oferta relevante
    url, oferta = ofertas[0]
    console.print(f"Generando para: {oferta.titulo} @ {oferta.empresa}")
    
    # Generar documentos
    start_time = time.time()
    state = JoberState(job_url=url, perfil=perfil, oferta=oferta)
    writer_result = await cv_writer_node(state)
    gen_time = time.time() - start_time
    
    if writer_result.get("error"):
        console.print(f"❌ Error generando: {writer_result['error']}")
        return
    
    docs = writer_result["documentos"]
    console.print(f"✅ Generación completada en {gen_time:.1f}s")
    console.print(f"   CV: {len(docs.cv_adaptado_md)} caracteres")
    console.print(f"   Cover Letter: {len(docs.cover_letter_md)} caracteres")
    console.print(f"   Match Score: {docs.match_score:.0%}")
    
    # Guardar documentos (incluyendo PDF)
    console.print("\nGuardando documentos...")
    save_start = time.time()
    output_dir = await save_application_output_async(oferta, docs)
    save_time = time.time() - save_start
    
    console.print(f"✅ Guardado en {save_time:.1f}s")
    console.print(f"   Directorio: {output_dir}")
    
    # Listar archivos generados
    files = list(output_dir.iterdir())
    for f in sorted(files):
        size = f.stat().st_size
        console.print(f"   📄 {f.name} ({size:,} bytes)")
    
    return output_dir


async def test_autonomous_loop(perfil, iterations=2):
    """Prueba el loop autónomo por N iteraciones."""
    console.print(f"\n[bold cyan]=== Probando Loop Autónomo ({iterations} iteraciones) ===[/bold cyan]")
    
    from jober.utils.tracking import add_record, read_all_records
    from jober.core.models import RegistroPostulacion, EstadoPostulacion
    
    stats = {
        "busquedas": 0,
        "ofertas_encontradas": 0,
        "ofertas_relevantes": 0,
        "aplicaciones": 0,
        "errores": 0,
        "tiempo_total": 0
    }
    
    start_total = time.time()
    
    for i in range(iterations):
        console.print(f"\n--- Iteración {i+1}/{iterations} ---")
        
        try:
            # 1. Buscar ofertas
            urls = await find_new_opportunities(perfil, max_per_platform=2)
            stats["busquedas"] += 1
            stats["ofertas_encontradas"] += len(urls)
            
            # 2. Procesar cada oferta
            for url in urls[:2]:  # Limitar para no sobrecargar
                try:
                    # Scrapear
                    state = JoberState(job_url=url, perfil=perfil)
                    scrape_result = await job_scraper_node(state)
                    
                    if scrape_result.get("error"):
                        continue
                    
                    oferta = scrape_result["oferta"]
                    
                    # Verificar relevancia
                    if not is_relevant_offer(oferta, perfil):
                        continue
                    
                    stats["ofertas_relevantes"] += 1
                    
                    # Generar CV
                    writer_result = await cv_writer_node(JoberState(job_url=url, perfil=perfil, oferta=oferta))
                    
                    if writer_result.get("error"):
                        continue
                    
                    docs = writer_result["documentos"]
                    
                    # Verificar match mínimo
                    if docs.match_score < perfil.preferencias.min_match_score:
                        console.print(f"   ⏸️  Match bajo ({docs.match_score:.0%} < {perfil.preferencias.min_match_score:.0%})")
                        continue
                    
                    # Aplicar (simulado)
                    output_dir = await save_application_output_async(oferta, docs)
                    
                    # Registrar
                    record = RegistroPostulacion(
                        empresa=oferta.empresa,
                        cargo=oferta.titulo,
                        plataforma=oferta.plataforma,
                        url=url,
                        estado=EstadoPostulacion.APLICADO,
                        carpeta_output=str(output_dir),
                        notas=f"Auto-aplicado | Match: {docs.match_score:.0%}"
                    )
                    await add_record(record)
                    stats["aplicaciones"] += 1
                    console.print(f"   ✅ Aplicado a {oferta.titulo} @ {oferta.empresa}")
                    
                    # Delay entre aplicaciones
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    stats["errores"] += 1
                    console.print(f"   ❌ Error procesando oferta: {str(e)[:50]}...")
            
            # Delay entre iteraciones
            if i < iterations - 1:
                console.print("   ⏳ Esperando 3 segundos...")
                await asyncio.sleep(3)
                
        except Exception as e:
            stats["errores"] += 1
            console.print(f"❌ Error en iteración {i+1}: {str(e)}")
    
    stats["tiempo_total"] = time.time() - start_total
    
    # Mostrar estadísticas
    console.print("\n" + "="*50)
    console.print(f"[bold green]Estadísticas del Loop Autónomo[/bold green]")
    console.print(f"")
    console.print(f"Busquedas realizadas: {stats['busquedas']}")
    console.print(f"Ofertas encontradas: {stats['ofertas_encontradas']}")
    console.print(f"Ofertas relevantes: {stats['ofertas_relevantes']}")
    console.print(f"Aplicaciones exitosas: {stats['aplicaciones']}")
    console.print(f"Errores: {stats['errores']}")
    console.print(f"Tiempo total: {stats['tiempo_total']:.1f}s")
    
    if stats['busquedas'] > 0:
        console.print(f"Promedio por búsqueda: {stats['ofertas_encontradas']/stats['busquedas']:.1f} ofertas")
    
    return stats


async def main():
    """Ejecuta todas las pruebas del pipeline."""
    console.print(Panel.fit(
        "[bold blue]Jober - Test Completo del Pipeline[/bold blue]\n"
        "Probando: onboarding → búsqueda → scraping → generación → aplicación",
        border_style="blue"
    ))
    
    # 1. Simular onboarding
    perfil = await simulate_onboarding()
    
    # 2. Probar búsqueda y filtrado
    ofertas_relevantes = await test_search_and_filter(perfil)
    
    # 3. Probar generación de CV
    if ofertas_relevantes:
        await test_cv_generation(perfil, ofertas_relevantes)
    
    # 4. Probar loop autónomo
    await test_autonomous_loop(perfil, iterations=2)
    
    console.print("\n[bold green]✅ Test completado![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
