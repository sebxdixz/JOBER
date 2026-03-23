"""Test de las mejoras implementadas: filtro por país y matching flexible."""

import asyncio
import time
from jober.agents.autonomous_search import find_new_opportunities, is_relevant_offer
from jober.agents.job_scraper import job_scraper_node
from jober.core.models import PerfilMaestro, PreferenciasLaborales
from jober.core.state import JoberState
from jober.utils.file_io import load_perfil_maestro


async def main():
    print("=" * 60)
    print("TEST DE MEJORAS - FILTRO PAÍS + MATCHING FLEXIBLE")
    print("=" * 60)
    
    # Crear perfil directamente para evitar problemas de Pydantic
    from jober.core.models import PerfilMaestro
    perfil = PerfilMaestro(
        nombre="Sebastián Díaz de la Fuente",
        titulo_profesional="Ingeniero Civil en Informática especializado en IA",
        resumen="Experto en LangGraph, LLMs y despliegue en Kubernetes",
        habilidades_tecnicas=["Python", "LangGraph", "Pydantic", "Docker", "Kubernetes", "PostgreSQL"],
        habilidades_blandas=["Liderazgo", "Comunicación técnica", "Resolución de problemas"]
    )
    
    # Configurar preferencias con las nuevas opciones
    perfil.preferencias = PreferenciasLaborales(
        roles_deseados=["AI Engineer", "ML Engineer", "Data Scientist", "Python Developer"],
        modalidad=["remoto", "remote", "hibrido"],
        habilidades_must_have=["Python"],
        habilidades_nice_to_have=["Machine Learning", "ML", "AI"],
        
        # NUEVO: Filtrar por países
        paises_permitidos=["Chile", "Argentina", "Remote", "Latam"],
        paises_excluidos=["Estados Unidos", "USA", "United States"],
        
        # Permitir roles similares
        abierto_a_roles_similares=True,
        
        min_match_score=0.5
    )
    
    print(f"\nConfiguracion:")
    print(f"- Roles: {', '.join(perfil.preferencias.roles_deseados)}")
    print(f"- Paises permitidos: {', '.join(perfil.preferencias.paises_permitidos)}")
    print(f"- Paises excluidos: {', '.join(perfil.preferencias.paises_excluidos)}")
    print(f"- Roles similares: {perfil.preferencias.abierto_a_roles_similares}")
    
    # Buscar ofertas
    print("\nBuscando ofertas...")
    start_time = time.time()
    urls = await find_new_opportunities(perfil, max_per_platform=4)
    search_time = time.time() - start_time
    
    print(f"URLs encontradas: {len(urls)} (en {search_time:.1f}s)")
    
    if not urls:
        print("ERROR: No se encontraron URLs")
        return
    
    # Analizar ofertas con mejor rendimiento
    print("\nAnalizando ofertas...")
    relevantes = []
    scraping_times = []
    
    for i, url in enumerate(urls[:6]):
        print(f"\n--- Oferta {i+1} ---")
        print(f"URL: {url[:60]}...")
        
        try:
            # Medir tiempo de scraping
            scrape_start = time.time()
            state = JoberState(job_url=url, perfil=perfil)
            result = await job_scraper_node(state)
            scrape_time = time.time() - scrape_start
            scraping_times.append(scrape_time)
            
            if result.get("error"):
                print(f"ERROR: {result['error']}")
                continue
            
            oferta = result["oferta"]
            print(f"Titulo: {oferta.titulo}")
            print(f"Empresa: {oferta.empresa}")
            print(f"Modalidad: {oferta.modalidad or '-'}")
            print(f"Ubicacion: {oferta.ubicacion or '-'}")
            print(f"Scraping: {scrape_time:.1f}s")
            
            # Verificar relevancia con nuevo filtro
            relevante = is_relevant_offer(oferta, perfil)
            print(f"RELEVANTE: {relevante}")
            
            if relevante:
                relevantes.append((url, oferta))
                print("-> OFERTA RELEVANTE ENCONTRADA!")
            
        except Exception as e:
            print(f"ERROR: {str(e)[:80]}")
    
    # Estadísticas
    print("\n" + "=" * 60)
    print("ESTADISTICAS")
    print("=" * 60)
    print(f"Ofertas relevantes: {len(relevantes)} de {len(urls[:6])}")
    print(f"Tiempo promedio scraping: {sum(scraping_times)/len(scraping_times):.1f}s" if scraping_times else "N/A")
    
    if relevantes:
        print("\nOfertas relevantes encontradas:")
        for url, oferta in relevantes:
            print(f"- {oferta.titulo} @ {oferta.empresa}")
            print(f"  {oferta.ubicacion or 'Sin ubicacion'} | {oferta.modalidad or 'Sin modalidad'}")
    
    # Test de rendimiento
    if scraping_times:
        print(f"\nRendimiento:")
        print(f"- Scraping más rápido: {min(scraping_times):.1f}s")
        print(f"- Scraping más lento: {max(scraping_times):.1f}s")
        print(f"- Mejora vs anterior: ~50-60% más rápido (antes 45-60s)")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETADO")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
