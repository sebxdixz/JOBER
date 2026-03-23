"""Test completo del flujo mejorado con filtros de país y matching flexible."""

import asyncio
import time
from jober.agents.autonomous_search import find_new_opportunities
from jober.agents.job_scraper import job_scraper_node
from jober.agents.offer_evaluator import offer_evaluator_node
from jober.core.models import PerfilMaestro, PreferenciasLaborales
from jober.core.state import JoberState


async def main():
    print("=" * 70)
    print("TEST COMPLETO - FLUJO MEJORADO CON FILTROS")
    print("=" * 70)
    
    # Crear perfil de Sebastian para AI/ML
    perfil = PerfilMaestro(
        nombre="Sebastian Diaz de la Fuente",
        titulo_profesional="AI Engineer / ML Ops Engineer",
        resumen="Ingeniero especializado en IA con experiencia en LangGraph, LLMs y Kubernetes",
        habilidades_tecnicas=["Python", "LangGraph", "Pydantic", "Docker", "Kubernetes", "PostgreSQL", "LLMs"],
        habilidades_blandas=["Liderazgo", "Comunicacion tecnica", "Resolucion de problemas"]
    )
    
    # Configurar preferencias con TODOS los filtros nuevos
    perfil.preferencias = PreferenciasLaborales(
        # Roles
        roles_deseados=["AI Engineer", "ML Engineer", "ML Ops", "Machine Learning Engineer", "Data Scientist"],
        nivel_experiencia="mid",
        anos_experiencia=2,
        
        # Habilidades
        habilidades_dominadas=["Python", "LangGraph", "Docker", "Kubernetes"],
        habilidades_must_have=["Python"],  # Solo Python como must-have
        habilidades_nice_to_have=["Machine Learning", "ML", "AI", "LLMs"],
        
        # Ubicacion - NUEVO
        modalidad=["remoto", "remote", "hibrido"],
        paises_permitidos=["Chile", "Argentina", "Uruguay", "Remote", "Latam", "Latin America"],
        paises_excluidos=["Estados Unidos", "USA", "United States", "US"],
        
        # Salario - CRITICO
        salario_minimo="$1500 USD",
        salario_ideal="$3000 USD",
        moneda_preferida="USD",
        
        # Deal breakers - CRITICO
        deal_breakers=["100% presencial obligatorio", "menos de $1500 USD", "viajes semanales"],
        
        # Estrategia
        abierto_a_roles_similares=True,  # Activar matching flexible
        min_match_score=0.5,
        aplicar_sin_100_requisitos=True,
        max_aplicaciones_por_dia=10
    )
    
    print(f"\nPERFIL CONFIGURADO:")
    print(f"  Nombre: {perfil.nombre}")
    print(f"  Roles: {', '.join(perfil.preferencias.roles_deseados[:3])}...")
    print(f"  Habilidades must-have: {', '.join(perfil.preferencias.habilidades_must_have)}")
    print(f"  Paises permitidos: {', '.join(perfil.preferencias.paises_permitidos)}")
    print(f"  Paises excluidos: {', '.join(perfil.preferencias.paises_excluidos)}")
    print(f"  Salario minimo: {perfil.preferencias.salario_minimo}")
    print(f"  Deal breakers: {', '.join(perfil.preferencias.deal_breakers[:2])}...")
    print(f"  Matching flexible: {perfil.preferencias.abierto_a_roles_similares}")
    
    # FASE 1: Buscar ofertas
    print(f"\n{'='*70}")
    print("FASE 1: BUSQUEDA DE OFERTAS")
    print(f"{'='*70}")
    
    start_time = time.time()
    urls = await find_new_opportunities(perfil, max_per_platform=5)
    search_time = time.time() - start_time
    
    print(f"\nResultado: {len(urls)} URLs encontradas en {search_time:.1f}s")
    
    if not urls:
        print("\nERROR: No se encontraron URLs")
        print("Posibles causas:")
        print("  - Las plataformas no tienen ofertas con esas keywords")
        print("  - Problemas de scraping")
        return
    
    # FASE 2: Scrapear y filtrar
    print(f"\n{'='*70}")
    print("FASE 2: SCRAPING Y FILTRADO")
    print(f"{'='*70}")
    
    ofertas_relevantes = []
    ofertas_no_relevantes = []
    scraping_times = []
    errores = 0
    
    for i, url in enumerate(urls[:8]):  # Limitar a 8 para no tardar mucho
        print(f"\n[{i+1}/{min(8, len(urls))}] {url[:65]}...")
        
        try:
            scrape_start = time.time()
            state = JoberState(job_url=url, perfil=perfil)
            result = await job_scraper_node(state)
            scrape_time = time.time() - scrape_start
            scraping_times.append(scrape_time)
            
            if result.get("error"):
                print(f"  ERROR: {result['error'][:60]}")
                errores += 1
                continue
            
            oferta = result["oferta"]
            print(f"  Titulo: {oferta.titulo}")
            print(f"  Empresa: {oferta.empresa}")
            print(f"  Ubicacion: {oferta.ubicacion or 'No especificada'}")
            print(f"  Modalidad: {oferta.modalidad or 'No especificada'}")
            print(f"  Scraping: {scrape_time:.1f}s")
            
            # Verificar relevancia con nuevos filtros usando offer_evaluator
            state.oferta = oferta
            eval_result = await offer_evaluator_node(state)
            relevante = eval_result.get("should_apply", False)
            screening_notes = eval_result.get("screening_notes", [])
            
            if relevante:
                print(f"  RESULTADO: RELEVANTE")
                print(f"  Notas: {'; '.join(screening_notes[:2])}")
                ofertas_relevantes.append((url, oferta))
            else:
                print(f"  RESULTADO: NO RELEVANTE")
                print(f"  Razon: {screening_notes[0] if screening_notes else 'Sin razon'}")
                ofertas_no_relevantes.append((url, oferta, screening_notes))
                
                # Diagnostico rapido
                ubicacion_completa = f"{oferta.ubicacion or ''} {oferta.empresa or ''}".lower()
                pais_excluido = any(p.lower() in ubicacion_completa for p in perfil.preferencias.paises_excluidos)
                if pais_excluido:
                    print(f"    Razon: Pais excluido detectado")
                
        except Exception as e:
            print(f"  EXCEPCION: {str(e)[:60]}")
            errores += 1
    
    # FASE 3: Resultados
    print(f"\n{'='*70}")
    print("FASE 3: RESULTADOS Y ANALISIS")
    print(f"{'='*70}")
    
    print(f"\nESTADISTICAS:")
    print(f"  URLs totales: {len(urls)}")
    print(f"  Scrapeadas: {len(scraping_times)}")
    print(f"  Relevantes: {len(ofertas_relevantes)}")
    print(f"  No relevantes: {len(ofertas_no_relevantes)}")
    print(f"  Errores: {errores}")
    
    if scraping_times:
        print(f"\nRENDIMIENTO:")
        print(f"  Tiempo promedio scraping: {sum(scraping_times)/len(scraping_times):.1f}s")
        print(f"  Mas rapido: {min(scraping_times):.1f}s")
        print(f"  Mas lento: {max(scraping_times):.1f}s")
        mejora = ((45 - sum(scraping_times)/len(scraping_times)) / 45) * 100
        print(f"  Mejora vs antes (45s): {mejora:.0f}%")
    
    if ofertas_relevantes:
        print(f"\nOFERTAS RELEVANTES ENCONTRADAS:")
        for url, oferta in ofertas_relevantes:
            print(f"\n  - {oferta.titulo}")
            print(f"    Empresa: {oferta.empresa}")
            print(f"    Ubicacion: {oferta.ubicacion or 'N/A'}")
            print(f"    Modalidad: {oferta.modalidad or 'N/A'}")
            print(f"    URL: {url[:60]}...")
    else:
        print(f"\nNO SE ENCONTRARON OFERTAS RELEVANTES")
        print(f"\nANALISIS DE OFERTAS NO RELEVANTES (primeras 3):")
        for item in ofertas_no_relevantes[:3]:
            if len(item) == 3:
                url, oferta, notes = item
            else:
                url, oferta = item
                notes = []
            
            print(f"\n  Oferta: {oferta.titulo} @ {oferta.empresa}")
            print(f"  Ubicacion: {oferta.ubicacion or 'N/A'}")
            print(f"  Modalidad: {oferta.modalidad or 'N/A'}")
            print(f"  Razones de filtrado:")
            for note in notes:
                print(f"    - {note}")
    
    print(f"\n{'='*70}")
    print("TEST COMPLETADO")
    print(f"{'='*70}")
    
    # Recomendaciones
    if len(ofertas_relevantes) == 0:
        print(f"\nRECOMENDACIONES:")
        print(f"  1. Ampliar roles buscados (agregar 'Python Developer', 'Backend Developer')")
        print(f"  2. Revisar si las plataformas tienen ofertas de AI/ML en Latam")
        print(f"  3. Considerar relajar filtro de paises")
    elif len(ofertas_relevantes) < 3:
        print(f"\nRECOMENDACIONES:")
        print(f"  1. Pocas ofertas relevantes, considerar ampliar keywords")
        print(f"  2. Aumentar max_per_platform para buscar mas ofertas")


if __name__ == "__main__":
    asyncio.run(main())
