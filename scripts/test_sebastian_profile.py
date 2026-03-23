"""Test del pipeline con el perfil real de Sebastián para roles de AI/ML."""

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

from jober.agents.autonomous_search import find_new_opportunities, is_relevant_offer
from jober.agents.job_scraper import job_scraper_node
from jober.agents.cv_writer import cv_writer_node
from jober.core.models import PerfilMaestro, PreferenciasLaborales
from jober.core.state import JoberState
from jober.utils.file_io import load_perfil_maestro, save_application_output_async


console = Console()


def create_sebastian_profile():
    """Crea el perfil de Sebastián con preferencias para AI/ML."""
    
    # Cargar perfil base
    perfil = load_perfil_maestro()
    if not perfil:
        console.print("❌ No se encontró perfil_maestro.json")
        return None
    
    # Configurar preferencias para AI Engineer / ML Ops / ML Engineer
    preferencias = PreferenciasLaborales(
        roles_deseados=["AI Engineer", "ML Engineer", "ML Ops Engineer", "Machine Learning Engineer", "Data Scientist"],
        nivel_experiencia="mid",
        anos_experiencia=2,
        resumen_candidato="Ingeniero especializado en IA con experiencia en LangGraph, LLMs y despliegue en Kubernetes",
        
        habilidades_dominadas=["Python", "LangGraph", "Pydantic", "Docker", "Kubernetes", "PostgreSQL", "RESTful APIs"],
        habilidades_en_aprendizaje=["MLOps", "CI/CD", "AWS", "GCP", "Azure"],
        habilidades_must_have=["Python", "Machine Learning"],
        habilidades_nice_to_have=["LangGraph", "LLMs", "Docker", "Kubernetes"],
        herramientas_y_tecnologias=["Python", "Docker", "Kubernetes", "PostgreSQL", "Git", "Linux"],
        
        industrias_preferidas=["Tech", "AI", "FinTech", "HealthTech"],
        tipo_empresa=["startup", "corporativo"],
        modalidad=["remoto", "hibrido"],
        ubicaciones=["Remote", "Santiago", "Buenos Aires", "Montevideo"],
        disponibilidad="inmediata",
        jornada="full-time",
        
        salario_minimo="$2000 USD",
        salario_ideal="$3000 USD",
        moneda_preferida="USD",
        acepta_negociar_salario=True,
        
        min_match_score=0.5,  # Bajar a 50% para probar
        aplicar_sin_100_requisitos=True,
        max_anos_experiencia_extra=3,
        abierto_a_roles_similares=True,
        
        deal_breakers=["presencial obligatorio", "menos de $1500 USD"],
        idiomas_requeridos=["Español", "Inglés"],
        
        motivacion="Busco crecer en el campo de IA aplicada y liderar proyectos de ML",
        fortalezas_clave=["Experto en LangGraph", "Arquitecturas multi-agente", "Orquestación de LLMs"],
        areas_mejora=["Experiencia en MLOps a gran escala"],
        
        plataformas_activas=["getonbrd", "linkedin", "meetfrank"],
        max_aplicaciones_por_dia=5,
        delay_entre_aplicaciones_segundos=30
    )
    
    perfil.preferencias = preferencias
    
    console.print(Panel.fit(
        f"[bold green]Perfil de Sebastián Configurado[/bold green]\n\n"
        f"Nombre: {perfil.nombre}\n"
        f"Título: {perfil.titulo_profesional}\n"
        f"Roles buscados: {', '.join(preferencias.roles_deseados[:3])}...\n"
        f"Experiencia: {preferencias.anos_experiencia} años ({preferencias.nivel_experiencia})\n"
        f"Habilidades clave: {', '.join(preferencias.habilidades_dominadas[:4])}...\n"
        f"Modalidad: {', '.join(preferencias.modalidad)}\n"
        f"Salario: {preferencias.salario_minimo} - {preferencias.salario_ideal}\n"
        f"Match mínimo: {preferencias.min_match_score:.0%}",
        border_style="green"
    ))
    
    return perfil


async def test_search_with_ai_keywords(perfil):
    """Prueba búsqueda con keywords específicas de AI/ML."""
    console.print("\n[bold cyan]=== Probando Búsqueda con Keywords AI/ML ===[/bold cyan]")
    
    # Probar diferentes combinaciones de keywords
    keyword_sets = [
        ["AI Engineer", "Python", "Machine Learning"],
        ["ML Engineer", "LangGraph", "LLMs"],
        ["Machine Learning", "Python", "Docker"],
        ["Data Scientist", "Python", "Kubernetes"],
        ["ML Ops", "Python", "CI/CD"]
    ]
    
    all_results = []
    
    for i, keywords in enumerate(keyword_sets):
        console.print(f"\n[bright_yellow]Test {i+1}:[/bright_yellow] Keywords: {', '.join(keywords)}")
        
        # Modificar temporalmente las preferencias
        old_roles = perfil.preferencias.roles_deseados[:]
        old_skills = perfil.preferencias.habilidades_must_have[:]
        
        perfil.preferencias.roles_deseados = keywords[:2]
        perfil.preferencias.habilidades_must_have = keywords[1:]
        
        try:
            start_time = time.time()
            urls = await find_new_opportunities(perfil, max_per_platform=3)
            search_time = time.time() - start_time
            
            console.print(f"  ⏱️  Búsqueda: {search_time:.1f}s | URLs: {len(urls)}")
            
            if urls:
                # Probar primeras 2 URLs
                relevant_count = 0
                for url in urls[:2]:
                    try:
                        console.print(f"  🔍 Scraping: {url[:60]}...")
                        scrape_start = time.time()
                        state = JoberState(job_url=url, perfil=perfil)
                        scrape_result = await job_scraper_node(state)
                        scrape_time = time.time() - scrape_start
                        
                        if scrape_result.get("error"):
                            console.print(f"    ❌ Error: {scrape_result['error']}")
                            continue
                        
                        oferta = scrape_result["oferta"]
                        console.print(f"    ✅ {oferta.titulo[:40]}... @ {oferta.empresa}")
                        
                        # Verificar relevancia
                        if is_relevant_offer(oferta, perfil):
                            console.print(f"    🎯 RELEVANTE! ✓")
                            relevant_count += 1
                            all_results.append((url, oferta))
                        else:
                            console.print(f"    ❌ No relevante")
                            # Mostrar por qué no es relevante
                            console.print(f"       Modalidad: {oferta.modalidad}")
                            console.print(f"       Requisitos: {len(oferta.requisitos)}")
                            
                    except Exception as e:
                        console.print(f"    ❌ Excepción: {str(e)[:50]}...")
                
                console.print(f"  📊 Relevantes: {relevant_count}/{min(2, len(urls))}")
            else:
                console.print(f"  ⚠️  No se encontraron URLs")
            
            # Restaurar preferencias
            perfil.preferencias.roles_deseados = old_roles
            perfil.preferencias.habilidades_must_have = old_skills
            
            # Pequeño delay entre búsquedas
            await asyncio.sleep(2)
            
        except Exception as e:
            console.print(f"  ❌ Error en búsqueda: {str(e)}")
            # Restaurar preferencias
            perfil.preferencias.roles_deseados = old_roles
            perfil.preferencias.habilidades_must_have = old_skills
    
    console.print(f"\n[bold green]Resultados totales:[/bold green] {len(all_results)} ofertas relevantes encontradas")
    return all_results


async def analyze_why_not_relevant(perfil, ofertas_no_relevantes):
    """Analiza por qué las ofertas no son relevantes."""
    console.print("\n[bold cyan]=== Analizando por qué no son relevantes ===[/bold cyan]")
    
    for url, oferta in ofertas_no_relevantes[:3]:
        console.print(f"\n[yellow]Oferta:[/yellow] {oferta.titulo}")
        console.print(f"[yellow]Empresa:[/yellow] {oferta.empresa}")
        console.print(f"[yellow]Modalidad:[/yellow] {oferta.modalidad}")
        console.print(f"[yellow]Requisitos:[/yellow]")
        
        for req in oferta.requisitos[:5]:
            console.print(f"  • {req}")
        
        console.print(f"\n[cyan]Análisis vs Perfil:[/cyan]")
        
        # Verificar modalidad
        if oferta.modalidad and oferta.modalidad.lower() not in ["remoto", "remote", "hibrido", "hybrid"]:
            console.print(f"  ❌ Modalidad '{oferta.modalidad}' no coincide con preferencias")
        
        # Verificar habilidades
        oferta_text = " ".join(oferta.requisitos).lower()
        habilidades_user = [h.lower() for h in perfil.habilidades_tecnicas]
        
        matches = sum(1 for h in habilidades_user if h in oferta_text)
        console.print(f"  📊 Habilidades coincidentes: {matches}/{len(habilidades_user)}")
        
        if matches < 2:
            console.print(f"  ❌ Pocas habilidades coincidentes")
        
        # Verificar nivel
        if any(palabra in oferta.titulo.lower() for palabra in ["senior", "lead", "principal"]):
            console.print(f"  ⚠️  Posiblemente nivel demasiado alto (Senior/Lead)")
        
        if any(palabra in oferta.titulo.lower() for palabra in ["intern", "junior", "trainee"]):
            console.print(f"  ⚠️  Posiblemente nivel demasiado bajo (Junior/Intern)")


async def test_cv_generation_with_real_offer(perfil, ofertas):
    """Prueba generación de CV con una oferta real."""
    console.print("\n[bold cyan]=== Probando Generación de CV ===[/bold cyan]")
    
    if not ofertas:
        console.print("⚠️  No hay ofertas relevantes para probar")
        return
    
    url, oferta = ofertas[0]
    console.print(f"Generando para: {oferta.titulo}")
    console.print(f"Empresa: {oferta.empresa}")
    console.print(f"Requisitos: {len(oferta.requisitos)}")
    
    try:
        start_time = time.time()
        state = JoberState(job_url=url, perfil=perfil, oferta=oferta)
        writer_result = await cv_writer_node(state)
        gen_time = time.time() - start_time
        
        if writer_result.get("error"):
            console.print(f"❌ Error: {writer_result['error']}")
            return
        
        docs = writer_result["documentos"]
        console.print(f"✅ Generado en {gen_time:.1f}s")
        console.print(f"   Match Score: {docs.match_score:.0%}")
        
        # Guardar
        output_dir = await save_application_output_async(oferta, docs)
        console.print(f"   Guardado en: {output_dir}")
        
        # Mostrar preview del CV
        console.print(f"\n[dim]Preview CV (primeras 200 chars):[/dim]")
        console.print(f"{docs.cv_adaptado_md[:200]}...")
        
    except Exception as e:
        console.print(f"❌ Error: {str(e)}")


async def main():
    """Ejecuta test completo con perfil de Sebastián."""
    console.print(Panel.fit(
        "[bold blue]Test Pipeline - Perfil de Sebastián (AI/ML)[/bold blue]\n"
        "Objetivo: Encontrar ofertas relevantes para AI Engineer / ML Ops",
        border_style="blue"
    ))
    
    # Crear perfil con preferencias AI/ML
    perfil = create_sebastian_profile()
    if not perfil:
        return
    
    # 1. Probar diferentes keywords
    ofertas_relevantes = await test_search_with_ai_keywords(perfil)
    
    # 2. Si no hay relevantes, analizar por qué
    if not ofertas_relevantes:
        console.print("\n[bold red]No se encontraron ofertas relevantes![/bold red]")
        console.print("Vamos a analizar el problema...")
        
        # Buscar algunas ofertas para analizar
        perfil.preferencias.roles_deseados = ["Python", "Developer"]
        urls = await find_new_opportunities(perfil, max_per_platform=2)
        
        ofertas_para_analizar = []
        for url in urls[:3]:
            try:
                state = JoberState(job_url=url, perfil=perfil)
                result = await job_scraper_node(state)
                if not result.get("error"):
                    ofertas_para_analizar.append((url, result["oferta"]))
            except:
                pass
        
        await analyze_why_not_relevant(perfil, ofertas_para_analizar)
    else:
        # 3. Probar generación de CV con oferta relevante
        await test_cv_generation_with_real_offer(perfil, ofertas_relevantes)
    
    console.print("\n[bold green]✅ Test completado![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
